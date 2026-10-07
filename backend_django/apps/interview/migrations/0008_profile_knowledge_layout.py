from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("interview", "0007_assistant_attachments"),
    ]

    operations = [
        migrations.AddField(
            model_name="interviewprofile",
            name="knowledge_layout",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
