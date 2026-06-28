# Audio file loader using librosa
import librosa
import numpy as np
from pathlib import Path
from typing import Tuple
from src.audio.metadata import read_audio_metadata
from src.utils.logger import setup_logger
from src.utils.config import SAMPLE_RATE, SUPPORTED_FORMATS

logger = setup_logger(__name__)

class AudioLoader:
    """Loads audio files in various formats."""

    @staticmethod
    def load(file_path: Path) -> Tuple[np.ndarray, int]:
        """
        Load audio file.

        Returns:
            Tuple of (audio_data, sample_rate)
            audio_data shape: (channels, samples) or (samples,) for mono
        """
        if not file_path.exists():
            raise FileNotFoundError(f"Audio file not found: {file_path}")

        if file_path.suffix.lower() not in SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported format: {file_path.suffix}")

        try:
            logger.info(f"Loading audio file: {file_path}")
            # Load as mono first, then convert if needed
            audio, sr = librosa.load(str(file_path), sr=SAMPLE_RATE, mono=False)
            logger.info(f"Loaded audio: shape={audio.shape}, sr={sr}")
            return audio, sr
        except Exception as e:
            logger.error(f"Error loading audio file {file_path}: {e}")
            raise

    @staticmethod
    def load_preview(file_path: Path, target_sr: int = 11025, max_seconds: int = 90) -> Tuple[np.ndarray, int]:
        """Load a lightweight preview for waveform drawing."""
        if not file_path.exists():
            raise FileNotFoundError(f"Audio file not found: {file_path}")

        try:
            audio, sr = librosa.load(
                str(file_path),
                sr=target_sr,
                mono=True,
                duration=max_seconds,
            )
            return audio, sr
        except Exception as e:
            logger.error(f"Error loading waveform preview {file_path}: {e}")
            raise

    @staticmethod
    def get_metadata(file_path: Path) -> dict:
        """Extract embedded and technical metadata from an audio file."""
        try:
            return read_audio_metadata(file_path)
        except Exception as e:
            logger.error(f"Error extracting metadata: {e}")
            return {}
