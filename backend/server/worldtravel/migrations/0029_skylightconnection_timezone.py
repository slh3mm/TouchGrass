from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('worldtravel', '0028_skylight_trip_detection'),
    ]

    operations = [
        migrations.AddField(
            model_name='skylightconnection',
            name='timezone',
            field=models.CharField(blank=True, default='UTC', max_length=64),
        ),
    ]
