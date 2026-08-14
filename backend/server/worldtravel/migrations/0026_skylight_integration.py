import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('worldtravel', '0025_trip_collection'),
    ]

    operations = [
        migrations.CreateModel(
            name='SkylightConnection',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('encrypted_credentials', models.TextField(blank=True, default='')),
                ('frame_id', models.CharField(blank=True, default='', max_length=80)),
                ('frame_name', models.CharField(blank=True, default='', max_length=160)),
                ('oauth_state_digest', models.CharField(blank=True, default='', max_length=64)),
                ('oauth_state_expires_at', models.DateTimeField(blank=True, null=True)),
                ('connected_at', models.DateTimeField(blank=True, null=True)),
                ('last_sync_at', models.DateTimeField(blank=True, null=True)),
                ('last_sync_error', models.CharField(blank=True, default='', max_length=500)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('owner', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='skylight_connection', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='SkylightProfileMapping',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('skylight_category_id', models.CharField(max_length=80)),
                ('skylight_category_name', models.CharField(max_length=160)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('connection', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='profile_mappings', to='worldtravel.skylightconnection')),
                ('profile', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='skylight_mappings', to='worldtravel.travelprofile')),
            ],
            options={'ordering': ['skylight_category_name']},
        ),
        migrations.CreateModel(
            name='SkylightTripSuggestion',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('skylight_event_id', models.CharField(max_length=100)),
                ('skylight_event_uid', models.CharField(blank=True, default='', max_length=255)),
                ('title', models.CharField(max_length=200)),
                ('start_date', models.DateField()),
                ('end_date', models.DateField()),
                ('notes', models.TextField(blank=True, default='')),
                ('location', models.CharField(blank=True, default='', max_length=500)),
                ('category_ids', models.JSONField(blank=True, default=list)),
                ('status', models.CharField(choices=[('pending', 'Pending review'), ('accepted', 'Accepted'), ('dismissed', 'Dismissed')], default='pending', max_length=16)),
                ('last_seen_at', models.DateTimeField(auto_now=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('connection', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='trip_suggestions', to='worldtravel.skylightconnection')),
                ('profiles', models.ManyToManyField(related_name='skylight_trip_suggestions', to='worldtravel.travelprofile')),
                ('trip', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='skylight_suggestions', to='worldtravel.trip')),
            ],
            options={'ordering': ['start_date', 'title']},
        ),
        migrations.AddConstraint(
            model_name='skylightprofilemapping',
            constraint=models.UniqueConstraint(fields=('connection', 'skylight_category_id'), name='unique_skylight_category_mapping'),
        ),
        migrations.AddConstraint(
            model_name='skylighttripsuggestion',
            constraint=models.UniqueConstraint(fields=('connection', 'skylight_event_id'), name='unique_skylight_trip_suggestion'),
        ),
        migrations.AddIndex(
            model_name='skylighttripsuggestion',
            index=models.Index(fields=['connection', 'status', 'start_date'], name='skylight_suggest_status_date'),
        ),
    ]
