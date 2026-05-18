from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("writing", "0004_writingprompt_image_url"),
    ]

    operations = [
        migrations.AddField(
            model_name="writingprompt",
            name="sort_order",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="writingprompt",
            name="source_book",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="writingprompt",
            name="source_question",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="writingprompt",
            name="source_test",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name="writingprompt",
            index=models.Index(fields=["task_type", "category", "is_active"], name="writing_wri_task_ty_19f4f8_idx"),
        ),
        migrations.AddIndex(
            model_name="writingprompt",
            index=models.Index(fields=["task_type", "source_book", "source_test", "source_question"], name="writing_wri_task_ty_e96f0d_idx"),
        ),
    ]
