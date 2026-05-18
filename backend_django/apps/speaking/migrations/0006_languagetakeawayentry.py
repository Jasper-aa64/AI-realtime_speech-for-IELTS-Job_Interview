from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ("speaking", "0005_p2corpusentry"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LanguageTakeawayEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("entry_id", models.CharField(max_length=160)),
                ("source_text", models.TextField()),
                ("chinese_text", models.TextField(blank=True)),
                ("source_language", models.CharField(blank=True, max_length=32)),
                ("target_language", models.CharField(default="zh", max_length=32)),
                ("context_url", models.TextField(blank=True)),
                ("context_label", models.CharField(blank=True, max_length=200)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="language_takeaway_entries", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "indexes": [
                    models.Index(fields=["user", "updated_at"], name="speaking_lt_user_updated_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("user", "entry_id"), name="unique_language_takeaway_per_user"),
                ],
            },
        ),
    ]
