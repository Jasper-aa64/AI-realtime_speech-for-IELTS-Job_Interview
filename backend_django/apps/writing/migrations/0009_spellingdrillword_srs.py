import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("writing", "0008_spellingdrillword"),
    ]

    operations = [
        migrations.AddField(
            model_name="spellingdrillword",
            name="review_stage",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="spellingdrillword",
            name="due_at",
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AddField(
            model_name="spellingdrillword",
            name="lapses",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddIndex(
            model_name="spellingdrillword",
            index=models.Index(
                fields=["user", "status", "due_at"],
                name="writing_sp_usr_st_due_idx",
            ),
        ),
    ]
