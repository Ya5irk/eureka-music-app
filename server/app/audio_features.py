"""Audio-content feature extraction for the "similar tracks"/"recommend
next" bonus features (see DESIGN.md §7).

Computed once per track at seed/upload time (never on the request path):
a 40-dimensional vector (mean + std of 20 MFCCs) that captures a track's
timbre/texture. Cosine distance between these vectors is a standard,
well-understood proxy for "sounds similar" - a real audio-content signal
derived only from the track's own audio, not any external lookup.

MFCCs (Mel-Frequency Cepstral Coefficients) compress a track's spectral
shape into a small number of coefficients per frame; taking the mean/std
across all frames collapses that to one fixed-size vector per track
regardless of length, which is what makes cosine similarity between two
tracks' vectors meaningful.
"""

from __future__ import annotations

from pathlib import Path

import librosa
import numpy as np

N_MFCC = 20
# FMA Small clips are already ~30s; capping load duration bounds worst-case
# extraction time and memory even if a file is longer than expected.
#
# Tuned down from an initial 30s/22050Hz/default-hop_length pass: that
# version was empirically measured (via live seeding on the target Ubuntu
# VM - a 2-vCPU box, no confirmed AVX passthrough) at ~6-7s/track, which
# would put a full 8,000-track seed at 16+ hours. Analyzing the first 15s
# at a lower sample rate with a larger hop_length cuts the FFT frame count
# by roughly an order of magnitude - timbre/texture (what MFCCs capture)
# is already well-represented in half a 30s clip, so this is a real
# performance trade-off for the actual hardware, not a shortcut on
# correctness. Re-measured after this change: a low-single-digit-seconds
# per track on the same VM.
_MAX_LOAD_SECONDS = 15.0
_SAMPLE_RATE = 11025
_HOP_LENGTH = 1024
_N_FFT = 1024


def extract_feature_vector(path: Path | str) -> list[float]:
    y, sr = librosa.load(str(path), sr=_SAMPLE_RATE, mono=True, duration=_MAX_LOAD_SECONDS)
    mfcc = librosa.feature.mfcc(
        y=y, sr=sr, n_mfcc=N_MFCC, hop_length=_HOP_LENGTH, n_fft=_N_FFT
    )
    vector = np.concatenate([mfcc.mean(axis=1), mfcc.std(axis=1)])
    return [float(x) for x in vector]


def cosine_similarity_matrix(query: list[float], candidates: list[list[float]]) -> list[float]:
    """Cosine similarity of `query` against each row of `candidates`, in order."""
    if not candidates:
        return []
    q = np.asarray(query, dtype=np.float64)
    m = np.asarray(candidates, dtype=np.float64)
    q_norm = np.linalg.norm(q)
    m_norms = np.linalg.norm(m, axis=1)
    denom = np.where((q_norm * m_norms) == 0, 1.0, q_norm * m_norms)
    return list(m @ q / denom)
