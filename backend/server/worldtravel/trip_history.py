"""Resolve confirmed Skylight trips into read-only travel history.

Skylight reviews remain the source of truth.  We cache a structured destination
on each confirmed review, then project completed reviews into map fills and
visit-history payloads without creating or deleting any manual visit records.
"""

import re
import unicodedata

from django.db.models import Q
from django.utils import timezone

from .models import (
    City,
    Country,
    ProfileCountryVisit,
    ProfileRegionVisit,
    Region,
    SkylightEventReview,
    TravelProfile,
)


SUBDIVISION_COUNTRIES = {'US', 'CA'}
US_REGION_CODES = {
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA', 'HI', 'ID',
    'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS',
    'MO', 'MT', 'NE', 'NV', 'NH', 'NJ', 'NM', 'NY', 'NC', 'ND', 'OH', 'OK',
    'OR', 'PA', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV',
    'WI', 'WY', 'DC',
}
CA_REGION_CODES = {
    'AB', 'BC', 'MB', 'NB', 'NL', 'NS', 'NT', 'NU', 'ON', 'PE', 'QC', 'SK', 'YT',
}

# Reusable informal place/institution names.  Values may contain alternatives;
# the profile's existing fills resolve ambiguity (for example Universal FL/CA).
PLACE_ALIASES = {
    'philly': ('US-PA',),
    'philadelphia': ('US-PA',),
    'uva': ('US-VA',),
    'universal': ('US-FL', 'US-CA'),
    'orlando': ('US-FL',),
    'boston': ('US-MA',),
    'nyc': ('US-NY',),
    'new york city': ('US-NY',),
    'austin': ('US-TX',),
    'charleston': ('US-SC',),
    'canaan valley': ('US-WV',),
    'harpers ferry': ('US-WV',),
    'wildwood': ('US-NJ',),
    'chincoteague': ('US-VA',),
    'san diego': ('US-CA',),
    'nashville': ('US-TN',),
    'toronto': ('CA-ON',),
    'london': ('GB',),
}

IGNORED_CITY_WORDS = {
    'trip', 'weekend', 'visit', 'with', 'and', 'the', 'for', 'retreat', 'skiing',
    'cabin', 'summer', 'winter', 'spring', 'fall', 'birthday', 'concert', 'travel',
}


def _normalize(value):
    value = unicodedata.normalize('NFKD', str(value or ''))
    value = ''.join(char for char in value if not unicodedata.combining(char))
    return re.sub(r'[^a-z0-9]+', ' ', value.casefold()).strip()


def apply_joint_profile_precedence(profile_ids, profiles):
    """Collapse a location's visible colors to Joint when Joint is present.

    This deliberately changes only presentation/aggregation.  Individual
    manual records and every dated Skylight trip remain intact for history.
    """

    values = set(profile_ids)
    joint_ids = {
        str(profile.id) for profile in profiles
        if _normalize(profile.name) == 'joint'
    }
    # Some callers aggregate UUIDs while the compact map endpoint aggregates
    # strings. Preserve the caller's value type while comparing consistently.
    joint_matches = {value for value in values if str(value) in joint_ids}
    return joint_matches or values


def _review_text(review):
    return ' '.join(
        value for value in (
            review.location,
            review.reviewer_note,
            review.title,
            review.calendar_description,
        ) if value
    )


def _contains_phrase(normalized_text, phrase):
    return f' {_normalize(phrase)} ' in f' {normalized_text} '


def _profile_ids(review):
    return list(review.profiles.values_list('id', flat=True))


def _best_region(review, candidate_ids):
    candidates = list(
        Region.objects.filter(id__in=candidate_ids).select_related('country')
    )
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    profile_ids = _profile_ids(review)
    filled_regions = set(
        ProfileRegionVisit.objects.filter(
            profile_id__in=profile_ids,
            region_id__in=[region.id for region in candidates],
        ).values_list('region_id', flat=True)
    )
    if len(filled_regions) == 1:
        return next(region for region in candidates if region.id in filled_regions)

    filled_countries = set(
        ProfileCountryVisit.objects.filter(
            profile_id__in=profile_ids,
            country_id__in=[region.country_id for region in candidates],
        ).values_list('country_id', flat=True)
    )
    country_matches = [region for region in candidates if region.country_id in filled_countries]
    if len(country_matches) == 1:
        return country_matches[0]
    return None


def _explicit_region(review, raw_text):
    # Require the calendar's uppercase spelling so normal words such as "in"
    # cannot be mistaken for a two-letter state code.
    codes = re.findall(r'(?<![A-Z])([A-Z]{2})(?![A-Z])', raw_text)
    for code in codes:
        region_id = None
        if code in US_REGION_CODES:
            region_id = f'US-{code}'
        elif code in CA_REGION_CODES:
            region_id = f'CA-{code}'
        if region_id:
            region = Region.objects.filter(id=region_id).select_related('country').first()
            if region:
                return region
    return None


def _named_region(normalized_text):
    matches = [
        region for region in Region.objects.filter(
            country__country_code__in=SUBDIVISION_COUNTRIES
        ).select_related('country')
        if _contains_phrase(normalized_text, region.name)
    ]
    if not matches:
        return None
    return max(matches, key=lambda region: len(_normalize(region.name)))


def _named_country(normalized_text):
    matches = [
        country for country in Country.objects.all()
        if len(_normalize(country.name)) >= 4 and _contains_phrase(normalized_text, country.name)
    ]
    if not matches:
        return None
    return max(matches, key=lambda country: len(_normalize(country.name)))


def _city_phrases(raw_text):
    words = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ']+", raw_text)
    phrases = set()
    for size in range(1, 5):
        for index in range(len(words) - size + 1):
            phrase_words = words[index:index + size]
            if size == 1 and phrase_words[0].casefold() in IGNORED_CITY_WORDS:
                continue
            phrases.add(' '.join(phrase_words))
    return phrases


def _city_region(review, raw_text):
    phrases = _city_phrases(raw_text)
    if not phrases:
        return None
    cities = list(
        City.objects.filter(name__in=phrases).select_related('region__country')[:250]
    )
    if not cities:
        return None

    profile_ids = _profile_ids(review)
    filled_regions = set(
        ProfileRegionVisit.objects.filter(profile_id__in=profile_ids).values_list(
            'region_id', flat=True
        )
    )
    filled_countries = set(
        ProfileCountryVisit.objects.filter(profile_id__in=profile_ids).values_list(
            'country_id', flat=True
        )
    )
    ranked = []
    for city in cities:
        score = len(city.name.split()) * 10
        if city.region_id in filled_regions:
            score += 100
        if city.region.country_id in filled_countries:
            score += 40
        ranked.append((score, city))
    ranked.sort(key=lambda item: item[0], reverse=True)
    if len(ranked) > 1 and ranked[0][0] == ranked[1][0] and ranked[0][1].region_id != ranked[1][1].region_id:
        return None
    return ranked[0][1].region


def resolve_review_destination(review, *, force=False):
    """Resolve and cache one primary destination for a confirmed trip review."""

    if review.destination_country_id and not force:
        return review.destination_country, review.destination_region

    raw_text = _review_text(review)
    normalized_text = _normalize(raw_text)
    region = _explicit_region(review, raw_text)

    if not region:
        for alias, candidate_ids in sorted(
            PLACE_ALIASES.items(), key=lambda item: len(item[0]), reverse=True
        ):
            if not _contains_phrase(normalized_text, alias):
                continue
            country_code = candidate_ids[0] if len(candidate_ids[0]) == 2 else None
            if country_code:
                country = Country.objects.filter(country_code=country_code).first()
                if country:
                    review.destination_country = country
                    review.destination_region = None
                    review.destination_label = country.name
                    review.destination_resolution = 'automatic'
                    review.save(update_fields=[
                        'destination_country', 'destination_region', 'destination_label',
                        'destination_resolution', 'updated_at',
                    ])
                    return country, None
            region = _best_region(review, candidate_ids)
            if region:
                break

    region = region or _named_region(normalized_text)
    if not region:
        country = _named_country(normalized_text)
        if country:
            review.destination_country = country
            review.destination_region = None
            review.destination_label = country.name
            review.destination_resolution = 'automatic'
            review.save(update_fields=[
                'destination_country', 'destination_region', 'destination_label',
                'destination_resolution', 'updated_at',
            ])
            return country, None
        region = _city_region(review, raw_text)

    if not region:
        review.destination_resolution = 'unresolved'
        review.save(update_fields=['destination_resolution', 'updated_at'])
        return None, None

    country = region.country
    saved_region = region if country.country_code in SUBDIVISION_COUNTRIES else None
    review.destination_country = country
    review.destination_region = saved_region
    review.destination_label = region.name if saved_region else country.name
    review.destination_resolution = 'automatic'
    review.save(update_fields=[
        'destination_country', 'destination_region', 'destination_label',
        'destination_resolution', 'updated_at',
    ])
    return country, saved_region


def ensure_trip_destinations(user=None, *, force=False):
    reviews = SkylightEventReview.objects.filter(
        human_label=SkylightEventReview.Label.TRIP
    ).select_related('destination_country', 'destination_region').prefetch_related('profiles')
    if user is not None:
        reviews = reviews.filter(
            Q(connection__owner=user)
            | Q(profiles__owner=user)
            | Q(profiles__shared_with=user)
        ).distinct()
    if not force:
        reviews = reviews.filter(destination_country__isnull=True)

    resolved = 0
    unresolved = 0
    for review in reviews:
        country, _ = resolve_review_destination(review, force=force)
        if country:
            resolved += 1
        else:
            unresolved += 1
    return {'resolved': resolved, 'unresolved': unresolved}


def completed_skylight_reviews(user, *, country_code=None, region_id=None, profile_id=None):
    ensure_trip_destinations(user)
    accessible_profiles = TravelProfile.objects.filter(
        Q(owner=user) | Q(shared_with=user)
    ).distinct()
    reviews = SkylightEventReview.objects.filter(
        Q(connection__owner=user)
        | Q(profiles__owner=user)
        | Q(profiles__shared_with=user),
        human_label=SkylightEventReview.Label.TRIP,
        start_date__lte=timezone.localdate(),
        destination_country__isnull=False,
        profiles__in=accessible_profiles,
    ).select_related(
        'destination_country', 'destination_region'
    ).prefetch_related('profiles').distinct()
    if country_code:
        reviews = reviews.filter(destination_country__country_code=country_code.upper())
    if region_id:
        reviews = reviews.filter(destination_region_id=region_id)
    if profile_id:
        reviews = reviews.filter(profiles__id=profile_id)
    return reviews


def skylight_visit_payloads(user, *, country_code=None, region_id=None, profile_id=None):
    accessible_profile_ids = set(
        TravelProfile.objects.filter(
            Q(owner=user) | Q(shared_with=user)
        ).values_list('id', flat=True)
    )
    payloads = []
    for review in completed_skylight_reviews(
        user,
        country_code=country_code,
        region_id=region_id,
        profile_id=profile_id,
    ):
        for profile in review.profiles.all():
            if profile.id not in accessible_profile_ids:
                continue
            if profile_id and str(profile.id) != str(profile_id):
                continue
            payloads.append({
                'id': f'skylight:{review.id}:{profile.id}',
                'profile': str(profile.id),
                'profile_name': profile.name,
                'profile_color': profile.color,
                'profile_avatar': profile.avatar,
                'country': review.destination_country_id,
                'country_code': review.destination_country.country_code,
                'country_name': review.destination_country.name,
                'region': review.destination_region_id,
                'region_name': review.destination_region.name if review.destination_region else None,
                'visit_date': review.start_date.isoformat(),
                'end_date': review.end_date.isoformat(),
                'notes': review.reviewer_note or review.calendar_description,
                'source': 'skylight',
                'source_title': review.title,
                'read_only': True,
                'created_at': review.created_at.isoformat(),
            })
    return payloads
