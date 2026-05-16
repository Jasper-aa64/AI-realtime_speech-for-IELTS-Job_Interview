from django.conf import settings
from django.db import connection
from django.http import FileResponse, Http404, JsonResponse
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


def frontend_asset(request, asset_path: str = "index.html"):
    normalized = (asset_path or "index.html").lstrip("/")
    if normalized in {"", "."}:
        normalized = "index.html"
    allowed = {"index.html": "text/html; charset=utf-8", "app.js": "text/javascript; charset=utf-8", "styles.css": "text/css; charset=utf-8"}
    if normalized not in allowed:
        raise Http404("Static asset not found")
    path = settings.BASE_DIR.parent / "web" / "static" / normalized
    if not path.exists():
        raise Http404("Static asset not found")
    response = FileResponse(open(path, "rb"), content_type=allowed[normalized])
    response["Cache-Control"] = "no-store"
    return response
