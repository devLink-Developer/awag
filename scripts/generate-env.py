"""Create a local .env without printing credentials or replacing an existing file."""
import os
import secrets
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    target = root / ".env"
    if target.exists():
        raise SystemExit(".env already exists; left unchanged")
    pg, redis, token = (secrets.token_hex(32) for _ in range(3))
    values = {
        "POSTGRES_PASSWORD": pg, "REDIS_PASSWORD": redis, "API_TOKEN": token,
        "DATABASE_URL": f"postgresql+psycopg://gateway:{pg}@127.0.0.1:5432/gateway",
        "REDIS_URL": f"redis://:{redis}@127.0.0.1:6379/0",
    }
    lines = []
    for line in (root / ".env.example").read_text(encoding="utf-8").splitlines():
        key = line.split("=", 1)[0]
        lines.append(key + "=" + values[key] if key in values else line)
    with target.open("x", encoding="utf-8", newline="\n") as output:
        output.write("\n".join(lines) + "\n")
    os.chmod(target, 0o600)
    for directory in ["incoming", "media", "screenshots"]:
        path = root / "data" / directory
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name == "posix":
            path.chmod(0o700)
    print("Created .env and data directories; no credentials printed")


if __name__ == "__main__":
    main()
