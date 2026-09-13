import numpy as np

from app.audio_levels import N_BARS, pcm_bytes_to_levels


def _sine_pcm16(frequency_hz: float, sample_rate: int = 44100, seconds: float = 0.1) -> bytes:
    t = np.linspace(0, seconds, int(sample_rate * seconds), endpoint=False)
    samples = (0.8 * np.iinfo(np.int16).max * np.sin(2 * np.pi * frequency_hz * t)).astype(np.int16)
    return samples.tobytes()


def test_empty_buffer_is_silence() -> None:
    levels = pcm_bytes_to_levels(b"", sample_size_bits=16, channel_count=1)
    assert levels == [0.0] * N_BARS


def test_returns_n_bars_in_unit_range() -> None:
    levels = pcm_bytes_to_levels(_sine_pcm16(440.0), sample_size_bits=16, channel_count=1)
    assert len(levels) == N_BARS
    assert all(0.0 <= level <= 1.0 for level in levels)
    assert max(levels) == 1.0  # each frame is peak-normalized


def test_low_frequency_tone_peaks_in_an_earlier_bar_than_high_frequency() -> None:
    low = pcm_bytes_to_levels(_sine_pcm16(100.0), sample_size_bits=16, channel_count=1)
    high = pcm_bytes_to_levels(_sine_pcm16(15000.0), sample_size_bits=16, channel_count=1)

    assert low.index(max(low)) < high.index(max(high))


def test_stereo_buffer_is_averaged_down_to_mono() -> None:
    mono = _sine_pcm16(440.0)
    mono_samples = np.frombuffer(mono, dtype=np.int16)
    stereo = np.repeat(mono_samples, 2).tobytes()  # identical L/R channels

    mono_levels = pcm_bytes_to_levels(mono, sample_size_bits=16, channel_count=1)
    stereo_levels = pcm_bytes_to_levels(stereo, sample_size_bits=16, channel_count=2)

    assert mono_levels == stereo_levels


def test_unsupported_sample_size_returns_silence_instead_of_raising() -> None:
    levels = pcm_bytes_to_levels(b"\x00" * 12, sample_size_bits=24, channel_count=1)
    assert levels == [0.0] * N_BARS


def test_float_samples_are_supported() -> None:
    t = np.linspace(0, 0.1, 4410, endpoint=False)
    samples = (0.5 * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32)
    levels = pcm_bytes_to_levels(
        samples.tobytes(), sample_size_bits=32, channel_count=1, is_float=True
    )
    assert len(levels) == N_BARS
    assert max(levels) > 0.0
