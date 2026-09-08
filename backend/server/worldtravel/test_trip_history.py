from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from .models import (
    Country,
    ProfileCountryVisit,
    ProfileRegionVisit,
    Region,
    SkylightConnection,
    SkylightEventReview,
    SkylightTripSuggestion,
    Trip,
    TripDestination,
    TravelProfile,
)
from adventures.models import Collection
from .trip_history import (
    ensure_trip_destinations,
    reconcile_skylight_reviews_into_trips,
    resolve_review_destination,
)


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
        self.spencer = TravelProfile.objects.create(
            owner=self.user, name='Spencer', color='#F7C948'
        )
        self.connection = SkylightConnection.objects.create(owner=self.user)
        self.us = Country.objects.create(name='United States', country_code='US')
        self.canada = Country.objects.create(name='Canada', country_code='CA')
        self.aruba = Country.objects.create(name='Aruba', country_code='AW')
        self.pa = Region.objects.create(id='US-PA', name='Pennsylvania', country=self.us)
        self.md = Region.objects.create(id='US-MD', name='Maryland', country=self.us)
        self.ma = Region.objects.create(id='US-MA', name='Massachusetts', country=self.us)
        self.wv = Region.objects.create(id='US-WV', name='West Virginia', country=self.us)
        self.ny = Region.objects.create(id='US-NY', name='New York', country=self.us)
        self.ca = Region.objects.create(id='US-CA', name='California', country=self.us)
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

    def test_household_stats_use_profile_visits_and_completed_skylight_trips(self):
        ProfileCountryVisit.objects.create(profile=self.joint, country=self.aruba)
        ProfileRegionVisit.objects.create(profile=self.ashley, region=self.pa)
        self.review('Boston!', profile=self.joint)

        response = self.client.get('/api/travel-stats/?format=json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['visited_country_count'], 2)
        self.assertEqual(response.json()['visited_region_count'], 2)
        self.assertEqual(response.json()['visited_city_count'], 0)

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

    def test_independent_california_visits_do_not_infer_joint_or_show_other_us_history(self):
        ProfileRegionVisit.objects.create(profile=self.spencer, region=self.ca)
        ProfileRegionVisit.objects.create(profile=self.ashley, region=self.ca)
        self.review('Weekend in Philly', profile=self.joint)

        map_response = self.client.get('/api/travel-region-map/?format=json')
        self.assertEqual(map_response.status_code, 200)
        ca_payload = next(region for region in map_response.json() if region['id'] == 'US-CA')
        self.assertEqual(
            set(ca_payload['profile_ids']),
            {str(self.spencer.id), str(self.ashley.id)},
        )
        self.assertNotIn(str(self.joint.id), ca_payload['profile_ids'])

        history_response = self.client.get(
            '/api/travel-visit-history/?country=US&region=US-CA&format=json'
        )
        self.assertEqual(history_response.status_code, 200)
        self.assertEqual(history_response.json(), [])

    def test_manual_visit_history_accepts_and_returns_a_date_range(self):
        start_date = timezone.localdate() - timedelta(days=5)
        end_date = start_date + timedelta(days=3)
        response = self.client.post(
            '/api/travel-visit-history/?format=json',
            {
                'profile': str(self.joint.id),
                'country': self.us.id,
                'region': self.ma.id,
                'visit_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'notes': 'Long weekend',
            },
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['end_date'], end_date.isoformat())

        history_response = self.client.get(
            '/api/travel-visit-history/?country=US&region=US-MA&format=json'
        )
        self.assertEqual(history_response.status_code, 200)
        self.assertEqual(history_response.json()[0]['end_date'], end_date.isoformat())

    def test_existing_trip_hides_matching_skylight_suggestion(self):
        start_date = timezone.localdate() + timedelta(days=10)
        collection = Collection.objects.create(
            user=self.user,
            name='Boston!',
            start_date=start_date,
            end_date=start_date + timedelta(days=2),
        )
        trip = Trip.objects.create(
            owner=self.user,
            collection=collection,
            title='Boston!',
            start_date=start_date,
            end_date=start_date + timedelta(days=2),
        )
        trip.profiles.add(self.joint)
        suggestion = SkylightTripSuggestion.objects.create(
            connection=self.connection,
            skylight_event_id='boston-existing-trip',
            title='Boston',
            start_date=start_date,
            end_date=start_date + timedelta(days=1),
        )
        suggestion.profiles.add(self.joint)

        response = self.client.get('/api/skylight/?format=json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['suggestions'], [])
        suggestion.refresh_from_db()
        self.assertEqual(suggestion.status, SkylightTripSuggestion.Status.ACCEPTED)
        self.assertEqual(suggestion.trip_id, trip.id)

    def test_confirmed_review_materializes_one_trip_and_accepts_its_suggestion(self):
        review = self.review('Weekend in Philly')
        suggestion = SkylightTripSuggestion.objects.create(
            connection=self.connection,
            skylight_event_id=review.skylight_event_id,
            title=review.title,
            start_date=review.start_date,
            end_date=review.end_date,
        )
        suggestion.profiles.add(self.joint)

        first = reconcile_skylight_reviews_into_trips(self.connection)
        second = reconcile_skylight_reviews_into_trips(self.connection)

        self.assertEqual(first['created'], 1)
        self.assertEqual(second['created'], 0)
        self.assertEqual(Trip.objects.count(), 1)
        trip = Trip.objects.get()
        self.assertEqual(trip.source_review_id, review.id)
        self.assertEqual(trip.collection.name, review.title)
        self.assertEqual(list(trip.profiles.all()), [self.joint])
        destination = TripDestination.objects.get(trip=trip)
        self.assertEqual(destination.country_id, self.us.id)
        self.assertEqual(destination.region_id, self.pa.id)
        suggestion.refresh_from_db()
        self.assertEqual(suggestion.status, SkylightTripSuggestion.Status.ACCEPTED)
        self.assertEqual(suggestion.trip_id, trip.id)

    def test_reviewer_note_is_private_classifier_evidence_not_trip_copy(self):
        review = self.review(
            'YAR',
            note='YAR means young alumni reunion.',
        )
        review.calendar_description = 'Original calendar description'
        review.save(update_fields=['calendar_description', 'updated_at'])

        reconcile_skylight_reviews_into_trips(self.connection)

        trip = Trip.objects.get(source_review=review)
        self.assertEqual(trip.notes, 'Original calendar description')
        self.assertEqual(trip.collection.description, 'Original calendar description')
        review.refresh_from_db()
        self.assertEqual(review.reviewer_note, 'YAR means young alumni reunion.')

        history = self.client.get('/api/travel-visit-history/?country=US&region=US-VA&format=json')
        self.assertEqual(history.status_code, 200)
        self.assertNotIn('YAR means', str(history.json()))

    def test_existing_reviewer_note_copy_is_cleaned_without_touching_manual_notes(self):
        review = self.review('YAR', note='Private review explanation')
        collection = Collection.objects.create(
            user=self.user, name='YAR', description=review.reviewer_note,
            start_date=review.start_date, end_date=review.end_date,
        )
        generated = Trip.objects.create(
            owner=self.user, collection=collection, source_review=review,
            title='YAR', start_date=review.start_date, end_date=review.end_date,
            notes=review.reviewer_note,
        )
        generated.profiles.add(self.joint)
        manual_collection = Collection.objects.create(
            user=self.user, name='Manual', description='My own note',
            start_date=review.start_date, end_date=review.end_date,
        )
        manual = Trip.objects.create(
            owner=self.user, collection=manual_collection, title='Manual',
            start_date=review.start_date, end_date=review.end_date, notes='My own note',
        )
        manual.profiles.add(self.joint)

        reconcile_skylight_reviews_into_trips(self.connection)

        generated.refresh_from_db()
        manual.refresh_from_db()
        self.assertEqual(generated.notes, '')
        self.assertEqual(generated.collection.description, '')
        self.assertEqual(manual.notes, 'My own note')

    def test_exact_existing_trip_review_is_linked_and_gets_destination(self):
        start = timezone.localdate() + timedelta(days=30)
        review = SkylightEventReview.objects.create(
            connection=self.connection,
            skylight_event_id='existing-nyc',
            title='NYC Visit',
            start_date=start,
            end_date=start + timedelta(days=2),
        )
        review.profiles.add(self.joint)
        collection = Collection.objects.create(
            user=self.user, name='NYC Visit', start_date=start, end_date=start + timedelta(days=2),
        )
        trip = Trip.objects.create(
            owner=self.user, collection=collection, title='NYC Visit',
            start_date=start, end_date=start + timedelta(days=2),
        )
        trip.profiles.add(self.joint)

        result = reconcile_skylight_reviews_into_trips(self.connection)

        review.refresh_from_db()
        trip.refresh_from_db()
        self.assertEqual(result['repaired'], 1)
        self.assertEqual(review.human_label, SkylightEventReview.Label.TRIP)
        self.assertEqual(trip.source_review_id, review.id)
        self.assertEqual(TripDestination.objects.get(trip=trip).region_id, self.ny.id)

    def test_poconos_alias_resolves_to_pennsylvania(self):
        review = self.review('Poconos')
        resolve_review_destination(review)
        review.refresh_from_db()
        self.assertEqual(review.destination_region_id, self.pa.id)

    def test_not_trip_review_dismisses_its_pending_suggestion(self):
        start_date = timezone.localdate() - timedelta(days=3)
        review = SkylightEventReview.objects.create(
            connection=self.connection,
            skylight_event_id='family-visit',
            title='Christmas in NJ',
            start_date=start_date,
            end_date=start_date + timedelta(days=1),
            human_label=SkylightEventReview.Label.NOT_TRIP,
        )
        suggestion = SkylightTripSuggestion.objects.create(
            connection=self.connection,
            skylight_event_id=review.skylight_event_id,
            title=review.title,
            start_date=review.start_date,
            end_date=review.end_date,
        )
        suggestion.profiles.add(self.joint)

        result = reconcile_skylight_reviews_into_trips(self.connection)

        self.assertEqual(result['dismissed'], 1)
        self.assertFalse(Trip.objects.exists())
        suggestion.refresh_from_db()
        self.assertEqual(suggestion.status, SkylightTripSuggestion.Status.DISMISSED)

    def test_map_can_attach_a_region_destination_to_an_existing_trip(self):
        start_date = timezone.localdate() + timedelta(days=20)
        collection = Collection.objects.create(
            user=self.user,
            name='Massachusetts weekend',
            start_date=start_date,
            end_date=start_date + timedelta(days=2),
        )
        trip = Trip.objects.create(
            owner=self.user,
            collection=collection,
            title=collection.name,
            start_date=collection.start_date,
            end_date=collection.end_date,
        )
        trip.profiles.add(self.joint)

        response = self.client.post(
            f'/api/trips/{trip.id}/destinations/?format=json',
            {'country': self.us.id, 'region': self.ma.id},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['region'], self.ma.id)

        trip_response = self.client.get(f'/api/trips/{trip.id}/?format=json')
        self.assertEqual(trip_response.status_code, 200)
        self.assertEqual(trip_response.json()['destinations'][0]['region_name'], 'Massachusetts')
