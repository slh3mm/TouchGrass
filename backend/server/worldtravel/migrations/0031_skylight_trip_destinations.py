from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('worldtravel', '0030_skylighteventreview'),
    ]

    operations = [
        migrations.AddField(
            model_name='skylighteventreview',
            name='destination_country',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='skylight_trip_reviews',
                to='worldtravel.country',
            ),
        ),
        migrations.AddField(
            model_name='skylighteventreview',
            name='destination_label',
            field=models.CharField(blank=True, default='', max_length=200),
        ),
        migrations.AddField(
            model_name='skylighteventreview',
            name='destination_region',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='skylight_trip_reviews',
                to='worldtravel.region',
            ),
        ),
        migrations.AddField(
            model_name='skylighteventreview',
            name='destination_resolution',
            field=models.CharField(blank=True, default='', max_length=16),
        ),
    ]
