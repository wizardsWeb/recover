"""Render the voiceover to a single MP3 aligned to the 1.5x video.

Reads `segments.json`, speaks each segment with macOS `say`, and lays the results
onto one silent track at their exact start offsets. The output drops onto the
video as a single audio layer with no nudging — which is the whole reason this
builds one track rather than nineteen files.

**Why it checks durations.** A segment that runs longer than its window talks
over the next one, and by the end the narration is describing a page that left
the screen a minute ago. Anything that overruns is re-rendered at a higher
speaking rate, up to a limit; past that limit it is reported rather than
silently squeezed into something nobody can follow. Shortening the words is then
a judgement, and it is yours.

    cd docs/voiceover
    python3 build-voiceover.py                 # Samantha, the default
    python3 build-voiceover.py --voice Rishi   # Indian English
    python3 build-voiceover.py --list-voices

Output:
    voiceover.mp3        one aligned track, drop it straight on the video
    segments/S01.mp3 …   per segment, if you would rather place them by hand
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEGMENTS_DIR = HERE / "segments"

#: Words per minute for `say`. 175 is its default and reads a little brisk for
#: narration; 165 is closer to a person explaining something.
BASE_RATE = 165

#: The fastest we will push a segment to make it fit. Past this it stops sounding
#: like explanation and starts sounding like a disclaimer.
MAX_RATE = 205

#: Leave a breath at the end of each window rather than running to the very edge.
TAIL_GAP = 0.35


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True)


def duration(path: Path) -> float:
    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=nw=1:nk=1", str(path),
        ],
        check=True, capture_output=True, text=True,
    )
    return float(out.stdout.strip())


def speak(text: str, voice: str, rate: int, out_aiff: Path) -> float:
    run(["say", "-v", voice, "-r", str(rate), "-o", str(out_aiff), text])
    return duration(out_aiff)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--voice", default="Samantha")
    parser.add_argument("--list-voices", action="store_true")
    parser.add_argument("--rate", type=int, default=BASE_RATE)
    args = parser.parse_args()

    if args.list_voices:
        subprocess.run(["say", "-v", "?"], check=False)
        return 0

    for tool in ("say", "ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            print(f"{tool} not found.")
            return 1

    spec = json.loads((HERE / "segments.json").read_text())
    segments = spec["segments"]

    SEGMENTS_DIR.mkdir(exist_ok=True)
    for stale in SEGMENTS_DIR.glob("*"):
        stale.unlink()

    print(f"Voice: {args.voice}   base rate: {args.rate} wpm\n")
    print(f"  {'seg':<5}{'start':>8}{'window':>8}{'spoken':>8}{'rate':>6}  fit")
    print("  " + "─" * 46)

    rendered: list[tuple[dict, Path, float]] = []
    overruns: list[str] = []

    for segment in segments:
        aiff = SEGMENTS_DIR / f"{segment['id']}.aiff"
        window = float(segment["window"])
        budget = max(1.0, window - TAIL_GAP)

        rate = args.rate
        spoken = speak(segment["text"], args.voice, rate, aiff)

        # Speed up only as far as needed, and only as far as MAX_RATE.
        while spoken > budget and rate < MAX_RATE:
            rate = min(MAX_RATE, int(rate * min(1.35, spoken / budget) + 1))
            spoken = speak(segment["text"], args.voice, rate, aiff)

        fits = spoken <= budget
        flag = "ok" if fits else f"OVER by {spoken - budget:.1f}s"
        if not fits:
            words = len(segment["text"].split())
            overruns.append(
                f"{segment['id']} ({segment['title']}): {spoken:.1f}s in a "
                f"{window:.1f}s window at {rate} wpm — {words} words, "
                f"cut about {int((spoken - budget) * rate / 60)}"
            )

        print(
            f"  {segment['id']:<5}{segment['start']:>8.1f}{window:>8.1f}"
            f"{spoken:>8.1f}{rate:>6}  {flag}"
        )

        mp3 = SEGMENTS_DIR / f"{segment['id']}.mp3"
        run(["ffmpeg", "-loglevel", "error", "-i", str(aiff),
             "-codec:a", "libmp3lame", "-q:a", "2", "-y", str(mp3)])
        rendered.append((segment, aiff, spoken))

    # One track: every segment delayed to its own start offset, mixed together.
    # adelay works in milliseconds and needs a value per channel.
    total_ms = int((float(segments[-1]["start"]) + rendered[-1][2] + 2) * 1000)
    inputs: list[str] = []
    filters: list[str] = []
    for index, (segment, aiff, _) in enumerate(rendered):
        inputs += ["-i", str(aiff)]
        delay = int(float(segment["start"]) * 1000)
        filters.append(f"[{index}:a]adelay={delay}|{delay},aformat=sample_fmts=fltp[a{index}]")
    mix = "".join(f"[a{i}]" for i in range(len(rendered)))
    graph = ";".join(filters) + f";{mix}amix=inputs={len(rendered)}:normalize=0[out]"

    out = HERE.parent / "voiceover.mp3"
    run([
        "ffmpeg", "-loglevel", "error", *inputs,
        "-filter_complex", graph, "-map", "[out]",
        "-t", str(total_ms / 1000),
        "-codec:a", "libmp3lame", "-q:a", "2", "-y", str(out),
    ])

    for _, aiff, _ in rendered:
        aiff.unlink(missing_ok=True)

    print(f"\n  aligned track: {out}  ({duration(out):.1f}s)")
    print(f"  per segment:   {SEGMENTS_DIR}/S*.mp3")

    if overruns:
        print("\n  These do not fit and will talk over the next segment:")
        for line in overruns:
            print(f"    - {line}")
        print("\n  Trim the text in segments.json and re-run.")
        return 1

    print("\n  Every segment fits its window.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
