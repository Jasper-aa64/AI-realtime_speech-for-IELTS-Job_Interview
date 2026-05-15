# Generated during Django database-first migration.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LegacyBillingUser",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("legacy_user_id", models.CharField(max_length=120, unique=True)),
                ("display_name", models.CharField(max_length=120)),
                ("balance_u", models.BigIntegerField(default=0)),
                ("reserved_u", models.BigIntegerField(default=0)),
                ("carry_numerator_u", models.BigIntegerField(default=0)),
                ("status", models.CharField(default="active", max_length=24)),
                ("legacy_created_at", models.DateTimeField(blank=True, null=True)),
                ("legacy_updated_at", models.DateTimeField(blank=True, null=True)),
                ("user", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="legacy_billing_user", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddIndex(
            model_name="legacybillinguser",
            index=models.Index(fields=["status", "updated_at"], name="billing_leg_status_a7ce82_idx"),
        ),
    ]
