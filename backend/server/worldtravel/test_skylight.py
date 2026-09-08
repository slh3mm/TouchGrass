from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from .models import SkylightConnection, SkylightEventReview, SkylightTripSuggestion, TravelProfile
from .skylight import (
    _destination_matches,
    _event_dates,
    _trip_detection,
    begin_oauth,
    decrypt_credentials,
    encrypt_credentials,
    login_with_password,
    sync_trip_suggestions,
)
from .views import _add_calendar_months, _connection_localdate


@override_settings(SECRET_KEY='touchgrass-skylight-test-secret')
class SkylightCredentialTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='skylight-test-user', password='test-password'
        )
        self.connection = SkylightConnection.objects.create(owner=self.user)

    def test_credentials_are_encrypted_and_round_trip(self):
        credentials = {
            'access_token': 'access-token-that-must-not-be-plaintext',
            'refresh_token': 'refresh-token-that-must-not-be-plaintext',
            'fingerprint': 'a42ddf32-018e-4b45-a5a0-e614089d7096',
            'expires_at': (timezone.now() + timedelta(hours=1)).isoformat(),
        }

        encrypted = encrypt_credentials(credentials)
        self.assertNotIn(credentials['access_token'], encrypted)
        self.assertNotIn(credentials['refresh_token'], encrypted)

        self.connection.encrypted_credentials = encrypted
        self.connection.save(update_fields=['encrypted_credentials'])
        self.assertEqual(decrypt_credentials(self.connection), credentials)

    def test_oauth_state_is_stored_only_as_a_digest(self):
        login_url = begin_oauth(self.connection)
        query = parse_qs(urlparse(login_url).query)
        state = query['state'][0]

        self.connection.refresh_from_db()
        self.assertNotEqual(self.connection.oauth_state_digest, state)
        self.assertEqual(len(self.connection.oauth_state_digest), 64)
        self.assertEqual(query['client_id'], ['skylight-mobile'])
        self.assertEqual(query['redirect_uri'], ['https://ourskylight.com/welcome'])

    @patch('worldtravel.skylight.sync_profile_mappings')
    @patch('worldtravel.skylight.discover_frame')
    @patch('worldtravel.skylight._token_request')
    @patch('worldtravel.skylight.requests.Session')
    def test_server_login_discards_password_and_stores_only_encrypted_oauth(
        self, session_class, token_request, discover_frame, sync_mappings
    ):
        login_page = SimpleNamespace(
            text='<input name="authenticity_token" value="csrf-value">',
            status_code=200,
            raise_for_status=lambda: None,
        )
        login_result = SimpleNamespace(
            status_code=302,
            headers={'Location': '/calendar'},
        )
        authorize_result = SimpleNamespace(
            status_code=302,
            headers={'Location': 'https://ourskylight.com/welcome?code=oauth-code'},
        )
        session = session_class.return_value
        session.get.side_effect = [login_page, authorize_result]
        session.post.return_value = login_result
        credentials = {
            'access_token': 'server-login-access-token',
            'refresh_token': 'server-login-refresh-token',
            'fingerprint': 'a42ddf32-018e-4b45-a5a0-e614089d7096',
            'expires_at': (timezone.now() + timedelta(hours=1)).isoformat(),
        }
        token_request.return_value = credentials

        login_with_password(self.connection, 'person@example.com', 'never-store-this')
        self.connection.refresh_from_db()

        self.assertNotIn('never-store-this', self.connection.encrypted_credentials)
        self.assertNotIn('person@example.com', self.connection.encrypted_credentials)
        self.assertEqual(decrypt_credentials(self.connection), credentials)
        self.assertFalse(
            any('never-store-this' in str(value) for value in self.connection.__dict__.values())
        )
        discover_frame.assert_called_once_with(self.connection)
        sync_mappings.assert_called_once_with(self.connection)


@override_settings(SECRET_KEY='touchgrass-skylight-sync-test-secret', TIME_ZONE='America/New_York')
class SkylightSyncTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='skylight-sync-user', password='test-password'
        )
        self.spencer = TravelProfile.objects.create(
            owner=self.user, name='Spencer', color='#F7C948', is_default=True
        )
        self.ashley = TravelProfile.objects.create(
            owner=self.user, name='Ashley', color='#EE86AC'
        )
        self.joint = TravelProfile.objects.create(
            owner=self.user, name='Joint', color='#43D39E'
        )
        self.connection = SkylightConnection.objects.create(
            owner=self.user,
            frame_id='3878603',
            encrypted_credentials=encrypt_credentials(
                {
                    'access_token': 'test-access',
                    'refresh_token': 'test-refresh',
                    'fingerprint': 'a42ddf32-018e-4b45-a5a0-e614089d7096',
                    'expires_at': (timezone.now() + timedelta(hours=1)).isoformat(),
                }
            ),
        )

    @staticmethod
    def categories_payload():
        return {
            'data': [
                {'id': '1', 'attributes': {'name': 'Spencer’s Events'}},
                {'id': '2', 'attributes': {'name': 'Ashley’s Events'}},
                {'id': '3', 'attributes': {'name': 'Joint Events'}},
                {'id': '4', 'attributes': {'name': 'US Holidays'}},
            ]
        }

    @staticmethod
    def events_payload():
        return {
            'data': [
                {
                    'id': 'trip-joint',
                    'attributes': {
                        'uid': 'trip-joint@example',
                        'summary': 'France trip',
                        'starts_at': '2026-09-01T00:00:00.000-04:00',
                        'ends_at': '2026-09-08T00:00:00.000-04:00',
                        'all_day': True,
                        'description': 'Paris and Lyon',
                        'location': 'France',
                    },
                    'relationships': {'categories': {'data': [{'id': '3'}]}},
                },
                {
                    'id': 'trip-ashley',
                    'attributes': {
                        'uid': 'trip-ashley@example',
                        'summary': 'Europe',
                        'starts_at': '2026-10-01T00:00:00.000-04:00',
                        'ends_at': '2026-10-06T00:00:00.000-04:00',
                        'all_day': True,
                    },
                    'relationships': {'categories': {'data': [{'id': '2'}]}},
                },
                {
                    'id': 'birthday',
                    'attributes': {
                        'uid': 'birthday@example',
                        'summary': 'Birthday dinner',
                        'starts_at': '2026-11-03T18:00:00.000-05:00',
                        'ends_at': '2026-11-03T20:00:00.000-05:00',
                        'all_day': False,
                    },
                    'relationships': {'categories': {'data': [{'id': '2'}]}},
                },
                {
                    'id': 'holiday-trip-word',
                    'attributes': {
                        'uid': 'holiday@example',
                        'summary': 'Travel observance',
                        'starts_at': '2026-12-01T00:00:00.000-05:00',
                        'ends_at': '2026-12-02T00:00:00.000-05:00',
                        'all_day': True,
                    },
                    'relationships': {'categories': {'data': [{'id': '4'}]}},
                },
            ]
        }

    def request_side_effect(self, connection, method, path, **kwargs):
        if path.endswith('/categories'):
            return self.categories_payload()
        if path.endswith('/calendar_events'):
            return self.events_payload()
        raise AssertionError(f'Unexpected Skylight path: {path}')

    def test_timed_evening_event_stays_on_its_skylight_calendar_date(self):
        attributes = {
            'starts_at': '2026-05-06T19:00:00.000-04:00',
            'ends_at': '2026-05-06T22:00:00.000-04:00',
            'timezone': 'America/New_York',
            'all_day': False,
        }
        start_date, end_date = _event_dates(
            attributes
        )
        self.assertEqual(start_date.isoformat(), '2026-05-06')
        self.assertEqual(end_date.isoformat(), '2026-05-06')
        detection = _trip_detection(attributes, start_date, end_date, ['Game'])
        self.assertFalse(detection['candidate'])

    def test_scored_detection_rejects_planning_and_local_events(self):
        local_event = _trip_detection(
            {'summary': 'Game Night', 'all_day': False, 'rrule': None},
            date(2026, 5, 6),
            date(2026, 5, 6),
            [],
        )
        planning_event = _trip_detection(
            {'summary': 'Finish up Ireland Itinerary', 'all_day': False, 'rrule': None},
            date(2026, 5, 7),
            date(2026, 5, 7),
            ['Ireland'],
        )
        real_trip = _trip_detection(
            {'summary': 'Portugal 🇵🇹', 'all_day': True, 'rrule': None},
            date(2026, 5, 21),
            date(2026, 5, 31),
            ['Portugal'],
        )
        explicit_day_trip = _trip_detection(
            {'summary': 'UVA BBall Trip', 'all_day': False, 'rrule': None},
            date(2026, 1, 10),
            date(2026, 1, 10),
            [],
        )

        self.assertFalse(local_event['candidate'])
        self.assertFalse(planning_event['candidate'])
        self.assertTrue(real_trip['candidate'])
        self.assertTrue(explicit_day_trip['candidate'])

    def test_personal_trip_policy_excludes_work_home_and_family_visits(self):
        work_trip = _trip_detection(
            {'summary': 'Raleigh Trip', 'all_day': True, 'rrule': None},
            date(2026, 3, 13),
            date(2026, 3, 13),
            ['Raleigh'],
            ['Work Travel'],
        )
        home_trip = _trip_detection(
            {'summary': 'Home for fam & DND', 'all_day': True, 'rrule': None},
            date(2026, 2, 27),
            date(2026, 3, 1),
            [],
        )
        family_visit = _trip_detection(
            {'summary': 'Grandma’s 80th bday', 'all_day': True, 'rrule': None},
            date(2026, 10, 30),
            date(2026, 11, 1),
            ['Annapolis'],
        )
        friend_visit = _trip_detection(
            {'summary': 'Matt Visit in NYC', 'all_day': True, 'rrule': None},
            date(2026, 3, 12),
            date(2026, 3, 15),
            ['New York City'],
        )

        self.assertFalse(work_trip['candidate'])
        self.assertFalse(home_trip['candidate'])
        self.assertFalse(family_visit['candidate'])
        self.assertTrue(friend_visit['candidate'])

    def test_destination_visit_title_becomes_a_trip_candidate(self):
        event = {
            'id': 'nyc-visit',
            'attributes': {
                'summary': 'NYC Visit',
                'location': '',
                'all_day': True,
            },
        }

        destinations = _destination_matches([event])['nyc-visit']
        detection = _trip_detection(
            event['attributes'],
            date(2026, 9, 11),
            date(2026, 9, 13),
            destinations,
        )

        self.assertEqual(destinations, ['New York City'])
        self.assertTrue(detection['candidate'])
        self.assertGreaterEqual(detection['score'], 4)

    def test_personal_trip_policy_handles_planning_calls_and_yar_shorthand(self):
        planning_call = _trip_detection(
            {'summary': 'Milwaukee trip ft', 'all_day': True, 'rrule': None},
            date(2026, 7, 13),
            date(2026, 7, 13),
            ['Milwaukee'],
        )
        yar = _trip_detection(
            {'summary': 'YAR 🔸🔹', 'all_day': True, 'rrule': None},
            date(2026, 10, 8),
            date(2026, 10, 11),
            [],
        )

        self.assertFalse(planning_call['candidate'])
        self.assertTrue(yar['candidate'])

    @patch('worldtravel.skylight._request')
    def test_sync_maps_joint_only_to_joint_and_is_idempotent(self, request_mock):
        request_mock.side_effect = self.request_side_effect

        first = sync_trip_suggestions(self.connection)
        second = sync_trip_suggestions(self.connection)

        self.assertEqual(first['created'], 2)
        self.assertEqual(first['skipped'], 2)
        self.assertEqual(second['created'], 0)
        self.assertEqual(SkylightTripSuggestion.objects.count(), 2)

        joint_suggestion = SkylightTripSuggestion.objects.get(
            skylight_event_id='trip-joint'
        )
        self.assertEqual(list(joint_suggestion.profiles.all()), [self.joint])
        self.assertNotIn(self.spencer, joint_suggestion.profiles.all())
        self.assertNotIn(self.ashley, joint_suggestion.profiles.all())
        self.assertEqual(joint_suggestion.end_date.isoformat(), '2026-09-07')

        mapping = self.connection.profile_mappings.get(skylight_category_id='3')
        self.assertEqual(mapping.skylight_category_name, 'Joint Events')
        self.assertEqual(mapping.profile, self.joint)

    @patch('worldtravel.skylight._request')
    def test_manual_ignore_survives_sync_and_removes_pending_suggestion(self, request_mock):
        request_mock.side_effect = self.request_side_effect
        sync_trip_suggestions(self.connection)

        mapping = self.connection.profile_mappings.get(skylight_category_id='2')
        mapping.profile = None
        mapping.manually_assigned = True
        mapping.save(update_fields=['profile', 'manually_assigned', 'updated_at'])

        result = sync_trip_suggestions(self.connection)
        mapping.refresh_from_db()

        self.assertIsNone(mapping.profile)
        self.assertTrue(mapping.manually_assigned)
        self.assertEqual(result['removed'], 1)
        self.assertFalse(
            SkylightTripSuggestion.objects.filter(skylight_event_id='trip-ashley').exists()
        )

    @patch('worldtravel.skylight._request')
    def test_sync_stores_every_event_and_preserves_human_ground_truth(self, request_mock):
        request_mock.side_effect = self.request_side_effect
        first = sync_trip_suggestions(self.connection)

        self.assertEqual(first['events_seen'], 4)
        self.assertEqual(first['reviews_created'], 4)
        self.assertEqual(SkylightEventReview.objects.count(), 4)

        birthday = SkylightEventReview.objects.get(skylight_event_id='birthday')
        self.assertFalse(birthday.predicted_is_trip)
        self.assertEqual(list(birthday.profiles.all()), [self.ashley])
        birthday.human_label = SkylightEventReview.Label.NOT_TRIP
        birthday.reviewer_note = 'A local birthday dinner, not travel.'
        birthday.save(update_fields=['human_label', 'reviewer_note', 'updated_at'])

        second = sync_trip_suggestions(self.connection)
        birthday.refresh_from_db()

        self.assertEqual(second['reviews_created'], 0)
        self.assertEqual(second['reviews_updated'], 4)
        self.assertEqual(birthday.human_label, SkylightEventReview.Label.NOT_TRIP)
        self.assertEqual(birthday.reviewer_note, 'A local birthday dinner, not travel.')

    @patch('worldtravel.skylight._request')
    def test_event_review_api_updates_only_human_fields(self, request_mock):
        request_mock.side_effect = self.request_side_effect
        sync_trip_suggestions(self.connection)
        review = SkylightEventReview.objects.get(skylight_event_id='trip-joint')
        self.client.force_login(self.user)

        response = self.client.patch(
            f'/api/skylight/events/{review.id}/',
            data={'human_label': 'trip', 'reviewer_note': 'Confirmed vacation.'},
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        review.refresh_from_db()
        self.assertEqual(review.human_label, SkylightEventReview.Label.TRIP)
        self.assertEqual(review.reviewer_note, 'Confirmed vacation.')
        self.assertEqual(review.title, 'France trip')

    @patch('worldtravel.skylight._request')
    def test_review_only_sync_does_not_create_trip_suggestions(self, request_mock):
        request_mock.side_effect = self.request_side_effect

        result = sync_trip_suggestions(self.connection, update_suggestions=False)

        self.assertEqual(result['reviews_created'], 4)
        self.assertEqual(SkylightEventReview.objects.count(), 4)
        self.assertEqual(SkylightTripSuggestion.objects.count(), 0)

    def test_event_review_list_hides_events_more_than_three_months_ahead(self):
        past = SkylightEventReview.objects.create(
            connection=self.connection,
            skylight_event_id='past-event',
            title='Past event',
            start_date=date(2020, 1, 1),
            end_date=date(2020, 1, 1),
        )
        SkylightEventReview.objects.create(
            connection=self.connection,
            skylight_event_id='far-future-event',
            title='Far future event',
            start_date=date(2030, 1, 1),
            end_date=date(2030, 1, 1),
        )
        self.client.force_login(self.user)

        response = self.client.get('/api/skylight/events/?format=json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['counts']['all'], 1)
        self.assertEqual(
            [event['id'] for event in response.data['events']],
            [str(past.id)],
        )

    def test_three_month_cutoff_uses_calendar_months(self):
        self.assertEqual(
            _add_calendar_months(date(2026, 11, 30), 3),
            date(2027, 2, 28),
        )
        self.assertEqual(
            _add_calendar_months(date(2026, 1, 31), 3),
            date(2026, 4, 30),
        )

    @patch('worldtravel.views.timezone.localdate')
    def test_review_cutoff_uses_connected_calendar_timezone(self, localdate):
        self.connection.timezone = 'America/New_York'
        localdate.return_value = date(2026, 8, 13)

        result = _connection_localdate(self.connection)

        self.assertEqual(result, date(2026, 8, 13))
        self.assertEqual(localdate.call_args.kwargs['timezone'].key, 'America/New_York')
