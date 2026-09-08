"""Skylight OAuth and read-only calendar synchronization.

Skylight's API is undocumented. The OAuth flow and endpoints here mirror the
published @kamilio/skylight-calendar-agent client, while keeping credentials
inside TouchGrass and encrypted at rest.
"""

import base64
import hashlib
import hmac
import html
import json
import os
import re
import unicodedata
import uuid
from datetime import timedelta
from urllib.parse import parse_qs, urlencode, urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import (
    City,
    Country,
    Region,
    SkylightConnection,
    SkylightEventReview,
    SkylightProfileMapping,
    SkylightTripSuggestion,
    TravelProfile,
)


API_BASE = 'https://app.ourskylight.com'
CLIENT_ID = 'skylight-mobile'
SCOPE = 'everything'
REDIRECT_URI = 'https://ourskylight.com/welcome'
DEFAULT_API_VERSION = '2026-07-14'
OAUTH_STATE_TTL = timedelta(minutes=20)
TOKEN_REFRESH_SKEW = timedelta(minutes=5)
MAX_ERROR_LENGTH = 500

EXPLICIT_TRIP_WORDS = re.compile(
    r'\b(trip|vacation|getaway|honeymoon|road\s*trip|weekend\s+in|'
    r'cabin\s+trip|retreat|camping|ski(?:ing)?|cruise|resort|yar)\b',
    re.IGNORECASE,
)
PLANNING_WORDS = re.compile(
    r'\b(plan|planning|itinerary|prep|prepare|research|travel\s+insurance|'
    r'book(?:ing)?|price\s+check)\b',
    re.IGNORECASE,
)
LOCAL_EVENT_WORDS = re.compile(
    r'\b(dinner|happy\s*h(?:ou)?r|concert|show|movie|party|game\s+night|'
    r'date\s+night|reservation|resy|restaurant|interview|pilates|bowling|'
    r'watch\s+party|housewarming|pregame|in\s+town|parents?\s+coming|'
    r'family\s+in\s+town|d\s*&?\s*d)\b',
    re.IGNORECASE,
)
HOME_FOR_WORDS = re.compile(r'^\s*home\s+for\b', re.IGNORECASE)
WORK_TRAVEL_WORDS = re.compile(
    r'\b(?:(?:work|business)\s+(?:travel|trip)|'
    r'(?:campus\s+)?recruiting\s+(?:trip|event)|customer\s+visit)\b',
    re.IGNORECASE,
)
TRIP_PLANNING_CALL_WORDS = re.compile(
    r'\btrip\s+(?:ft|facetime)\b', re.IGNORECASE
)
FAMILY_VISIT_WORDS = re.compile(
    r"\b(?:"
    r"visit(?:ing)?\s+(?:family|fam|parents?|mom|dad|grandparents?|grandma|grandpa|aunts?|uncles?|cousins?|siblings?|brothers?|sisters?)|"
    r"(?:family|fam|parents?|mom|dad|grandparents?|grandma|grandpa|aunts?|uncles?|cousins?|siblings?|brothers?|sisters?)\s+(?:visit|visiting|coming|in\s+town)|"
    r"(?:with|w/)\s+(?:the\s+)?(?:family|fam|parents?|mom|dad|grandparents?|grandma|grandpa|aunts?|uncles?|cousins?|siblings?|brothers?|sisters?)|"
    r"grandm(?:a|o)(?:[’']s)?\s+\d+(?:st|nd|rd|th)?\s+(?:birthday|bday)"
    r")\b",
    re.IGNORECASE,
)
FLAG_EMOJI = re.compile(r'[\U0001F1E6-\U0001F1FF]{2}')
DESTINATION_ALIASES = {
    'africa': 'Africa',
    'asia': 'Asia',
    'europe': 'Europe',
    'north america': 'North America',
    'south america': 'South America',
    'caribbean': 'Caribbean',
    'philly': 'Philadelphia',
    'nyc': 'New York City',
    'poconos': 'Poconos',
    'nj': 'New Jersey',
}
PROFILE_SUFFIX = re.compile(r"(?:[’']s)?\s+events?$", re.IGNORECASE)


class SkylightError(Exception):
    """A safe, user-displayable Skylight integration error."""


def _fernet_key(raw_key):
    value = raw_key.strip().encode('utf-8')
    try:
        decoded = base64.urlsafe_b64decode(value)
        if len(decoded) == 32:
            return value
    except Exception:
        pass
    return base64.urlsafe_b64encode(
        hashlib.sha256(b'touchgrass-skylight-credentials-v1\0' + value).digest()
    )


def _local_credential_key():
    """Return a private persistent key for a single-host Docker installation."""

    configured_path = os.environ.get('SKYLIGHT_CREDENTIAL_KEY_FILE', '').strip()
    key_path = configured_path or os.path.join(settings.MEDIA_ROOT, '.skylight-credential-key')
    try:
        with open(key_path, 'rb') as key_file:
            stored_key = key_file.read().strip()
        if stored_key:
            return stored_key.decode('ascii')
    except FileNotFoundError:
        pass
    except (OSError, UnicodeDecodeError) as exc:
        raise SkylightError('The local Skylight credential key could not be read.') from exc

    key_directory = os.path.dirname(key_path)
    if key_directory:
        os.makedirs(key_directory, exist_ok=True)
    generated_key = Fernet.generate_key()
    try:
        descriptor = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        # Another worker won the first-start race. Always use the winning key.
        try:
            with open(key_path, 'rb') as key_file:
                return key_file.read().strip().decode('ascii')
        except (OSError, UnicodeDecodeError) as exc:
            raise SkylightError('The local Skylight credential key could not be read.') from exc
    except OSError as exc:
        raise SkylightError('The local Skylight credential key could not be created.') from exc
    with os.fdopen(descriptor, 'wb') as key_file:
        key_file.write(generated_key + b'\n')
    return generated_key.decode('ascii')


def credential_cipher():
    """Return a rotating authenticated cipher for stored OAuth credentials.

    The first key encrypts new values; every configured key may decrypt old
    values. An explicit key is recommended. SECRET_KEY remains an encrypted
    fallback so credentials are never silently written as plaintext.
    """

    raw_keys = [
        item.strip()
        for item in os.environ.get('SKYLIGHT_CREDENTIAL_KEYS', '').split(',')
        if item.strip()
    ]
    if not raw_keys:
        # The media volume persists across local Docker rebuilds. SECRET_KEY is
        # retained as a decrypt-only fallback for credentials created before
        # this dedicated key existed.
        raw_keys = [_local_credential_key(), settings.SECRET_KEY]
    return MultiFernet([Fernet(_fernet_key(key)) for key in raw_keys])


def encrypt_credentials(credentials):
    payload = json.dumps(credentials, separators=(',', ':'), sort_keys=True).encode('utf-8')
    return credential_cipher().encrypt(payload).decode('ascii')


def decrypt_credentials(connection):
    if not connection.encrypted_credentials:
        raise SkylightError('Skylight is not connected.')
    try:
        cleartext = credential_cipher().decrypt(
            connection.encrypted_credentials.encode('ascii')
        )
        credentials = json.loads(cleartext.decode('utf-8'))
    except (InvalidToken, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise SkylightError(
            'The Skylight credential could not be decrypted. Check the configured credential key.'
        ) from exc
    required = {'access_token', 'refresh_token', 'fingerprint', 'expires_at'}
    if not isinstance(credentials, dict) or not required.issubset(credentials):
        raise SkylightError('The stored Skylight credential is incomplete. Reconnect Skylight.')
    return credentials


def _state_digest(state):
    return hashlib.sha256(state.encode('ascii')).hexdigest()


def begin_oauth(connection):
    state = str(uuid.uuid4())
    connection.oauth_state_digest = _state_digest(state)
    connection.oauth_state_expires_at = timezone.now() + OAUTH_STATE_TTL
    connection.save(update_fields=['oauth_state_digest', 'oauth_state_expires_at', 'updated_at'])
    query = urlencode(
        {
            'client_id': CLIENT_ID,
            'response_type': 'code',
            'redirect_uri': REDIRECT_URI,
            'scope': SCOPE,
            'state': state,
            'skylight_api_client_device_fingerprint': state,
        }
    )
    return f'{API_BASE}/oauth/authorize?{query}'


def _device_values(fingerprint):
    return {
        'skylight_api_client_device_fingerprint': fingerprint,
        'skylight_api_client_device_platform': 'web',
        'skylight_api_client_device_name': 'TouchGrass',
        'skylight_api_client_device_os_version': 'server',
        'skylight_api_client_device_app_version': '1',
        'skylight_api_client_device_hardware': 'TouchGrass',
        'source': 'js-mobile',
    }


def _token_request(values):
    try:
        response = requests.post(
            f'{API_BASE}/oauth/token',
            data=values,
            headers={'Accept': 'application/json'},
            timeout=30,
        )
    except requests.RequestException as exc:
        raise SkylightError('Could not reach Skylight. Try again in a moment.') from exc
    if not response.ok:
        raise SkylightError(f'Skylight rejected the login request ({response.status_code}).')
    try:
        payload = response.json()
        expires_in = int(payload['expires_in'])
        access_token = str(payload['access_token'])
        refresh_token = str(payload['refresh_token'])
    except (ValueError, TypeError, KeyError) as exc:
        raise SkylightError('Skylight returned an incomplete OAuth credential.') from exc
    if not access_token or not refresh_token or expires_in <= 0:
        raise SkylightError('Skylight returned an invalid OAuth credential.')
    return {
        'access_token': access_token,
        'refresh_token': refresh_token,
        'fingerprint': str(values['skylight_api_client_device_fingerprint']),
        'expires_at': (timezone.now() + timedelta(seconds=expires_in)).isoformat(),
    }


@transaction.atomic
def complete_oauth(connection, callback_url):
    parsed = urlparse(str(callback_url).strip())
    if parsed.scheme != 'https' or parsed.hostname != 'ourskylight.com' or parsed.path != '/welcome':
        raise SkylightError('Paste the complete https://ourskylight.com/welcome URL.')
    query = parse_qs(parsed.query)
    code = (query.get('code') or [''])[0]
    state = (query.get('state') or [''])[0]
    if not code or not state:
        raise SkylightError('The Skylight callback URL is missing its code or state.')
    if (
        not connection.oauth_state_digest
        or not connection.oauth_state_expires_at
        or connection.oauth_state_expires_at < timezone.now()
        or not hmac.compare_digest(
            connection.oauth_state_digest, _state_digest(state)
        )
    ):
        raise SkylightError('This Skylight login has expired. Start the connection again.')

    credentials = _token_request(
        {
            'grant_type': 'authorization_code',
            'code': code,
            'client_id': CLIENT_ID,
            'redirect_uri': REDIRECT_URI,
            'scope': SCOPE,
            **_device_values(state),
        }
    )
    connection.encrypted_credentials = encrypt_credentials(credentials)
    connection.oauth_state_digest = ''
    connection.oauth_state_expires_at = None
    connection.connected_at = timezone.now()
    connection.last_sync_error = ''
    connection.save()
    discover_frame(connection)
    sync_profile_mappings(connection)
    return connection


def _login_csrf_token(page):
    match = re.search(
        r'name=["\']authenticity_token["\'][^>]*value=["\']([^"\']+)["\']',
        page,
        re.IGNORECASE,
    ) or re.search(
        r'value=["\']([^"\']+)["\'][^>]*name=["\']authenticity_token["\']',
        page,
        re.IGNORECASE,
    )
    if not match:
        raise SkylightError('Skylight login did not return its security token.')
    return html.unescape(match.group(1))


@transaction.atomic
def login_with_password(connection, email, password):
    """Complete Skylight OAuth server-side without persisting the password."""

    if not email or not password:
        raise SkylightError('Enter your Skylight email and password.')
    fingerprint = str(uuid.uuid4())
    session = requests.Session()
    browser_headers = {
        'User-Agent': (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        ),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }
    try:
        login_page = session.get(
            f'{API_BASE}/auth/session/new', headers=browser_headers, timeout=30
        )
        login_page.raise_for_status()
        session_response = session.post(
            f'{API_BASE}/auth/session',
            data={
                'authenticity_token': _login_csrf_token(login_page.text),
                'email': email,
                'password': password,
            },
            headers={
                **browser_headers,
                'Origin': API_BASE,
                'Referer': f'{API_BASE}/auth/session/new',
            },
            allow_redirects=False,
            timeout=30,
        )
        session_location = urlparse(session_response.headers.get('Location', '')).path
        if session_response.status_code not in {200, 302, 303} or session_location == '/auth/session/new':
            raise SkylightError(
                'Skylight rejected the login. Check your credentials or complete device verification in Skylight.'
            )
        authorize_query = urlencode(
            {
                'client_id': CLIENT_ID,
                'response_type': 'code',
                'redirect_uri': REDIRECT_URI,
                'scope': SCOPE,
                'skylight_api_client_device_fingerprint': fingerprint,
            }
        )
        authorize_url = f'{API_BASE}/oauth/authorize?{authorize_query}'
        authorize_response = session.get(
            authorize_url,
            headers=browser_headers,
            allow_redirects=False,
            timeout=30,
        )
    except SkylightError:
        raise
    except requests.RequestException as exc:
        raise SkylightError('Could not reach Skylight. Try again in a moment.') from exc

    redirect = urlparse(authorize_response.headers.get('Location', ''))
    code = (parse_qs(redirect.query).get('code') or [''])[0]
    if not code:
        raise SkylightError(
            'Skylight requires additional verification. Use the browser login once to complete it.'
        )
    credentials = _token_request(
        {
            'grant_type': 'authorization_code',
            'code': code,
            'client_id': CLIENT_ID,
            'redirect_uri': REDIRECT_URI,
            'scope': SCOPE,
            **_device_values(fingerprint),
        }
    )
    connection.encrypted_credentials = encrypt_credentials(credentials)
    connection.oauth_state_digest = ''
    connection.oauth_state_expires_at = None
    connection.connected_at = timezone.now()
    connection.last_sync_error = ''
    connection.save()
    discover_frame(connection)
    sync_profile_mappings(connection)
    return connection


def _credential_expiry(credentials):
    parsed = parse_datetime(str(credentials.get('expires_at', '')))
    if parsed is None:
        raise SkylightError('The stored Skylight credential has an invalid expiry. Reconnect Skylight.')
    return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed)


def refresh_credentials(connection, credentials=None):
    credentials = credentials or decrypt_credentials(connection)
    fingerprint = str(credentials['fingerprint'])
    refreshed = _token_request(
        {
            'grant_type': 'refresh_token',
            'refresh_token': credentials['refresh_token'],
            'client_id': CLIENT_ID,
            **_device_values(fingerprint),
        }
    )
    connection.encrypted_credentials = encrypt_credentials(refreshed)
    connection.save(update_fields=['encrypted_credentials', 'updated_at'])
    return refreshed


def _request(connection, method, path, *, params=None, retry=True):
    credentials = decrypt_credentials(connection)
    if _credential_expiry(credentials) <= timezone.now() + TOKEN_REFRESH_SKEW:
        credentials = refresh_credentials(connection, credentials)
    headers = {
        'Accept': 'application/json',
        'Authorization': f"Bearer {credentials['access_token']}",
        'Skylight-Api-Version': os.environ.get(
            'SKYLIGHT_API_VERSION', DEFAULT_API_VERSION
        ),
    }
    try:
        response = requests.request(
            method,
            f'{API_BASE}{path}',
            headers=headers,
            params=params,
            timeout=30,
        )
    except requests.RequestException as exc:
        raise SkylightError('Could not reach Skylight. Try again in a moment.') from exc
    if response.status_code in {401, 403} and retry:
        refresh_credentials(connection, credentials)
        return _request(connection, method, path, params=params, retry=False)
    if not response.ok:
        raise SkylightError(f'Skylight returned an error ({response.status_code}).')
    try:
        return response.json()
    except ValueError as exc:
        raise SkylightError('Skylight returned an unreadable response.') from exc


def _jsonapi_data(payload):
    data = payload.get('data', []) if isinstance(payload, dict) else []
    return data if isinstance(data, list) else []


def discover_frame(connection):
    frames = _jsonapi_data(_request(connection, 'GET', '/api/frames/calendar'))
    if not frames:
        raise SkylightError('No Skylight calendar frame was found for this account.')
    if connection.frame_id:
        selected = next(
            (frame for frame in frames if str(frame.get('id')) == connection.frame_id), None
        )
    else:
        selected = frames[0] if len(frames) == 1 else None
    if selected is None:
        raise SkylightError('Multiple Skylight frames were found; frame selection is required.')
    attributes = selected.get('attributes') or {}
    connection.frame_id = str(selected['id'])
    connection.frame_name = str(
        attributes.get('household_name') or attributes.get('name') or 'Skylight Calendar'
    )[:160]
    connection.save(update_fields=['frame_id', 'frame_name', 'updated_at'])
    return selected


def _normalized_profile_name(category_name):
    return PROFILE_SUFFIX.sub('', category_name.strip()).strip().casefold()


def sync_profile_mappings(connection):
    payload = _request(
        connection, 'GET', f'/api/frames/{connection.frame_id}/categories'
    )
    categories = _jsonapi_data(payload)
    profiles = list(TravelProfile.objects.filter(owner=connection.owner))
    profiles_by_name = {profile.name.strip().casefold(): profile for profile in profiles}
    seen = set()
    for category in categories:
        category_id = str(category.get('id', '')).strip()
        attributes = category.get('attributes') or {}
        name = str(
            attributes.get('name') or attributes.get('summary') or attributes.get('label') or ''
        ).strip()
        if not category_id or not name:
            continue
        normalized = _normalized_profile_name(name)
        profile = profiles_by_name.get(normalized)
        mapping, created = SkylightProfileMapping.objects.get_or_create(
            connection=connection,
            skylight_category_id=category_id,
            defaults={'skylight_category_name': name, 'profile': profile},
        )
        update_fields = []
        if mapping.skylight_category_name != name:
            mapping.skylight_category_name = name
            update_fields.append('skylight_category_name')
        if (
            not created
            and not mapping.manually_assigned
            and mapping.profile_id is None
            and profile is not None
        ):
            mapping.profile = profile
            update_fields.append('profile')
        if update_fields:
            update_fields.append('updated_at')
            mapping.save(update_fields=update_fields)
        seen.add(category_id)
    return list(connection.profile_mappings.filter(skylight_category_id__in=seen))


def _event_dates(attributes):
    start = parse_datetime(str(attributes.get('starts_at') or ''))
    end = parse_datetime(str(attributes.get('ends_at') or ''))
    if start is None:
        return None
    if timezone.is_naive(start):
        start = timezone.make_aware(start)
    if end is None:
        end = start
    elif timezone.is_naive(end):
        end = timezone.make_aware(end)
    # Preserve the wall dates encoded by Skylight. A server-timezone
    # conversion can otherwise make an evening event appear to span two days.
    start_date = start.date()
    end_date = end.date()
    if attributes.get('all_day') and end > start:
        end_date -= timedelta(days=1)
    return start_date, max(start_date, end_date)


def _event_category_ids(event):
    relationships = event.get('relationships') or {}
    categories = ((relationships.get('categories') or {}).get('data') or [])
    return [str(item.get('id')) for item in categories if item.get('id') is not None]


def _normalized_words(value):
    decomposed = unicodedata.normalize('NFKD', str(value or ''))
    ascii_text = ''.join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r'[^a-z0-9]+', ' ', ascii_text.casefold()).strip()


def _candidate_phrases(value):
    words = _normalized_words(value).split()
    phrases = set()
    for size in range(1, min(4, len(words)) + 1):
        for index in range(len(words) - size + 1):
            phrase = ' '.join(words[index:index + size])
            if size > 1 or len(phrase) >= 4 or phrase in DESTINATION_ALIASES:
                phrases.add(phrase)
    return phrases


def _place_is_destination(title, location, phrase):
    normalized_title = _normalized_words(title)
    normalized_location = _normalized_words(location)
    if normalized_location and re.search(rf'\b{re.escape(phrase)}\b', normalized_location):
        return True
    if normalized_title == phrase:
        return True
    if re.search(rf'\b(?:in|to|at)\s+{re.escape(phrase)}\b', normalized_title):
        return True
    return bool(
        re.match(
            rf'^{re.escape(phrase)}\s+(?:trip|visit|with|weekend|vacation|getaway)\b',
            normalized_title,
        )
    )


def _destination_matches(events):
    """Resolve destination-like title phrases against TouchGrass geography."""

    event_phrases = {}
    all_phrases = set()
    for event in events:
        attributes = event.get('attributes') or {}
        event_id = str(event.get('id') or '')
        phrases = _candidate_phrases(
            f"{attributes.get('summary') or ''} {attributes.get('location') or ''}"
        )
        event_phrases[event_id] = phrases
        all_phrases.update(phrases)

    known_names = {}
    for name, capital in Country.objects.values_list('name', 'capital'):
        for value in (name, capital):
            normalized = _normalized_words(value)
            if normalized in all_phrases:
                known_names[normalized] = str(value)
    for name in Region.objects.values_list('name', flat=True):
        normalized = _normalized_words(name)
        if normalized in all_phrases:
            known_names[normalized] = str(name)

    # The city table is large, so scan it once for this sync's small phrase set
    # instead of retaining a 150k-name Python cache in every backend process.
    city_candidates = [phrase for phrase in all_phrases if len(phrase) >= 4]
    if city_candidates:
        lookup_names = list(city_candidates)
        lookup_names.extend(
            ' '.join(part.capitalize() for part in phrase.split())
            for phrase in city_candidates
        )
        for name in City.objects.filter(name__in=lookup_names).values_list('name', flat=True).distinct():
            normalized = _normalized_words(name)
            known_names.setdefault(normalized, str(name))

    matches = {}
    events_by_id = {str(event.get('id') or ''): event for event in events}
    for event_id, phrases in event_phrases.items():
        attributes = (events_by_id.get(event_id) or {}).get('attributes') or {}
        title = str(attributes.get('summary') or '')
        location = str(attributes.get('location') or '')
        destinations = set()
        for phrase in phrases:
            display_name = known_names.get(phrase)
            if not display_name:
                continue
            if _place_is_destination(title, location, phrase):
                destinations.add(display_name)
        for alias, display_name in DESTINATION_ALIASES.items():
            if alias in phrases and _place_is_destination(title, location, alias):
                destinations.add(display_name)
        matches[event_id] = sorted(destinations, key=str.casefold)
    return matches


def _trip_detection(
    attributes, start_date, end_date, destinations, source_categories=()
):
    title = str(attributes.get('summary') or '').strip()
    all_day = bool(attributes.get('all_day'))
    duration_days = (end_date - start_date).days + 1
    explicit_trip = bool(EXPLICIT_TRIP_WORDS.search(title))
    score = 0
    reasons = []
    hard_exclusion = False

    if explicit_trip:
        score += 4
        reasons.append('Trip language in the title')
    if destinations:
        score += 3
        reasons.append(f"Destination: {', '.join(destinations[:3])}")
        normalized_title = _normalized_words(title)
        if re.search(r'\b(in|to|at)\b', normalized_title):
            score += 1
    if FLAG_EMOJI.search(title):
        score += 1
        reasons.append('Country flag in the title')
    if all_day and duration_days >= 2:
        score += 2
        reasons.append(f'{duration_days}-day all-day event')
    elif duration_days >= 2:
        score += 1
        reasons.append(f'{duration_days}-day event')

    if PLANNING_WORDS.search(title):
        score -= 6
        reasons.append('Looks like trip planning, not the trip')
    if TRIP_PLANNING_CALL_WORDS.search(title):
        score -= 10
        hard_exclusion = True
        reasons.append('Looks like a trip-planning FaceTime call')
    if HOME_FOR_WORDS.search(title):
        score -= 10
        hard_exclusion = True
        reasons.append('Going home does not count as a TouchGrass trip')
    if FAMILY_VISIT_WORDS.search(title):
        score -= 10
        hard_exclusion = True
        reasons.append('Family visits do not count as TouchGrass trips')
    if WORK_TRAVEL_WORDS.search(title) or any(
        _normalized_words(category) == 'work travel'
        for category in source_categories
    ):
        score -= 10
        hard_exclusion = True
        reasons.append('Work travel does not count as a TouchGrass trip')
    if attributes.get('rrule'):
        score -= 4
        reasons.append('Recurring calendar event')
    if LOCAL_EVENT_WORDS.search(title) and not explicit_trip:
        score -= 3
        reasons.append('Looks like a local appointment or activity')
    if not all_day and duration_days == 1 and not explicit_trip:
        score -= 2
        reasons.append('Short timed event')

    return {
        'candidate': (
            not hard_exclusion
            and score >= 4
            and (duration_days >= 2 or explicit_trip)
        ),
        'score': score,
        'reasons': reasons,
    }


@transaction.atomic
def sync_trip_suggestions(
    connection,
    *,
    date_min=None,
    date_max=None,
    timezone_name=None,
    update_suggestions=True,
):
    if not connection.is_connected:
        raise SkylightError('Connect Skylight before syncing.')
    sync_profile_mappings(connection)
    today = timezone.localdate()
    date_min = date_min or today - timedelta(days=365)
    date_max = date_max or today + timedelta(days=730)
    requested_timezone = str(timezone_name or connection.timezone or settings.TIME_ZONE)
    try:
        ZoneInfo(requested_timezone)
    except ZoneInfoNotFoundError:
        raise SkylightError('TouchGrass received an invalid browser timezone.')
    if connection.timezone != requested_timezone:
        connection.timezone = requested_timezone
        connection.save(update_fields=['timezone', 'updated_at'])
    mappings = {
        mapping.skylight_category_id: mapping.profile
        for mapping in connection.profile_mappings.select_related('profile')
        if mapping.profile_id
    }
    category_names = {
        mapping.skylight_category_id: mapping.skylight_category_name
        for mapping in connection.profile_mappings.all()
    }
    payload = _request(
        connection,
        'GET',
        f'/api/frames/{connection.frame_id}/calendar_events',
        params={
            'date_min': date_min.isoformat(),
            'date_max': date_max.isoformat(),
            'timezone': requested_timezone,
            'include': 'categories,calendar_account,event_notification_setting',
        },
    )
    events = _jsonapi_data(payload)
    destination_matches = _destination_matches(events)
    created_count = 0
    updated_count = 0
    reviews_created = 0
    reviews_updated = 0
    needs_review_count = 0
    removed_count = 0
    skipped_count = 0
    for event in events:
        attributes = event.get('attributes') or {}
        event_id = str(event.get('id') or '').strip()
        dates = _event_dates(attributes)
        category_ids = _event_category_ids(event)
        profiles = []
        seen_profile_ids = set()
        for category_id in category_ids:
            profile = mappings.get(category_id)
            if profile and profile.id not in seen_profile_ids:
                profiles.append(profile)
                seen_profile_ids.add(profile.id)
        if not event_id or not dates:
            if event_id:
                stale_suggestions = connection.trip_suggestions.filter(
                    skylight_event_id=event_id,
                    status=SkylightTripSuggestion.Status.PENDING,
                )
                removed_count += stale_suggestions.count()
                stale_suggestions.delete()
            skipped_count += 1
            continue
        start_date, end_date = dates
        detection = _trip_detection(
            attributes,
            start_date,
            end_date,
            destination_matches.get(event_id, []),
            [category_names.get(category_id, '') for category_id in category_ids],
        )
        title = str(attributes.get('summary') or 'Untitled Skylight event').strip()[:200]
        review_defaults = {
            'skylight_event_uid': str(attributes.get('uid') or '')[:255],
            'title': title,
            'start_date': start_date,
            'end_date': end_date,
            'all_day': bool(attributes.get('all_day')),
            'calendar_description': str(attributes.get('description') or ''),
            'location': str(attributes.get('location') or '')[:500],
            'category_ids': category_ids,
            'predicted_is_trip': detection['candidate'],
            'detection_score': detection['score'],
            'detection_reasons': detection['reasons'],
        }
        review, review_created = SkylightEventReview.objects.update_or_create(
            connection=connection,
            skylight_event_id=event_id,
            defaults=review_defaults,
        )
        review.profiles.set(profiles)
        if review_created:
            reviews_created += 1
        else:
            reviews_updated += 1
        if (
            review_created
            and profiles
            and review.human_label == SkylightEventReview.Label.UNREVIEWED
            and not detection['candidate']
        ):
            needs_review_count += 1

        # The ground-truth lab scans a much wider calendar range than the
        # normal suggestions queue. It stores classifier output for every
        # event without flooding Trips with years of historical candidates.
        if not update_suggestions:
            continue

        if not profiles:
            stale_suggestions = connection.trip_suggestions.filter(
                skylight_event_id=event_id,
                status=SkylightTripSuggestion.Status.PENDING,
            )
            removed_count += stale_suggestions.count()
            stale_suggestions.delete()
            skipped_count += 1
            continue
        if not detection['candidate']:
            stale_suggestions = connection.trip_suggestions.filter(
                skylight_event_id=event_id,
                status=SkylightTripSuggestion.Status.PENDING,
            )
            removed_count += stale_suggestions.count()
            stale_suggestions.delete()
            skipped_count += 1
            continue
        defaults = {
            'skylight_event_uid': str(attributes.get('uid') or '')[:255],
            'title': title,
            'start_date': start_date,
            'end_date': end_date,
            'notes': str(attributes.get('description') or ''),
            'location': str(attributes.get('location') or '')[:500],
            'category_ids': category_ids,
            'detection_score': detection['score'],
            'detection_reasons': detection['reasons'],
        }
        suggestion, created = SkylightTripSuggestion.objects.get_or_create(
            connection=connection,
            skylight_event_id=event_id,
            defaults=defaults,
        )
        if created:
            created_count += 1
        else:
            changed = False
            for field, value in defaults.items():
                if getattr(suggestion, field) != value:
                    setattr(suggestion, field, value)
                    changed = True
            if changed:
                suggestion.save()
                updated_count += 1
        if suggestion.status == SkylightTripSuggestion.Status.PENDING:
            suggestion.profiles.set(profiles)
    connection.last_sync_at = timezone.now()
    connection.last_sync_error = ''
    connection.save(update_fields=['last_sync_at', 'last_sync_error', 'updated_at'])
    return {
        'created': created_count,
        'updated': updated_count,
        'removed': removed_count,
        'skipped': skipped_count,
        'events_seen': len(events),
        'reviews_created': reviews_created,
        'reviews_updated': reviews_updated,
        'needs_review': needs_review_count,
    }


def record_sync_error(connection, error):
    connection.last_sync_error = str(error)[:MAX_ERROR_LENGTH]
    connection.save(update_fields=['last_sync_error', 'updated_at'])
