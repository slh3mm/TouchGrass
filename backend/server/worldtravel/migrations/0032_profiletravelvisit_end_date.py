from django.db import migrations, models


def backfill_end_dates(apps, schema_editor):
    ProfileTravelVisit = apps.get_model('worldtravel', 'ProfileTravelVisit')
    ProfileTravelVisit.objects.filter(end_date__isnull=True).update(
        end_date=models.F('visit_date')
    )


class Migration(migrations.Migration):

    dependencies = [
        ('worldtravel', '0031_skylight_trip_destinations'),
    ]

    operations = [
        migrations.AddField(
            model_name='profiletravelvisit',
            name='end_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.RunPython(backfill_end_dates, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='profiletravelvisit',
            name='end_date',
            field=models.DateField(),
        ),
    ]
