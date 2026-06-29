"""Mic diagnostic: lists input devices and measures the level the VAD actually sees.

Run from the SAME environment you run the bot in:

    .\\.venv\\Scripts\\python.exe scripts\\mic_check.py

Speak normally for the 4-second capture. If `max_rms` stays well below the VAD
threshold (0.01), the bot will never detect speech — the mic is too quiet, muted,
or the wrong input device is the default.
"""

from __future__ import annotations

import numpy as np
import sounddevice as sd

_SR = 16000
_SECONDS = 4.0
_VAD_THRESHOLD = 0.01  # must match VADConfig.threshold


def main() -> int:
    print("=== Input devices ===")
    print(sd.query_devices())
    try:
        default_in = sd.default.device[0]
    except Exception:  # noqa: BLE001
        default_in = None
    print(f"\nDefault input device index: {default_in}")
    try:
        info = sd.query_devices(default_in, "input") if default_in is not None else None
        if info:
            print(f"Default input name: {info['name']}")
    except Exception as exc:  # noqa: BLE001
        print(f"(could not query default input: {exc})")

    print(f"\nRecording {_SECONDS:.0f}s — speak now…")
    audio = sd.rec(int(_SR * _SECONDS), samplerate=_SR, channels=1, dtype="float32")
    sd.wait()
    samples = np.asarray(audio, dtype=np.float32).reshape(-1)

    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    rms = float(np.sqrt(np.mean(samples**2))) if samples.size else 0.0

    # Fraction of 30ms frames that clear the VAD speech threshold.
    frame = _SR * 30 // 1000
    n = samples.size // frame
    speech_frames = 0
    max_rms = 0.0
    for i in range(n):
        f = samples[i * frame : (i + 1) * frame]
        fr = float(np.sqrt(np.mean(f**2)))
        max_rms = max(max_rms, fr)
        if fr >= _VAD_THRESHOLD:
            speech_frames += 1

    print("\n=== Levels ===")
    print(f"overall peak : {peak:.4f}")
    print(f"overall rms  : {rms:.4f}")
    print(f"max frame rms: {max_rms:.4f}   (VAD threshold = {_VAD_THRESHOLD})")
    pct = (100.0 * speech_frames / n) if n else 0.0
    print(f"frames over threshold: {speech_frames}/{n} ({pct:.0f}%)")

    print("\n=== Verdict ===")
    if peak < 1e-4:
        print("SILENT — mic delivered no signal. Wrong device, muted, or no OS mic permission.")
    elif max_rms < _VAD_THRESHOLD:
        print("TOO QUIET — signal present but below the VAD threshold. Lower threshold or raise mic gain.")
    else:
        print("OK — speech clears the threshold. The VAD should detect your voice.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
