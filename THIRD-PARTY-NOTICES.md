# Third-party notices

- Qwen Image Edit 2509 model: [Qwen/Qwen-Image-Edit-2509](https://huggingface.co/Qwen/Qwen-Image-Edit-2509), Apache License 2.0 according to its model card. The weights are fetched separately by the user and are never bundled in the app source or member ZIP.
- GGUF diffusion weights: [QuantStack/Qwen-Image-Edit-2509-GGUF](https://huggingface.co/QuantStack/Qwen-Image-Edit-2509-GGUF), downloaded separately by the user.
- Text encoder and VAE: [Comfy-Org/Qwen-Image_ComfyUI](https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI), downloaded separately by the user.
- Embedded inference modules: [ComfyUI](https://github.com/Comfy-Org/ComfyUI), GPLv3; see `vendor/comfy_core/SOURCE.md` and `vendor/comfy_core/LICENSE`.
- GGUF loader: [city96/ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF), Apache License 2.0; see `vendor/comfy_gguf/LICENSE`.
- Transformers runtime: [huggingface/transformers](https://github.com/huggingface/transformers), Apache License 2.0.
- Gradio interface: [gradio-app/gradio](https://github.com/gradio-app/gradio), Apache License 2.0.
- uv Python/environment manager: [astral-sh/uv](https://github.com/astral-sh/uv), MIT or Apache License 2.0.

The optional ComfyUI model-manager BAT in the member package is the legacy GGF script. It is separate from the standalone runtime.
