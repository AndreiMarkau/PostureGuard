"""
generate_alert.py — creates assets/alert.wav (a harsh buzzer sound).
Run once during setup. No external deps beyond stdlib.
"""
import math
import os
import struct
import wave


def generate_buzzer(path: str, duration_sec: float = 1.5, sample_rate: int = 44100):
    """Generate an unpleasant buzzer/alarm tone and save as WAV."""
    n_samples = int(duration_sec * sample_rate)
    samples = []

    for i in range(n_samples):
        t = i / sample_rate
        # Mix two slightly detuned square waves → harsh buzzer
        freq1, freq2 = 480.0, 620.0
        # Square wave approximation (sum of odd harmonics)
        v1 = sum(math.sin(2 * math.pi * freq1 * (2*k+1) * t) / (2*k+1)
                 for k in range(8))
        v2 = sum(math.sin(2 * math.pi * freq2 * (2*k+1) * t) / (2*k+1)
                 for k in range(8))
        # Amplitude envelope: short attack, sustain, short decay
        env = 1.0
        attack = 0.02
        decay  = 0.05
        if t < attack:
            env = t / attack
        elif t > duration_sec - decay:
            env = (duration_sec - t) / decay

        raw = (v1 + v2) * 0.35 * env   # scale to avoid clipping
        clamped = max(-1.0, min(1.0, raw))
        samples.append(int(clamped * 32767))

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f"<{n_samples}h", *samples))

    print(f"[generate_alert] Written {path} ({n_samples} samples, {duration_sec}s)")


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out  = os.path.join(here, "assets", "alert.wav")
    generate_buzzer(out)
