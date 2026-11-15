"""Generate local-only credentials, refusing to overwrite existing configuration."""

import secrets
from pathlib import Path


def main():
    target = Path(__file__).resolve().parents[1] / ".env"
    if target.exists():
        print(".env already exists; leaving it unchanged")
        return
    with target.open("x") as f:
        f.write("POSTGRES_PASSWORD=" + secrets.token_hex(24) + "\n")
    target.chmod(0o600)
    print("Created .env with a random local password")


if __name__ == "__main__":
    main()
