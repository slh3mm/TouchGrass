from django.shortcuts import get_object_or_404
from .models import Country, Region, VisitedRegion, City, VisitedCity, TravelProfile, ProfileCountryVisit, ProfileRegionVisit, Trip
from .serializers import CitySerializer, CountrySerializer, RegionSerializer, VisitedRegionSerializer, VisitedCitySerializer, TravelProfileSerializer, TripSerializer
from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes, action
from django.contrib.gis.geos import Point
from adventures.models import Location
from collections import defaultdict
from django.db.models import Count, Q
from django.contrib.auth import get_user_model

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def regions_by_country(request, country_code):
    country = get_object_or_404(Country, country_code=country_code)
    regions = Region.objects.filter(country=country).order_by('name')
    serializer = RegionSerializer(regions, many=True, context={'request': request})
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
    queryset = Country.objects.all().order_by('name')
    serializer_class = CountrySerializer
    permission_classes = [IsAuthenticated]

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
        profile_region_map = defaultdict(set)
        for region_id, profile_id in ProfileRegionVisit.objects.filter(
            Q(profile__owner=user) | Q(profile__shared_with=user)
        ).values_list('region_id', 'profile_id'):
            profile_region_map[region_id].add(profile_id)
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
        return Trip.objects.filter(
            Q(owner=self.request.user) | Q(profiles__owner=self.request.user) | Q(profiles__shared_with=self.request.user)
        ).prefetch_related('profiles').distinct()

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


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
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def profile_region_visit(request, profile_id, region_id):
    profile = get_object_or_404(TravelProfile.objects.filter(Q(owner=request.user) | Q(shared_with=request.user)), id=profile_id)
    region = get_object_or_404(Region, id=region_id)
    if request.method == 'PUT':
        ProfileRegionVisit.objects.get_or_create(profile=profile, region=region)
        return Response({'visited': True}, status=status.HTTP_200_OK)
    ProfileRegionVisit.objects.filter(profile=profile, region=region).delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def profile_region_map(request):
    """Compact region/profile assignments for the world map initial load."""
    accessible_profiles = TravelProfile.objects.filter(
        Q(owner=request.user) | Q(shared_with=request.user)
    ).distinct()
    region_map = defaultdict(set)
    for region_id, profile_id in ProfileRegionVisit.objects.filter(
        profile__in=accessible_profiles
    ).values_list('region_id', 'profile_id'):
        region_map[region_id].add(str(profile_id))
    for region_id, profile_id in Location.objects.filter(
        Q(user=request.user) | Q(profiles__shared_with=request.user),
        region_id__isnull=False, visits__isnull=False, profiles__in=accessible_profiles,
    ).values_list('region_id', 'profiles__id').distinct():
        region_map[region_id].add(str(profile_id))
    return Response([
        {'id': region_id, 'profile_ids': sorted(profile_ids)}
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
