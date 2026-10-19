# GGF Qwen3 Edit

<a href="https://getgoingfast.pro/tools/qwen3edit/"><img src="https://getgoingfast.pro/assets/images/qwen3edit.png" alt="Qwen image editing example" width="720"></a>

An app-owned Windows image editor for [Qwen Image Edit 2509](https://huggingface.co/Qwen/Qwen-Image-Edit-2509). Upload an image, describe the change, add up to two optional references, and generate. Its private worker uses the embedded Comfy inference core with a selectable [GGUF diffusion model](https://huggingface.co/QuantStack/Qwen-Image-Edit-2509-GGUF). It does not use or launch your separate ComfyUI installation. Models download into this app's own `models` folder through Settings. A phone can control the app while the Windows PC performs the generation.

The [Get Going Fast Qwen3 Edit page](https://getgoingfast.pro/tools/qwen3edit/) has the member quick installer. This source repository is for manual setup and review; it intentionally does not include the member installer BAT.

## Manual Windows setup

1. Install the [uv Windows executable](https://docs.astral.sh/uv/getting-started/installation/) and make it available on PATH.
2. In Command Prompt, from this repository folder, run `uv venv --managed-python --python 3.11 .venv`.
3. Run `uv pip install --python .venv\Scripts\python.exe --index-url https://download.pytorch.org/whl/cu130 torch==2.11.0 torchvision==0.26.0 torchaudio==2.11.0`.
4. Run `uv pip install --python .venv\Scripts\python.exe -r requirements.txt`.
5. Run `.venv\Scripts\python.exe app.py`. In Settings, choose a GGUF quant and download it. The default Q4_K_M and two support files total about 22.7 GB. Downloads can be resumed; other quants can be added later without repeating the shared support files.
6. To use a phone, choose My Wi-Fi or Temporary phone link under Settings, save, then restart the app. The PC must remain on.

The member package includes `UPDATE.bat`; close the app before running it. Updates download the current source revision from Codeberg or GitHub, back up existing source files, and preserve local models, outputs, and settings.

Use an NVIDIA driver compatible with CUDA 13 (Windows R580.88 or newer). The CUDA 13 PyTorch build supports Turing (RTX 20 series) and newer NVIDIA architectures; smaller cards may offload more model data to RAM and run slowly. The app runs image inference in a one-shot worker so the model is released from GPU memory after each job. `outputs/`, `jobs/`, `.venv/`, and `models/` are local data, not source files. If a phone disconnects, use **Show latest saved image on this PC** to reopen a completed result.

The original ComfyUI model manager is distributed separately with the member package in an optional `ComfyUI` folder. It is not required for this standalone app. The app-local core is derived from ComfyUI and the GGUF loader from ComfyUI-GGUF; their notices and licenses are kept under `vendor/`.
