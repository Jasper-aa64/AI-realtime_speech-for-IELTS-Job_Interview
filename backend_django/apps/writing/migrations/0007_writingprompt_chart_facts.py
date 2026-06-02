from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("writing", "0006_writingscore_analysis_payload"),
    ]

    operations = [
        migrations.AddField(
            model_name="writingprompt",
            name="chart_facts",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="writingprompt",
            name="chart_facts_status",
            field=models.CharField(default="none", max_length=32),
        ),
    ]
