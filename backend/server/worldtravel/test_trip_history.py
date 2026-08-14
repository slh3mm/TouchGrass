from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from .models import (
    Country,
    Region,
    SkylightConnection,
    SkylightEventReview,
    TravelProfile,
)
from .trip_history import ensure_trip_destinations, resolve_review_destination


class SkylightTripHistoryTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='trip-history-user', password='test-password'
        )
        self.joint = TravelProfile.objects.create(
            owner=self.user, name='Joint', color='#43D39E', is_default=True
        )
        self.ashley = TravelProfile.objects.create(
            owner=self.user, name='Ashley', color='#EE86AC'
        )
        self.connection = SkylightConnection.objects.create(owner=self.user)
        self.us = Country.objects.create(name='United States', country_code='US')
        self.canada = Country.objects.create(name='Canada', country_code='CA')
        self.aruba = Country.objects.create(name='Aruba', country_code='AW')
        self.pa = Region.objects.create(id='US-PA', name='Pennsylvania', country=self.us)
        self.md = Region.objects.create(id='US-MD', name='Maryland', country=self.us)
        self.ma = Region.objects.create(id='US-MA', name='Massachusetts', country=self.us)
        self.wv = Region.objects.create(id='US-WV', name='West Virginia', country=self.us)
        self.on = Region.objects.create(id='CA-ON', name='Ontario', country=self.canada)
        self.client.force_login(self.user)

    def review(self, title, *, start_date=None, note='', profile=None):
        start_date = start_date or timezone.localdate() - timedelta(days=2)
        review = SkylightEventReview.objects.create(
            connection=self.connection,
            skylight_event_id=f'event-{SkylightEventReview.objects.count()}',
            title=title,
            start_date=start_date,
            end_date=start_date + timedelta(days=1),
            human_label=SkylightEventReview.Label.TRIP,
            reviewer_note=note,
        )
        review.profiles.add(profile or self.joint)
        return review

    def test_resolves_informal_place_and_explicit_state_without_trip_title_rules(self):
        philly = self.review('Weekend in Philly')
        cabin = self.review(
            'Cabin Trip',
            note='Destination for this event: Harpers Ferry, MD.',
            profile=self.ashley,
        )

        resolve_review_destination(philly)
        resolve_review_destination(cabin)
        philly.refresh_from_db()
        cabin.refresh_from_db()

        self.assertEqual(philly.destination_region_id, 'US-PA')
        # Explicit calendar metadata wins over the reusable Harpers Ferry alias.
        self.assertEqual(cabin.destination_region_id, 'US-MD')

    def test_completed_confirmed_trip_augments_country_region_and_history_apis(self):
        review = self.review('Weekend in Philly')
        ensure_trip_destinations(self.user)

        country_response = self.client.get('/api/countries/?format=json')
        self.assertEqual(country_response.status_code, 200)
        us_payload = next(
            country for country in country_response.json() if country['country_code'] == 'US'
        )
        self.assertIn(str(self.joint.id), us_payload['profile_ids'])

        map_response = self.client.get('/api/travel-region-map/?format=json')
        self.assertEqual(map_response.status_code, 200)
        pa_payload = next(region for region in map_response.json() if region['id'] == 'US-PA')
        self.assertIn(str(self.joint.id), pa_payload['profile_ids'])

        history_response = self.client.get('/api/travel-visit-history/?country=US&format=json')
        self.assertEqual(history_response.status_code, 200)
        self.assertEqual(len(history_response.json()), 1)
        history = history_response.json()[0]
        self.assertEqual(history['source'], 'skylight')
        self.assertEqual(history['source_title'], review.title)
        self.assertEqual(history['region'], 'US-PA')
        self.assertTrue(history['read_only'])

    def test_future_trip_is_resolved_but_does_not_fill_map_or_history_yet(self):
        review = self.review(
            'Toronto!',
            start_date=timezone.localdate() + timedelta(days=2),
            profile=self.ashley,
        )
        ensure_trip_destinations(self.user)
        review.refresh_from_db()
        self.assertEqual(review.destination_region_id, 'CA-ON')

        map_response = self.client.get('/api/travel-region-map/?format=json')
        self.assertFalse(any(region['id'] == 'CA-ON' for region in map_response.json()))
        history_response = self.client.get('/api/travel-visit-history/?country=CA&format=json')
        self.assertEqual(history_response.json(), [])

    def test_country_only_trip_is_visible_in_country_history(self):
        self.review('Aruba')
        ensure_trip_destinations(self.user)
        response = self.client.get('/api/travel-visit-history/?country=AW&format=json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]['country_code'], 'AW')
        self.assertIsNone(response.json()[0]['region'])

    def test_joint_masks_individual_map_color_but_preserves_every_trip_in_history(self):
        self.review('Boston!', profile=self.joint)
        self.review('Ariana in Boston', profile=self.ashley)
        ensure_trip_destinations(self.user)

        country_response = self.client.get('/api/countries/?format=json')
        us_payload = next(
            country for country in country_response.json() if country['country_code'] == 'US'
        )
        self.assertEqual(us_payload['profile_ids'], [str(self.joint.id)])

        map_response = self.client.get('/api/travel-region-map/?format=json')
        ma_payload = next(region for region in map_response.json() if region['id'] == 'US-MA')
        self.assertEqual(ma_payload['profile_ids'], [str(self.joint.id)])

        history_response = self.client.get(
            '/api/travel-visit-history/?country=US&region=US-MA&format=json'
        )
        history = history_response.json()
        self.assertEqual(
            {entry['source_title'] for entry in history},
            {'Boston!', 'Ariana in Boston'},
        )
        self.assertEqual(
            {entry['profile_name'] for entry in history},
            {'Joint', 'Ashley'},
        )
