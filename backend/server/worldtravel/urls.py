# travel/urls.py

from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import CountryViewSet, RegionViewSet, VisitedRegionViewSet, TravelProfileViewSet, ProfileTravelVisitViewSet, TripViewSet, BallparkVisitViewSet, regions_by_country, visits_by_country, cities_by_region, VisitedCityViewSet, visits_by_region, globespin, profile_country_visit, profile_region_visit, profile_region_map, skylight_status, skylight_connect, skylight_login, skylight_complete, skylight_sync, skylight_event_reviews, skylight_event_review, skylight_event_reviews_refresh, skylight_mapping, skylight_suggestion_accept, skylight_suggestion_dismiss, skylight_disconnect
router = DefaultRouter()
router.register(r'countries', CountryViewSet, basename='countries')
router.register(r'regions', RegionViewSet, basename='regions')
router.register(r'visitedregion', VisitedRegionViewSet, basename='visitedregion')
router.register(r'visitedcity', VisitedCityViewSet, basename='visitedcity')
router.register(r'travel-profiles', TravelProfileViewSet, basename='travel-profiles')
router.register(r'travel-visit-history', ProfileTravelVisitViewSet, basename='travel-visit-history')
router.register(r'trips', TripViewSet, basename='trips')
router.register(r'ballpark-visits', BallparkVisitViewSet, basename='ballpark-visits')

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
    path('skylight/', skylight_status, name='skylight-status'),
    path('skylight/connect/', skylight_connect, name='skylight-connect'),
    path('skylight/login/', skylight_login, name='skylight-login'),
    path('skylight/complete/', skylight_complete, name='skylight-complete'),
    path('skylight/sync/', skylight_sync, name='skylight-sync'),
    path('skylight/events/', skylight_event_reviews, name='skylight-event-reviews'),
    path('skylight/events/refresh/', skylight_event_reviews_refresh, name='skylight-event-reviews-refresh'),
    path('skylight/events/<uuid:review_id>/', skylight_event_review, name='skylight-event-review'),
    path('skylight/mappings/<uuid:mapping_id>/', skylight_mapping, name='skylight-mapping'),
    path('skylight/suggestions/<uuid:suggestion_id>/accept/', skylight_suggestion_accept, name='skylight-suggestion-accept'),
    path('skylight/suggestions/<uuid:suggestion_id>/dismiss/', skylight_suggestion_dismiss, name='skylight-suggestion-dismiss'),
    path('skylight/disconnect/', skylight_disconnect, name='skylight-disconnect'),
]
