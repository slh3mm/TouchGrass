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


class Trip(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='trips')
    title = models.CharField(max_length=160)
    start_date = models.DateField()
    end_date = models.DateField()
    notes = models.TextField(blank=True, default='')
    profiles = models.ManyToManyField(TravelProfile, related_name='trips')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_date', '-created_at']

    def clean(self):
        if self.end_date < self.start_date:
            raise ValidationError('End date must be on or after the start date.')

    def __str__(self):
        return self.title
