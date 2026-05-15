from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0002_legacybillinguser"),
    ]

    operations = [
        migrations.AddField(
            model_name="codexusageevent",
            name="metadata",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
