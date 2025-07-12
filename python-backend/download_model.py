# python-backend/download_model.py
"""
Download and cache the FunASR streaming model for offline usage.
This script is run during Docker build to pre-cache the model.
"""

import logging
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

MODEL_NAME = "paraformer-zh-streaming"   # exact HF / ModelScope repo name
MODEL_REV  = "v2.0.4"                    # keep in sync with server code

def download_model():
    """Download and cache the FunASR model."""
    logging.info(f"Attempting to download model '{MODEL_NAME}' (rev {MODEL_REV})...")
    
    try:
        from funasr import AutoModel
        
        # Instantiating AutoModel downloads and caches the model
        model = AutoModel(
            model=MODEL_NAME,
            model_revision=MODEL_REV,
            mode="online",
            device="cpu",
            hub="hf",        # use 'ms' if you prefer ModelScope's mirror
        )
        logging.info("Model cached successfully.")
        return True
        
    except ImportError:
        logging.warning("FunASR not available, model download skipped.")
        return False
    except Exception as exc:
        logging.exception(f"Model download failed: {exc}")
        return False

if __name__ == "__main__":
    success = download_model()
    if not success:
        logging.info("Model download failed or skipped. The application will use mock mode.")
        # Don't exit with error code to allow Docker build to continue
        exit(0)
