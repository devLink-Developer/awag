"""Install the pinned API 35 image using verified HTTP ranges and sparse files.

No ZIP is stored on the VPS. File contents remain identical; zero blocks are holes.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import struct
import time
import urllib.request
import zipfile
import zlib

IMAGE_URL = "https://dl.google.com/android/repository/sys-img/google_apis/x86_64-35_r09.zip"
IMAGE_SHA1 = "0103e6dab21290c4b9d16550a3ce99476f884eef"
IMAGES = {
    "google_apis": (IMAGE_URL, IMAGE_SHA1),
    "default": ("https://dl.google.com/android/repository/sys-img/android/x86_64-35_r02.zip",
                "2d857d170c0d1b827149565da34b3383e5306f7f"),
}


def request(url, byte_range=None):
    headers = {"Range": byte_range} if byte_range else {}
    response = urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=120)
    if byte_range and response.status != 206:
        response.close()
        raise ValueError("HTTP range unsupported; refusing a full buffered download")
    return response


def install_image(destination, url=IMAGE_URL, checksum=IMAGE_SHA1, minimum_free=768 * 1024**2):
    destination = Path(destination)
    marker = destination / ".image-complete.json"
    if marker.exists() and json.loads(marker.read_text())["sha1"] == checksum:
        print("Pinned system image already installed", flush=True)
        return
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    digest, checked, updated = hashlib.sha1(), 0, time.monotonic()
    with request(url) as response:
        while block := response.read(1024**2):
            digest.update(block)
            checked += len(block)
            if time.monotonic() - updated > 30:
                print(f"Checksum stream: {checked} bytes", flush=True)
                updated = time.monotonic()
    if digest.hexdigest() != checksum:
        raise ValueError("System image archive checksum mismatch")
    print(f"Archive checksum verified: {checked} bytes", flush=True)
    with request(url, "bytes=-65536") as response:
        tail = response.read()
    position = tail.rfind(b"PK\x05\x06")
    if position < 0:
        raise ValueError("ZIP directory missing")
    end = list(struct.unpack("<4s4H2LH", tail[position:position + 22]))
    size, offset = end[5:7]
    with request(url, f"bytes={offset}-{offset + size - 1}") as response:
        directory = response.read()
    end[6] = 0
    with zipfile.ZipFile(io.BytesIO(directory + struct.pack("<4s4H2LH", *end))) as archive:
        members = archive.infolist()
    for member in members:
        path = PurePosixPath(member.filename)
        if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != "x86_64":
            raise ValueError("Unsafe system image archive path")
        if member.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            raise ValueError("Unsupported archive compression")
    zeros = bytes(4096)
    for member in members:
        relative = PurePosixPath(member.filename).relative_to("x86_64")
        target = destination.joinpath(*relative.parts)
        if member.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if target.exists():
            if target.stat().st_size == member.file_size:
                crc = 0
                with target.open("rb") as existing:
                    while block := existing.read(1024**2):
                        crc = zlib.crc32(block, crc)
                if crc == member.CRC:
                    continue
            raise ValueError("Existing image file differs; refusing to replace it")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".partial")
        if temporary.exists():
            raise ValueError("Interrupted partial file needs operator review")
        with request(url, f"bytes={member.header_offset}-{member.header_offset + 29}") as response:
            header = struct.unpack("<4s5H3L2H", response.read())
        if header[0] != b"PK\x03\x04":
            raise ValueError("Invalid ZIP member header")
        start = member.header_offset + 30 + header[-2] + header[-1]
        crc, count = 0, 0
        decoder = zlib.decompressobj(-zlib.MAX_WBITS) if member.compress_type == zipfile.ZIP_DEFLATED else None
        try:
            with temporary.open("xb") as output:
                def write(block):
                    nonlocal crc, count
                    if shutil.disk_usage(destination).free < minimum_free:
                        raise OSError("Disk reserve reached; stopping image preparation")
                    crc = zlib.crc32(block, crc)
                    count += len(block)
                    if count > member.file_size:
                        raise ValueError("Expanded file exceeds declared size")
                    for index in range(0, len(block), 4096):
                        chunk = block[index:index + 4096]
                        if chunk == zeros[:len(chunk)]:
                            output.seek(len(chunk), os.SEEK_CUR)
                        else:
                            output.write(chunk)
                if member.compress_size:
                    with request(url, f"bytes={start}-{start + member.compress_size - 1}") as response:
                        while compressed := response.read(65536):
                            if decoder is None:
                                write(compressed)
                            else:
                                pending = compressed
                                while pending:
                                    write(decoder.decompress(pending, 1024**2))
                                    pending = decoder.unconsumed_tail
                    if decoder is not None:
                        write(decoder.flush())
                        if not decoder.eof:
                            raise ValueError("Incomplete compressed file")
                if count != member.file_size or crc != member.CRC:
                    raise ValueError("System image member CRC/size mismatch")
                output.truncate(count)
                output.flush()
                os.fsync(output.fileno())
            temporary.chmod(0o444)
            temporary.rename(target)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        print(f"Installed {relative}: logical={count}, allocated={target.stat().st_blocks * 512 if hasattr(target.stat(), 'st_blocks') else count}", flush=True)
    marker.write_text(json.dumps({"sha1": checksum, "url": url}) + "\n")


def create_avd(root, variant="google_apis"):
    root = Path(root)
    avd = root / "avd" / "WhatsApp_QA.avd"
    avd.mkdir(parents=True, exist_ok=True, mode=0o700)
    (root / "adb").mkdir(exist_ok=True, mode=0o700)
    sysdir = f"/opt/android/system-images/android-35/{variant}/x86_64/"
    if (avd / "config.ini").exists():
        config = dict(line.split("=", 1) for line in (avd / "config.ini").read_text().splitlines() if "=" in line)
        if {key.strip(): value.strip() for key, value in config.items()}.get("image.sysdir.1") != sysdir:
            raise ValueError("Existing AVD uses another image; refusing to change persistent data")
    if not (avd / "config.ini").exists():
        values = {"AvdId": "WhatsApp_QA", "avd.ini.encoding": "UTF-8", "abi.type": "x86_64",
                  "hw.cpu.arch": "x86_64", "hw.cpu.ncore": "1", "hw.ramSize": "768",
                  "hw.lcd.width": "480", "hw.lcd.height": "800", "hw.lcd.density": "160",
                  "hw.gpu.enabled": "yes", "hw.gpu.mode": "swiftshader", "vm.heapSize": "128",
                  "disk.dataPartition.size": "1024M", "tag.id": variant,
                  "tag.display": "Google APIs" if variant == "google_apis" else "Default Android System Image",
                  "image.sysdir.1": sysdir,
                  "PlayStore.enabled": "false", "showDeviceFrame": "no", "fastboot.forceColdBoot": "yes"}
        (avd / "config.ini").write_text("\n".join(f"{key}={value}" for key, value in values.items()) + "\n")
    ini = root / "avd" / "WhatsApp_QA.ini"
    if not ini.exists():
        ini.write_text("avd.ini.encoding=UTF-8\npath=/data/avd/WhatsApp_QA.avd\npath.rel=WhatsApp_QA.avd\ntarget=android-35\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("/android"))
    parser.add_argument("--variant", choices=IMAGES, default="google_apis")
    args = parser.parse_args()
    url, checksum = IMAGES[args.variant]
    install_image(args.root / "system-images" / "android-35" / args.variant / "x86_64", url, checksum)
    create_avd(args.root, args.variant)
    print("Persistent software AVD prepared; existing userdata left unchanged", flush=True)
