"""File-system locations (works from source and from a PyInstaller bundle)."""
import os
import sys
from pathlib import Path


def resource_path(rel: str) -> str:
    base = getattr(sys, "_MEIPASS", None) or Path(__file__).resolve().parent.parent
    return str(Path(base) / rel)


def data_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or Path.home()) / "DNSChanger"
    else:
        base = Path.home() / ".dnschanger"
    base.mkdir(parents=True, exist_ok=True)
    return base
