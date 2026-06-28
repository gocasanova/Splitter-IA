# Mixer logic for volume, mute, and solo
import numpy as np
from dataclasses import dataclass
from typing import Dict
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

@dataclass
class StemControl:
    """Control state for a single stem."""
    name: str
    volume: float = 1.0  # 0.0 to 1.0
    muted: bool = False
    soloed: bool = False

    def get_gain(self, any_soloed: bool = False) -> float:
        """Get effective gain accounting for mute."""
        if any_soloed and not self.soloed:
            return 0.0
        if self.muted:
            return 0.0
        return self.volume

class Mixer:
    """Manages mixing of multiple audio stems."""

    def __init__(self):
        self.stems: Dict[str, StemControl] = {}
        self.any_soloed = False

    def add_stem(self, name: str) -> None:
        """Add a new stem."""
        self.stems[name] = StemControl(name)
        logger.info(f"Added stem: {name}")

    def set_volume(self, stem_name: str, volume: float) -> None:
        """Set volume for a stem (0.0 to 1.0)."""
        if stem_name in self.stems:
            self.stems[stem_name].volume = np.clip(volume, 0.0, 1.0)

    def set_mute(self, stem_name: str, muted: bool) -> None:
        """Set mute state for a stem."""
        if stem_name in self.stems:
            self.stems[stem_name].muted = muted

    def toggle_mute(self, stem_name: str) -> bool:
        """Toggle mute for a stem."""
        if stem_name in self.stems:
            self.stems[stem_name].muted = not self.stems[stem_name].muted
            return self.stems[stem_name].muted
        return False

    def toggle_solo(self, stem_name: str) -> None:
        """Toggle solo for a stem."""
        if stem_name in self.stems:
            self.stems[stem_name].soloed = not self.stems[stem_name].soloed
            self._update_solo_state()

    def _update_solo_state(self) -> None:
        """Update any_soloed flag."""
        self.any_soloed = any(s.soloed for s in self.stems.values())

    def mix_stems(self, stems_audio: Dict[str, np.ndarray]) -> np.ndarray:
        """Mix multiple stems together with current controls."""
        if not stems_audio:
            return np.array([])

        # Get reference shape from first stem
        first_stem = next(iter(stems_audio.values()))
        mixed = np.zeros_like(first_stem)

        for stem_name, audio in stems_audio.items():
            if stem_name in self.stems:
                gain = self.stems[stem_name].get_gain(self.any_soloed)
                mixed += audio * gain

        return np.clip(mixed, -1.0, 1.0)

    def reset(self) -> None:
        """Reset all controls."""
        for stem in self.stems.values():
            stem.volume = 1.0
            stem.muted = False
            stem.soloed = False
        self.any_soloed = False
