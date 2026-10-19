"""Private GGUF model selection, download and verification for Qwen Image Edit 2509."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

APP = Path(__file__).resolve().parent
MODEL_DIR = APP / "models" / "qwen-edit-2509-gguf"
SETTINGS = APP / "runtime" / "model-settings.json"
RECEIPTS = MODEL_DIR / "receipts"
DEFAULT_REPO = "QuantStack/Qwen-Image-Edit-2509-GGUF"
ENCODER_REPO = "Comfy-Org/Qwen-Image_ComfyUI"
ENCODER_FILE = "split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors"
VAE_FILE = "split_files/vae/qwen_image_vae.safetensors"
QUANTS = (
    "Q2_K", "Q3_K_S", "Q3_K_M", "Q4_0", "Q4_1", "Q4_K_S", "Q4_K_M",
    "Q5_0", "Q5_1", "Q5_K_S", "Q5_K_M", "Q6_K", "Q8_0",
)
DEFAULT_QUANT = "Q4_K_M"
ALLOWED_HOSTS = {"huggingface.co", "www.huggingface.co", "hf-mirror.com"}


def gguf_name(quant: str) -> str:
    if quant not in QUANTS:
        raise ValueError("Select one of the listed GGUF quantizations.")
    return f"Qwen-Image-Edit-2509-{quant}.gguf"


def selected_quant() -> str:
    try:
        choice = json.loads(SETTINGS.read_text(encoding="utf-8")).get("quant")
        return choice if choice in QUANTS else DEFAULT_QUANT
    except (OSError, ValueError):
        return DEFAULT_QUANT


def save_quant(quant: str) -> str:
    gguf_name(quant)
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps({"quant": quant}, indent=2) + "\n", encoding="utf-8")
    return f"Selected {quant}. Download it below if it is not yet installed. Other downloaded quants remain on this PC."


def repo_from_url(value: str) -> tuple[str, str]:
    value = (value or "").strip() or f"https://huggingface.co/{DEFAULT_REPO}"
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS or parsed.username or parsed.password:
        raise ValueError("Enter an HTTPS Hugging Face GGUF repository page URL.")
    pieces = [p for p in parsed.path.split("/") if p]
    if len(pieces) != 2 or not all(re.fullmatch(r"[A-Za-z0-9_.-]+", p) for p in pieces):
        raise ValueError("Use the model repository page, not an individual weight-file URL.")
    if parsed.query or parsed.fragment:
        raise ValueError("Remove query parameters and fragments from the repository URL.")
    return "/".join(pieces), "https://hf-mirror.com" if parsed.hostname == "hf-mirror.com" else "https://huggingface.co"


def _receipt_path(quant: str) -> Path:
    return RECEIPTS / f"{quant}.json"


def _read_receipt(quant: str) -> dict | None:
    try:
        return json.loads(_receipt_path(quant).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def verify(quant: str | None = None) -> tuple[bool, str]:
    quant = quant or selected_quant()
    gguf_name(quant)
    receipt = _read_receipt(quant)
    if not receipt or receipt.get("quant") != quant:
        return False, f"{quant} is not installed. Open Settings to download this quant and its support models."
    required = {gguf_name(quant), ENCODER_FILE, VAE_FILE}
    files = receipt.get("files", [])
    if {item.get("path") for item in files} != required:
        return False, f"{quant} download record is incomplete. Resume in Settings."
    for item in files:
        path = MODEL_DIR / item["path"]
        if not path.is_file() or path.stat().st_size != item.get("size"):
            return False, f"Missing or partial model file: {item['path']}. Resume in Settings."
    return True, f"{quant} GGUF and both support models installed and verified."


def installed_receipt(quant: str | None = None) -> dict | None:
    quant = quant or selected_quant()
    return _read_receipt(quant) if verify(quant)[0] else None


def _file_info(repo: str, name: str, endpoint: str) -> dict:
    from huggingface_hub import HfApi
    info = HfApi(endpoint=endpoint).model_info(repo, files_metadata=True)
    sibling = next((item for item in info.siblings if item.rfilename == name), None)
    if sibling is None:
        raise RuntimeError(f"{repo} does not contain {name}.")
    size = sibling.size or (sibling.lfs or {}).get("size")
    if not size or int(size) < 100_000_000:
        raise RuntimeError(f"Cannot confirm the size of {repo}/{name}; download stopped.")
    return {"repo": repo, "revision": info.sha, "path": name, "size": int(size),
            "sha256": (sibling.lfs or {}).get("sha256", "")}


def _verify_hash(path: Path, expected: str) -> None:
    if not expected:
        return
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest().lower() != expected.lower():
        raise RuntimeError(f"Integrity check failed for {path.name}. Resume the download.")


def download(url: str, quant: str | None = None, report=print) -> str:
    from huggingface_hub import hf_hub_download

    quant = quant or selected_quant()
    name = gguf_name(quant)
    repo, endpoint = repo_from_url(url)
    report(f"Checking {quant} and its two support models…")
    files = [_file_info(repo, name, endpoint),
             _file_info(ENCODER_REPO, ENCODER_FILE, "https://huggingface.co"),
             _file_info(ENCODER_REPO, VAE_FILE, "https://huggingface.co")]
    old = _read_receipt(quant)
    if old and old.get("files") == files and verify(quant)[0]:
        return f"{quant} is already installed."
    total = sum(item["size"] for item in files) / 1e9
    report(f"Downloading {quant} and support files, about {total:.1f} GB total; existing files will be reused.")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    for index, item in enumerate(files, 1):
        target = MODEL_DIR / item["path"]
        valid_existing = target.is_file() and target.stat().st_size == item["size"]
        if valid_existing:
            try:
                _verify_hash(target, item["sha256"])
            except RuntimeError:
                archived = target.with_name(f"{target.name}.previous-{datetime.now():%Y%m%d-%H%M%S}")
                target.rename(archived)
                report(f"Existing file did not match this source. Preserved it as {archived.name}.")
                valid_existing = False
        if valid_existing:
            report(f"Using existing file {index}/3: {target.name}")
        else:
            report(f"Downloading file {index}/3: {target.name} ({item['size'] / 1e9:.1f} GB)")
            hf_hub_download(repo_id=item["repo"], filename=item["path"], revision=item["revision"],
                            endpoint=endpoint if index == 1 else "https://huggingface.co",
                            local_dir=MODEL_DIR)
        if not target.is_file() or target.stat().st_size != item["size"]:
            raise RuntimeError(f"Download incomplete: {target.name}. Press Install again to resume.")
        report(f"Checking integrity of {target.name}…")
        _verify_hash(target, item["sha256"])
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    _receipt_path(quant).write_text(json.dumps({"quant": quant, "files": files}, indent=2) + "\n", encoding="utf-8")
    return verify(quant)[1]
