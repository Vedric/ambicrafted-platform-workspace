"""Regression boundaries for the multilingual phoneme and chunk pipeline."""

import pytest

from voix_locale.fichiers import ErreurVoix
from voix_locale.synthese import MAX_PHONEMES, decouper, phonemiser


def test_decoupage_conserve_tous_les_phonemes_sans_depassement():
    phrase = ("bɔ̃ʒˈuʁ vedʁˈik " * 100).strip()
    morceaux = list(decouper(phrase))
    assert len(morceaux) > 1
    assert " ".join(morceaux) == phrase
    assert all(0 < len(m) <= MAX_PHONEMES for m in morceaux)
    mot = "a" * 2000
    assert "".join(decouper(mot)) == mot
    assert max(map(len, decouper(mot))) <= MAX_PHONEMES


def test_lexique_reste_dans_une_phrase_et_ponctuation_conservee(monkeypatch):
    from piper.phonemize_espeak import EspeakPhonemizer

    calls = []

    def phonemize(self, voice, text):
        calls.append(voice)
        return [list(part + ".") for part in text.split(".") if part.strip()]

    monkeypatch.setattr(EspeakPhonemizer, "phonemize", phonemize)
    vocab = {
        c: i
        for i, c in enumerate(" abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ.,?!ˈɡɪthʌbɹ")
    }
    result = phonemiser("Inspect GitHub now.", "fr", vocab)
    assert len(result) == 1 and "ɡˈɪthʌb" in result[0]
    assert calls == ["fr", "fr"]


def test_phoneme_inconnu_ne_disparait_pas_silencieusement(monkeypatch):
    from piper.phonemize_espeak import EspeakPhonemizer

    monkeypatch.setattr(EspeakPhonemizer, "phonemize", lambda *args: [list("a☃")])
    with pytest.raises(ErreurVoix, match="prononciation"):
        phonemiser("hello", "en", {"a": 1})


def test_phrase_vide_ne_produit_pas_audio_silencieux():
    with pytest.raises(ErreurVoix):
        phonemiser("   ", "en", {" ": 1})


def test_alternance_repetee_des_langues_ne_reinitialise_pas_espeak():
    """A native deadlock must fail within a deadline, never hang the suite."""
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
from concurrent.futures import ThreadPoolExecutor
from voix_locale.synthese import phonemiser
vocab = {chr(i): i for i in range(65536)}
phrases = {"fr": "Bonjour, comment allez-vous ?", "en": "Hello, how are you today?"}
def say(language):
    return phonemiser(phrases[language], language, vocab)
expected = {language: say(language) for language in phrases}
assert expected['fr'] != expected['en']
languages = ['fr', 'en'] * 12
with ThreadPoolExecutor(max_workers=4) as pool:
    actual = list(pool.map(say, languages))
assert all(value == expected[language] for value, language in zip(actual, languages))
""",
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    # ONNX device discovery can warn about a virtual PCI path on hosted runners.
    # The regression concerns eSpeak corruption, not unrelated hardware notices.
    assert "Invalid instruction" not in result.stderr
