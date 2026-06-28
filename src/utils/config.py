# Configuration and paths
import os
from pathlib import Path

# App name
APP_NAME = "AI Band Practice Tool"
APP_VERSION = "1.1.0"

# Paths
BASE_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = BASE_DIR / "src"
LOCAL_CACHE_DIR = BASE_DIR / "cache"
DEFAULT_CACHE_BASE_DIR = Path.home() / "Music" / "AIStemsCache"
CACHE_BASE_DIR = Path(os.environ.get("AI_STEMS_CACHE_DIR", DEFAULT_CACHE_BASE_DIR))
MODELS_CACHE_DIR = Path(os.environ.get("TORCH_HOME", Path.home() / ".cache" / "torch")) / "hub"


def ensure_directory(path: Path, fallback: Path | None = None) -> Path:
    """Create a directory and fall back when the preferred location is unavailable."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_test"
        probe.touch(exist_ok=True)
        probe.unlink(missing_ok=True)
        return path
    except OSError:
        if fallback is None:
            raise
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


# Create cache directories if they don't exist. In sandboxed/dev runs, use local cache.
CACHE_BASE_DIR = ensure_directory(CACHE_BASE_DIR, LOCAL_CACHE_DIR)
MODELS_CACHE_DIR = ensure_directory(MODELS_CACHE_DIR, LOCAL_CACHE_DIR / "torch" / "hub")

# Audio settings
SAMPLE_RATE = 44100  # Hz
AUDIO_CHANNELS = 2
CHUNK_SIZE = 2048  # Samples per buffer
DEVICE_LATENCY = "low"  # 'low' for minimum latency

# AI Model settings
DEMUCS_MODEL = "htdemucs"  # High-quality default
DEMUCS_SHIFT = 1  # Number of random shifts for separation
DEMUCS_OVERLAP = 0.25  # Overlap ratio
DEMUCS_JOBS = 4  # Parallel jobs

# Supported audio formats
SUPPORTED_FORMATS = ('.wav', '.mp3', '.flac', '.ogg', '.m4a')

# UI Settings
DARK_THEME = True
SLIDER_TICK_INTERVAL = 10
SLIDER_SINGLE_STEP = 1

# Logging
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
