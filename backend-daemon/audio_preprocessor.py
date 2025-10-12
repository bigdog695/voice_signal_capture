"""
Audio Preprocessing Module with AEC (Acoustic Echo Cancellation)

This module provides audio preprocessing capabilities including:
- Acoustic Echo Cancellation (AEC) using WebRTC
- Noise Suppression (NS)
- Automatic Gain Control (AGC)
- Energy-based voice activity detection

Usage:
    preprocessor = AudioPreprocessor(
        sample_rate=8000,
        enable_aec=True,
        enable_ns=True,
        enable_agc=True
    )

    # With reference signal (far-end audio, e.g., citizen audio in headset)
    cleaned = preprocessor.process(near_end_audio, far_end_audio)

    # Without reference signal (fallback to NS only)
    cleaned = preprocessor.process(near_end_audio)
"""

import os
import logging
import numpy as np
from typing import Optional

log = logging.getLogger("ASRDaemon.AudioPreprocessor")


class AudioPreprocessor:
    """
    Audio preprocessor with AEC, noise suppression, and AGC.

    Supports both modes:
    1. Full AEC mode: Requires far-end reference signal (citizen audio)
    2. NS-only mode: Fallback when no reference signal is available
    """

    def __init__(
        self,
        sample_rate: int = 8000,
        enable_aec: bool = True,
        enable_ns: bool = True,
        enable_agc: bool = False,
        frame_size_ms: int = 10,
        filter_length_ms: int = 200,
    ):
        """
        Initialize audio preprocessor.

        Args:
            sample_rate: Audio sample rate in Hz (8000, 16000, 32000, 48000)
            enable_aec: Enable acoustic echo cancellation
            enable_ns: Enable noise suppression
            enable_agc: Enable automatic gain control
            frame_size_ms: Frame size in milliseconds (10, 20, 30)
            filter_length_ms: AEC filter length in milliseconds (longer = better cancellation but more latency)
        """
        self.sample_rate = sample_rate
        self.enable_aec = enable_aec
        self.enable_ns = enable_ns
        self.enable_agc = enable_agc
        self.frame_size_ms = frame_size_ms
        self.filter_length_ms = filter_length_ms

        # Calculate frame size in samples
        self.frame_size = int(sample_rate * frame_size_ms / 1000)
        self.filter_length = int(sample_rate * filter_length_ms / 1000)

        # WebRTC components (lazy loaded)
        self._webrtc_apm = None
        self._speex_aec = None
        self._use_webrtc = False
        self._use_speex = False

        # Audio buffers for frame alignment
        self._near_buffer = np.array([], dtype=np.int16)
        self._far_buffer = np.array([], dtype=np.int16)

        self._init_aec()

        log.info(
            f"AudioPreprocessor initialized: sr={sample_rate}, "
            f"frame_size={self.frame_size}, aec={enable_aec}, "
            f"ns={enable_ns}, agc={enable_agc}, "
            f"backend={'webrtc' if self._use_webrtc else 'speex' if self._use_speex else 'none'}"
        )

    def _init_aec(self):
        """Initialize AEC backend (WebRTC or Speex fallback)."""
        if not self.enable_aec:
            log.info("AEC disabled by configuration")
            return

        # Try WebRTC first (best quality)
        try:
            from webrtc_audio_processing import AudioProcessingModule
            self._webrtc_apm = AudioProcessingModule(
                enable_aec=True,
                enable_ns=self.enable_ns,
                enable_agc=self.enable_agc,
                sample_rate=self.sample_rate,
            )
            self._use_webrtc = True
            log.info("WebRTC AEC initialized successfully")
            return
        except ImportError:
            log.warning("webrtc-audio-processing not available, trying Speex")
        except Exception as e:
            log.warning(f"Failed to initialize WebRTC AEC: {e}, trying Speex")

        # Fallback to Speex
        try:
            from speexdsp import EchoCanceller
            self._speex_aec = EchoCanceller(
                frame_size=self.frame_size,
                filter_length=self.filter_length,
                sample_rate=self.sample_rate,
            )
            self._use_speex = True
            log.info("Speex AEC initialized successfully")
            return
        except ImportError:
            log.error("speexdsp-python not available. AEC will be disabled.")
            log.error("Install with: pip install webrtc-audio-processing OR pip install speexdsp-python")
        except Exception as e:
            log.error(f"Failed to initialize Speex AEC: {e}")

        # No AEC available
        self.enable_aec = False
        log.warning("AEC disabled: no backend available")

    def process(
        self,
        near_end_audio: np.ndarray,
        far_end_audio: Optional[np.ndarray] = None
    ) -> np.ndarray:
        """
        Process audio with AEC and noise suppression.

        Args:
            near_end_audio: Audio from microphone (with echo), int16 or float32
            far_end_audio: Reference audio playing in speaker (optional), int16 or float32

        Returns:
            Processed audio as int16 numpy array
        """
        # Convert to int16 if needed
        near_audio = self._ensure_int16(near_end_audio)

        # If AEC is disabled or no backend, return original or apply simple NS
        if not self.enable_aec or (not self._use_webrtc and not self._use_speex):
            if self.enable_ns:
                return self._simple_noise_suppression(near_audio)
            return near_audio

        # If no far-end audio provided, fallback to NS only
        if far_end_audio is None:
            log.debug("No far-end audio provided, applying noise suppression only")
            if self.enable_ns:
                return self._simple_noise_suppression(near_audio)
            return near_audio

        far_audio = self._ensure_int16(far_end_audio)

        # Process with AEC backend
        if self._use_webrtc:
            return self._process_webrtc(near_audio, far_audio)
        elif self._use_speex:
            return self._process_speex(near_audio, far_audio)

        return near_audio

    def _process_webrtc(
        self,
        near_audio: np.ndarray,
        far_audio: np.ndarray
    ) -> np.ndarray:
        """Process audio using WebRTC APM."""
        try:
            # WebRTC expects float32 in [-1, 1]
            near_float = near_audio.astype(np.float32) / 32768.0
            far_float = far_audio.astype(np.float32) / 32768.0

            # Process
            processed_float = self._webrtc_apm.process_stream(
                near_end=near_float,
                far_end=far_float
            )

            # Convert back to int16
            processed = (processed_float * 32768.0).astype(np.int16)
            return processed

        except Exception as e:
            log.error(f"WebRTC processing error: {e}")
            return near_audio

    def _process_speex(
        self,
        near_audio: np.ndarray,
        far_audio: np.ndarray
    ) -> np.ndarray:
        """Process audio using Speex echo canceller frame by frame."""
        try:
            # Add new audio to buffers
            self._near_buffer = np.concatenate([self._near_buffer, near_audio])
            self._far_buffer = np.concatenate([self._far_buffer, far_audio])

            # Process complete frames
            output_frames = []
            while len(self._near_buffer) >= self.frame_size and len(self._far_buffer) >= self.frame_size:
                near_frame = self._near_buffer[:self.frame_size]
                far_frame = self._far_buffer[:self.frame_size]

                # Process frame
                cleaned_frame = self._speex_aec.process(
                    input_frame=near_frame,
                    echo_frame=far_frame
                )
                output_frames.append(cleaned_frame)

                # Remove processed frames
                self._near_buffer = self._near_buffer[self.frame_size:]
                self._far_buffer = self._far_buffer[self.frame_size:]

            if output_frames:
                return np.concatenate(output_frames)
            else:
                # Not enough data for a complete frame
                return np.array([], dtype=np.int16)

        except Exception as e:
            log.error(f"Speex processing error: {e}")
            # Clear buffers on error
            self._near_buffer = np.array([], dtype=np.int16)
            self._far_buffer = np.array([], dtype=np.int16)
            return near_audio

    def _simple_noise_suppression(self, audio: np.ndarray) -> np.ndarray:
        """
        Simple spectral subtraction-based noise suppression.
        Fallback when no AEC backend is available.
        """
        try:
            # Simple noise gate based on signal energy
            if len(audio) == 0:
                return audio

            # Calculate RMS energy
            rms = np.sqrt(np.mean(audio.astype(np.float32) ** 2))

            # Adaptive threshold (10% of max possible RMS)
            threshold = 3276.8  # 0.1 * 32768

            if rms < threshold:
                # Below threshold: apply aggressive attenuation
                return (audio * 0.1).astype(np.int16)
            else:
                # Above threshold: apply light noise reduction
                # Simple high-pass filter to remove low-frequency noise
                if len(audio) > 10:
                    from scipy.signal import butter, filtfilt
                    nyquist = self.sample_rate / 2
                    cutoff = 100  # 100 Hz high-pass
                    b, a = butter(2, cutoff / nyquist, btype='high')
                    filtered = filtfilt(b, a, audio.astype(np.float32))
                    return filtered.astype(np.int16)
                return audio

        except Exception as e:
            log.error(f"Noise suppression error: {e}")
            return audio

    def _ensure_int16(self, audio: np.ndarray) -> np.ndarray:
        """Convert audio to int16 format."""
        if audio.dtype == np.int16:
            return audio
        elif audio.dtype in (np.float32, np.float64):
            # Assume normalized float in [-1, 1]
            return (audio * 32768.0).astype(np.int16)
        else:
            return audio.astype(np.int16)

    def reset(self):
        """Reset internal buffers and state."""
        self._near_buffer = np.array([], dtype=np.int16)
        self._far_buffer = np.array([], dtype=np.int16)

        # Reset Speex state if using it
        if self._use_speex and self._speex_aec:
            try:
                self._speex_aec.reset()
            except Exception as e:
                log.warning(f"Failed to reset Speex AEC: {e}")

        log.debug("AudioPreprocessor state reset")
