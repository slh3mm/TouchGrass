import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('worldtravel', '0022_trip'),
    ]

    operations = [
        migrations.CreateModel(
            name='BallparkVisit',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('ballpark_id', models.CharField(max_length=16)),
                ('first_visit_date', models.DateField(blank=True, null=True)),
                ('last_visit_date', models.DateField(blank=True, null=True)),
                ('visit_count', models.PositiveIntegerField(default=1)),
                ('notes', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('profile', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ballpark_visits', to='worldtravel.travelprofile')),
            ],
            options={
                'ordering': ['ballpark_id', 'profile__name'],
                'constraints': [
                    models.UniqueConstraint(fields=('profile', 'ballpark_id'), name='unique_profile_ballpark_visit'),
                ],
            },
        ),
    ]
