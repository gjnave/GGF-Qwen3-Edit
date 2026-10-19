# GGF Qwen3 Edit

<a href="https://getgoingfast.pro/tools/qwen3edit/"><img src="https://getgoingfast.pro/assets/images/qwen3edit.png" alt="Qwen image editing example" width="720"></a>

An app-owned Windows image editor for [Qwen Image Edit 2509](https://huggingface.co/Qwen/Qwen-Image-Edit-2509). Upload an image, describe the change, add up to two optional references, and generate. No ComfyUI installation or server is needed. The model downloads into this app's own `models` folder through Settings. A phone can control the app while the Windows PC performs the generation.

The [Get Going Fast Qwen3 Edit page](https://getgoingfast.pro/tools/qwen3edit/) has the member quick installer. This source repository is for manual setup and review; it intentionally does not include the member installer BAT.

## Manual Windows setup

1. Install the [uv Windows executable](https://docs.astral.sh/uv/getting-started/installation/) and make it available on PATH.
2. In Command Prompt, from this repository folder, run `uv venv --managed-python --python 3.11 .venv`.
3. Run `uv pip install --python .venv\Scripts\python.exe --index-url https://download.pytorch.org/whl/cu128 torch==2.11.0 torchvision==0.26.0`.
4. Run `uv pip install --python .venv\Scripts\python.exe -r requirements.txt`.
5. Run `.venv\Scripts\python.exe app.py`. In Settings, download the default official model to this PC. The first model download is large (roughly 60 GB) and can be resumed.
6. To use a phone, choose My Wi-Fi or Temporary phone link under Settings, save, then restart the app. The PC must remain on.

The member package includes `UPDATE.bat`; close the app before running it. Updates download the current source revision from Codeberg or GitHub, back up existing source files, and preserve local models, outputs, and settings.

Use a current NVIDIA driver. The app runs image inference in a one-shot worker so the model is released from GPU memory after each job. `outputs/`, `jobs/`, `.venv/`, and `models/` are local data, not source files. If a phone disconnects, use **Show latest saved image on this PC** to reopen a completed result.

The original ComfyUI model manager is distributed separately with the member package in an optional `ComfyUI` folder. It is not required for this standalone app.
