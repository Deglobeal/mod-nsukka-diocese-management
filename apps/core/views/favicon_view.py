from django.conf import settings
from django.http import FileResponse, Http404


def favicon_view(request):
    icon_path = settings.BASE_DIR / "static" / "favicon.ico"
    if not icon_path.is_file():
        raise Http404("Favicon not found")
    return FileResponse(
        icon_path.open("rb"),
        content_type="image/vnd.microsoft.icon",
    )
