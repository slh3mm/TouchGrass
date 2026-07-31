import os
from django.db.models import Q
from .models import (
    Country, Region, VisitedRegion, City, VisitedCity, TravelProfile,
    ProfileCountryVisit, ProfileRegionVisit, Trip,
)
from rest_framework import serializers
from main.utils import CustomModelSerializer


class CountrySerializer(serializers.ModelSerializer):
    def get_public_url(self, obj):
        return os.environ.get('PUBLIC_URL', 'http://127.0.0.1:8000').rstrip('/').replace("'", "")

    flag_url = serializers.SerializerMethodField()
    num_regions = serializers.SerializerMethodField()
    num_visits = serializers.SerializerMethodField()
    profile_ids = serializers.SerializerMethodField()

    def get_flag_url(self, obj):
        public_url = self.get_public_url(obj)
        return public_url + '/media/' + 'flags/' + obj.country_code.lower() + '.png'
    
    def get_num_regions(self, obj):
        # get the number of regions in the country
        return Region.objects.filter(country=obj).count()
    
    def get_num_visits(self, obj):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        
        if user and user.is_authenticated:
            return VisitedRegion.objects.filter(region__country=obj, user=user).count()
        
        return 0

    def get_profile_ids(self, obj):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return []

        profile_country_map = self.context.get('profile_country_map')
        if profile_country_map is not None:
            return [str(value) for value in profile_country_map.get(obj.id, set())]

        accessible = Q(profile__owner=user) | Q(profile__shared_with=user)
        manual_ids = ProfileCountryVisit.objects.filter(accessible, country=obj).values_list('profile_id', flat=True)
        region_ids = ProfileRegionVisit.objects.filter(
            accessible, region__country=obj
        ).values_list('profile_id', flat=True)
        from adventures.models import Location
        adventure_ids = Location.objects.filter(
            Q(user=user) | Q(profiles__shared_with=user), country=obj, visits__isnull=False
        ).values_list('profiles__id', flat=True)
        return [str(value) for value in set(manual_ids) | set(region_ids) | set(adventure_ids) if value]

    class Meta:
        model = Country
        fields = '__all__'
        read_only_fields = ['id', 'name', 'country_code', 'subregion', 'flag_url', 'num_regions', 'num_visits', 'longitude', 'latitude', 'capital']


class RegionSerializer(serializers.ModelSerializer):
    num_cities = serializers.SerializerMethodField()
    country_name = serializers.CharField(source='country.name', read_only=True)
    profile_ids = serializers.SerializerMethodField()
    class Meta:
        model = Region
        fields = '__all__'
        read_only_fields = ['id', 'name', 'country', 'longitude', 'latitude', 'num_cities', 'country_name']

    def get_num_cities(self, obj):
        annotated_count = getattr(obj, '_num_cities', None)
        return annotated_count if annotated_count is not None else City.objects.filter(region=obj).count()

    def get_profile_ids(self, obj):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return []
        profile_region_map = self.context.get('profile_region_map')
        if profile_region_map is not None:
            return [str(value) for value in profile_region_map.get(obj.id, set())]
        manual_ids = ProfileRegionVisit.objects.filter(
            Q(profile__owner=user) | Q(profile__shared_with=user), region=obj
        ).values_list('profile_id', flat=True)
        from adventures.models import Location
        adventure_ids = Location.objects.filter(
            Q(user=user) | Q(profiles__shared_with=user), region=obj, visits__isnull=False
        ).values_list('profiles__id', flat=True)
        return [str(value) for value in set(manual_ids) | set(adventure_ids) if value]


class TravelProfileSerializer(serializers.ModelSerializer):
    visited_countries = serializers.SerializerMethodField()
    visited_regions = serializers.SerializerMethodField()
    shared_with = serializers.SlugRelatedField(many=True, read_only=True, slug_field='username')

    class Meta:
        model = TravelProfile
        fields = ['id', 'name', 'color', 'avatar', 'linked_user', 'is_default', 'visited_countries', 'visited_regions', 'shared_with']
        read_only_fields = ['id', 'linked_user', 'is_default', 'visited_countries', 'visited_regions']

    def get_visited_countries(self, obj):
        return obj.country_visits.count()

    def get_visited_regions(self, obj):
        return obj.region_visits.count()


class TripSerializer(serializers.ModelSerializer):
    profiles = serializers.PrimaryKeyRelatedField(many=True, queryset=TravelProfile.objects.none())
    profile_details = TravelProfileSerializer(source='profiles', many=True, read_only=True)

    class Meta:
        model = Trip
        fields = ['id', 'title', 'start_date', 'end_date', 'notes', 'profiles', 'profile_details', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            self.fields['profiles'].child_relation.queryset = TravelProfile.objects.filter(
                Q(owner=request.user) | Q(shared_with=request.user)
            ).distinct()

    def validate(self, attrs):
        start = attrs.get('start_date', getattr(self.instance, 'start_date', None))
        end = attrs.get('end_date', getattr(self.instance, 'end_date', None))
        if start and end and end < start:
            raise serializers.ValidationError({'end_date': 'End date must be on or after the start date.'})
        if not attrs.get('profiles') and not self.instance:
            raise serializers.ValidationError({'profiles': 'Choose at least one profile.'})
        return attrs

class CitySerializer(serializers.ModelSerializer):
    region_name = serializers.CharField(source='region.name', read_only=True)
    country_name = serializers.CharField(source='region.country.name', read_only=True
    )
    class Meta:
        model = City
        fields = '__all__'
        read_only_fields = ['id', 'name', 'region', 'longitude', 'latitude', 'region_name', 'country_name']

class VisitedRegionSerializer(CustomModelSerializer):
    longitude = serializers.DecimalField(source='region.longitude', max_digits=9, decimal_places=6, read_only=True)
    latitude = serializers.DecimalField(source='region.latitude', max_digits=9, decimal_places=6, read_only=True)
    name = serializers.CharField(source='region.name', read_only=True)

    class Meta:
        model = VisitedRegion
        fields = ['id', 'user', 'region', 'longitude', 'latitude', 'name']
        read_only_fields = ['user', 'id', 'longitude', 'latitude', 'name']

class VisitedCitySerializer(CustomModelSerializer):
    longitude = serializers.DecimalField(source='city.longitude', max_digits=9, decimal_places=6, read_only=True)
    latitude = serializers.DecimalField(source='city.latitude', max_digits=9, decimal_places=6, read_only=True)
    name = serializers.CharField(source='city.name', read_only=True)

    class Meta:
        model = VisitedCity
        fields = ['id', 'user', 'city', 'longitude', 'latitude', 'name']
        read_only_fields = ['user', 'id', 'longitude', 'latitude', 'name']
