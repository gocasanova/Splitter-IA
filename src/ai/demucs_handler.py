# Demucs model wrapper for stem separation
import torch
import torchaudio
import numpy as np
from pathlib import Path
from typing import Dict, Optional
from demucs.pretrained import get_model
from demucs.apply import apply_model
from src.utils.logger import setup_logger
from src.utils.config import DEMUCS_MODEL, SAMPLE_RATE, DEMUCS_OVERLAP, DEMUCS_SHIFT

logger = setup_logger(__name__)

class DemucsHandler:
    """Wraps Demucs model for audio stem separation."""

    def __init__(self, model_name: str = DEMUCS_MODEL, device: Optional[str] = None):
        """Initialize Demucs handler."""
        self.model_name = model_name
        self.device = device or self._get_device()
        self.model = None
        logger.info(f"Initializing Demucs with device: {self.device}")

    def _get_device(self) -> str:
        """Get appropriate device (cuda or cpu, prioritize Apple Silicon)."""
        # Check for Apple Silicon
        if torch.backends.mps.is_available():
            return "mps"
        elif torch.cuda.is_available():
            return "cuda"
        return "cpu"

    def load_model(self) -> None:
        """Load Demucs model."""
        try:
            if self.model is None:
                logger.info(f"Loading {self.model_name} model...")
                self.model = get_model(self.model_name)
                self.model.to(self.device)
                self.model.eval()
                logger.info(f"Model loaded successfully on {self.device}")
        except Exception as e:
            logger.error(f"Error loading model: {e}")
            raise

    def separate(self, audio: np.ndarray, sr: int, progress_callback=None) -> Dict[str, np.ndarray]:
        """
        Separate audio into stems.

        Args:
            audio: Input audio array (channels, samples)
            sr: Sample rate
            progress_callback: Optional callback for progress updates

        Returns:
            Dictionary of stems {stem_name: audio_array}
        """
        if self.model is None:
            self.load_model()

        try:
            logger.info("Starting stem separation...")

            # Convert numpy to torch tensor
            if len(audio.shape) == 1:
                audio = audio[np.newaxis, :]  # Add channel dimension
            if audio.shape[0] == 1:
                audio = np.repeat(audio, 2, axis=0)
            elif audio.shape[0] > 2:
                audio = audio[:2]
            audio = audio.astype(np.float32, copy=False)

            # Resample if needed
            model_sr = getattr(self.model, "samplerate", SAMPLE_RATE)
            if sr != model_sr:
                logger.info(f"Resampling from {sr} to {model_sr}")
                resampler = torchaudio.transforms.Resample(sr, model_sr)
                audio_tensor = torch.from_numpy(audio).float()
                audio_tensor = resampler(audio_tensor)
            else:
                audio_tensor = torch.from_numpy(audio).float()

            # Move to device
            audio_tensor = audio_tensor.to(self.device)
            if progress_callback:
                progress_callback(35)

            # Apply model
            with torch.no_grad():
                stems_tensor = apply_model(
                    self.model,
                    audio_tensor.unsqueeze(0),  # Add batch dimension
                    shifts=DEMUCS_SHIFT,
                    overlap=DEMUCS_OVERLAP,
                    split=True,
                    device=self.device,
                    progress=False
                )
            if progress_callback:
                progress_callback(90)

            # Extract stems
            stems = {}
            stem_names = self.model.sources

            stems_tensor = stems_tensor.squeeze(0)  # Remove batch dimension

            for i, name in enumerate(stem_names):
                stem_audio = stems_tensor[i].cpu().numpy()
                stems[name] = stem_audio
                logger.info(f"Extracted {name}: shape {stem_audio.shape}")

            logger.info("Stem separation completed")
            return stems

        except Exception as e:
            logger.error(f"Error during separation: {e}")
            raise

    def get_stem_names(self) -> list:
        """Get names of stems for current model."""
        if self.model is None:
            self.load_model()
        return self.model.sources
