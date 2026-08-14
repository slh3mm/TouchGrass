from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('worldtravel', '0027_skylightprofilemapping_manually_assigned'),
    ]

    operations = [
        migrations.AddField(
            model_name='skylighttripsuggestion',
            name='detection_reasons',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='skylighttripsuggestion',
            name='detection_score',
            field=models.SmallIntegerField(default=0),
        ),
    ]
