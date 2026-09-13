"""Pure signal-processing core for the "now playing" visualizer (one of the
brief's own bonus-feature examples: "music visualizer in 2D/3D"). Kept free
of any Qt/QAudioBuffer dependency so it's unit-testable without a live
QMediaPlayer/GStreamer pipeline - only PlayerController's thin adapter
(_on_audio_buffer) touches actual Qt Multimedia types.
"""

from __future__ import annotations

import numpy as np

N_BARS = 24


def _dtype_for(sample_size_bits: int, is_float: bool, is_signed: bool) -> np.dtype:
    if is_float:
        return np.dtype(np.float32 if sample_size_bits == 32 else np.float64)
    if sample_size_bits == 8:
        return np.dtype(np.int8 if is_signed else np.uint8)
    if sample_size_bits == 16:
        return np.dtype(np.int16 if is_signed else np.uint16)
    if sample_size_bits == 32:
        return np.dtype(np.int32 if is_signed else np.uint32)
    raise ValueError(f"unsupported PCM sample size: {sample_size_bits} bits")


def pcm_bytes_to_levels(
    raw: bytes,
    *,
    sample_size_bits: int,
    channel_count: int,
    is_float: bool = False,
    is_signed: bool = True,
) -> list[float]:
    """Converts one raw interleaved-PCM audio buffer into N_BARS bar heights
    in [0, 1] - an FFT magnitude spectrum collapsed into log-spaced bands
    (so bass frequencies, where music's energy concentrates, get more bars
    than a linear split would give them), each frame normalized to its own
    peak. Returns all-zero bars (silence) for empty/unparseable input
    rather than raising - a single bad buffer shouldn't kill playback.
    """
    silence = [0.0] * N_BARS
    if not raw:
        return silence

    try:
        dtype = _dtype_for(sample_size_bits, is_float, is_signed)
        samples = np.frombuffer(raw, dtype=dtype)
    except ValueError:
        return silence

    if channel_count > 1 and samples.size >= channel_count:
        usable = samples.size - (samples.size % channel_count)
        samples = samples[:usable].reshape(-1, channel_count).mean(axis=1)
    if samples.size == 0:
        return silence

    samples = samples.astype(np.float64)
    if not is_float:
        samples = samples / float(2 ** (sample_size_bits - 1))

    spectrum = np.abs(np.fft.rfft(samples))
    if spectrum.size < 2:
        return silence

    edges = np.geomspace(1, spectrum.size, N_BARS + 1).astype(int)
    edges = np.clip(edges, 0, spectrum.size)
    bars = []
    for i in range(N_BARS):
        lo, hi = int(edges[i]), max(int(edges[i + 1]), int(edges[i]) + 1)
        band = spectrum[lo:hi]
        bars.append(float(band.mean()) if band.size else 0.0)

    peak = max(bars) or 1.0
    return [min(1.0, b / peak) for b in bars]
