"""App-owned Qwen Image Edit 2509 model download and verification."""
from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path
from urllib.parse import urlparse

APP = Path(__file__).resolve().parent
MODEL_DIR = APP / "models" / "qwen-image-edit-2509"
RECEIPT = MODEL_DIR / "ggf-model-receipt.json"
DEFAULT_REPO = "Qwen/Qwen-Image-Edit-2509"
REQUIRED_PARTS = ("model_index.json", "transformer/", "text_encoder/", "vae/", "processor/")
ALLOWED_HOSTS = {"huggingface.co", "www.huggingface.co", "hf-mirror.com"}


def repo_from_url(value: str) -> tuple[str, str]:
    """Accept a model repository URL, never an arbitrary file or local URL."""
    value = (value or "").strip() or f"https://huggingface.co/{DEFAULT_REPO}"
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS or parsed.username or parsed.password:
        raise ValueError("Enter an HTTPS Hugging Face model page, such as https://huggingface.co/Qwen/Qwen-Image-Edit-2509.")
    pieces = [p for p in parsed.path.split("/") if p]
    if len(pieces) != 2 or not all(p not in (".", "..") and re.fullmatch(r"[A-Za-z0-9_.-]+", p) for p in pieces):
        raise ValueError("Use the model repository page URL, not an individual weight-file link.")
    if parsed.query or parsed.fragment:
        raise ValueError("Remove URL query parameters and fragments from the model page link.")
    return "/".join(pieces), "https://hf-mirror.com" if parsed.hostname == "hf-mirror.com" else "https://huggingface.co"


def _file_entries(info) -> list[dict]:
    entries = []
    for sibling in info.siblings:
        name = sibling.rfilename
        path = Path(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
            raise RuntimeError(f"The model repository has an unsafe file path: {name}")
        if name.startswith((".", "README")):
            continue
        size = sibling.size or (sibling.lfs or {}).get("size")
        if size is None:
            raise RuntimeError(f"The model host did not provide a file size for {name}; refusing an unverifiable download.")
        entries.append({"name": name, "size": int(size), "sha256": (sibling.lfs or {}).get("sha256", "")})
    for part in REQUIRED_PARTS:
        if not any(item["name"] == part or item["name"].startswith(part) for item in entries):
            raise RuntimeError(f"This repository is not a complete Qwen Image Edit pipeline: missing {part}")
    return entries


def fetch_manifest(repo: str, endpoint: str) -> dict:
    from huggingface_hub import HfApi
    info = HfApi(endpoint=endpoint).model_info(repo, files_metadata=True)
    return {"repo": repo, "endpoint": endpoint, "revision": info.sha, "files": _file_entries(info)}


def verify(manifest: dict | None = None) -> tuple[bool, str]:
    if manifest is None:
        if not RECEIPT.is_file():
            return False, "Model not installed. Open Settings to download it to this PC."
        try:
            manifest = json.loads(RECEIPT.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return False, "Model receipt is unreadable. Resume the download in Settings."
    files = manifest.get("files", [])
    if not files or not manifest.get("revision"):
        return False, "Model receipt is incomplete. Resume the download in Settings."
    for item in files:
        path = MODEL_DIR / item["name"]
        if not path.is_file() or path.stat().st_size != item["size"]:
            return False, f"Missing or partial model file: {item['name']}. Resume in Settings."
    return True, f"Installed and verified: {manifest['repo']} ({len(files)} files)."


def installed_receipt() -> dict | None:
    ready, _ = verify()
    return json.loads(RECEIPT.read_text(encoding="utf-8")) if ready else None


def disk_progress(manifest: dict) -> tuple[int, int, int]:
    files = manifest["files"]
    present = sum(1 for item in files if (MODEL_DIR / item["name"]).is_file()
                  and (MODEL_DIR / item["name"]).stat().st_size == item["size"])
    bytes_ready = sum(item["size"] for item in files if (MODEL_DIR / item["name"]).is_file()
                      and (MODEL_DIR / item["name"]).stat().st_size == item["size"])
    return present, len(files), bytes_ready


def verify_hashes(manifest: dict, report=print) -> None:
    weighted = [item for item in manifest["files"] if item.get("sha256")]
    for index, item in enumerate(weighted, 1):
        report(f"Verifying downloaded model file {index} of {len(weighted)}: {item['name']}")
        digest = hashlib.sha256()
        with (MODEL_DIR / item["name"]).open("rb") as handle:
            for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest().lower() != item["sha256"].lower():
            raise RuntimeError(f"Integrity check failed for {item['name']}. Resume the model download.")


def download(url: str, report=print) -> str:
    repo, endpoint = repo_from_url(url)
    report(f"Checking {repo} model file list…")
    manifest = fetch_manifest(repo, endpoint)
    current = installed_receipt()
    if current and current.get("repo") == repo and current.get("revision") == manifest["revision"]:
        return f"Already installed and verified: {repo}."
    total_gb = sum(item["size"] for item in manifest["files"]) / 1e9
    report(f"Downloading {len(manifest['files'])} files, about {total_gb:.1f} GB, to this PC. Partial files can be resumed.")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    from huggingface_hub import snapshot_download
    snapshot_download(repo_id=repo, revision=manifest["revision"], endpoint=endpoint,
                      local_dir=MODEL_DIR, allow_patterns=[item["name"] for item in manifest["files"]],
                      max_workers=4)
    ready, message = verify(manifest)
    if not ready:
        raise RuntimeError(message)
    verify_hashes(manifest, report)
    manifest["sha256_verified"] = True
    RECEIPT.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return message
