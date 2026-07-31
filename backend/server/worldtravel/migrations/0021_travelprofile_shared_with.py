from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('worldtravel', '0020_backfill_profile_region_visits'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='travelprofile',
            name='shared_with',
            field=models.ManyToManyField(blank=True, related_name='shared_travel_profiles', to=settings.AUTH_USER_MODEL),
        ),
    ]
