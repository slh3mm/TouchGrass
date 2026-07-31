from django.db import migrations


def backfill_location_profiles(apps, schema_editor):
    Location = apps.get_model('adventures', 'Location')
    TravelProfile = apps.get_model('worldtravel', 'TravelProfile')
    through = Location.profiles.through
    profiles = {profile.owner_id: profile for profile in TravelProfile.objects.filter(is_default=True)}
    rows = []
    for location in Location.objects.all().iterator():
        profile = profiles.get(location.user_id)
        if profile:
            rows.append(through(location_id=location.id, travelprofile_id=profile.id))
    through.objects.bulk_create(rows, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [
        ('adventures', '0072_location_profiles'),
        ('worldtravel', '0020_backfill_profile_region_visits'),
    ]
    operations = [migrations.RunPython(backfill_location_profiles, migrations.RunPython.noop)]
