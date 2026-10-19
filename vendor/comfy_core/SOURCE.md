# Embedded inference modules

These third-party Python modules were copied from
[ComfyUI](https://github.com/Comfy-Org/ComfyUI) commit
`b0f4b7b294ce482a2e071d9d762c133d38c7aa07`.

Included: `comfy/`, `comfy_api/`, `comfy_execution/`, `utils/`,
`comfy_extras/nodes_qwen.py`, `nodes.py`, `folder_paths.py`,
`latent_preview.py`, `node_helpers.py`, `protocol.py`, and
`comfyui_version.py`. The ComfyUI web interface, server, custom-node manager,
and other application files are not included. GGF Qwen3 Edit starts only its
private inference worker process; it does not start a ComfyUI server.

`comfy_extras/nodes_model_advanced.py` and `comfy_extras/nodes_cfg.py` were
copied from ComfyUI commit `5a665890ded5020c282f63c4ea2dd9e083e025ff`
for the Qwen Image Edit 2509 sampling patches.

This embedded third-party code retains ComfyUI's GPLv3 license in `LICENSE`.
GGF Qwen3 Edit's own license does not replace the upstream license.
