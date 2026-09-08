import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('worldtravel', '0032_profiletravelvisit_end_date'),
    ]

    operations = [
        migrations.CreateModel(
            name='TripDestination',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('country', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='trip_destinations', to='worldtravel.country')),
                ('region', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='trip_destinations', to='worldtravel.region')),
                ('trip', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='destinations', to='worldtravel.trip')),
            ],
            options={'ordering': ['country__name', 'region__name']},
        ),
        migrations.AddConstraint(
            model_name='tripdestination',
            constraint=models.UniqueConstraint(condition=models.Q(region__isnull=True), fields=('trip', 'country'), name='unique_trip_country_destination'),
        ),
        migrations.AddConstraint(
            model_name='tripdestination',
            constraint=models.UniqueConstraint(condition=models.Q(region__isnull=False), fields=('trip', 'region'), name='unique_trip_region_destination'),
        ),
    ]
