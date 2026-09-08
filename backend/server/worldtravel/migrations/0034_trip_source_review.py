from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('worldtravel', '0033_tripdestination'),
    ]

    operations = [
        migrations.AddField(
            model_name='trip',
            name='source_review',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='materialized_trip',
                to='worldtravel.skylighteventreview',
            ),
        ),
    ]
