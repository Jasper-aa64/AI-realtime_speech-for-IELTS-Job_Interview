from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ai", "0002_aitask_attempt_count_aitask_available_at_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="aitask",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("running", "Running"),
                    ("succeeded", "Succeeded"),
                    ("failed", "Failed"),
                    ("fallback", "Fallback"),
                    ("cancelled", "Cancelled"),
                ],
                default="pending",
                max_length=24,
            ),
        ),
    ]
