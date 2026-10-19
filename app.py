"""GGF Qwen3 Edit: standalone Windows image editor with optional phone UI."""
from __future__ import annotations

import argparse
import html
import ipaddress
import json
import os
import queue
import socket
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import gradio as gr
from PIL import Image, ImageOps

from access import MODES, load as load_access, save as save_access, verify as verify_access
from model_store import APP, DEFAULT_REPO, MODEL_DIR, installed_receipt, verify as verify_model

ASSETS = APP / "assets"
OUTPUTS = APP / "outputs"
JOBS = APP / "jobs"
CSS = (APP / "ui.css").read_text(encoding="utf-8")
ACTIVE_LOCK = threading.Lock()
ACTIVE_PROCESS: subprocess.Popen | None = None
ACTIVE_KIND = ""
ACTIVE_LINK = ""
ACTIVE_LOCAL = ""
ACTIVE_ACCESS = "local"

CTRL_ENTER = """() => {
  if (window.__ggfQwenShortcut) return;
  window.__ggfQwenShortcut = true;
  document.addEventListener('keydown', event => {
    if (!event.ctrlKey || event.key !== 'Enter' || event.repeat || event.isComposing) return;
    const button = document.querySelector('#ggf-generate button, button#ggf-generate');
    if (!button || button.disabled || button.offsetParent === null) return;
    event.preventDefault(); button.click();
  });
}"""


def model_status() -> str:
    ready, note = verify_model()
    return (f"<div class='model-ready'>✓ {note}</div>" if ready else
            f"<div class='model-missing'>Model download required on this PC. {note}</div>")


def _claim(process: subprocess.Popen, kind: str) -> bool:
    global ACTIVE_PROCESS, ACTIVE_KIND
    with ACTIVE_LOCK:
        if ACTIVE_PROCESS is not None and ACTIVE_PROCESS.poll() is None:
            return False
        ACTIVE_PROCESS, ACTIVE_KIND = process, kind
    def clear_on_exit():
        global ACTIVE_PROCESS, ACTIVE_KIND
        process.wait()
        with ACTIVE_LOCK:
            if ACTIVE_PROCESS is process:
                ACTIVE_PROCESS, ACTIVE_KIND = None, ""
    threading.Thread(target=clear_on_exit, daemon=True).start()
    return True


def _busy() -> str:
    with ACTIVE_LOCK:
        return ACTIVE_KIND if ACTIVE_PROCESS is not None and ACTIVE_PROCESS.poll() is None else ""


def _start(command: list[str], kind: str, log: Path) -> subprocess.Popen:
    if _busy():
        raise RuntimeError(f"The PC is already busy with {_busy()}. Finish or stop it before starting another job.")
    log.parent.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(command, cwd=APP, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, encoding="utf-8", errors="replace", bufsize=1,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    if not _claim(process, kind):
        process.terminate()
        raise RuntimeError("Another job started at the same time. Try again after it finishes.")
    return process


def _stop() -> str:
    with ACTIVE_LOCK:
        process, kind = ACTIVE_PROCESS, ACTIVE_KIND
    if process is None or process.poll() is not None:
        return "Nothing is running."
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
    else:
        process.terminate()
    return f"Stopping {kind}. Saved outputs and partial model downloads remain on disk."


def _lines(process: subprocess.Popen, log: Path):
    messages: queue.Queue[str | None] = queue.Queue()
    def reader():
        with log.open("a", encoding="utf-8") as handle:
            for line in process.stdout:
                handle.write(line)
                handle.flush()
                messages.put(line)
        messages.put(None)
    threading.Thread(target=reader, daemon=True).start()
    while True:
        try:
            line = messages.get(timeout=1.0)
        except queue.Empty:
            yield None
            continue
        if line is None:
            return
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            if line.strip():
                yield {"detail": line.strip()[:240]}


def _job_dir() -> Path:
    path = JOBS / f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def generate(first, second, third, prompt, negative, steps, cfg, seed, preview=False):
    yield None, "⏳ Starting generation · checking inputs…", gr.update(interactive=False), gr.update(interactive=False)
    try:
        if not prompt or not prompt.strip():
            raise ValueError("Tell the app what should change in the image.")
        if not first:
            raise ValueError("Upload the image you want to edit.")
        ready, note = verify_model()
        if not ready:
            raise ValueError(f"{note} Go to Settings and install models first.")
        if _busy():
            raise RuntimeError(f"This PC is already running {_busy()}.")
        job = _job_dir()
        images = []
        for index, source in enumerate((first, second, third), 1):
            if not source:
                continue
            target = job / f"input-{index}.png"
            with Image.open(source) as opened:
                ImageOps.exif_transpose(opened).convert("RGB").save(target)
            images.append(str(target))
        label = "PREVIEW-" if preview else ""
        result = OUTPUTS / f"GGF-Qwen3-Edit-{label}{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}.png"
        request = {"images": images, "prompt": prompt.strip(), "negative_prompt": negative,
                   "steps": 12 if preview else int(steps), "cfg": float(cfg), "seed": int(seed),
                   "megapixels": 0.45 if preview else 1.0, "output": str(result)}
        request_path = job / "request.json"
        request_path.write_text(json.dumps(request, indent=2), encoding="utf-8")
        process = _start([sys.executable, "-u", str(APP / "worker.py"), str(request_path)],
                         "image generation", job / "worker.log")
        finished = False
        began = time.monotonic()
        stage = "Loading or preparing the model…"
        for message in _lines(process, job / "worker.log"):
            if message is None:
                elapsed = int(time.monotonic() - began)
                yield None, f"<progress></progress> ⏳ {html.escape(stage)} · {elapsed}s elapsed", gr.update(interactive=False), gr.update(interactive=False)
            elif "complete" in message:
                finished = True
                yield str(result), f"✓ Generation complete · seed {message['seed']} · saved to {result.name}", gr.update(interactive=True), gr.update(interactive=True)
            elif "error" in message:
                yield None, f"Generation stopped: {html.escape(message['error'])}", gr.update(interactive=True), gr.update(interactive=True)
            elif "status" in message:
                current = message["status"]
                stage = current
                step = message.get("step")
                progress = (f"<progress value='{step}' max='{message['total']}'></progress> " if step else
                            "<progress></progress> ")
                yield None, progress + html.escape(current), gr.update(interactive=False), gr.update(interactive=False)
        process.wait()
        if not finished and process.returncode != 0:
            yield None, f"Generation stopped. See {job / 'worker.log'} for details.", gr.update(interactive=True), gr.update(interactive=True)
    except Exception as error:
        yield None, f"Could not generate: {html.escape(str(error))}", gr.update(interactive=True), gr.update(interactive=True)


def quick_preview(*args):
    yield from generate(*args, preview=True)


def latest_output():
    files = sorted(OUTPUTS.glob("GGF-Qwen3-Edit-*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None, "No saved output yet."
    return str(files[0]), f"Loaded saved output: {files[0].name}"


def install_models(url):
    yield model_status(), "⏳ Checking model source…", gr.update(interactive=False), gr.update(interactive=False), gr.update(interactive=False)
    try:
        if _busy():
            raise RuntimeError(f"This PC is already running {_busy()}.")
        job = _job_dir()
        process = _start([sys.executable, "-u", str(APP / "download_models.py"), url],
                         "model download", job / "download.log")
        last = "Downloading to this PC…"
        for message in _lines(process, job / "download.log"):
            if message is None:
                size = sum(p.stat().st_size for p in MODEL_DIR.rglob("*") if p.is_file()) / 1e9 if MODEL_DIR.exists() else 0
                yield model_status(), f"⏳ {last} · about {size:.1f} GB now in the model folder.", gr.update(interactive=False), gr.update(interactive=False), gr.update(interactive=False)
            elif "error" in message:
                last = message["error"]
                yield model_status(), f"Download stopped: {last}", gr.update(interactive=True), gr.update(interactive=False), gr.update(interactive=False)
            elif "status" in message:
                last = message["status"]
                yield model_status(), f"⏳ {last}", gr.update(interactive=False), gr.update(interactive=False), gr.update(interactive=False)
        process.wait()
        if process.returncode == 0:
            yield model_status(), "✓ Model download complete and files verified. You can now create an image.", gr.update(interactive=True), gr.update(interactive=True), gr.update(interactive=True)
        else:
            yield model_status(), f"Download incomplete. {last} Partial files remain; press Install again to resume.", gr.update(interactive=True), gr.update(interactive=False), gr.update(interactive=False)
    except Exception as error:
        yield model_status(), f"Download could not start: {error}", gr.update(interactive=True), gr.update(interactive=False), gr.update(interactive=False)


def phone_status() -> str:
    return f"Local PC: {ACTIVE_LOCAL or 'starting'} · Phone: {ACTIVE_LINK or 'off'}"


def phone_url(local_url: str) -> str:
    port = urlparse(local_url).port
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("1.1.1.1", 80))
            return f"http://{probe.getsockname()[0]}:{port}/"
    except OSError:
        for candidate in socket.gethostbyname_ex(socket.gethostname())[2]:
            address = ipaddress.ip_address(candidate)
            if address.is_private and not address.is_loopback and not address.is_link_local:
                return f"http://{candidate}:{port}/"
        return f"Find this PC's Wi-Fi IP address and open port {port} on your phone."


def liz_media(name: str):
    clip = ASSETS / name
    if clip.is_file():
        gr.Video(value=str(clip), interactive=False, show_label=False, height=225)
    else:
        gr.Image(value=str(ASSETS / "liz-guide.png"), interactive=False, show_label=False, height=225)


def stop_server() -> str:
    if _busy():
        return "Stop the current job before shutting down this app."
    def exit_later():
        time.sleep(1.5)
        os._exit(0)
    threading.Thread(target=exit_later, daemon=True).start()
    return "Server stopping. Restart RUN.bat on this PC to use it again."


def build_ui():
    missing = not verify_model()[0]
    settings = load_access()
    receipt = installed_receipt()
    saved_source = f"{receipt['endpoint']}/{receipt['repo']}" if receipt else f"https://huggingface.co/{DEFAULT_REPO}"
    default_mode = next(label for label, mode in MODES.items() if mode == settings["mode"])
    with gr.Blocks(title="GGF Qwen3 Edit") as demo:
        with gr.Column(elem_id="ggf-shell"):
            gr.HTML("<div id='ggf-hero'><div class='kicker'>GET GOING FAST · LOCAL AI</div><h1>GGF Qwen3 Edit</h1>"
                    "<p>Change an image with plain words. Add reference images when they help.</p>"
                    "<div class='links'><a href='https://getgoingfast.pro/tools/qwen3edit/' target='_blank'>GetGoingFast.pro ↗</a>"
                    "<a href='https://youtube.com/@TheAIHobbyGuy' target='_blank'>The AI Hobby Guy ↗</a></div></div>")
            header_model_note = gr.HTML(model_status(), elem_id="ggf-model-state")
            with gr.Tabs(selected="settings" if missing else "create"):
                with gr.Tab("Create", id="create"):
                    gr.Markdown("Upload the image you want to edit. References are optional. The PC runs the model; a phone can control this page.")
                    with gr.Row():
                        first = gr.Image(label="Your image · required", type="filepath", sources=["upload", "clipboard"])
                        second = gr.Image(label="Reference 1 · optional", type="filepath", sources=["upload", "clipboard"])
                        third = gr.Image(label="Reference 2 · optional", type="filepath", sources=["upload", "clipboard"])
                    prompt = gr.Textbox(label="What should change?", lines=4, placeholder="Example: Keep the person the same, but change the jacket to red leather.")
                    with gr.Accordion("More control", open=False):
                        negative = gr.Textbox(label="Things to avoid · optional", value="")
                        steps = gr.Slider(label="Generation steps", minimum=10, maximum=80, value=40, step=1)
                        cfg = gr.Slider(label="Prompt guidance", minimum=1, maximum=8, value=4, step=0.5)
                        seed = gr.Number(label="Seed · -1 chooses a new one", value=-1, precision=0)
                    preview_button = gr.Button("Quick preview · smaller image, fewer steps", variant="secondary", interactive=not missing)
                    generate_button = gr.Button("Generate edit · Ctrl+Enter", variant="primary", elem_id="ggf-generate", interactive=not missing)
                    stop = gr.Button("Stop current job · keep files", variant="secondary")
                    status = gr.HTML("Ready." if not missing else "Install the model in Settings before generating.", elem_id="ggf-status")
                    output = gr.Image(label="Your edited image", interactive=False, height=520)
                    latest = gr.Button("Show latest saved image on this PC")
                with gr.Tab("Settings", id="settings"):
                    gr.Markdown("### First, download the model to this PC")
                    with gr.Column(visible=missing, elem_id="ggf-liz-guide") as guide:
                        with gr.Column(visible=True) as step_one:
                            gr.Markdown("### LiZ · getting started")
                            liz_media("liz-qwen-download.mp4")
                            gr.Markdown("**First download the Qwen Image Edit model to your PC.** A phone can control the app, but the model stays and runs on the PC.")
                            next_button = gr.Button("Next · make your first edit", variant="primary")
                            skip = gr.Button("Skip introduction")
                        with gr.Column(visible=False) as step_two:
                            liz_media("liz-qwen-create.mp4")
                            gr.Markdown("Upload an image, describe your change, and optionally add reference pictures. Then press Generate.")
                            done = gr.Button("Show model download", variant="primary")
                    replay = gr.Button("Meet LiZ · replay the guide", visible=not missing)
                    model_note = gr.HTML(model_status(), elem_id="ggf-model-installed")
                    url = gr.Textbox(label="Model source URL · change only if you use another Hugging Face repository", value=saved_source)
                    gr.Markdown("The default is the official Qwen Image Edit 2509 model. This large download stays on the PC, resumes after interruption, and is checked before the app marks it installed. Other repository URLs must contain the same complete Diffusers pipeline structure.")
                    install = gr.Button("Install / resume model download on this PC", variant="primary")
                    install_status = gr.Markdown("Choose Install to begin. The first download may need roughly 60 GB plus working space.")
                    stop_download = gr.Button("Stop current download · keep partial files")
                    refresh = gr.Button("Refresh installed status")
                    gr.Markdown("### Use it from your phone")
                    gr.Markdown("Your PC generates the image and must stay on. Choose Wi-Fi for your own network, or a temporary link for access elsewhere. Restart the app after saving.")
                    mode = gr.Dropdown(label="Phone access", choices=list(MODES), value=default_mode)
                    username = gr.Textbox(label="Remote username · optional when password is blank", value=settings["username"])
                    password = gr.Textbox(label="Remote password · optional", type="password")
                    save_phone = gr.Button("Save phone settings")
                    access_note = gr.Markdown(phone_status())
                    save_note = gr.Markdown()
                    gr.Markdown("### App controls")
                    release = gr.Button("Release models / free GPU memory")
                    release_note = gr.Markdown("The model runs in a separate worker and is released after each job.")
                    shutdown = gr.Button("Stop server", variant="secondary")
                    confirm = gr.Button("Confirm: stop this app; restart it on the PC later", visible=False)
                    shutdown_note = gr.Markdown()
            gr.HTML("<div id='ggf-footer'>Powered by Qwen Image Edit 2509 · Get Going Fast makes the local workflow easier.</div>")

        generate_button.click(generate, inputs=[first, second, third, prompt, negative, steps, cfg, seed],
                              outputs=[output, status, generate_button, preview_button], show_progress="minimal")
        preview_button.click(quick_preview, inputs=[first, second, third, prompt, negative, steps, cfg, seed],
                             outputs=[output, status, generate_button, preview_button], show_progress="minimal")
        stop.click(_stop, outputs=[status], queue=False)
        latest.click(latest_output, outputs=[output, status], queue=False)
        install.click(install_models, inputs=[url], outputs=[model_note, install_status, install, generate_button, preview_button], show_progress="minimal")
        stop_download.click(_stop, outputs=[install_status], queue=False)
        refresh.click(lambda: (model_status(), model_status(), gr.update(interactive=verify_model()[0]), gr.update(interactive=verify_model()[0])),
                      outputs=[model_note, header_model_note, generate_button, preview_button], queue=False)
        next_button.click(lambda: (gr.update(visible=False), gr.update(visible=True)), outputs=[step_one, step_two], queue=False)
        skip.click(lambda: (gr.update(visible=False), gr.update(visible=True)), outputs=[guide, replay], queue=False)
        done.click(lambda: (gr.update(visible=False), gr.update(visible=True)), outputs=[guide, replay], queue=False)
        replay.click(lambda: (gr.update(visible=True), gr.update(visible=True), gr.update(visible=False), gr.update(visible=False)),
                     outputs=[guide, step_one, step_two, replay], queue=False)
        save_phone.click(lambda m, u, p: save_access(m, u, p), inputs=[mode, username, password], outputs=[save_note], queue=False)
        release.click(lambda: "The worker releases GPU memory after every job." if not _busy() else "Stop the current job first.",
                      outputs=[release_note], queue=False)
        shutdown.click(lambda: gr.update(visible=True), outputs=[confirm], queue=False)
        confirm.click(stop_server, outputs=[shutdown_note], queue=False)
        demo.load(phone_status, outputs=[access_note], queue=False, js=CTRL_ENTER)
    return demo


def launch_one(demo, port, **kwargs):
    for candidate in range(port, port + 30):
        try:
            return demo.launch(server_port=candidate, prevent_thread_lock=True, show_error=True,
                               allowed_paths=[str(OUTPUTS), str(ASSETS)], css=CSS,
                               theme=gr.themes.Base(primary_hue="amber", neutral_hue="slate"), **kwargs)
        except OSError as error:
            if "Cannot find empty port" not in str(error) and getattr(error, "winerror", None) != 10048:
                raise
    raise RuntimeError("No free app port found.")


def main():
    global ACTIVE_ACCESS, ACTIVE_LINK, ACTIVE_LOCAL
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--port", type=int, default=7874)
    args = parser.parse_args()
    OUTPUTS.mkdir(exist_ok=True)
    JOBS.mkdir(exist_ok=True)
    settings = load_access()
    ACTIVE_ACCESS = settings["mode"]
    local = build_ui().queue(default_concurrency_limit=1)
    _, ACTIVE_LOCAL, _ = launch_one(local, args.port, server_name="127.0.0.1", share=False,
                                    auth=None, inbrowser=not args.no_browser)
    print(f"Local app (no login): {ACTIVE_LOCAL}", flush=True)
    if ACTIVE_ACCESS != "local":
        try:
            remote = build_ui().queue(default_concurrency_limit=1)
            auth = (lambda u, p: verify_access(u, p, settings)) if settings["hash"] else None
            _, remote_local, public = launch_one(remote, args.port + 1000,
                server_name="0.0.0.0" if ACTIVE_ACCESS == "lan" else "127.0.0.1",
                share=ACTIVE_ACCESS == "public", auth=auth, inbrowser=False)
            ACTIVE_LINK = public or (phone_url(remote_local) if ACTIVE_ACCESS == "lan" else remote_local)
            print(f"Phone access: {ACTIVE_LINK}", flush=True)
        except Exception as error:
            print(f"Phone access failed: {error}. Local app remains available.", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        _stop()


if __name__ == "__main__":
    main()
