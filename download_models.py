"""Child-process entry point so the UI can stop only its own download."""
import json
import os
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent
os.environ.setdefault("HF_HOME", str(APP / "runtime" / "huggingface"))
from model_store import download


def report(message):
    print(json.dumps({"status": message}), flush=True)


if __name__ == "__main__":
    try:
        report(download(sys.argv[1], report))
        print(json.dumps({"complete": True}), flush=True)
    except Exception as exc:
        detail = str(exc)
        if "gated" in detail.lower() or "401" in detail or "403" in detail:
            detail += " Open the model page in your browser, accept any access terms, and sign in with a Hugging Face token on this PC before resuming."
        print(json.dumps({"error": detail}), flush=True)
        raise SystemExit(1)
