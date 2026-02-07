# Test configuration
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

# Add repo root to path so tests can import modules
sys.path.insert(0, str(REPO_ROOT))

# Prefer local model cache for offline-safe tests
model_cache = REPO_ROOT / "model_cache"
if model_cache.exists():
    os.environ["SENTENCE_TRANSFORMERS_HOME"] = str(model_cache / "sentence_transformers")
    os.environ["HF_HOME"] = str(model_cache / "huggingface")
    os.environ["HF_HUB_CACHE"] = str(model_cache / "huggingface" / "hub")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
