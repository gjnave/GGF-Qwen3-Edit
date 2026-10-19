"""One-shot app-local Comfy core worker with a GGUF diffusion model."""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

from PIL import Image, ImageOps

from model_store import ENCODER_FILE, MODEL_DIR, VAE_FILE, gguf_name, verify

APP = Path(__file__).resolve().parent
CORE = APP / "vendor" / "comfy_core"
VENDOR = APP / "vendor"


def emit(**fields):
    print(json.dumps(fields), flush=True)


def _image_tensor(path: str, width: int, height: int):
    import numpy as np
    import torch

    with Image.open(path) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
        if image.width * image.height > 32_000_000 or max(image.size) > 8192:
            raise ValueError("Reference image exceeds 32 megapixels or 8192 pixels on one side.")
        image = image.resize((width, height), Image.Resampling.LANCZOS)
        return torch.from_numpy(np.asarray(image, dtype=np.float32).copy() / 255).unsqueeze(0)


def main(request_path: Path) -> None:
    request = json.loads(request_path.read_text(encoding="utf-8"))
    quant = str(request["quant"])
    ready, message = verify(quant)
    if not ready:
        raise RuntimeError(message)
    if not (CORE / "nodes.py").is_file() or not (VENDOR / "comfy_gguf" / "nodes.py").is_file():
        raise RuntimeError("App-local Comfy core or GGUF loader is missing. Reinstall the app source.")
    emit(status=f"Loading Qwen Image Edit 2509 {quant} with the app-local Comfy core…")
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("An NVIDIA GPU with a compatible CUDA driver is required.")
    if not request["images"]:
        raise ValueError("Upload an image to edit.")
    with Image.open(request["images"][0]) as source:
        source_width, source_height = ImageOps.exif_transpose(source).size
    target_pixels = float(request.get("megapixels", 1.0)) * 1024 * 1024
    scale = math.sqrt(target_pixels / (source_width * source_height))
    width = max(256, min(2048, round(source_width * scale / 32) * 32))
    height = max(256, min(2048, round(source_height * scale / 32) * 32))
    images = [_image_tensor(source, width, height) for source in request["images"]]
    os.chdir(CORE)
    sys.path.insert(0, str(CORE))
    sys.path.insert(0, str(VENDOR))
    sys.argv = [sys.argv[0], "--models-directory", str(MODEL_DIR)]
    import folder_paths
    import nodes
    folder_paths.add_model_folder_path("diffusion_models", str(MODEL_DIR), is_default=True)
    folder_paths.add_model_folder_path("text_encoders", str(MODEL_DIR / "split_files" / "text_encoders"), is_default=True)
    folder_paths.add_model_folder_path("vae", str(MODEL_DIR / "split_files" / "vae"), is_default=True)
    from comfy_gguf.nodes import UnetLoaderGGUF
    from comfy_extras.nodes_cfg import CFGNorm
    from comfy_extras.nodes_model_advanced import ModelSamplingAuraFlow
    from comfy_extras.nodes_qwen import TextEncodeQwenImageEditPlus

    model = UnetLoaderGGUF().load_unet(gguf_name(quant))[0]
    clip = nodes.CLIPLoader().load_clip(Path(ENCODER_FILE).name, "qwen_image", "default")[0]
    vae = nodes.VAELoader().load_vae(Path(VAE_FILE).name)[0]
    model = ModelSamplingAuraFlow().patch_aura(model, 3.0)[0]
    model = CFGNorm.execute(model, 1.0, False)[0]
    emit(status="Model loaded. Encoding your image and prompt…")
    references = (images + [None, None, None])[:3]
    with torch.no_grad():
        positive = TextEncodeQwenImageEditPlus.execute(
            clip, request["prompt"], vae=vae,
            image1=references[0], image2=references[1], image3=references[2])[0]
        negative = TextEncodeQwenImageEditPlus.execute(
            clip, request.get("negative_prompt") or "", vae=vae,
            image1=references[0], image2=references[1], image3=references[2])[0]
        latent = nodes.VAEEncode().encode(vae, images[0])[0]
    seed = int(request["seed"])
    if seed < 0:
        seed = int.from_bytes(os.urandom(4), "little")
    import latent_preview
    original_callback_factory = latent_preview.prepare_callback

    def progress_callback_factory(model_for_preview, total_steps, x0_output_dict=None):
        base_callback = original_callback_factory(model_for_preview, total_steps, x0_output_dict)

        def report_step(step, x0, x, count):
            base_callback(step, x0, x, count)
            emit(step=step + 1, total=count,
                 status=f"Generating · step {step + 1} of {count} · {quant}")

        return report_step

    latent_preview.prepare_callback = progress_callback_factory
    emit(status=f"Generating {width} × {height} image · {request['steps']} steps with {quant}…")
    with torch.no_grad():
        sampled = nodes.KSampler().sample(
            model=model, seed=seed, steps=int(request["steps"]), cfg=float(request["cfg"]),
            sampler_name="euler", scheduler="simple", positive=positive, negative=negative,
            latent_image=latent, denoise=1.0)[0]
        pixels = nodes.VAEDecode().decode(vae, sampled)[0][0]
    import numpy as np
    result = Image.fromarray((pixels.detach().cpu().numpy().clip(0, 1) * 255).astype(np.uint8))
    output = Path(request["output"])
    output.parent.mkdir(parents=True, exist_ok=True)
    result.save(output)
    emit(complete=str(output), seed=seed, quant=quant)


if __name__ == "__main__":
    try:
        main(Path(sys.argv[1]))
    except Exception as exc:
        emit(error=f"{type(exc).__name__}: {exc}")
        raise SystemExit(1)
