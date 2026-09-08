"""Resolve confirmed Skylight trips into travel history and trip planners.

Skylight reviews remain the source of truth.  We cache a structured destination
on each confirmed review, project completed reviews into map fills and visit
history, and materialize each confirmed review as one persistent Trip.
"""

import re
import unicodedata

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import (
    City,
    Country,
    ProfileCountryVisit,
    ProfileRegionVisit,
    Region,
    SkylightEventReview,
    SkylightTripSuggestion,
    Trip,
    TripDestination,
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
    'poconos': ('US-PA',),
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


def _share_trip_collection(collection, profiles):
    collaborator_ids = set()
    for profile in profiles:
        collaborator_ids.add(profile.owner_id)
        if profile.linked_user_id:
            collaborator_ids.add(profile.linked_user_id)
        collaborator_ids.update(profile.shared_with.values_list('id', flat=True))
    collaborator_ids.discard(collection.user_id)
    if collaborator_ids:
        collection.shared_with.add(*collaborator_ids)


def _matching_existing_trip(owner, review):
    candidates = Trip.objects.filter(
        owner=owner,
        start_date__lte=review.end_date,
        end_date__gte=review.start_date,
    )
    normalized_review_title = _normalize(review.title)
    return next(
        (
            trip for trip in candidates
            if _normalize(trip.title) == normalized_review_title
        ),
        None,
    )


def _label_exact_existing_trip_reviews(connection):
    """Treat one exact calendar match as the source for an existing trip.

    This repairs older trips accepted before source-review linking existed. A
    match must be unique by normalized title and exact date range; ambiguous
    reviews remain untouched for manual classification.
    """

    labeled = 0
    trips = Trip.objects.filter(
        owner=connection.owner,
        source_review__isnull=True,
    ).prefetch_related('profiles')
    for trip in trips:
        candidates = list(connection.event_reviews.filter(
            human_label=SkylightEventReview.Label.UNREVIEWED,
            start_date=trip.start_date,
            end_date=trip.end_date,
        ))
        matches = [review for review in candidates if _normalize(review.title) == _normalize(trip.title)]
        if len(matches) != 1:
            continue
        review = matches[0]
        review.human_label = SkylightEventReview.Label.TRIP
        review.save(update_fields=['human_label', 'updated_at'])
        review.profiles.add(*trip.profiles.all())
        labeled += 1
    return labeled


def _clean_copied_reviewer_notes(connection):
    """Remove reviewer-only prose copied into user-facing trip descriptions."""

    cleaned = 0
    trips = Trip.objects.filter(
        owner=connection.owner,
        source_review__isnull=False,
    ).select_related('source_review', 'collection')
    for trip in trips:
        review = trip.source_review
        reviewer_note = (review.reviewer_note or '').strip()
        if not reviewer_note:
            continue
        replacement = review.calendar_description or ''
        trip_changed = (trip.notes or '').strip() == reviewer_note
        collection_changed = (trip.collection.description or '').strip() == reviewer_note
        if trip_changed:
            trip.notes = replacement
            trip.save(update_fields=['notes', 'updated_at'])
        if collection_changed:
            trip.collection.description = replacement
            trip.collection.save(update_fields=['description', 'updated_at'])
        if trip_changed or collection_changed:
            cleaned += 1
    return cleaned


@transaction.atomic
def reconcile_skylight_reviews_into_trips(connection):
    """Materialize confirmed review labels and clear their review suggestions.

    The source-review relationship makes the operation idempotent. Older
    manually-created trips with the same title and overlapping dates are linked
    instead of duplicated.
    """

    from adventures.models import Collection

    repaired = _label_exact_existing_trip_reviews(connection)
    cleaned = _clean_copied_reviewer_notes(connection)
    pending_suggestions = {
        suggestion.skylight_event_id: suggestion
        for suggestion in connection.trip_suggestions.select_for_update().filter(
            status=SkylightTripSuggestion.Status.PENDING
        )
    }
    materialized_review_ids = set(
        Trip.objects.filter(
            owner=connection.owner,
            source_review__isnull=False,
        ).values_list('source_review_id', flat=True)
    )
    candidate_review_ids = set(
        connection.event_reviews.filter(
            human_label=SkylightEventReview.Label.TRIP,
        ).exclude(id__in=materialized_review_ids).values_list('id', flat=True)
    )
    if pending_suggestions:
        candidate_review_ids.update(
            connection.event_reviews.filter(
                skylight_event_id__in=pending_suggestions,
                human_label__in=[
                    SkylightEventReview.Label.TRIP,
                    SkylightEventReview.Label.NOT_TRIP,
                ],
            ).values_list('id', flat=True)
        )
    stats = {
        'created': 0, 'linked': 0, 'accepted': 0, 'dismissed': 0,
        'skipped': 0, 'repaired': repaired, 'cleaned': cleaned,
    }
    if not candidate_review_ids:
        return stats

    reviews = connection.event_reviews.select_for_update().filter(
        id__in=candidate_review_ids,
        human_label__in=[
            SkylightEventReview.Label.TRIP,
            SkylightEventReview.Label.NOT_TRIP,
        ]
    ).prefetch_related('profiles', 'profiles__shared_with')

    for review in reviews:
        suggestion = pending_suggestions.get(review.skylight_event_id)
        if review.human_label == SkylightEventReview.Label.NOT_TRIP:
            if suggestion and not suggestion.trip_id:
                suggestion.status = SkylightTripSuggestion.Status.DISMISSED
                suggestion.save(update_fields=['status', 'updated_at'])
                stats['dismissed'] += 1
            continue

        profiles = list(review.profiles.all())
        if not profiles:
            stats['skipped'] += 1
            continue

        trip = Trip.objects.filter(source_review=review).first()
        if not trip and suggestion and suggestion.trip_id:
            trip = suggestion.trip
        if not trip:
            trip = _matching_existing_trip(connection.owner, review)
            if trip:
                stats['linked'] += 1

        if not trip:
            collection = Collection.objects.create(
                user=connection.owner,
                name=review.title,
                description=review.calendar_description or '',
                start_date=review.start_date,
                end_date=review.end_date,
            )
            trip = Trip.objects.create(
                owner=connection.owner,
                collection=collection,
                source_review=review,
                title=review.title,
                start_date=review.start_date,
                end_date=review.end_date,
                notes=review.calendar_description or '',
            )
            trip.profiles.set(profiles)
            _share_trip_collection(collection, profiles)
            stats['created'] += 1
        else:
            if not trip.source_review_id:
                trip.source_review = review
                trip.save(update_fields=['source_review', 'updated_at'])
            reviewer_note = (review.reviewer_note or '').strip()
            replacement = review.calendar_description or ''
            if reviewer_note and (trip.notes or '').strip() == reviewer_note:
                trip.notes = replacement
                trip.save(update_fields=['notes', 'updated_at'])
            if reviewer_note and (trip.collection.description or '').strip() == reviewer_note:
                trip.collection.description = replacement
                trip.collection.save(update_fields=['description', 'updated_at'])
            trip.profiles.add(*profiles)
            _share_trip_collection(trip.collection, trip.profiles.all())

        country, region = resolve_review_destination(review)
        if country:
            TripDestination.objects.get_or_create(
                trip=trip,
                country=country,
                region=region,
            )

        if suggestion:
            suggestion.trip = trip
            suggestion.status = SkylightTripSuggestion.Status.ACCEPTED
            suggestion.save(update_fields=['trip', 'status', 'updated_at'])
            stats['accepted'] += 1

    return stats


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
                'notes': review.calendar_description,
                'source': 'skylight',
                'source_title': review.title,
                'read_only': True,
                'created_at': review.created_at.isoformat(),
            })
    return payloads
