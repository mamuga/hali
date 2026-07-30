"""Build the silent HALI product demo from the clean web and phone sources.

Run from the repository root with::

    python3 demo/assemble.py

The script deliberately uses beat-XX.webm, never captioned-XX.mp4. It trims,
normalizes every source to 1920x1080/30fps/yuv420p, makes three title cards,
and assembles them with short xfade transitions and no audio stream.
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo"
CLIPS = DEMO / "clips"
TRIMMED = CLIPS / "trimmed"
NORMALIZED = TRIMMED / "normalized"
OUTPUT = DEMO / "HALI_product_demo_final.mp4"


def executable() -> str:
    configured = os.getenv("FFMPEG")
    if configured and Path(configured).exists():
        return configured
    candidates = [CLIPS / "../../node_modules/ffmpeg-static/ffmpeg"]
    candidates += [Path(p) for p in glob.glob(str(ROOT / "node_modules/.ffmpeg-static-*/ffmpeg"))]
    candidates += [Path("/usr/bin/ffmpeg"), Path("/usr/local/bin/ffmpeg")]
    for candidate in candidates:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate.resolve())
    raise RuntimeError("ffmpeg not found; set FFMPEG=/path/to/ffmpeg")


FFMPEG = executable()


def run(args: list[str]) -> None:
    print("$", " ".join(args))
    subprocess.run(args, check=True)


def duration(path: Path) -> float:
    result = subprocess.run([FFMPEG, "-i", str(path)], capture_output=True, text=True, check=False)
    match = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr)
    if not match:
        raise RuntimeError(f"Could not read duration for {path}")
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def clean_dirs() -> None:
    TRIMMED.mkdir(parents=True, exist_ok=True)
    NORMALIZED.mkdir(parents=True, exist_ok=True)
    for path in TRIMMED.glob("beat-*.mp4"):
        path.unlink()
    for path in TRIMMED.glob("phone-*.mp4"):
        path.unlink()
    for path in NORMALIZED.glob("*.mp4"):
        path.unlink()


def normalize(source: Path, output: Path, start: float, length: float, portrait: bool) -> None:
    # Trim and normalize in one re-encode so cuts land on clean frames and all
    # inputs share exactly the same video parameters before xfade.
    scale = "scale=-2:1080" if portrait else "scale=1920:1080:force_original_aspect_ratio=decrease"
    vf = f"{scale},pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0x0e1824,fps=30,format=yuv420p"
    run([
        FFMPEG, "-y", "-ss", str(start), "-i", str(source), "-t", str(length),
        "-vf", vf, "-an", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output),
    ])


def title_card(text: str, output: Path) -> None:
    # Render the card with the installed Chromium engine, avoiding font and
    # drawtext differences across ffmpeg builds, then normalize it like every
    # other source.
    raw = output.with_suffix(".webm")
    render_python = DEMO / ".venv/bin/python"
    if not render_python.exists():
        raise RuntimeError("demo/.venv/bin/python is required to render title cards")
    run([str(render_python), str(DEMO / "render_title.py"), text, str(raw)])
    normalize(raw, output, 0, 1.8, portrait=False)


def xfade_chain(order: list[Path], output: Path) -> None:
    durations = [duration(path) for path in order]
    inputs: list[str] = []
    for path in order:
        inputs += ["-i", str(path)]

    xfade = 0.4
    cumulative = durations[0]
    last = "0:v"
    filters: list[str] = []
    for index in range(1, len(order)):
        offset = max(0.0, cumulative - xfade)
        label = f"v{index}"
        filters.append(
            f"[{last}][{index}:v]xfade=transition=fade:duration={xfade}:offset={offset:.3f}[{label}]"
        )
        last = label
        cumulative += durations[index] - xfade

    run([
        FFMPEG, "-y", *inputs, "-filter_complex", ";".join(filters),
        "-map", f"[{last}]", "-an", "-c:v", "libx264", "-preset", "ultrafast",
        "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output),
    ])
    print(f"Wrote {output} ({cumulative:.2f}s before final transitions)")


def concat_copy(order: list[Path], output: Path) -> None:
    """Join byte-identical normalized clips with clean hard cuts."""
    list_file = Path("/tmp") / f"hali-{output.stem}-concat.txt"
    list_file.write_text("".join(f"file '{path.resolve()}'\n" for path in order))
    run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
         "-c", "copy", "-movflags", "+faststart", str(output)])


def assemble(web: list[Path], ussd: list[Path], whatsapp: list[Path]) -> None:
    # Every input is byte-identical after normalization. Title cards carry
    # their own short fade, so hard cuts between the normalized segments stay
    # crisp and avoid a large multi-input xfade graph.
    concat_copy(web + ussd + whatsapp, OUTPUT)
    print(f"Wrote {OUTPUT}")


def main() -> None:
    clean_dirs()

    # Keep the meaningful late-state portions of the map beats: beat 04's AOI
    # result and beat 07's hotspot popup occur near the end of their captures.
    web_trim = {
        "01": (0.3, 8.9), "02": (0.5, 16.3), "03": (0.5, 18.9),
        "04": (0.3, 41.0), "05": (0.5, 3.3), "06": (0.5, 14.7),
        "07": (0.3, 30.4),
    }
    web_order: list[Path] = []
    title_card("1. Web app", NORMALIZED / "title-01-web.mp4")
    web_order.append(NORMALIZED / "title-01-web.mp4")
    for number, (start, length) in web_trim.items():
        trimmed = TRIMMED / f"beat-{number}.mp4"
        normalized = NORMALIZED / f"web-{number}.mp4"
        normalize(CLIPS / f"beat-{number}.webm", trimmed, start, length, portrait=False)
        shutil.copy2(trimmed, normalized)
        web_order.append(normalized)

    title_card("2. USSD", NORMALIZED / "title-02-ussd.mp4")
    ussd_order = [NORMALIZED / "title-02-ussd.mp4"]
    ussd = TRIMMED / "phone-ussd.mp4"
    normalize(DEMO / "ussd.mp4", ussd, 0.3, 78.0, portrait=True)
    ussd_normalized = NORMALIZED / "ussd.mp4"
    shutil.copy2(ussd, ussd_normalized)
    ussd_order.append(ussd_normalized)

    title_card("3. WhatsApp", NORMALIZED / "title-03-whatsapp.mp4")
    whatsapp_order = [NORMALIZED / "title-03-whatsapp.mp4"]
    whatsapp = TRIMMED / "phone-whatsapp.mp4"
    normalize(DEMO / "whatsapp.mp4", whatsapp, 0.3, 52.3, portrait=True)
    whatsapp_normalized = NORMALIZED / "whatsapp.mp4"
    shutil.copy2(whatsapp, whatsapp_normalized)
    whatsapp_order.append(whatsapp_normalized)

    assemble(web_order, ussd_order, whatsapp_order)


if __name__ == "__main__":
    main()
