"""Read a single connection secret from environment or a mounted file, never both."""

import os
from pathlib import Path


def resolve_secret(name, value=None, file_path=None):
    value = os.environ.get(name) if value is None else value
    file_path = os.environ.get(name + "_FILE") if file_path is None else file_path
    if value and file_path:
        raise ValueError(f"Configure only {name} or {name}_FILE")
    if file_path:
        try:
            path = Path(file_path)
            if not path.is_file() or path.stat().st_size > 16384:
                raise ValueError("Invalid secret file")
            value = path.read_text().strip()
        except OSError:
            raise ValueError("Secret file unavailable") from None
    if not value or "\n" in value or "\r" in value:
        raise ValueError(f"{name} is required and must be one line")
    return value
