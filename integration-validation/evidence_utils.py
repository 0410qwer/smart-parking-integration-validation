"""Preserve prior report versions before refreshing latest convenience files."""
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import shutil


def new_run_id():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ-') + uuid4().hex[:8]


def archive_existing(paths):
    existing = [Path(p) for p in paths if Path(p).is_file()]
    if existing:
        archive = existing[0].parent / 'history' / new_run_id()
        archive.mkdir(parents=True, exist_ok=False)
        for path in existing:
            shutil.copy2(path, archive / path.name)
        return archive
