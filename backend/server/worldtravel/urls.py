# travel/urls.py

from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import CountryViewSet, RegionViewSet, VisitedRegionViewSet, TravelProfileViewSet, TripViewSet, regions_by_country, visits_by_country, cities_by_region, VisitedCityViewSet, visits_by_region, globespin, profile_country_visit, profile_region_visit, profile_region_map
router = DefaultRouter()
router.register(r'countries', CountryViewSet, basename='countries')
router.register(r'regions', RegionViewSet, basename='regions')
router.register(r'visitedregion', VisitedRegionViewSet, basename='visitedregion')
router.register(r'visitedcity', VisitedCityViewSet, basename='visitedcity')
router.register(r'travel-profiles', TravelProfileViewSet, basename='travel-profiles')
router.register(r'trips', TripViewSet, basename='trips')

urlpatterns = [
    path('', include(router.urls)),
    path('<str:country_code>/regions/', regions_by_country, name='regions-by-country'),
    path('<str:country_code>/visits/', visits_by_country, name='visits-by-country'),
    path('regions/<str:region_id>/cities/', cities_by_region, name='cities-by-region'),
    path('regions/<str:region_id>/cities/visits/', visits_by_region, name='visits-by-region'),
    path('globespin/', globespin, name='globespin'),
    path('travel-profiles/<uuid:profile_id>/countries/<str:country_code>/', profile_country_visit, name='profile-country-visit'),
    path('travel-profiles/<uuid:profile_id>/regions/<str:region_id>/', profile_region_visit, name='profile-region-visit'),
    path('travel-region-map/', profile_region_map, name='profile-region-map'),
]
