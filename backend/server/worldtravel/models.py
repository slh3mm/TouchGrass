from django.db import models
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
import uuid
from django.contrib.gis.db import models as gis_models


User = get_user_model()

default_user = 1  # Replace with an actual user ID


class TravelProfile(models.Model):
    """A household member whose calendar and travel data can be color coded."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='travel_profiles')
    name = models.CharField(max_length=80)
    color = models.CharField(
        max_length=7,
        default='#4A90E2',
        validators=[RegexValidator(r'^#[0-9A-Fa-f]{6}$', 'Use a six-digit hex color.')],
    )
    avatar = models.CharField(max_length=8, blank=True, default='')
    linked_user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='linked_travel_profiles'
    )
    shared_with = models.ManyToManyField(User, blank=True, related_name='shared_travel_profiles')
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'name']
        constraints = [
            models.UniqueConstraint(fields=['owner', 'name'], name='unique_travel_profile_name'),
        ]

    def __str__(self):
        return self.name

class Country(models.Model):

    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    country_code = models.CharField(max_length=2, unique=True) #iso2 code
    subregion = models.CharField(max_length=100, blank=True, null=True)
    capital = models.CharField(max_length=100, blank=True, null=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    class Meta:
        verbose_name = "Country"
        verbose_name_plural = "Countries"

    def __str__(self):
        return self.name

class Region(models.Model):
    id = models.CharField(primary_key=True)
    name = models.CharField(max_length=100)
    country = models.ForeignKey(Country, on_delete=models.CASCADE)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    def __str__(self):
        return self.name
    
class City(models.Model):
    id = models.CharField(primary_key=True)
    name = models.CharField(max_length=100)
    region = models.ForeignKey(Region, on_delete=models.CASCADE)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    class Meta:
        verbose_name_plural = "Cities"

    def __str__(self):
        return self.name

class VisitedRegion(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, default=default_user)
    region = models.ForeignKey(Region, on_delete=models.CASCADE)

    def __str__(self):
        return f'{self.region.name} ({self.region.country.country_code}) visited by: {self.user.username}'
    
    def save(self, *args, **kwargs):
        if VisitedRegion.objects.filter(user=self.user, region=self.region).exists():
            raise ValidationError("Region already visited by user.")
        super().save(*args, **kwargs)

class VisitedCity(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, default=default_user)
    city = models.ForeignKey(City, on_delete=models.CASCADE)

    def __str__(self):
        return f'{self.city.name} ({self.city.region.name}) visited by: {self.user.username}'
    
    def save(self, *args, **kwargs):
        if VisitedCity.objects.filter(user=self.user, city=self.city).exists():
            raise ValidationError("City already visited by user.")
        super().save(*args, **kwargs)

    class Meta:
        verbose_name_plural = "Visited Cities"


class ProfileCountryVisit(models.Model):
    profile = models.ForeignKey(TravelProfile, on_delete=models.CASCADE, related_name='country_visits')
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name='profile_visits')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['profile', 'country'], name='unique_profile_country_visit'),
        ]


class ProfileRegionVisit(models.Model):
    profile = models.ForeignKey(TravelProfile, on_delete=models.CASCADE, related_name='region_visits')
    region = models.ForeignKey(Region, on_delete=models.CASCADE, related_name='profile_visits')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['profile', 'region'], name='unique_profile_region_visit'),
        ]


class ProfileTravelVisit(models.Model):
    """A dated visit to a country or one of its states/provinces."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(
        TravelProfile, on_delete=models.CASCADE, related_name='travel_visit_history'
    )
    country = models.ForeignKey(
        Country, on_delete=models.CASCADE, related_name='profile_visit_history'
    )
    region = models.ForeignKey(
        Region, on_delete=models.CASCADE, related_name='profile_visit_history',
        null=True, blank=True,
    )
    visit_date = models.DateField()
    end_date = models.DateField()
    notes = models.CharField(max_length=500, blank=True, default='')
    place_visit = models.ForeignKey(
        'adventures.Visit', on_delete=models.CASCADE, null=True, blank=True, related_name='passport_visits'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-visit_date', '-created_at']
        indexes = [
            models.Index(fields=['country', 'region', 'visit_date'], name='travel_visit_place_date'),
            models.Index(fields=['profile', 'visit_date'], name='travel_visit_profile_date'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['profile', 'place_visit'],
                condition=models.Q(place_visit__isnull=False),
                name='unique_profile_place_visit',
            )
        ]

    def clean(self):
        if self.region_id and self.region.country_id != self.country_id:
            raise ValidationError('The selected region does not belong to this country.')

    def __str__(self):
        place = self.region.name if self.region_id else self.country.name
        return f'{self.profile.name} visited {place} on {self.visit_date}'


class Trip(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='trips')
    collection = models.OneToOneField(
        'adventures.Collection',
        on_delete=models.CASCADE,
        related_name='touchgrass_trip',
    )
    title = models.CharField(max_length=160)
    start_date = models.DateField()
    end_date = models.DateField()
    notes = models.TextField(blank=True, default='')
    profiles = models.ManyToManyField(TravelProfile, related_name='trips')
    source_review = models.OneToOneField(
        'SkylightEventReview',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='materialized_trip',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_date', '-created_at']

    def clean(self):
        if self.end_date < self.start_date:
            raise ValidationError('End date must be on or after the start date.')

    def __str__(self):
        return self.title


class TripDestination(models.Model):
    """A country or subdivision intentionally attached to a TouchGrass trip."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name='destinations')
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name='trip_destinations')
    region = models.ForeignKey(
        Region,
        on_delete=models.CASCADE,
        related_name='trip_destinations',
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['country__name', 'region__name']
        constraints = [
            models.UniqueConstraint(
                fields=['trip', 'country'],
                condition=models.Q(region__isnull=True),
                name='unique_trip_country_destination',
            ),
            models.UniqueConstraint(
                fields=['trip', 'region'],
                condition=models.Q(region__isnull=False),
                name='unique_trip_region_destination',
            ),
        ]

    def clean(self):
        if self.region_id and self.region.country_id != self.country_id:
            raise ValidationError('The selected region does not belong to this country.')

    def __str__(self):
        return self.region.name if self.region_id else self.country.name


class SkylightConnection(models.Model):
    """A user's Skylight OAuth connection.

    ``encrypted_credentials`` contains an authenticated-encryption envelope;
    access and refresh tokens are never stored as plaintext database columns.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='skylight_connection'
    )
    encrypted_credentials = models.TextField(blank=True, default='')
    frame_id = models.CharField(max_length=80, blank=True, default='')
    frame_name = models.CharField(max_length=160, blank=True, default='')
    timezone = models.CharField(max_length=64, blank=True, default='UTC')
    oauth_state_digest = models.CharField(max_length=64, blank=True, default='')
    oauth_state_expires_at = models.DateTimeField(null=True, blank=True)
    connected_at = models.DateTimeField(null=True, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_sync_error = models.CharField(max_length=500, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_connected(self):
        return bool(self.encrypted_credentials and self.frame_id)

    def __str__(self):
        return f'Skylight connection for {self.owner}'


class SkylightProfileMapping(models.Model):
    """Maps a Skylight category/family member to a TouchGrass profile."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    connection = models.ForeignKey(
        SkylightConnection, on_delete=models.CASCADE, related_name='profile_mappings'
    )
    skylight_category_id = models.CharField(max_length=80)
    skylight_category_name = models.CharField(max_length=160)
    manually_assigned = models.BooleanField(default=False)
    profile = models.ForeignKey(
        TravelProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='skylight_mappings',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['skylight_category_name']
        constraints = [
            models.UniqueConstraint(
                fields=['connection', 'skylight_category_id'],
                name='unique_skylight_category_mapping',
            ),
        ]

    def __str__(self):
        target = self.profile.name if self.profile_id else 'unmapped'
        return f'{self.skylight_category_name} -> {target}'


class SkylightEventReview(models.Model):
    """A persistent human label for a raw Skylight calendar event.

    Calendar metadata and classifier output are refreshed from Skylight. The
    human label and reviewer note are intentionally separate fields so a sync
    can never overwrite the ground truth supplied in TouchGrass.
    """

    class Label(models.TextChoices):
        UNREVIEWED = 'unreviewed', 'Unreviewed'
        TRIP = 'trip', 'Trip'
        NOT_TRIP = 'not_trip', 'Not a trip'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    connection = models.ForeignKey(
        SkylightConnection, on_delete=models.CASCADE, related_name='event_reviews'
    )
    skylight_event_id = models.CharField(max_length=100)
    skylight_event_uid = models.CharField(max_length=255, blank=True, default='')
    title = models.CharField(max_length=200)
    start_date = models.DateField()
    end_date = models.DateField()
    all_day = models.BooleanField(default=False)
    calendar_description = models.TextField(blank=True, default='')
    location = models.CharField(max_length=500, blank=True, default='')
    category_ids = models.JSONField(default=list, blank=True)
    profiles = models.ManyToManyField(
        TravelProfile, related_name='skylight_event_reviews', blank=True
    )
    predicted_is_trip = models.BooleanField(default=False)
    detection_score = models.SmallIntegerField(default=0)
    detection_reasons = models.JSONField(default=list, blank=True)
    human_label = models.CharField(
        max_length=16, choices=Label.choices, default=Label.UNREVIEWED
    )
    reviewer_note = models.TextField(blank=True, default='')
    destination_country = models.ForeignKey(
        Country,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='skylight_trip_reviews',
    )
    destination_region = models.ForeignKey(
        Region,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='skylight_trip_reviews',
    )
    destination_label = models.CharField(max_length=200, blank=True, default='')
    destination_resolution = models.CharField(max_length=16, blank=True, default='')
    last_seen_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_date', 'title']
        constraints = [
            models.UniqueConstraint(
                fields=['connection', 'skylight_event_id'],
                name='unique_skylight_event_review',
            ),
        ]
        indexes = [
            models.Index(
                fields=['connection', 'human_label', 'start_date'],
                name='skylight_review_label_date',
            ),
        ]

    def __str__(self):
        return f'{self.title} ({self.start_date})'

    def clean(self):
        if (
            self.destination_region_id
            and self.destination_country_id
            and self.destination_region.country_id != self.destination_country_id
        ):
            raise ValidationError('The trip destination region does not belong to its country.')


class SkylightTripSuggestion(models.Model):
    """A reviewable trip candidate imported from a Skylight event."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending review'
        ACCEPTED = 'accepted', 'Accepted'
        DISMISSED = 'dismissed', 'Dismissed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    connection = models.ForeignKey(
        SkylightConnection, on_delete=models.CASCADE, related_name='trip_suggestions'
    )
    skylight_event_id = models.CharField(max_length=100)
    skylight_event_uid = models.CharField(max_length=255, blank=True, default='')
    title = models.CharField(max_length=200)
    start_date = models.DateField()
    end_date = models.DateField()
    notes = models.TextField(blank=True, default='')
    location = models.CharField(max_length=500, blank=True, default='')
    category_ids = models.JSONField(default=list, blank=True)
    detection_score = models.SmallIntegerField(default=0)
    detection_reasons = models.JSONField(default=list, blank=True)
    profiles = models.ManyToManyField(TravelProfile, related_name='skylight_trip_suggestions')
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    trip = models.ForeignKey(
        Trip,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='skylight_suggestions',
    )
    last_seen_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['start_date', 'title']
        constraints = [
            models.UniqueConstraint(
                fields=['connection', 'skylight_event_id'],
                name='unique_skylight_trip_suggestion',
            ),
        ]
        indexes = [
            models.Index(
                fields=['connection', 'status', 'start_date'],
                name='skylight_suggest_status_date',
            ),
        ]

    def __str__(self):
        return f'{self.title} ({self.start_date} - {self.end_date})'


class BallparkVisit(models.Model):
    """A profile's persistent MLB ballpark passport entry."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(
        TravelProfile, on_delete=models.CASCADE, related_name='ballpark_visits'
    )
    ballpark_id = models.CharField(max_length=16)
    first_visit_date = models.DateField(null=True, blank=True)
    last_visit_date = models.DateField(null=True, blank=True)
    visit_count = models.PositiveIntegerField(default=1)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['ballpark_id', 'profile__name']
        constraints = [
            models.UniqueConstraint(
                fields=['profile', 'ballpark_id'], name='unique_profile_ballpark_visit'
            ),
        ]

    def clean(self):
        if (
            self.first_visit_date
            and self.last_visit_date
            and self.last_visit_date < self.first_visit_date
        ):
            raise ValidationError('Last visit must be on or after the first visit.')

    def __str__(self):
        return f'{self.ballpark_id} visited by {self.profile.name}'
