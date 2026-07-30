"""Add an original, royalty-safe upbeat instrumental bed to the silent demo."""

from __future__ import annotations

import math
import os
import random
import re
import subprocess
import sys
import wave
from array import array
from pathlib import Path


ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "HALI_product_demo_final.mp4"
OUTPUT = ROOT / "HALI_product_demo_with_music.mp4"
MUSIC_DIR = ROOT / "music"
MUSIC_MP3 = MUSIC_DIR / "hali_upbeat_original.mp3"
TEMP_WAV = Path("/tmp/hali_upbeat_original.wav")


def ffmpeg_path() -> str:
    configured = os.environ.get("FFMPEG")
    candidates = [
        configured,
        "/tmp/ffmpeg-dist/usr/bin/ffmpeg",
        str(ROOT.parent / "node_modules/ffmpeg-static/ffmpeg"),
        "ffmpeg",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
        if candidate == "ffmpeg":
            return candidate
    raise RuntimeError("ffmpeg was not found")


def run(cmd: list[str]) -> None:
    env = os.environ.copy()
    if "/tmp/ffmpeg-dist/" in cmd[0]:
        env["LD_LIBRARY_PATH"] = "/tmp/ffmpeg-dist/usr/lib/x86_64-linux-gnu"
    subprocess.run(cmd, check=True, env=env)


def probe_duration(ffmpeg: str, path: Path) -> float:
    proc = subprocess.run(
        [ffmpeg, "-i", str(path)], capture_output=True, text=True,
        env={**os.environ, "LD_LIBRARY_PATH": "/tmp/ffmpeg-dist/usr/lib/x86_64-linux-gnu"},
    )
    match = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", proc.stderr)
    if not match:
        raise RuntimeError(f"Could not determine duration of {path}")
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def envelope(t: float, length: float, decay: float) -> float:
    return math.exp(-decay * t / length)


def generate_music(duration: float) -> None:
    """Generate a restrained 112 BPM kick/snare/hat/bass instrumental."""
    sample_rate = 44100
    bpm = 112.0
    beat = 60.0 / bpm
    total = int(math.ceil(duration + 1.0) * sample_rate)
    rng = random.Random(20260730)
    samples = array("h")

    # A four-bar harmonic loop keeps the bed energetic without competing with UI text.
    bass_notes = (110.00, 123.47, 146.83, 130.81)
    for index in range(total):
        t = index / sample_rate
        beat_index = int(t / beat)
        phase = t % beat
        bar_beat = beat_index % 16
        value = 0.0

        # Four-on-the-floor kick with a light syncopated pickup.
        if bar_beat in (0, 4, 8, 12) or (bar_beat in (3, 11) and phase < 0.045):
            k = phase if bar_beat in (0, 4, 8, 12) else phase
            value += 0.34 * math.sin(2 * math.pi * (72 - 24 * min(k / 0.18, 1.0)) * k) * math.exp(-k * 26)

        # Snare/clap on beats two and four.
        if bar_beat in (4, 12) and phase < 0.14:
            s = rng.uniform(-1.0, 1.0)
            value += 0.13 * s * math.exp(-phase * 24)
            value += 0.045 * math.sin(2 * math.pi * 190 * phase) * math.exp(-phase * 30)

        # Tight eighth-note hats, with alternating accents.
        eighth = beat / 2
        eighth_phase = t % eighth
        if eighth_phase < 0.032:
            h = rng.uniform(-1.0, 1.0)
            value += (0.027 if (beat_index % 2) else 0.038) * h * math.exp(-eighth_phase * 95)

        # Short, warm bass pulses following a four-bar progression.
        if phase < beat * 0.72:
            note = bass_notes[(beat_index // 4) % len(bass_notes)]
            value += 0.075 * math.sin(2 * math.pi * note * t) * math.exp(-phase * 2.4)

        # Gentle master fade and a little headroom for AAC encoding.
        if t < 1.0:
            value *= t
        if t > duration - 3.0:
            value *= max(0.0, (duration - t) / 3.0)
        value *= 0.72
        value = max(-0.92, min(0.92, value))
        pcm = int(value * 32767)
        samples.append(pcm)
        samples.append(pcm)

    TEMP_WAV.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(TEMP_WAV), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(samples.tobytes())


def main() -> None:
    if not INPUT.exists():
        raise SystemExit(f"Missing input video: {INPUT}")
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    ffmpeg = ffmpeg_path()
    duration = probe_duration(ffmpeg, INPUT)
    print(f"Demo duration: {duration:.2f}s")
    print("Generating original upbeat instrumental...")
    generate_music(duration)

    # Keep a compact reusable music asset, while mixing from the lossless temporary source.
    run([ffmpeg, "-y", "-i", str(TEMP_WAV), "-codec:a", "libmp3lame", "-b:a", "160k", str(MUSIC_MP3)])
    run([
        ffmpeg, "-y", "-i", str(INPUT), "-i", str(TEMP_WAV),
        "-filter_complex", "[1:a]volume=1.0[a]",
        "-map", "0:v:0", "-map", "[a]", "-c:v", "copy",
        "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart",
        str(OUTPUT),
    ])
    TEMP_WAV.unlink(missing_ok=True)
    print(f"Wrote {OUTPUT}")
    print(f"Music source: {MUSIC_MP3}")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode) from exc
