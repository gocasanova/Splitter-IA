# File hashing for caching
import hashlib
from pathlib import Path
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

def hash_file(file_path: Path, algorithm: str = "sha256") -> str:
    """Generate hash of file for caching."""
    hash_obj = hashlib.new(algorithm)

    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hash_obj.update(chunk)
        return hash_obj.hexdigest()
    except Exception as e:
        logger.error(f"Error hashing file {file_path}: {e}")
        raise
