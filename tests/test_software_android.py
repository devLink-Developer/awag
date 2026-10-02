import hashlib
import io
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from scripts.prepare_software_android import create_avd, install_image


@pytest.fixture
def archive_server():
    buffer = io.BytesIO()
    payload = b"\0" * 16384 + b"android-image" * 500
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("x86_64/system.img", payload)
    state = {"data": buffer.getvalue(), "corrupt_range": False}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            data = state["data"]
            byte_range = self.headers.get("Range")
            if byte_range:
                left, right = byte_range.removeprefix("bytes=").split("-")
                start = max(0, len(data) - int(right)) if not left else int(left)
                end = len(data) - 1 if not left or not right else int(right)
                body = data[start:end + 1]
                if state["corrupt_range"] and start == 30 + len("x86_64/system.img"):
                    body = body[:-2]
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
            else:
                body = data
                self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield state, f"http://127.0.0.1:{server.server_port}/image.zip", payload
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def test_verified_range_install_and_repeat(tmp_path, archive_server):
    state, url, payload = archive_server
    checksum = hashlib.sha1(state["data"]).hexdigest()
    install_image(tmp_path, url, checksum, minimum_free=0)
    assert (tmp_path / "system.img").read_bytes() == payload
    assert (tmp_path / ".image-complete.json").exists()
    # A successful repeat uses the completion marker without changing data.
    state["data"] = b"unavailable"
    install_image(tmp_path, url, checksum, minimum_free=0)
    assert (tmp_path / "system.img").read_bytes() == payload


def test_archive_checksum_rejected_before_extraction(tmp_path, archive_server):
    _, url, _ = archive_server
    with pytest.raises(ValueError, match="checksum mismatch"):
        install_image(tmp_path, url, "0" * 40, minimum_free=0)
    assert not list(tmp_path.iterdir())


def test_truncated_member_leaves_no_partial_or_marker(tmp_path, archive_server):
    state, url, _ = archive_server
    state["corrupt_range"] = True
    with pytest.raises(ValueError, match="Incomplete|CRC/size"):
        install_image(tmp_path, url, hashlib.sha1(state["data"]).hexdigest(), minimum_free=0)
    assert not list(tmp_path.iterdir())


def test_archive_traversal_rejected(tmp_path, archive_server):
    state, url, _ = archive_server
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("x86_64/../outside", b"unsafe")
    state["data"] = buffer.getvalue()
    with pytest.raises(ValueError, match="Unsafe"):
        install_image(tmp_path, url, hashlib.sha1(state["data"]).hexdigest(), minimum_free=0)
    assert not list(tmp_path.iterdir())


def test_disk_reserve_cleans_partial(tmp_path, archive_server):
    state, url, _ = archive_server
    with pytest.raises(OSError, match="Disk reserve"):
        install_image(tmp_path, url, hashlib.sha1(state["data"]).hexdigest(), minimum_free=2**63)
    assert not list(tmp_path.iterdir())


def test_avd_preserves_userdata_and_rejects_image_switch(tmp_path):
    create_avd(tmp_path, "default")
    userdata = tmp_path / "avd" / "WhatsApp_QA.avd" / "userdata-qemu.img"
    userdata.write_bytes(b"persistent-session")
    create_avd(tmp_path, "default")
    assert userdata.read_bytes() == b"persistent-session"
    with pytest.raises(ValueError, match="another image"):
        create_avd(tmp_path, "google_apis")
    assert userdata.read_bytes() == b"persistent-session"
