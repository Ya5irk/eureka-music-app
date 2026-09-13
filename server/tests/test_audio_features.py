import io
from pathlib import Path

from app.audio_features import N_MFCC, cosine_similarity_matrix, extract_feature_vector
from tests.conftest import wav_bytes


def _write_wav(tmp_path: Path, name: str, **kwargs: float) -> Path:
    path = tmp_path / name
    path.write_bytes(wav_bytes(**kwargs))
    return path


def test_extract_feature_vector_has_expected_shape(tmp_path: Path) -> None:
    path = _write_wav(tmp_path, "tone.wav")
    vector = extract_feature_vector(path)

    assert len(vector) == 2 * N_MFCC  # mean + std per MFCC coefficient
    assert all(isinstance(x, float) for x in vector)


def test_extract_feature_vector_is_deterministic(tmp_path: Path) -> None:
    path = _write_wav(tmp_path, "tone.wav", frequency_hz=440.0)

    assert extract_feature_vector(path) == extract_feature_vector(path)


def test_similar_tones_score_higher_than_dissimilar(tmp_path: Path) -> None:
    # Two renders of the same 440Hz tone should be closer to each other in
    # feature space than either is to a very different 4000Hz tone - this is
    # the actual property the /similar endpoint's ranking relies on.
    a = extract_feature_vector(_write_wav(tmp_path, "a.wav", frequency_hz=440.0))
    b = extract_feature_vector(_write_wav(tmp_path, "b.wav", frequency_hz=440.0, seconds=1.2))
    c = extract_feature_vector(_write_wav(tmp_path, "c.wav", frequency_hz=4000.0))

    sim_ab, sim_ac = cosine_similarity_matrix(a, [b, c])
    assert sim_ab > sim_ac


def test_cosine_similarity_matrix_empty_candidates() -> None:
    assert cosine_similarity_matrix([1.0, 0.0], []) == []


def test_wav_bytes_helper_round_trips_via_soundfile() -> None:
    # Sanity check on the test helper itself: make sure it produces bytes
    # librosa/soundfile can actually decode, not just well-formed-looking noise.
    import soundfile as sf

    data, sr = sf.read(io.BytesIO(wav_bytes()))
    assert sr == 22050
    assert len(data) > 0
