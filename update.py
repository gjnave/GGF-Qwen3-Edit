"""Recoverable source update from a repository's current main revision."""
from __future__ import annotations

import io
import json
import shutil
import sys
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

APP = Path(__file__).resolve().parent
RUNTIME = APP / "runtime"
RECEIPT = RUNTIME / "source-revision.json"
HOSTS = (
    ("Codeberg", "https://codeberg.org/api/v1/repos/Cognibuild/GGF-Qwen3-Edit/branches/main",
     "https://codeberg.org/Cognibuild/GGF-Qwen3-Edit/archive/{sha}.zip"),
    ("GitHub", "https://api.github.com/repos/gjnave/GGF-Qwen3-Edit/commits/main",
     "https://github.com/gjnave/GGF-Qwen3-Edit/archive/{sha}.zip"),
)
REQUIRED = {"app.py", "worker.py", "model_store.py", "update.py", "requirements.txt"}


def _read(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "GGF-Qwen3-Edit-Updater/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def source() -> tuple[str, str, bytes]:
    failures = []
    for name, api, archive in HOSTS:
        try:
            info = json.loads(_read(api))
            sha = info.get("commit", {}).get("id") if name == "Codeberg" else info.get("sha")
            if not sha or len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha.lower()):
                raise ValueError("Repository did not return a valid commit ID")
            return name, sha, _read(archive.format(sha=sha))
        except Exception as error:
            failures.append(f"{name}: {error}")
    raise RuntimeError("Could not check either source repository. " + "; ".join(failures))


def update() -> str:
    name, sha, archive_bytes = source()
    if RECEIPT.is_file() and json.loads(RECEIPT.read_text(encoding="utf-8")).get("sha") == sha:
        return f"Already current: {sha[:12]} from {name}."
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    staging = RUNTIME / f"update-stage-{stamp}-{sha[:12]}"
    backup = APP / "update-backups" / f"{stamp}-{sha[:12]}"
    staging.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as bundle:
        members = [item for item in bundle.infolist() if not item.is_dir()]
        roots = {item.filename.split("/", 1)[0] for item in members}
        if len(roots) != 1:
            raise ValueError("Source archive has an unexpected layout")
        files = {}
        for item in members:
            parts = Path(item.filename).parts
            if len(parts) < 2 or ".." in parts or "\\" in item.filename or ":" in item.filename:
                raise ValueError(f"Unsafe source archive path: {item.filename}")
            relative = Path(*parts[1:])
            if relative.parts[0] in {"models", "outputs", "jobs", "runtime", ".venv", "update-backups"}:
                raise ValueError(f"Source archive contains app data: {relative}")
            files[str(relative).replace("\\", "/")] = item
        if not REQUIRED.issubset(files):
            raise ValueError("Source archive is missing required app files")
        for relative, item in files.items():
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(item) as source_file, target.open("wb") as target_file:
                shutil.copyfileobj(source_file, target_file)
    backup.mkdir(parents=True, exist_ok=False)
    for relative in files:
        target = APP / relative
        staged = staging / relative
        if target.exists():
            old = backup / relative
            old.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, old)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(staged, target)
    RUNTIME.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps({"host": name, "sha": sha, "updated_at": stamp}) + "\n", encoding="utf-8")
    return f"Updated to {sha[:12]} from {name}. Previous source files backed up at {backup}."


if __name__ == "__main__":
    try:
        print(update())
    except Exception as error:
        print(f"Update stopped: {error}", file=sys.stderr)
        raise SystemExit(1)
