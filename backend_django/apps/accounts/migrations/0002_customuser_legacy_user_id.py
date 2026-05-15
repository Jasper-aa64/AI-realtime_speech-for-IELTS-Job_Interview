# Generated during Django database-first migration.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="customuser",
            name="legacy_user_id",
            field=models.CharField(blank=True, max_length=120, null=True, unique=True),
        ),
    ]
