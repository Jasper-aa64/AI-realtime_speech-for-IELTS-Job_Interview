from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UserOwnedModel(TimeStampedModel):
    user = models.ForeignKey("accounts.CustomUser", on_delete=models.CASCADE)

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=["user", "created_at"]),
        ]
