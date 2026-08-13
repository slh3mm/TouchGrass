import os
from django.db import transaction
from django.db.models import Q
from .models import (
    Country, Region, VisitedRegion, City, VisitedCity, TravelProfile,
    ProfileCountryVisit, ProfileRegionVisit, ProfileTravelVisit, Trip, BallparkVisit,
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
        # Flags ship with the frontend so the 250-card atlas never fans out
        # through Django, session authentication, or the SvelteKit proxy.
        return '/flags/' + obj.country_code.lower() + '.png'
    
    def get_num_regions(self, obj):
        annotated_count = getattr(obj, '_num_regions', None)
        return annotated_count if annotated_count is not None else Region.objects.filter(country=obj).count()
    
    def get_num_visits(self, obj):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        
        if user and user.is_authenticated:
            visit_count_map = self.context.get('visit_count_map')
            if visit_count_map is not None:
                return visit_count_map.get(obj.id, 0)
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


class ProfileTravelVisitSerializer(serializers.ModelSerializer):
    profile_name = serializers.CharField(source='profile.name', read_only=True)
    profile_color = serializers.CharField(source='profile.color', read_only=True)
    profile_avatar = serializers.CharField(source='profile.avatar', read_only=True)
    country_code = serializers.CharField(source='country.country_code', read_only=True)
    country_name = serializers.CharField(source='country.name', read_only=True)
    region_name = serializers.CharField(source='region.name', read_only=True, allow_null=True)

    class Meta:
        model = ProfileTravelVisit
        fields = [
            'id', 'profile', 'profile_name', 'profile_color', 'profile_avatar',
            'country', 'country_code', 'country_name', 'region', 'region_name',
            'visit_date', 'notes', 'created_at',
        ]
        read_only_fields = [
            'id', 'profile_name', 'profile_color', 'profile_avatar', 'country_code',
            'country_name', 'region_name', 'created_at',
        ]

    def validate_profile(self, profile):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError('Authentication is required.')
        if not (
            profile.owner_id == request.user.id
            or profile.shared_with.filter(id=request.user.id).exists()
        ):
            raise serializers.ValidationError('This profile is not available to you.')
        return profile

    def validate(self, attrs):
        country = attrs.get('country', getattr(self.instance, 'country', None))
        region = attrs.get('region', getattr(self.instance, 'region', None))
        if region and country and region.country_id != country.id:
            raise serializers.ValidationError(
                {'region': 'The selected state or province does not belong to this country.'}
            )
        return attrs


class TripSerializer(serializers.ModelSerializer):
    profiles = serializers.PrimaryKeyRelatedField(many=True, queryset=TravelProfile.objects.none())
    profile_details = TravelProfileSerializer(source='profiles', many=True, read_only=True)
    planner_id = serializers.UUIDField(source='collection_id', read_only=True)
    planner_url = serializers.SerializerMethodField()

    class Meta:
        model = Trip
        fields = [
            'id', 'title', 'start_date', 'end_date', 'notes', 'profiles',
            'profile_details', 'planner_id', 'planner_url', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'planner_id', 'planner_url', 'created_at', 'updated_at']

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

    def get_planner_url(self, obj):
        return f'/collections/{obj.collection_id}'

    def share_planner_with_profile_users(self, collection, profiles):
        collaborator_ids = set()
        for profile in profiles:
            collaborator_ids.add(profile.owner_id)
            if profile.linked_user_id:
                collaborator_ids.add(profile.linked_user_id)
            collaborator_ids.update(profile.shared_with.values_list('id', flat=True))
        collaborator_ids.discard(collection.user_id)
        if collaborator_ids:
            collection.shared_with.add(*collaborator_ids)

    @transaction.atomic
    def create(self, validated_data):
        from adventures.models import Collection

        profiles = validated_data.pop('profiles', [])
        owner = validated_data['owner']
        collection = Collection.objects.create(
            user=owner,
            name=validated_data['title'],
            description=validated_data.get('notes') or '',
            start_date=validated_data['start_date'],
            end_date=validated_data['end_date'],
        )
        trip = Trip.objects.create(collection=collection, **validated_data)
        trip.profiles.set(profiles)
        self.share_planner_with_profile_users(collection, profiles)
        return trip

    @transaction.atomic
    def update(self, instance, validated_data):
        profiles = validated_data.pop('profiles', None)
        instance = super().update(instance, validated_data)
        if profiles is not None:
            instance.profiles.set(profiles)

        collection = instance.collection
        collection.name = instance.title
        collection.description = instance.notes
        collection.start_date = instance.start_date
        collection.end_date = instance.end_date
        collection.save(update_fields=['name', 'description', 'start_date', 'end_date', 'updated_at'])
        self.share_planner_with_profile_users(collection, instance.profiles.all())
        return instance

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        collection = getattr(instance, 'collection', None)
        if collection:
            start_date = collection.start_date or instance.start_date
            end_date = collection.end_date or instance.end_date
            representation.update({
                'title': collection.name,
                'notes': collection.description or '',
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
            })
        return representation


class BallparkVisitSerializer(serializers.ModelSerializer):
    profile_detail = TravelProfileSerializer(source='profile', read_only=True)

    class Meta:
        model = BallparkVisit
        fields = [
            'id', 'profile', 'profile_detail', 'ballpark_id', 'first_visit_date',
            'last_visit_date', 'visit_count', 'notes', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_profile(self, profile):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError('Authentication is required.')
        if not (
            profile.owner_id == request.user.id
            or profile.shared_with.filter(id=request.user.id).exists()
        ):
            raise serializers.ValidationError('This profile is not available to you.')
        return profile

    def validate_ballpark_id(self, value):
        normalized = value.strip().upper()
        if not normalized or len(normalized) > 16:
            raise serializers.ValidationError('Choose a valid ballpark.')
        return normalized

    def validate(self, attrs):
        first = attrs.get('first_visit_date', getattr(self.instance, 'first_visit_date', None))
        last = attrs.get('last_visit_date', getattr(self.instance, 'last_visit_date', None))
        if first and last and last < first:
            raise serializers.ValidationError(
                {'last_visit_date': 'Last visit must be on or after the first visit.'}
            )
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
