# python-backend/download_model.py
"""
Download and cache the ModelScope ASR streaming model for offline usage.
This script is run during Docker build to pre-cache the model.
"""

import logging
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

MODEL_NAME = "iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-online"   # ModelScope repo name
MODEL_REV  = "v2.0.4"                    # keep in sync with server code

def download_model():
    """Download and cache the ModelScope ASR model."""
    logging.info(f"Attempting to download ModelScope model '{MODEL_NAME}' (rev {MODEL_REV})...")
    
    try:
        from modelscope.pipelines import pipeline
        from modelscope.utils.constant import Tasks
        from modelscope.utils.logger import get_logger as get_ms_logger
        
        # 设置ModelScope日志级别
        ms_logger = get_ms_logger(log_level=logging.INFO)
        ms_logger.setLevel(logging.INFO)
        
        # 设置模型缓存目录
        os.environ["MODELSCOPE_CACHE"] = "./model_cache"
        
        # Instantiating pipeline downloads and caches the model
        inference_pipeline = pipeline(
            task=Tasks.auto_speech_recognition,
            model=MODEL_NAME,
            model_revision=MODEL_REV,
            cache_dir="./model_cache",
        )
        logging.info("ModelScope model cached successfully.")
        return True
        
    except ImportError as e:
        logging.warning(f"ModelScope not available: {e}. Model download skipped.")
        return False
    except Exception as exc:
        logging.exception(f"ModelScope model download failed: {exc}")
        return False

if __name__ == "__main__":
    success = download_model()
    if not success:
        logging.info("ModelScope model download failed or skipped. The application will use mock mode.")
        # Don't exit with error code to allow Docker build to continue
        exit(1)
