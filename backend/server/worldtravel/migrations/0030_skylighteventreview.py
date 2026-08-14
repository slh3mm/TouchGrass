import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('worldtravel', '0029_skylightconnection_timezone'),
    ]

    operations = [
        migrations.CreateModel(
            name='SkylightEventReview',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('skylight_event_id', models.CharField(max_length=100)),
                ('skylight_event_uid', models.CharField(blank=True, default='', max_length=255)),
                ('title', models.CharField(max_length=200)),
                ('start_date', models.DateField()),
                ('end_date', models.DateField()),
                ('all_day', models.BooleanField(default=False)),
                ('calendar_description', models.TextField(blank=True, default='')),
                ('location', models.CharField(blank=True, default='', max_length=500)),
                ('category_ids', models.JSONField(blank=True, default=list)),
                ('predicted_is_trip', models.BooleanField(default=False)),
                ('detection_score', models.SmallIntegerField(default=0)),
                ('detection_reasons', models.JSONField(blank=True, default=list)),
                ('human_label', models.CharField(choices=[('unreviewed', 'Unreviewed'), ('trip', 'Trip'), ('not_trip', 'Not a trip')], default='unreviewed', max_length=16)),
                ('reviewer_note', models.TextField(blank=True, default='')),
                ('last_seen_at', models.DateTimeField(auto_now=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('connection', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='event_reviews', to='worldtravel.skylightconnection')),
                ('profiles', models.ManyToManyField(blank=True, related_name='skylight_event_reviews', to='worldtravel.travelprofile')),
            ],
            options={
                'ordering': ['-start_date', 'title'],
                'indexes': [models.Index(fields=['connection', 'human_label', 'start_date'], name='skylight_review_label_date')],
                'constraints': [models.UniqueConstraint(fields=('connection', 'skylight_event_id'), name='unique_skylight_event_review')],
            },
        ),
    ]
