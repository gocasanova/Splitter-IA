#!/usr/bin/env python3
"""Integration test for AI Band Practice Tool."""

import sys
from pathlib import Path
import numpy as np

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.audio.loader import AudioLoader
from src.audio.mixer import Mixer
from src.audio.player import AudioPlayer
from src.ai.demucs_handler import DemucsHandler
from src.cache.cache_manager import CacheManager
from src.utils.logger import setup_logger
from src.utils.config import CACHE_BASE_DIR

logger = setup_logger("test")

def test_imports():
    """Test all imports."""
    print("✓ Testing imports...")
    from src.utils.config import APP_NAME, SUPPORTED_FORMATS
    from src.ui.widgets import StemControlWidget
    from src.ui.styles import apply_dark_theme
    print(f"  - App: {APP_NAME}")
    print(f"  - Formats: {SUPPORTED_FORMATS}")
    print("  ✓ All imports successful")

def test_mixer():
    """Test mixer logic."""
    print("\n✓ Testing mixer...")
    mixer = Mixer()
    mixer.add_stem("vocals")
    mixer.add_stem("drums")
    mixer.add_stem("bass")
    mixer.add_stem("other")

    # Create dummy audio
    stems = {
        "vocals": np.random.randn(2, 44100),
        "drums": np.random.randn(2, 44100),
        "bass": np.random.randn(2, 44100),
        "other": np.random.randn(2, 44100),
    }

    # Test volume
    mixer.set_volume("vocals", 0.5)
    assert mixer.stems["vocals"].volume == 0.5
    print("  ✓ Volume control")

    # Test mute
    mixer.toggle_mute("drums")
    assert mixer.stems["drums"].muted == True
    print("  ✓ Mute control")

    # Test solo
    mixer.toggle_solo("bass")
    assert mixer.stems["bass"].soloed == True
    print("  ✓ Solo control")

    # Test mixing
    mixed = mixer.mix_stems(stems)
    assert mixed.shape == stems["vocals"].shape
    print("  ✓ Mixing audio")

def test_cache():
    """Test caching system."""
    print("\n✓ Testing cache system...")
    cache = CacheManager()

    # Create dummy file info
    test_file = CACHE_BASE_DIR / "test_audio.wav"

    # Test hash generation
    from src.utils.file_hasher import hash_file

    # Create a small test file
    test_file.parent.mkdir(parents=True, exist_ok=True)
    with open(test_file, "wb") as f:
        f.write(b"test audio data")

    file_hash = hash_file(test_file)
    print(f"  ✓ File hash: {file_hash[:16]}...")

    # Test cache path generation
    cache_path = cache.get_cache_path(test_file)
    print(f"  ✓ Cache path: {cache_path}")

    # Cleanup
    test_file.unlink()

def test_demucs_device():
    """Test Demucs device detection."""
    print("\n✓ Testing Demucs device selection...")
    handler = DemucsHandler()
    print(f"  ✓ Selected device: {handler.device}")
    print(f"  ✓ Model: {handler.model_name}")

def test_logger():
    """Test logging."""
    print("\n✓ Testing logger...")
    test_logger = setup_logger("test_module")
    test_logger.info("Test log message")
    print("  ✓ Logger initialized")

def main():
    """Run all tests."""
    print("=" * 50)
    print("AI Band Practice Tool - Integration Tests")
    print("=" * 50)

    try:
        test_imports()
        test_mixer()
        test_cache()
        test_demucs_device()
        test_logger()

        print("\n" + "=" * 50)
        print("✓ All tests passed!")
        print("=" * 50)
        return 0

    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
