# Local model definition

`coder.Modelfile` is the definition previously stored outside Git. The
manifest records the Ollama version and model digests observed on the
workstation. Models themselves are not committed.

```sh
ollama pull qwen3.6:27b
ollama pull nomic-embed-text
ollama create coder -f models/coder.Modelfile
uv run --locked scripts/plateforme.py verifier
```

Run these commands against the host Ollama used by the gateway. A tag can
change; compare its digest with `manifest.json` before accepting the result.
If the exact artifact is no longer available, restore a trusted model cache
or review a new digest and rerun the evaluations. Do not silently update the
manifest just to make the checker green.

The model is configured for a 65,536-token context. GPU memory requirements
and latency must be measured on a replacement workstation; installation of
the Python packages alone does not provision inference capacity.
