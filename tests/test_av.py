import json
import shutil
import subprocess
from unittest.mock import Mock

import pytest

from app.models.entities import MessageType
from app.services.errors import GatewayError
from app.services.media import validate_content
from scripts.make_fixtures import make_fixtures


@pytest.mark.parametrize("kind,suffix,streams,fmt,mime", [
    (MessageType.audio, ".mp3", [{"codec_type": "audio", "codec_name": "mp3"}], "mp3", "audio/mpeg"),
    (MessageType.audio, ".m4a", [{"codec_type": "audio", "codec_name": "aac"}], "mov,mp4,m4a", "audio/mp4"),
    (MessageType.audio, ".ogg", [{"codec_type": "audio", "codec_name": "opus"}], "ogg", "audio/ogg"),
    (MessageType.video, ".mp4", [{"codec_type": "video", "codec_name": "h264"},
                                {"codec_type": "audio", "codec_name": "aac"}], "mov,mp4", "video/mp4"),
])
def test_av_metadata(monkeypatch, tmp_path, kind, suffix, streams, fmt, mime):
    result = Mock(stdout=json.dumps({"streams": streams, "format": {"format_name": fmt}}).encode())
    monkeypatch.setattr(subprocess, "run", Mock(return_value=result))
    assert validate_content(tmp_path / "media", kind, suffix) == mime


@pytest.mark.parametrize("streams,fmt", [([], "mov,mp4"),
    ([{"codec_type": "video", "codec_name": "hevc"}], "mov,mp4"),
    ([{"codec_type": "video", "codec_name": "h264"}, {"codec_type": "audio", "codec_name": "mp3"}], "mov,mp4"),
    ([{"codec_type": "video", "codec_name": "h264"}], "matroska")])
def test_reject_unsupported_video(monkeypatch, tmp_path, streams, fmt):
    result = Mock(stdout=json.dumps({"streams": streams, "format": {"format_name": fmt}}).encode())
    monkeypatch.setattr(subprocess, "run", Mock(return_value=result))
    with pytest.raises(GatewayError):
        validate_content(tmp_path / "media", MessageType.video, ".mp4")


def test_real_ffprobe(tmp_path):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("ffmpeg/ffprobe not installed on this host; exercised in Linux image")
    make_fixtures(tmp_path)
    assert validate_content(tmp_path / "qa-audio.mp3", MessageType.audio, ".mp3") == "audio/mpeg"
    assert validate_content(tmp_path / "qa-video.mp4", MessageType.video, ".mp4") == "video/mp4"
