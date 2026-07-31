from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('adventures', '0071_alter_collectionitineraryitem_unique_together_and_more'),
        ('worldtravel', '0019_travel_profiles'),
    ]

    operations = [
        migrations.AddField(
            model_name='location',
            name='profiles',
            field=models.ManyToManyField(blank=True, related_name='locations', to='worldtravel.travelprofile'),
        ),
    ]
