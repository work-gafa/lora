import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_DISABLE_XET"] = "1"
from huggingface_hub import snapshot_download

p = snapshot_download("IDEA-Research/grounding-dino-tiny",
                      local_dir="vlm/grounding-dino-tiny")
print("DONE", p)
