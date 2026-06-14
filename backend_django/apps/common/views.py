from django.conf import settings
from django.db import connection
from django.http import FileResponse, Http404, HttpResponseNotModified, JsonResponse
from django.utils.http import http_date
from django.views.decorators.http import require_GET
from django.views.static import was_modified_since


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
    allowed = {
        "index.html": "text/html; charset=utf-8",
        "shared-ui.js": "text/javascript; charset=utf-8",
        "writing-image-preload.js": "text/javascript; charset=utf-8",
        "writing-image-viewer.js": "text/javascript; charset=utf-8",
        "writing-prompt-picker.js": "text/javascript; charset=utf-8",
        "corpus-markdown-editor.js": "text/javascript; charset=utf-8",
        "corpus-takeaway.js": "text/javascript; charset=utf-8",
        "spelling-drill.js": "text/javascript; charset=utf-8",
        "candidate-profile.js": "text/javascript; charset=utf-8",
        "realtime-pcm-uplink.js": "text/javascript; charset=utf-8",
        "speaking-audio-preprocessor-runtime.js": "text/javascript; charset=utf-8",
        "api-client.js": "text/javascript; charset=utf-8",
        "appearance.js": "text/javascript; charset=utf-8",
        "view-router.js": "text/javascript; charset=utf-8",
        "app.js": "text/javascript; charset=utf-8",
        "styles.css": "text/css; charset=utf-8",
    }
    if normalized not in allowed:
        raise Http404("Static asset not found")
    path = settings.BASE_DIR.parent / "web" / "static" / normalized
    if not path.exists():
        raise Http404("Static asset not found")
    response = FileResponse(open(path, "rb"), content_type=allowed[normalized])
    response["Cache-Control"] = frontend_cache_control(request, is_index=normalized == "index.html")
    return response


def frontend_cache_control(request, *, is_index: bool = False) -> str:
    if is_index:
        return "no-store"
    if request.GET.get("v"):
        return "public, max-age=31536000, immutable"
    return "no-cache"


def _conditional_file_response(request, path, *, content_type=None, max_age: int = 604800):
    """Serve a file with a 7-day cache + Last-Modified/If-Modified-Since 304.

    Image/asset bytes are effectively immutable, so once a client has a copy it
    can revalidate with a cheap 304 after expiry instead of re-downloading the
    whole file.
    """
    stat_result = path.stat()
    last_modified = stat_result.st_mtime
    if not was_modified_since(request.META.get("HTTP_IF_MODIFIED_SINCE"), last_modified):
        response = HttpResponseNotModified()
    elif content_type is not None:
        response = FileResponse(open(path, "rb"), content_type=content_type)
    else:
        response = FileResponse(open(path, "rb"))
    response["Cache-Control"] = f"public, max-age={max_age}"
    response["Last-Modified"] = http_date(last_modified)
    return response


@require_GET
def frontend_static_asset(request, asset_path: str):
    normalized = (asset_path or "").lstrip("/")
    if not normalized or ".." in normalized.split("/"):
        raise Http404("Static asset not found")
    path = settings.BASE_DIR.parent / "web" / "static" / "assets" / normalized
    if not path.exists() or not path.is_file():
        raise Http404("Static asset not found")
    return _conditional_file_response(request, path)


@require_GET
def frontend_wasm_asset(request, asset_path: str):
    normalized = (asset_path or "").lstrip("/")
    if not normalized or ".." in normalized.split("/"):
        raise Http404("Static asset not found")
    path = settings.BASE_DIR.parent / "web" / "static" / "wasm" / normalized
    if not path.exists() or not path.is_file():
        raise Http404("Static asset not found")
    content_types = {
        ".html": "text/html; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
        ".wasm": "application/wasm",
    }
    return _conditional_file_response(request, path, content_type=content_types.get(path.suffix))


@require_GET
def frontend_vendor_asset(request, asset_path: str):
    normalized = (asset_path or "").lstrip("/")
    if not normalized or any(part in {"", ".", ".."} for part in normalized.split("/")):
        raise Http404("Static asset not found")
    vendor_root = (settings.BASE_DIR.parent / "web" / "static" / "vendor").resolve()
    path = (vendor_root / normalized).resolve()
    try:
        path.relative_to(vendor_root)
    except ValueError:
        raise Http404("Static asset not found")
    if not path.exists() or not path.is_file():
        raise Http404("Static asset not found")
    content_types = {
        ".js": "text/javascript; charset=utf-8",
    }
    response = FileResponse(open(path, "rb"), content_type=content_types.get(path.suffix))
    response["Cache-Control"] = frontend_cache_control(request)
    return response
