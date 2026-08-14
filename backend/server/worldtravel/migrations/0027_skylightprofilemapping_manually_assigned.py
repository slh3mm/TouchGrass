from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('worldtravel', '0026_skylight_integration'),
    ]

    operations = [
        migrations.AddField(
            model_name='skylightprofilemapping',
            name='manually_assigned',
            field=models.BooleanField(default=False),
        ),
    ]
