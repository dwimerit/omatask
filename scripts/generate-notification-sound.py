#!/usr/bin/env python3
"""Generate Omatask's original, centered two-note chime using only stdlib."""
import math
from pathlib import Path
import struct
import wave

RATE = 48000
DURATION = 0.8
target = Path(__file__).resolve().parent.parent / 'omatask/assets/notification.wav'
target.parent.mkdir(parents=True, exist_ok=True)
frames = bytearray()
for index in range(round(RATE * DURATION)):
    t = index / RATE
    value = 0.0
    for start, frequency, gain in ((0.0, 880.0, 0.11), (0.16, 1174.659, 0.13)):
        age = t - start
        if age >= 0:
            envelope = min(1.0, age / 0.008) * math.exp(-age / 0.14)
            value += gain * envelope * math.sin(2 * math.pi * frequency * age)
    value *= min(1.0, (DURATION - t) / 0.04)
    sample = round(value * 32767)
    # Identical PCM samples guarantee the notification has no stereo panning.
    frames.extend(struct.pack('<hh', sample, sample))
with wave.open(str(target), 'wb') as sound:
    sound.setnchannels(2)
    sound.setsampwidth(2)
    sound.setframerate(RATE)
    sound.writeframes(frames)
print(target)
