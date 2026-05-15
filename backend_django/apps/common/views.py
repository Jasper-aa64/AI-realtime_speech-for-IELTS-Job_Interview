from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def health(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    return JsonResponse(
        {
            "ok": True,
            "service": "ielts-django-backend",
            "version": settings.PROJECT_VERSION,
            "owner": {
                "name": settings.PROJECT_OWNER_NAME,
                "email": settings.PROJECT_OWNER_EMAIL,
            },
            "database": {
                "vendor": connection.vendor,
                "alias": connection.alias,
            },
        }
    )
