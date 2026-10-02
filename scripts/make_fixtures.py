"""Create small real test files, without using third-party media."""
import argparse
import subprocess
from pathlib import Path

from PIL import Image


def make_fixtures(directory):
    directory.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (160, 120), (20, 130, 180)).save(directory / "qa-image.png")
    (directory / "qa-document.txt").write_text("Documento de prueba QA\n", encoding="utf-8")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=1", "-c:a", "libmp3lame", str(directory / "qa-audio.mp3")],
                   check=True, timeout=30)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "color=c=blue:s=160x120:r=15:d=1", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=1", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", "-movflags", "+faststart", str(directory / "qa-video.mp4")],
                   check=True, timeout=30)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    make_fixtures(parser.parse_args().directory)
