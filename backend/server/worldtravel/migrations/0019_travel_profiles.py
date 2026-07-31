import uuid
from django.db import migrations, models
import django.db.models.deletion
import django.core.validators


PROFILE_COLORS = ['#fb8072', '#fdbf6f', '#a6cee3', '#cab2d6', '#80b1d3', '#b3de69']


def create_default_profiles(apps, schema_editor):
    User = apps.get_model('users', 'CustomUser')
    TravelProfile = apps.get_model('worldtravel', 'TravelProfile')
    for index, user in enumerate(User.objects.all().iterator()):
        TravelProfile.objects.get_or_create(
            owner=user,
            name=user.username or 'Me',
            defaults={
                'color': PROFILE_COLORS[index % len(PROFILE_COLORS)],
                'linked_user': user,
                'is_default': True,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ('users', '0009_alter_customuser_map_style'),
        ('worldtravel', '0018_rename_user_id_visitedcity_user'),
    ]

    operations = [
        migrations.CreateModel(
            name='TravelProfile',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=80)),
                ('color', models.CharField(default='#4A90E2', max_length=7, validators=[django.core.validators.RegexValidator('^#[0-9A-Fa-f]{6}$', 'Use a six-digit hex color.')])),
                ('avatar', models.CharField(blank=True, default='', max_length=8)),
                ('is_default', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('linked_user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='linked_travel_profiles', to='users.customuser')),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='travel_profiles', to='users.customuser')),
            ],
            options={'ordering': ['created_at', 'name']},
        ),
        migrations.CreateModel(
            name='ProfileCountryVisit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('country', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='profile_visits', to='worldtravel.country')),
                ('profile', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='country_visits', to='worldtravel.travelprofile')),
            ],
        ),
        migrations.CreateModel(
            name='ProfileRegionVisit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('profile', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='region_visits', to='worldtravel.travelprofile')),
                ('region', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='profile_visits', to='worldtravel.region')),
            ],
        ),
        migrations.AddConstraint(model_name='travelprofile', constraint=models.UniqueConstraint(fields=('owner', 'name'), name='unique_travel_profile_name')),
        migrations.AddConstraint(model_name='profilecountryvisit', constraint=models.UniqueConstraint(fields=('profile', 'country'), name='unique_profile_country_visit')),
        migrations.AddConstraint(model_name='profileregionvisit', constraint=models.UniqueConstraint(fields=('profile', 'region'), name='unique_profile_region_visit')),
        migrations.RunPython(create_default_profiles, migrations.RunPython.noop),
    ]
