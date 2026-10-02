import hashlib
import json
import mimetypes
import os
import stat
import subprocess
import uuid
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.models.entities import Media, MessageType
from app.services.errors import GatewayError


def validate_content(path, kind, suffix):
    if kind == MessageType.image:
        try:
            with Image.open(path) as image:
                image.verify()
                fmt = image.format
        except (OSError, UnidentifiedImageError, Image.DecompressionBombError, SyntaxError, ValueError):
            raise GatewayError("INVALID_IMAGE") from None
        allowed = {"JPEG": ({".jpg", ".jpeg"}, "image/jpeg"), "PNG": ({".png"}, "image/png")}
        if fmt not in allowed or suffix not in allowed[fmt][0]:
            raise GatewayError("UNSUPPORTED_IMAGE_FORMAT")
        return allowed[fmt][1]
    if kind in {MessageType.audio, MessageType.video}:
        audio_types = {".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".ogg": "audio/ogg"}
        if (kind == MessageType.audio and suffix not in audio_types) or (
            kind == MessageType.video and suffix != ".mp4"
        ):
            raise GatewayError("UNSUPPORTED_AV_FORMAT")
        try:
            result = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format",
                                     "-of", "json", str(path)], capture_output=True, timeout=20, check=True)
            data = json.loads(result.stdout)
        except FileNotFoundError:
            raise GatewayError("FFPROBE_UNAVAILABLE", 503) from None
        except (subprocess.SubprocessError, ValueError):
            raise GatewayError("INVALID_AV_FILE") from None
        streams = data.get("streams", [])
        audio = [s for s in streams if s.get("codec_type") == "audio"]
        video = [s for s in streams if s.get("codec_type") == "video" and not
                 s.get("disposition", {}).get("attached_pic")]
        fmt = set(data.get("format", {}).get("format_name", "").split(","))
        if kind == MessageType.audio:
            formats = {".mp3": {"mp3"}, ".m4a": {"mov", "mp4", "m4a"}, ".ogg": {"ogg"}}
            if not audio or video or not fmt.intersection(formats[suffix]):
                raise GatewayError("INVALID_AUDIO")
            return audio_types[suffix]
        if not video or any(s.get("codec_name") != "h264" for s in video) or any(
            s.get("codec_name") != "aac" for s in audio
        ) or not fmt.intersection({"mov", "mp4"}):
            raise GatewayError("UNSUPPORTED_VIDEO_CODEC")
        return "video/mp4"
    return mimetypes.guess_type("file" + suffix)[0] or "application/octet-stream"


def register_media(db, settings, request):
    name = request.filename
    if name in {".", ".."} or any(c in name for c in "/\\:") or any(ord(c) < 32 for c in name):
        raise GatewayError("INVALID_FILENAME")
    source = settings.incoming_dir.resolve() / name
    limit = {
        MessageType.image: settings.image_limit_bytes, MessageType.audio: settings.av_limit_bytes,
        MessageType.video: settings.av_limit_bytes, MessageType.document: settings.document_limit_bytes,
    }[request.type]
    suffix = Path(name).suffix.lower()
    # Generated storage names never contain user supplied path components.
    safe_suffix = suffix if suffix.isascii() and suffix[1:].isalnum() and len(suffix) <= 12 else ".bin"
    media_id = uuid.uuid4()
    storage_name = str(media_id) + safe_suffix
    settings.media_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = settings.media_dir / storage_name
    temp = target.with_suffix(target.suffix + ".partial")
    committed = False
    try:
        before_path = source.lstat()
        if not stat.S_ISREG(before_path.st_mode):
            raise GatewayError("FILE_NOT_REGULAR")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        with os.fdopen(os.open(source, flags), "rb") as src:
            before = os.fstat(src.fileno())
            if not stat.S_ISREG(before.st_mode) or (before.st_ino, before.st_dev) != (
                before_path.st_ino, before_path.st_dev
            ):
                raise GatewayError("FILE_CHANGED")
            if before.st_size <= 0:
                raise GatewayError("EMPTY_FILE")
            if before.st_size > limit:
                raise GatewayError("FILE_TOO_LARGE", 413)
            digest = hashlib.sha256()
            size = 0
            with temp.open("xb") as dst:
                while chunk := src.read(1024 * 1024):
                    size += len(chunk)
                    if size > limit:
                        raise GatewayError("FILE_TOO_LARGE", 413)
                    digest.update(chunk)
                    dst.write(chunk)
                dst.flush()
                os.fsync(dst.fileno())
            after = os.fstat(src.fileno())
            current = source.lstat()
            if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size, after.st_mtime_ns, after.st_ctime_ns
            ) or (current.st_ino, current.st_dev, current.st_mtime_ns) != (
                before.st_ino, before.st_dev, before.st_mtime_ns
            ) or size != before.st_size:
                raise GatewayError("FILE_CHANGED")
        mime = validate_content(temp, request.type, suffix)
        temp.replace(target)
        if os.name == "posix":
            target.chmod(0o440)
        media = Media(id=media_id, type=request.type, original_name=name, storage_name=storage_name,
                      mime_type=mime, size_bytes=size, sha256=digest.hexdigest())
        db.add(media)
        db.commit()
        committed = True
        return media
    except FileNotFoundError:
        raise GatewayError("FILE_NOT_FOUND", 404) from None
    except OSError:
        raise GatewayError("FILE_ACCESS_ERROR", 422) from None
    finally:
        temp.unlink(missing_ok=True)
        if not committed:
            target.unlink(missing_ok=True)
