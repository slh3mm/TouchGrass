import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('worldtravel', '0023_ballparkvisit'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProfileTravelVisit',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('visit_date', models.DateField()),
                ('notes', models.CharField(blank=True, default='', max_length=500)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('country', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='profile_visit_history', to='worldtravel.country')),
                ('profile', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='travel_visit_history', to='worldtravel.travelprofile')),
                ('region', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='profile_visit_history', to='worldtravel.region')),
            ],
            options={
                'ordering': ['-visit_date', '-created_at'],
                'indexes': [
                    models.Index(fields=['country', 'region', 'visit_date'], name='travel_visit_place_date'),
                    models.Index(fields=['profile', 'visit_date'], name='travel_visit_profile_date'),
                ],
            },
        ),
    ]
