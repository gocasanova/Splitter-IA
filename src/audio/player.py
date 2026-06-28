# Multi-stem audio playback engine using sounddevice
import numpy as np
import sounddevice as sd
import threading
from pathlib import Path
from typing import Dict, Optional, Callable
from dataclasses import dataclass
from src.utils.logger import setup_logger
from src.utils.config import SAMPLE_RATE, CHUNK_SIZE

logger = setup_logger(__name__)

@dataclass
class PlaybackState:
    """Current playback state."""
    is_playing: bool = False
    current_frame: int = 0
    total_frames: int = 0
    volume: float = 1.0
    loop_enabled: bool = False
    loop_start_frame: int = 0
    loop_end_frame: int = 0

class AudioPlayer:
    """Manages multi-stem audio playback with real-time mixing."""

    def __init__(self, callback_fn: Optional[Callable] = None):
        """
        Initialize player.

        Args:
            callback_fn: Optional callback for progress updates (frame_number)
        """
        self.stems: Dict[str, np.ndarray] = {}
        self.stem_gains: Dict[str, float] = {}
        self.mixed_audio: Optional[np.ndarray] = None
        self.state = PlaybackState()
        self.stream: Optional[sd.OutputStream] = None
        self.callback_fn = callback_fn
        self._lock = threading.Lock()
        self._play_thread: Optional[threading.Thread] = None
        self._stream_lock = threading.Lock()

    def load_stems(self, stems: Dict[str, np.ndarray]) -> None:
        """Load stems dictionary {stem_name: audio_array}."""
        with self._lock:
            self.stems = stems.copy()
            self.stem_gains = {name: 1.0 for name in stems}
            self.mixed_audio = None
            if stems:
                first_stem = next(iter(stems.values()))
                self.state.total_frames = first_stem.shape[-1]
                self.state.current_frame = 0
                self.clear_loop()
                logger.info(f"Loaded {len(stems)} stems, total frames: {self.state.total_frames}")

    def set_mixed_audio(self, mixed: np.ndarray) -> None:
        """Set pre-mixed audio (e.g., from mixer)."""
        with self._lock:
            self.mixed_audio = mixed.astype(np.float32, copy=False)
            self.state.total_frames = mixed.shape[-1]
            self.state.current_frame = min(self.state.current_frame, max(self.state.total_frames - 1, 0))

    def set_stem_gains(self, gains: Dict[str, float]) -> None:
        """Set effective per-stem gains used by the streaming mixer."""
        with self._lock:
            self.stem_gains = {
                name: float(np.clip(gain, 0.0, 1.0))
                for name, gain in gains.items()
            }

    def set_loop(self, start_frame: int, end_frame: int) -> bool:
        """Enable an A/B loop. Returns False when the range is invalid."""
        with self._lock:
            start = max(0, min(start_frame, max(self.state.total_frames - 1, 0)))
            end = max(0, min(end_frame, self.state.total_frames))
            if end <= start:
                return False
            self.state.loop_start_frame = start
            self.state.loop_end_frame = end
            self.state.loop_enabled = True
            if self.state.current_frame < start or self.state.current_frame >= end:
                self.state.current_frame = start
            return True

    def clear_loop(self) -> None:
        """Disable A/B looping."""
        self.state.loop_enabled = False
        self.state.loop_start_frame = 0
        self.state.loop_end_frame = 0

    def play(self) -> None:
        """Start playback."""
        if self.state.is_playing:
            return

        if self.mixed_audio is None and not self.stems:
            logger.warning("No audio loaded")
            return

        self._wait_for_playback_thread()

        try:
            if self.state.current_frame >= self.state.total_frames:
                self.state.current_frame = 0

            # Create stream
            if self.mixed_audio is not None:
                channels = self.mixed_audio.shape[0]
            elif self.stems:
                channels = next(iter(self.stems.values())).shape[0]
            else:
                channels = 2
            with self._stream_lock:
                self.stream = sd.OutputStream(
                    channels=channels,
                    samplerate=SAMPLE_RATE,
                    dtype="float32",
                    blocksize=CHUNK_SIZE,
                    latency="low",
                )
                self.stream.start()
            self.state.is_playing = True

            # Start playback thread
            play_thread = threading.Thread(target=self._playback_loop, daemon=True)
            self._play_thread = play_thread
            play_thread.start()

            logger.info("Playback started")
        except Exception as e:
            logger.error(f"Error starting playback: {e}")
            self.state.is_playing = False
            raise

    def _playback_loop(self) -> None:
        """Main playback loop running in separate thread."""
        if self.mixed_audio is None and not self.stems:
            return

        try:
            while self.state.is_playing:
                with self._lock:
                    loop_active = (
                        self.state.loop_enabled
                        and self.state.loop_end_frame > self.state.loop_start_frame
                    )
                    if loop_active and self.state.current_frame >= self.state.loop_end_frame:
                        self.state.current_frame = self.state.loop_start_frame

                    if self.state.current_frame >= self.state.total_frames:
                        self.state.is_playing = False
                        break

                    # Get next chunk
                    limit_frame = self.state.loop_end_frame if loop_active else self.state.total_frames
                    end_frame = min(
                        self.state.current_frame + CHUNK_SIZE,
                        limit_frame
                    )

                    chunk = self._get_chunk_locked(self.state.current_frame, end_frame)
                    self.state.current_frame = end_frame
                    if loop_active and self.state.current_frame >= self.state.loop_end_frame:
                        self.state.current_frame = self.state.loop_start_frame

                # Write to stream (outside lock to avoid blocking)
                if self.stream:
                    output = np.clip(chunk.T * self.state.volume, -1.0, 1.0)
                    self.stream.write(np.ascontiguousarray(output, dtype=np.float32))

                # Callback for UI updates
                if self.callback_fn:
                    self.callback_fn(self.state.current_frame)

        except Exception as e:
            logger.error(f"Playback error: {e}")
        finally:
            self.state.is_playing = False
            self._close_stream()

    def _get_chunk_locked(self, start_frame: int, end_frame: int) -> np.ndarray:
        """Return a mixed audio chunk. Caller must hold _lock."""
        if self.mixed_audio is not None:
            return self.mixed_audio[:, start_frame:end_frame].copy()

        first_stem = next(iter(self.stems.values()))
        chunk = np.zeros(
            (first_stem.shape[0], end_frame - start_frame),
            dtype=np.float32,
        )
        for stem_name, audio in self.stems.items():
            gain = self.stem_gains.get(stem_name, 1.0)
            if gain <= 0:
                continue
            chunk += audio[:, start_frame:end_frame] * gain
        return np.clip(chunk, -1.0, 1.0)

    def pause(self) -> bool:
        """Pause playback."""
        self.state.is_playing = False
        stopped = self._wait_for_playback_thread()
        logger.info("Playback paused")
        return stopped

    def stop(self) -> bool:
        """Stop and reset playback."""
        self.state.is_playing = False
        stopped = self._wait_for_playback_thread()
        with self._lock:
            self.state.current_frame = 0
        logger.info("Playback stopped")
        return stopped

    def _wait_for_playback_thread(self) -> bool:
        """Wait for audio thread to close its PortAudio stream."""
        thread = self._play_thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=3.0)
            if thread.is_alive():
                logger.error("Audio thread did not stop in time")
                return False
        if thread and not thread.is_alive():
            self._play_thread = None
        if self.stream and not (thread and thread.is_alive()):
            self._close_stream()
        return True

    def _close_stream(self) -> None:
        """Close stream exactly once."""
        with self._stream_lock:
            stream = self.stream
            self.stream = None

        if not stream:
            return

        try:
            stream.stop()
        except Exception as e:
            logger.warning(f"Error stopping stream: {e}")
        try:
            stream.close()
        except Exception as e:
            logger.warning(f"Error closing stream: {e}")

    def seek(self, frame: int) -> None:
        """Seek to frame."""
        with self._lock:
            self.state.current_frame = max(0, min(frame, self.state.total_frames - 1))

    def set_volume(self, volume: float) -> None:
        """Set master volume (0.0 to 1.0)."""
        self.state.volume = np.clip(volume, 0.0, 1.0)

    def get_duration_seconds(self) -> float:
        """Get total duration in seconds."""
        return self.state.total_frames / SAMPLE_RATE

    def get_current_time_seconds(self) -> float:
        """Get current playback position in seconds."""
        return self.state.current_frame / SAMPLE_RATE

    def is_playing(self) -> bool:
        """Check if currently playing."""
        return self.state.is_playing
