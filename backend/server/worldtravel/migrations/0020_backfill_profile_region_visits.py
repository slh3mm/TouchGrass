from django.db import migrations


def backfill_region_visits(apps, schema_editor):
    TravelProfile = apps.get_model('worldtravel', 'TravelProfile')
    VisitedRegion = apps.get_model('worldtravel', 'VisitedRegion')
    ProfileRegionVisit = apps.get_model('worldtravel', 'ProfileRegionVisit')
    profiles = {profile.owner_id: profile for profile in TravelProfile.objects.filter(is_default=True)}
    rows = []
    for visit in VisitedRegion.objects.all().iterator():
        profile = profiles.get(visit.user_id)
        if profile:
            rows.append(ProfileRegionVisit(profile_id=profile.id, region_id=visit.region_id))
    ProfileRegionVisit.objects.bulk_create(rows, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [('worldtravel', '0019_travel_profiles')]
    operations = [migrations.RunPython(backfill_region_visits, migrations.RunPython.noop)]
