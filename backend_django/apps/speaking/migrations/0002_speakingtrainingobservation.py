# Generated during Django database-first migration.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("speaking", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SpeakingTrainingObservation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("observation_id", models.CharField(max_length=160, unique=True)),
                ("legacy_attempt_id", models.CharField(db_index=True, max_length=120)),
                ("legacy_turn_id", models.CharField(max_length=120)),
                ("question_id", models.CharField(db_index=True, max_length=160)),
                ("part", models.CharField(max_length=16)),
                ("question", models.TextField()),
                ("transcript", models.TextField(blank=True)),
                ("overall_band", models.DecimalField(blank=True, decimal_places=1, max_digits=3, null=True)),
                ("fluency_coherence", models.DecimalField(blank=True, decimal_places=1, max_digits=3, null=True)),
                ("lexical_resource", models.DecimalField(blank=True, decimal_places=1, max_digits=3, null=True)),
                ("grammar_range_accuracy", models.DecimalField(blank=True, decimal_places=1, max_digits=3, null=True)),
                ("pronunciation", models.DecimalField(blank=True, decimal_places=1, max_digits=3, null=True)),
                ("relevance", models.DecimalField(decimal_places=3, max_digits=4)),
                ("weak_item_flag", models.BooleanField(default=False)),
                ("weak_reasons", models.JSONField(blank=True, default=list)),
                ("model_version", models.CharField(blank=True, max_length=80)),
                ("observed_at", models.DateTimeField()),
                ("next_due", models.DateTimeField()),
                ("attempt", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="training_observations", to="speaking.speakingattempt")),
                ("turn", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="training_observations", to="speaking.speakingturn")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="speaking_training_observations", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddIndex(
            model_name="speakingtrainingobservation",
            index=models.Index(fields=["user", "created_at"], name="speaking_sp_user_id_4197c9_idx"),
        ),
        migrations.AddIndex(
            model_name="speakingtrainingobservation",
            index=models.Index(fields=["user", "next_due", "weak_item_flag"], name="speaking_sp_user_id_ef45e6_idx"),
        ),
        migrations.AddIndex(
            model_name="speakingtrainingobservation",
            index=models.Index(fields=["question_id"], name="speaking_sp_questio_c54040_idx"),
        ),
        migrations.AddIndex(
            model_name="speakingtrainingobservation",
            index=models.Index(fields=["user", "part", "weak_item_flag", "observed_at"], name="speaking_sp_user_id_8c53ce_idx"),
        ),
    ]
