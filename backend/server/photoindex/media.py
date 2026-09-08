import os
import re
import subprocess
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, HttpResponse, StreamingHttpResponse
from django.utils import timezone
from PIL import Image, ImageOps

from .services import resolve_asset_path


def preview_path(asset):
    root = Path(settings.PHOTO_PREVIEW_CACHE)
    return root / str(asset.id)[:2] / f"{asset.id}.webp"


def cleanup_preview_cache():
    root = Path(settings.PHOTO_PREVIEW_CACHE)
    if not root.exists():
        return
    cutoff = timezone.now().timestamp() - settings.PHOTO_PREVIEW_TTL_DAYS * 86400
    files = [item for item in root.rglob("*.webp") if item.is_file()]
    for item in files:
        if item.stat().st_atime < cutoff:
            item.unlink(missing_ok=True)
    files = sorted((item for item in root.rglob("*.webp") if item.is_file()), key=lambda item: item.stat().st_atime)
    total = sum(item.stat().st_size for item in files)
    ceiling = settings.PHOTO_PREVIEW_CACHE_MAX_BYTES
    for item in files:
        if total <= ceiling:
            break
        size = item.stat().st_size
        item.unlink(missing_ok=True)
        total -= size


def ensure_preview(asset):
    target = preview_path(asset)
    if target.exists():
        os.utime(target, None)
        return target
    original = resolve_asset_path(asset)
    if not original.exists():
        raise FileNotFoundError(original)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp.webp")
    if asset.media_kind == "video":
        command = [
            settings.FFMPEG_BINARY, "-hide_banner", "-loglevel", "error", "-y", "-ss", "1",
            "-i", str(original), "-frames:v", "1", "-vf", "scale='min(1600,iw)':-2", "-c:v", "libwebp",
            "-quality", "75", str(temporary),
        ]
        subprocess.run(command, check=True, timeout=90, capture_output=True)
    else:
        if original.suffix.lower() in {".heic", ".heif"}:
            import pillow_heif
            pillow_heif.register_heif_opener()
        with Image.open(original) as image:
            image.seek(0)
            image = ImageOps.exif_transpose(image)
            image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGB")
            image.save(temporary, "WEBP", quality=75, method=4, exif=b"")
    temporary.replace(target)
    cleanup_preview_cache()
    return target


def preview_response(asset):
    path = ensure_preview(asset)
    response = FileResponse(path.open("rb"), content_type="image/webp")
    response["Cache-Control"] = "private, max-age=86400"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def original_response(request, asset):
    path = resolve_asset_path(asset)
    if not path.exists():
        raise FileNotFoundError(path)
    size = path.stat().st_size
    range_header = request.headers.get("Range", "")
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header)
    filename = re.sub(r"[^A-Za-z0-9._ -]", "_", asset.filename)
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Disposition": f'inline; filename="{filename}"',
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
    }
    if not range_header:
        response = FileResponse(path.open("rb"), content_type=asset.mime_type)
        for key, value in headers.items():
            response[key] = value
        response["Content-Length"] = size
        return response
    if not match:
        response = HttpResponse(status=416)
        response["Content-Range"] = f"bytes */{size}"
        return response
    first, last = match.groups()
    if not first:
        suffix_length = int(last or 0)
        if suffix_length <= 0:
            response = HttpResponse(status=416)
            response["Content-Range"] = f"bytes */{size}"
            return response
        start = max(0, size - suffix_length)
        end = size - 1
    else:
        start = int(first)
        end = int(last) if last else size - 1
    if start >= size or end < start:
        response = HttpResponse(status=416)
        response["Content-Range"] = f"bytes */{size}"
        return response
    end = min(end, size - 1)
    length = end - start + 1

    def iterator():
        remaining = length
        with path.open("rb") as stream:
            stream.seek(start)
            while remaining:
                chunk = stream.read(min(1024 * 256, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    response = StreamingHttpResponse(iterator(), status=206, content_type=asset.mime_type)
    for key, value in headers.items():
        response[key] = value
    response["Content-Length"] = length
    response["Content-Range"] = f"bytes {start}-{end}/{size}"
    return response
