from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("speaking", "0007_p2bankcorpusentry_p3bankfollowupcorpusentry"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TakeawayReviewState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("kind", models.CharField(choices=[("language", "Language"), ("writing", "Writing")], max_length=16)),
                ("state", models.JSONField(blank=True, default=dict)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="takeaway_review_states", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "indexes": [
                    models.Index(fields=["user", "kind"], name="speaking_trs_user_kind_idx"),
                    models.Index(fields=["user", "updated_at"], name="speaking_trs_user_updated_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("user", "kind"), name="unique_takeaway_review_state_per_user_kind"),
                ],
            },
        ),
    ]
