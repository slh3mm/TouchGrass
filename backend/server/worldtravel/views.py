from django.shortcuts import get_object_or_404
from .models import Country, Region, VisitedRegion, City, VisitedCity, TravelProfile, ProfileCountryVisit, ProfileRegionVisit, ProfileTravelVisit, Trip, BallparkVisit, SkylightConnection, SkylightProfileMapping, SkylightEventReview, SkylightTripSuggestion
from .serializers import CitySerializer, CountrySerializer, RegionSerializer, VisitedRegionSerializer, VisitedCitySerializer, TravelProfileSerializer, ProfileTravelVisitSerializer, TripSerializer, BallparkVisitSerializer, SkylightProfileMappingSerializer, SkylightEventReviewSerializer, SkylightTripSuggestionSerializer
from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes, action
from django.contrib.gis.geos import Point
from adventures.models import Location
from collections import defaultdict
from django.db.models import Count, Q
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from calendar import monthrange
from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .skylight import (
    SkylightError,
    begin_oauth,
    complete_oauth,
    login_with_password,
    record_sync_error,
    sync_trip_suggestions,
)
from .trip_history import (
    apply_joint_profile_precedence,
    completed_skylight_reviews,
    ensure_trip_destinations,
    resolve_review_destination,
    skylight_visit_payloads,
)


def _skylight_connection_status(connection, request):
    mappings = connection.profile_mappings.select_related('profile').all()
    suggestions = connection.trip_suggestions.filter(
        status=SkylightTripSuggestion.Status.PENDING
    ).prefetch_related('profiles')
    return {
        'connected': connection.is_connected,
        'frame_id': connection.frame_id or None,
        'frame_name': connection.frame_name or None,
        'connected_at': connection.connected_at,
        'last_sync_at': connection.last_sync_at,
        'last_sync_error': connection.last_sync_error or None,
        'credential_storage': 'encrypted database credential',
        'mappings': SkylightProfileMappingSerializer(
            mappings, many=True, context={'request': request}
        ).data,
        'suggestions': SkylightTripSuggestionSerializer(
            suggestions, many=True, context={'request': request}
        ).data,
    }


def _add_calendar_months(value, months):
    """Return the same day N calendar months later, clamped if necessary."""

    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def _connection_localdate(connection):
    try:
        calendar_timezone = ZoneInfo(connection.timezone or 'UTC')
    except ZoneInfoNotFoundError:
        calendar_timezone = ZoneInfo('UTC')
    return timezone.localdate(timezone=calendar_timezone)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def skylight_status(request):
    connection, _ = SkylightConnection.objects.get_or_create(owner=request.user)
    return Response(_skylight_connection_status(connection, request))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def skylight_connect(request):
    connection, _ = SkylightConnection.objects.get_or_create(owner=request.user)
    return Response({'login_url': begin_oauth(connection)})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def skylight_login(request):
    email = str(request.data.get('email') or '').strip()
    password = str(request.data.get('password') or '')
    connection, _ = SkylightConnection.objects.get_or_create(owner=request.user)
    try:
        login_with_password(connection, email, password)
    except SkylightError as exc:
        return Response({'error': str(exc)}, status=400)
    return Response(_skylight_connection_status(connection, request))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def skylight_complete(request):
    callback_url = str(request.data.get('callback_url') or '').strip()
    if not callback_url:
        return Response({'error': 'Paste the final Skylight URL.'}, status=400)
    connection, _ = SkylightConnection.objects.get_or_create(owner=request.user)
    try:
        complete_oauth(connection, callback_url)
    except SkylightError as exc:
        return Response({'error': str(exc)}, status=400)
    return Response(_skylight_connection_status(connection, request))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def skylight_sync(request):
    connection = get_object_or_404(SkylightConnection, owner=request.user)
    try:
        result = sync_trip_suggestions(
            connection,
            timezone_name=str(request.data.get('timezone') or '').strip() or None,
        )
    except SkylightError as exc:
        record_sync_error(connection, exc)
        return Response({'error': str(exc)}, status=400)
    return Response({
        'sync': result,
        'connection': _skylight_connection_status(connection, request),
    })


def _event_review_payload(connection, request):
    ensure_trip_destinations(connection.owner)
    future_cutoff = _add_calendar_months(_connection_localdate(connection), 3)
    reviews = connection.event_reviews.filter(
        start_date__lte=future_cutoff
    ).prefetch_related('profiles')
    counts = {
        'all': reviews.count(),
        'unreviewed': reviews.filter(
            human_label=SkylightEventReview.Label.UNREVIEWED
        ).count(),
        'trip': reviews.filter(human_label=SkylightEventReview.Label.TRIP).count(),
        'not_trip': reviews.filter(
            human_label=SkylightEventReview.Label.NOT_TRIP
        ).count(),
    }
    return {
        'connected': connection.is_connected,
        'last_sync_at': connection.last_sync_at,
        'future_cutoff': future_cutoff,
        'counts': counts,
        'events': SkylightEventReviewSerializer(
            reviews, many=True, context={'request': request}
        ).data,
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def skylight_event_reviews(request):
    connection, _ = SkylightConnection.objects.get_or_create(owner=request.user)
    return Response(_event_review_payload(connection, request))


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def skylight_event_review(request, review_id):
    review = get_object_or_404(
        SkylightEventReview.objects.prefetch_related('profiles'),
        id=review_id,
        connection__owner=request.user,
    )
    serializer = SkylightEventReviewSerializer(
        review, data=request.data, partial=True, context={'request': request}
    )
    serializer.is_valid(raise_exception=True)
    review = serializer.save()
    if review.human_label == SkylightEventReview.Label.TRIP:
        force_resolution = (
            review.destination_resolution != 'manual'
            and any(field in request.data for field in ('location', 'reviewer_note'))
        )
        if any(field in request.data for field in ('destination_country', 'destination_region')):
            review.destination_resolution = 'manual'
            if review.destination_region_id:
                review.destination_country = review.destination_region.country
            review.destination_label = (
                review.destination_region.name
                if review.destination_region_id
                else review.destination_country.name if review.destination_country_id else ''
            )
            review.save(update_fields=[
                'destination_country', 'destination_label',
                'destination_resolution', 'updated_at',
            ])
        else:
            resolve_review_destination(review, force=force_resolution)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def skylight_event_reviews_refresh(request):
    connection = get_object_or_404(SkylightConnection, owner=request.user)
    today = _connection_localdate(connection)
    future_cutoff = _add_calendar_months(today, 3)
    try:
        result = sync_trip_suggestions(
            connection,
            date_min=date(1900, 1, 1),
            date_max=future_cutoff,
            timezone_name=str(request.data.get('timezone') or '').strip() or None,
            update_suggestions=False,
        )
    except SkylightError as exc:
        record_sync_error(connection, exc)
        return Response({'error': str(exc)}, status=400)
    return Response({
        'sync': result,
        'review_data': _event_review_payload(connection, request),
    })


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def skylight_mapping(request, mapping_id):
    mapping = get_object_or_404(
        SkylightProfileMapping.objects.select_related('connection'),
        id=mapping_id,
        connection__owner=request.user,
    )
    serializer = SkylightProfileMappingSerializer(
        mapping, data=request.data, partial=True, context={'request': request}
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@transaction.atomic
def skylight_suggestion_accept(request, suggestion_id):
    suggestion = get_object_or_404(
        SkylightTripSuggestion.objects.select_for_update().prefetch_related('profiles'),
        id=suggestion_id,
        connection__owner=request.user,
    )
    if suggestion.status == SkylightTripSuggestion.Status.ACCEPTED and suggestion.trip_id:
        return Response(TripSerializer(suggestion.trip, context={'request': request}).data)

    payload = {
        'title': request.data.get('title', suggestion.title),
        'start_date': request.data.get('start_date', suggestion.start_date),
        'end_date': request.data.get('end_date', suggestion.end_date),
        'notes': request.data.get('notes', suggestion.notes),
        'profiles': request.data.get(
            'profiles', [str(value) for value in suggestion.profiles.values_list('id', flat=True)]
        ),
    }
    serializer = TripSerializer(data=payload, context={'request': request})
    serializer.is_valid(raise_exception=True)
    trip = serializer.save(owner=request.user)
    suggestion.trip = trip
    suggestion.status = SkylightTripSuggestion.Status.ACCEPTED
    suggestion.save(update_fields=['trip', 'status', 'updated_at'])
    return Response(TripSerializer(trip, context={'request': request}).data, status=201)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def skylight_suggestion_dismiss(request, suggestion_id):
    suggestion = get_object_or_404(
        SkylightTripSuggestion,
        id=suggestion_id,
        connection__owner=request.user,
    )
    suggestion.status = SkylightTripSuggestion.Status.DISMISSED
    suggestion.save(update_fields=['status', 'updated_at'])
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def skylight_disconnect(request):
    connection = SkylightConnection.objects.filter(owner=request.user).first()
    if connection:
        connection.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def regions_by_country(request, country_code):
    country = get_object_or_404(Country, country_code=country_code)
    regions = Region.objects.filter(country=country).select_related('country').annotate(
        _num_cities=Count('city')
    ).order_by('name')
    accessible_profiles = TravelProfile.objects.filter(
        Q(owner=request.user) | Q(shared_with=request.user)
    ).distinct()
    accessible_profile_ids = set(accessible_profiles.values_list('id', flat=True))
    profile_region_map = defaultdict(set)
    for region_id, profile_id in ProfileRegionVisit.objects.filter(
        profile__in=accessible_profiles, region__country=country
    ).values_list('region_id', 'profile_id'):
        profile_region_map[region_id].add(profile_id)
    for review in completed_skylight_reviews(request.user, country_code=country_code):
        if not review.destination_region_id:
            continue
        for profile in review.profiles.all():
            if profile.id in accessible_profile_ids:
                profile_region_map[review.destination_region_id].add(profile.id)
    for region_id, profile_id in Location.objects.filter(
        Q(user=request.user) | Q(profiles__shared_with=request.user),
        country=country,
        region_id__isnull=False,
        visits__isnull=False,
        profiles__in=accessible_profiles,
    ).values_list('region_id', 'profiles__id').distinct():
        if region_id and profile_id:
            profile_region_map[region_id].add(profile_id)
    serializer = RegionSerializer(
        regions, many=True,
        context={'request': request, 'profile_region_map': profile_region_map},
    )
    return Response(serializer.data)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def visits_by_country(request, country_code):
    country = get_object_or_404(Country, country_code=country_code)
    visits = VisitedRegion.objects.filter(region__country=country, user=request.user.id)
    serializer = VisitedRegionSerializer(visits, many=True)
    return Response(serializer.data)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def cities_by_region(request, region_id):
    region = get_object_or_404(Region, id=region_id)
    cities = City.objects.filter(region=region).order_by('name')
    serializer = CitySerializer(cities, many=True)
    return Response(serializer.data)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def visits_by_region(request, region_id):
    region = get_object_or_404(Region, id=region_id)
    visits = VisitedCity.objects.filter(city__region=region, user=request.user.id)
    serializer = VisitedCitySerializer(visits, many=True)
    return Response(serializer.data)

# view called spin the globe that return a random country, a random region in that country and a random city in that region
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def globespin(request):
    country = Country.objects.order_by('?').first()
    data = {
        "country": CountrySerializer(country).data,
    }
    
    regions = Region.objects.filter(country=country)
    if regions.exists():
        region = regions.order_by('?').first()
        data["region"] = RegionSerializer(region).data
        
        cities = City.objects.filter(region=region)
        if cities.exists():
            city = cities.order_by('?').first()
            data["city"] = CitySerializer(city).data
    
    return Response(data)

class CountryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Country.objects.all()
    serializer_class = CountrySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Country.objects.annotate(_num_regions=Count('region', distinct=True)).order_by('name')

    def get_serializer_context(self):
        context = super().get_serializer_context()
        user = self.request.user
        accessible_profiles = TravelProfile.objects.filter(
            Q(owner=user) | Q(shared_with=user)
        ).distinct()
        accessible_profile_ids = set(accessible_profiles.values_list('id', flat=True))
        profile_country_map = defaultdict(set)
        for country_id, profile_id in ProfileCountryVisit.objects.filter(
            profile__in=accessible_profiles
        ).values_list('country_id', 'profile_id'):
            profile_country_map[country_id].add(profile_id)
        for country_id, profile_id in ProfileRegionVisit.objects.filter(
            profile__in=accessible_profiles
        ).values_list('region__country_id', 'profile_id'):
            profile_country_map[country_id].add(profile_id)
        for review in completed_skylight_reviews(user):
            for profile in review.profiles.all():
                if profile.id in accessible_profile_ids:
                    profile_country_map[review.destination_country_id].add(profile.id)
        for country_id, profile_id in Location.objects.filter(
            Q(user=user) | Q(profiles__shared_with=user),
            country_id__isnull=False,
            visits__isnull=False,
            profiles__in=accessible_profiles,
        ).values_list('country_id', 'profiles__id').distinct():
            if country_id and profile_id:
                profile_country_map[country_id].add(profile_id)
        context['profile_country_map'] = profile_country_map
        context['visit_count_map'] = {
            row['region__country_id']: row['count']
            for row in VisitedRegion.objects.filter(user=user)
            .values('region__country_id')
            .annotate(count=Count('id'))
        }
        return context

    @action(detail=False, methods=['get'])
    def check_point_in_region(self, request):
        lat = float(request.query_params.get('lat'))
        lon = float(request.query_params.get('lon'))
        point = Point(lon, lat, srid=4326)
        region = Region.objects.filter(geometry__contains=point).first()
        if region:
            return Response({'in_region': True, 'region_name': region.name, 'region_id': region.id})
        else:
            return Response({'in_region': False})

    @action(detail=False, methods=['post'])
    def region_check_all_adventures(self, request):
        adventures = Location.objects.filter(user=request.user.id, type='visited')
        count = 0
        for adventure in adventures:
            if adventure.latitude is not None and adventure.longitude is not None:
                try:
                    point = Point(float(adventure.longitude), float(adventure.latitude), srid=4326)
                    region = Region.objects.filter(geometry__contains=point).first()
                    if region:
                        if not VisitedRegion.objects.filter(user=request.user.id, region=region).exists():
                            VisitedRegion.objects.create(user=request.user, region=region)
                            count += 1
                except Exception as e:
                    print(f"Error processing adventure {adventure.id}: {e}")
                    continue
        return Response({'regions_visited': count})

class RegionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Region.objects.select_related('country').annotate(_num_cities=Count('city'))
    serializer_class = RegionSerializer
    permission_classes = [IsAuthenticated]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        user = self.request.user
        accessible_profile_ids = set(
            TravelProfile.objects.filter(
                Q(owner=user) | Q(shared_with=user)
            ).values_list('id', flat=True)
        )
        profile_region_map = defaultdict(set)
        for region_id, profile_id in ProfileRegionVisit.objects.filter(
            Q(profile__owner=user) | Q(profile__shared_with=user)
        ).values_list('region_id', 'profile_id'):
            profile_region_map[region_id].add(profile_id)
        for review in completed_skylight_reviews(user):
            if not review.destination_region_id:
                continue
            for profile in review.profiles.all():
                if profile.id in accessible_profile_ids:
                    profile_region_map[review.destination_region_id].add(profile.id)
        for region_id, profile_id in Location.objects.filter(
            Q(user=user) | Q(profiles__shared_with=user), visits__isnull=False, profiles__isnull=False
        ).values_list('region_id', 'profiles__id').distinct():
            if region_id and profile_id:
                profile_region_map[region_id].add(profile_id)
        context['profile_region_map'] = profile_region_map
        return context


class TravelProfileViewSet(viewsets.ModelViewSet):
    serializer_class = TravelProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.action in {'update', 'partial_update', 'destroy'}:
            return TravelProfile.objects.filter(owner=self.request.user)
        return TravelProfile.objects.filter(
            Q(owner=self.request.user) | Q(shared_with=self.request.user)
        ).distinct()

    def perform_create(self, serializer):
        is_first = not TravelProfile.objects.filter(owner=self.request.user).exists()
        serializer.save(owner=self.request.user, is_default=is_first)

    @action(detail=False, methods=['post'])
    def share(self, request):
        username = str(request.data.get('username', '')).strip()
        member = get_object_or_404(get_user_model(), username__iexact=username)
        if member == request.user:
            return Response({'error': 'This calendar already belongs to you.'}, status=400)
        profiles = TravelProfile.objects.filter(owner=request.user)
        for profile in profiles:
            profile.shared_with.add(member)
        return Response({'shared_with': member.username, 'profiles': profiles.count()})

    def perform_destroy(self, instance):
        if self.get_queryset().count() == 1:
            from rest_framework.exceptions import ValidationError
            raise ValidationError('At least one profile is required.')
        was_default = instance.is_default
        instance.delete()
        if was_default:
            replacement = self.get_queryset().first()
            if replacement:
                replacement.is_default = True
                replacement.save(update_fields=['is_default'])


class TripViewSet(viewsets.ModelViewSet):
    serializer_class = TripSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Trip.objects.filter(
            Q(owner=self.request.user)
            | Q(collection__shared_with=self.request.user)
            | Q(profiles__owner=self.request.user)
            | Q(profiles__shared_with=self.request.user)
        ).select_related('collection').prefetch_related('profiles').distinct()
        collection_id = self.request.query_params.get('collection')
        if collection_id:
            queryset = queryset.filter(collection_id=collection_id)
        return queryset

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def perform_destroy(self, instance):
        # Deleting the planner cascades to its linked TouchGrass trip and every
        # itinerary item in the same transaction.
        instance.collection.delete()


class BallparkVisitViewSet(viewsets.ModelViewSet):
    serializer_class = BallparkVisitSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return BallparkVisit.objects.filter(
            Q(profile__owner=self.request.user) | Q(profile__shared_with=self.request.user)
        ).select_related('profile').distinct()


class ProfileTravelVisitViewSet(viewsets.ModelViewSet):
    serializer_class = ProfileTravelVisitSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = ProfileTravelVisit.objects.filter(
            Q(profile__owner=self.request.user) | Q(profile__shared_with=self.request.user)
        ).select_related('profile', 'country', 'region').distinct()
        profile_id = self.request.query_params.get('profile')
        country_code = self.request.query_params.get('country')
        region_id = self.request.query_params.get('region')
        if profile_id:
            queryset = queryset.filter(profile_id=profile_id)
        if country_code:
            queryset = queryset.filter(country__country_code=country_code.upper())
        if region_id:
            queryset = queryset.filter(region_id=region_id)
        return queryset

    def perform_create(self, serializer):
        visit = serializer.save()
        if visit.region_id:
            ProfileRegionVisit.objects.get_or_create(profile=visit.profile, region=visit.region)
        else:
            ProfileCountryVisit.objects.get_or_create(profile=visit.profile, country=visit.country)

    def list(self, request, *args, **kwargs):
        manual_visits = list(
            self.get_serializer(self.filter_queryset(self.get_queryset()), many=True).data
        )
        for visit in manual_visits:
            visit.update({
                'end_date': visit['visit_date'],
                'source': 'manual',
                'source_title': '',
                'read_only': False,
            })
        skylight_visits = skylight_visit_payloads(
            request.user,
            country_code=request.query_params.get('country'),
            region_id=request.query_params.get('region'),
            profile_id=request.query_params.get('profile'),
        )
        visits = manual_visits + skylight_visits
        visits.sort(key=lambda visit: (visit['visit_date'], visit.get('created_at') or ''), reverse=True)
        return Response(visits)


@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def profile_country_visit(request, profile_id, country_code):
    profile = get_object_or_404(TravelProfile.objects.filter(Q(owner=request.user) | Q(shared_with=request.user)), id=profile_id)
    country = get_object_or_404(Country, country_code=country_code.upper())
    if request.method == 'PUT':
        ProfileCountryVisit.objects.get_or_create(profile=profile, country=country)
        return Response({'visited': True}, status=status.HTTP_200_OK)
    ProfileCountryVisit.objects.filter(profile=profile, country=country).delete()
    ProfileRegionVisit.objects.filter(profile=profile, region__country=country).delete()
    trip_history_remains = completed_skylight_reviews(
        request.user,
        country_code=country.country_code,
        profile_id=profile.id,
    ).exists()
    return Response(
        {'visited': trip_history_remains, 'source': 'trip' if trip_history_remains else None},
        status=status.HTTP_200_OK,
    )


@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def profile_region_visit(request, profile_id, region_id):
    profile = get_object_or_404(TravelProfile.objects.filter(Q(owner=request.user) | Q(shared_with=request.user)), id=profile_id)
    region = get_object_or_404(Region, id=region_id)
    if request.method == 'PUT':
        ProfileRegionVisit.objects.get_or_create(profile=profile, region=region)
        return Response({'visited': True}, status=status.HTTP_200_OK)
    ProfileRegionVisit.objects.filter(profile=profile, region=region).delete()
    trip_history_remains = completed_skylight_reviews(
        request.user,
        region_id=region.id,
        profile_id=profile.id,
    ).exists()
    return Response(
        {'visited': trip_history_remains, 'source': 'trip' if trip_history_remains else None},
        status=status.HTTP_200_OK,
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def profile_region_map(request):
    """Compact region/profile assignments for the world map initial load."""
    accessible_profiles = TravelProfile.objects.filter(
        Q(owner=request.user) | Q(shared_with=request.user)
    ).distinct()
    accessible_profile_ids = set(accessible_profiles.values_list('id', flat=True))
    region_map = defaultdict(set)
    for region_id, profile_id in ProfileRegionVisit.objects.filter(
        profile__in=accessible_profiles
    ).values_list('region_id', 'profile_id'):
        region_map[region_id].add(str(profile_id))
    for review in completed_skylight_reviews(request.user):
        if not review.destination_region_id:
            continue
        for profile in review.profiles.all():
            if profile.id in accessible_profile_ids:
                region_map[review.destination_region_id].add(str(profile.id))
    for region_id, profile_id in Location.objects.filter(
        Q(user=request.user) | Q(profiles__shared_with=request.user),
        region_id__isnull=False, visits__isnull=False, profiles__in=accessible_profiles,
    ).values_list('region_id', 'profiles__id').distinct():
        region_map[region_id].add(str(profile_id))
    return Response([
        {
            'id': region_id,
            'profile_ids': sorted(
                apply_joint_profile_precedence(profile_ids, accessible_profiles)
            ),
        }
        for region_id, profile_ids in region_map.items()
    ])

class VisitedRegionViewSet(viewsets.ModelViewSet):
    serializer_class = VisitedRegionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return VisitedRegion.objects.filter(user=self.request.user.id)
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def create(self, request, *args, **kwargs):
        request.data['user'] = request.user
        if VisitedRegion.objects.filter(user=request.user.id, region=request.data['region']).exists():
            return Response({"error": "Region already visited by user."}, status=400)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
    
    def destroy(self, request, **kwargs):
        region = get_object_or_404(Region, id=kwargs['pk'])
        visited_region = VisitedRegion.objects.filter(user=request.user.id, region=region)
        if visited_region.exists():
            visited_region.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        else:
            return Response({"error": "Visited region not found."}, status=status.HTTP_404_NOT_FOUND)
    
class VisitedCityViewSet(viewsets.ModelViewSet):
    serializer_class = VisitedCitySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return VisitedCity.objects.filter(user=self.request.user.id)
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def create(self, request, *args, **kwargs):
        request.data['user'] = request.user
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        # Ensure a VisitedRegion exists for the city
        region = serializer.validated_data['city'].region
        if not VisitedRegion.objects.filter(user=request.user.id, region=region).exists():
            VisitedRegion.objects.create(user=request.user, region=region)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
    
    def destroy(self, request, **kwargs):
        city = get_object_or_404(City, id=kwargs['pk'])
        visited_city = VisitedCity.objects.filter(user=request.user.id, city=city)
        if visited_city.exists():
            visited_city.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        else:
            return Response({"error": "Visited city not found."}, status=status.HTTP_404_NOT_FOUND)
