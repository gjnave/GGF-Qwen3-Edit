"""One-shot Diffusers worker: GPU memory is released when this process exits."""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

from PIL import Image, ImageOps

from model_store import MODEL_DIR, verify


def emit(**fields):
    print(json.dumps(fields), flush=True)


def main(request_path: Path) -> None:
    request = json.loads(request_path.read_text(encoding="utf-8"))
    ready, message = verify()
    if not ready:
        raise RuntimeError(message)
    emit(status="Loading Qwen Image Edit 2509. Large models can take several minutes to load…")
    import torch
    from diffusers import QwenImageEditPlusPipeline

    if not torch.cuda.is_available():
        raise RuntimeError("An NVIDIA GPU with a compatible CUDA driver is required.")
    images = []
    for source in request["images"]:
        with Image.open(source) as opened:
            images.append(ImageOps.exif_transpose(opened).convert("RGB"))
    if not images:
        raise ValueError("Upload an image to edit.")
    source_width, source_height = images[0].size
    target_pixels = float(request.get("megapixels", 1.0)) * 1024 * 1024
    scale = math.sqrt(target_pixels / (source_width * source_height))
    width = max(256, min(2048, round(source_width * scale / 16) * 16))
    height = max(256, min(2048, round(source_height * scale / 16) * 16))
    pipe = QwenImageEditPlusPipeline.from_pretrained(str(MODEL_DIR), torch_dtype=torch.bfloat16,
                                                       use_safetensors=True, local_files_only=True)
    free_bytes, _total_bytes = torch.cuda.mem_get_info()
    if free_bytes < 19 * 1024 ** 3:
        emit(status="Limited free GPU memory. Using slower low-memory offload; close other GPU apps for speed…")
        pipe.enable_sequential_cpu_offload()
    else:
        pipe.enable_model_cpu_offload()
    emit(status="Model loaded. Preparing image and prompt…")
    seed = int(request["seed"])
    if seed < 0:
        seed = int.from_bytes(os.urandom(4), "little")
    generator = torch.Generator(device="cpu").manual_seed(seed)

    def step_callback(_pipe, step, _timestep, values):
        emit(step=step + 1, total=int(request["steps"]), status=f"Generating · step {step + 1} of {request['steps']}")
        return values

    result = pipe(image=images if len(images) > 1 else images[0], prompt=request["prompt"],
                  negative_prompt=request.get("negative_prompt") or " ",
                  true_cfg_scale=float(request["cfg"]), num_inference_steps=int(request["steps"]),
                  width=width, height=height,
                  generator=generator, callback_on_step_end=step_callback,
                  callback_on_step_end_tensor_inputs=[]).images[0]
    output = Path(request["output"])
    output.parent.mkdir(parents=True, exist_ok=True)
    result.save(output)
    emit(complete=str(output), seed=seed)


if __name__ == "__main__":
    try:
        main(Path(sys.argv[1]))
    except Exception as exc:
        emit(error=f"{type(exc).__name__}: {exc}")
        raise SystemExit(1)
