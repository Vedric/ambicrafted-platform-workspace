import numpy as np
import pytest

from voix_locale.prosodie import pause_entre, silence_bord


@pytest.mark.parametrize("rate", [16000, 22050, 24000])
def test_pause_comble_seulement_le_silence_manquant(rate):
    signal = np.full(rate, 2000, dtype="<i2").tobytes()
    assert len(pause_entre(signal, signal, rate)) == int(rate * 0.180) * 2
    queue = bytes(int(rate * 0.050) * 2)
    debut = bytes(int(rate * 0.080) * 2)
    pause = pause_entre(signal + queue, debut + signal, rate)
    assert len(pause) + len(queue) + len(debut) == int(rate * 0.180) * 2
    assert pause_entre(signal + bytes(rate), signal, rate) == b""


def test_amplitude_negative_ne_deborde_pas_et_pas_de_decoupe():
    signal = np.array([-32768, 32767, 64, -64, 0], dtype="<i2").tobytes()
    assert silence_bord(signal, 16000, debut=True) == 0
    assert silence_bord(signal, 16000, debut=False) == 3
    assert silence_bord(b"", 16000, debut=True) == 0
