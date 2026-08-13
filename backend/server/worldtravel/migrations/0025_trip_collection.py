from django.db import migrations, models
import django.db.models.deletion


def create_trip_collections(apps, schema_editor):
    Trip = apps.get_model('worldtravel', 'Trip')
    Collection = apps.get_model('adventures', 'Collection')

    for trip in Trip.objects.filter(collection__isnull=True).iterator():
        collection = Collection.objects.create(
            user_id=trip.owner_id,
            name=trip.title,
            description=trip.notes or '',
            start_date=trip.start_date,
            end_date=trip.end_date,
        )
        trip.collection_id = collection.id
        trip.save(update_fields=['collection'])

        collaborator_ids = set()
        for profile in trip.profiles.all():
            collaborator_ids.add(profile.owner_id)
            if profile.linked_user_id:
                collaborator_ids.add(profile.linked_user_id)
            collaborator_ids.update(profile.shared_with.values_list('id', flat=True))
        collaborator_ids.discard(trip.owner_id)
        if collaborator_ids:
            collection.shared_with.add(*collaborator_ids)


class Migration(migrations.Migration):
    dependencies = [
        ('adventures', '0073_backfill_location_profiles'),
        ('worldtravel', '0024_profiletravelvisit'),
    ]

    operations = [
        migrations.AddField(
            model_name='trip',
            name='collection',
            field=models.OneToOneField(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='touchgrass_trip',
                to='adventures.collection',
            ),
        ),
        migrations.RunPython(create_trip_collections, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='trip',
            name='collection',
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='touchgrass_trip',
                to='adventures.collection',
            ),
        ),
    ]
