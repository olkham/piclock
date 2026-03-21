"""Alarm audio playback using pygame.mixer."""

import os

import pygame

_SOUNDS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "sounds")
_current_sound = None


def play_alarm_sound(sound_name="default"):
    """Play an alarm sound. Falls back to a beep if file not found."""
    global _current_sound

    if not pygame.mixer.get_init():
        try:
            pygame.mixer.init()
        except Exception:
            return  # No audio available

    # Look for the sound file
    for ext in (".wav", ".ogg", ".mp3"):
        path = os.path.join(_SOUNDS_DIR, sound_name + ext)
        if os.path.isfile(path):
            try:
                _current_sound = pygame.mixer.Sound(path)
                _current_sound.play(loops=-1)  # Loop until stopped
                return
            except Exception:
                continue

    # Fallback: generate a simple beep
    try:
        import numpy as np
        sample_rate = 44100
        duration = 0.5
        freq = 880
        t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
        wave = (np.sin(2 * np.pi * freq * t) * 32767).astype(np.int16)
        stereo = np.column_stack([wave, wave])
        sound = pygame.sndarray.make_sound(stereo)
        _current_sound = sound
        _current_sound.play(loops=-1)
    except Exception:
        pass


def stop_alarm_sound():
    """Stop any currently playing alarm sound."""
    global _current_sound
    if _current_sound:
        _current_sound.stop()
        _current_sound = None
