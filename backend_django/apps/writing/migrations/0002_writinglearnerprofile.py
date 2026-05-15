# Generated during Django database-first migration.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("writing", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="WritingLearnerProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("total_scored", models.PositiveIntegerField(default=0)),
                ("task_counts", models.JSONField(blank=True, default=dict)),
                ("average_overall_band", models.DecimalField(blank=True, decimal_places=2, max_digits=4, null=True)),
                ("criterion_averages", models.JSONField(blank=True, default=dict)),
                ("tag_counts", models.JSONField(blank=True, default=dict)),
                ("primary_focus", models.CharField(default="insufficient_data", max_length=80)),
                ("primary_focus_text", models.TextField(blank=True)),
                ("recent_evidence", models.JSONField(blank=True, default=list)),
                ("profile_payload", models.JSONField(blank=True, default=dict)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="writing_learner_profile", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddIndex(
            model_name="writinglearnerprofile",
            index=models.Index(fields=["user", "created_at"], name="writing_wri_user_id_282f13_idx"),
        ),
        migrations.AddIndex(
            model_name="writinglearnerprofile",
            index=models.Index(fields=["primary_focus", "updated_at"], name="writing_wri_primary_4c3efc_idx"),
        ),
    ]
