"""Render the voiceover with ElevenLabs and lay it onto one aligned track.

Same job as `build-voiceover.py`, better voice. It reads `segments.json`, calls
the ElevenLabs text-to-speech API once per segment, checks each clip fits the
window it has to sit in, and mixes them onto a single track at their exact start
offsets — so the result drops onto the video as one audio layer with nothing to
nudge.

**Generate per segment, not in one blob.** Pasting the whole script into the web
app gives you one long clip with no way to know where segment nine begins, and
the narration drifts out from under the picture within a minute. Nineteen clips
at known offsets is the only version that stays in sync.

Cost is charged per character. The whole script is about six thousand
characters, so a full render is roughly six thousand credits. Clips are cached in
`segments-11labs/`, and a re-run only regenerates what changed — editing one
segment costs one segment.

    export ELEVENLABS_API_KEY=sk_...

    python3 build-voiceover-elevenlabs.py --list-voices
    python3 build-voiceover-elevenlabs.py --voice Rachel
    python3 build-voiceover-elevenlabs.py --voice Rachel --force   # ignore cache

If you would rather paste the text into the web app by hand, generate the clips
there, save them as S01.mp3 … S19.mp3 in a folder, and assemble with:

    python3 build-voiceover-elevenlabs.py --from-dir ~/Downloads/vo

`script-for-elevenlabs.txt` is that text, one segment per block.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLIPS = HERE / "segments-11labs"
API = "https://api.elevenlabs.io/v1"

#: Multilingual, because several segments quote Hinglish — "baaki twenty five
#: tak", "beta ab coaching nahi le raha". An English-only model mangles them.
DEFAULT_MODEL = "eleven_multilingual_v2"

#: Leave a breath at the end of each window rather than running to the edge.
TAIL_GAP = 0.35

#: How far we will speed a clip up to make it fit. ElevenLabs accepts more, but
#: past this it stops sounding like explanation.
MAX_SPEED = 1.18


def die(message: str) -> int:
    print(f"\n{message}\n")
    return 1


def api(path: str, key: str, body: dict | None = None, raw: bool = False) -> bytes | dict:
    url = f"{API}{path}"
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    request.add_header("xi-api-key", key)
    if data:
        request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=180) as response:
        payload = response.read()
    return payload if raw else json.loads(payload)


def duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(out.stdout.strip())


#: The long-standing premade voices, by id.
#:
#: Here because an API key scoped to text-to-speech alone cannot read /voices —
#: it comes back 401 "missing the permission voices_read" — and refusing to
#: synthesise because we could not look up a name we already know would be a
#: silly way to fail.
PREMADE = {
    # Verified reachable on a free-tier key. The older set — Rachel, Aria,
    # Charlotte — now counts as "library" voices and returns 402
    # paid_plan_required, so they are deliberately not listed here.
    "brian": ("nPczCjzI2devNBz1zQrb", "Brian"),
    "george": ("JBFqnCBsd6RMkjVDRZzb", "George"),
    "daniel": ("onwK4e9ZLuTAKqWW03F9", "Daniel"),
    "roger": ("CwhRBWXzGAHq8TQ4Fs17", "Roger"),
    "sarah": ("EXAVITQu4vr4xnSDxMaL", "Sarah"),
    "laura": ("FGY2WhTYpPnrIDTdsKH5", "Laura"),
    "alice": ("Xb7hH8MSUJpSbSDYk0k2", "Alice"),
    "matilda": ("XrExE9yKIg1WjnnlVkGX", "Matilda"),
    "jessica": ("cgSgspJ2msm6clMCkdW9", "Jessica"),
    "lily": ("pFZP5JQG7iQjIQuC4Bku", "Lily"),
}


def resolve_voice(name: str, key: str) -> tuple[str, str]:
    """Accept a voice id or a voice name, and return (id, name).

    Tries the account's own voice list first, because that is the only way to
    reach a cloned or custom voice. Falls back to the premade table when the key
    is not allowed to read it.
    """
    try:
        voices = api("/voices", key)["voices"]
    except urllib.error.HTTPError as error:
        if error.code not in (401, 403):
            raise
        if name.lower() in PREMADE:
            return PREMADE[name.lower()]
        if len(name) >= 20 and name.isalnum():
            return name, name
        raise SystemExit(
            f"This key cannot list voices, and {name!r} is not one of the premade "
            f"ones ({', '.join(sorted(PREMADE))}).\n"
            "Pass a voice id directly, or use a key with the voices_read scope."
        ) from error

    for voice in voices:
        if voice["voice_id"] == name:
            return voice["voice_id"], voice["name"]
    for voice in voices:
        if voice["name"].lower() == name.lower():
            return voice["voice_id"], voice["name"]
    available = ", ".join(sorted(v["name"] for v in voices))
    raise SystemExit(f"No voice called {name!r}. Available: {available}")


def synthesise(text: str, voice_id: str, key: str, model: str, speed: float, out: Path) -> None:
    audio = api(
        f"/text-to-speech/{voice_id}?output_format=mp3_44100_128",
        key,
        {
            "text": text,
            "model_id": model,
            "voice_settings": {
                # A narration voice should not wander. Higher stability keeps the
                # read even across nineteen separately generated clips, which is
                # what stops them sounding like nineteen different takes.
                "stability": 0.55,
                "similarity_boost": 0.75,
                "style": 0.0,
                "use_speaker_boost": True,
                "speed": round(speed, 3),
            },
        },
        raw=True,
    )
    out.write_bytes(audio)  # type: ignore[arg-type]


def assemble(segments: list[dict], clips: dict[str, Path], out: Path) -> float:
    """Mix every clip onto one track at its own start offset."""
    inputs: list[str] = []
    filters: list[str] = []
    for index, segment in enumerate(segments):
        inputs += ["-i", str(clips[segment["id"]])]
        delay = int(float(segment["start"]) * 1000)
        filters.append(
            f"[{index}:a]adelay={delay}|{delay},aformat=sample_fmts=fltp[a{index}]"
        )
    mix = "".join(f"[a{i}]" for i in range(len(segments)))
    graph = ";".join(filters) + f";{mix}amix=inputs={len(segments)}:normalize=0[out]"

    subprocess.run(
        ["ffmpeg", "-loglevel", "error", *inputs, "-filter_complex", graph,
         "-map", "[out]", "-codec:a", "libmp3lame", "-q:a", "2", "-y", str(out)],
        check=True, capture_output=True,
    )
    return duration(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--voice", default="Brian", help="voice name or voice_id")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--list-voices", action="store_true")
    parser.add_argument("--force", action="store_true", help="regenerate cached clips")
    parser.add_argument("--from-dir", help="assemble S01.mp3…S19.mp3 from this folder instead")
    args = parser.parse_args()

    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            return die(f"{tool} not found — brew install ffmpeg")

    spec = json.loads((HERE / "segments.json").read_text())
    segments = spec["segments"]
    out = HERE.parent / "voiceover.mp3"

    # ── assemble clips generated elsewhere ───────────────────────────
    if args.from_dir:
        source = Path(args.from_dir).expanduser()
        clips: dict[str, Path] = {}
        missing: list[str] = []
        for segment in segments:
            path = source / f"{segment['id']}.mp3"
            if path.exists():
                clips[segment["id"]] = path
            else:
                missing.append(path.name)
        if missing:
            return die(f"Missing in {source}: {', '.join(missing)}")

        print(f"  {'seg':<5}{'start':>8}{'window':>8}{'clip':>8}  fit")
        print("  " + "─" * 40)
        over = 0
        for segment in segments:
            spoken = duration(clips[segment["id"]])
            budget = float(segment["window"]) - TAIL_GAP
            fits = spoken <= budget
            over += 0 if fits else 1
            print(
                f"  {segment['id']:<5}{segment['start']:>8.1f}"
                f"{segment['window']:>8.1f}{spoken:>8.1f}  "
                f"{'ok' if fits else f'OVER by {spoken - budget:.1f}s'}"
            )
        total = assemble(segments, clips, out)
        print(f"\n  aligned track: {out}  ({total:.1f}s)")
        if over:
            print(f"\n  {over} clip(s) overrun. Regenerate those with a faster speed,")
            print("  or trim the text in segments.json.")
            return 1
        return 0

    # ── generate through the API ─────────────────────────────────────
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        return die(
            "ELEVENLABS_API_KEY is not set.\n"
            "  Get one at elevenlabs.io → your profile → API Keys, then:\n"
            "    export ELEVENLABS_API_KEY=sk_...\n"
            "  Or generate the clips in the web app and use --from-dir."
        )

    try:
        if args.list_voices:
            for voice in api("/voices", key)["voices"]:
                labels = voice.get("labels") or {}
                description = ", ".join(f"{k}={v}" for k, v in labels.items())
                print(f"  {voice['name']:<22} {voice['voice_id']}  {description}")
            return 0
        voice_id, voice_name = resolve_voice(args.voice, key)
    except urllib.error.HTTPError as error:
        return die(f"ElevenLabs returned {error.code}: {error.read().decode()[:300]}")
    except urllib.error.URLError as error:
        return die(f"Could not reach ElevenLabs: {error.reason}")

    CLIPS.mkdir(exist_ok=True)
    characters = sum(len(s["text"]) for s in segments)
    print(f"Voice: {voice_name} ({voice_id})   model: {args.model}")
    print(f"Script: {characters} characters across {len(segments)} segments\n")
    print(f"  {'seg':<5}{'start':>8}{'window':>8}{'spoken':>8}{'speed':>7}  fit")
    print("  " + "─" * 47)

    clips = {}
    overruns: list[str] = []

    for segment in segments:
        path = CLIPS / f"{segment['id']}.mp3"
        stamp = CLIPS / f"{segment['id']}.txt"
        budget = float(segment["window"]) - TAIL_GAP

        # Only pay again for a segment whose words, voice or model changed.
        signature = f"{voice_id}|{args.model}|{segment['text']}"
        cached = path.exists() and stamp.exists() and stamp.read_text() == signature
        if cached and not args.force:
            spoken, speed, mark = duration(path), 1.0, "cached"
        else:
            speed = 1.0
            try:
                synthesise(segment["text"], voice_id, key, args.model, speed, path)
            except urllib.error.HTTPError as error:
                return die(
                    f"{segment['id']} failed with {error.code}: "
                    f"{error.read().decode()[:300]}"
                )
            spoken = duration(path)

            # Too long for its window: speed up rather than re-writing, but only
            # so far. Past MAX_SPEED the words stop landing.
            while spoken > budget and speed < MAX_SPEED:
                speed = min(MAX_SPEED, speed * min(1.15, spoken / budget))
                synthesise(segment["text"], voice_id, key, args.model, speed, path)
                spoken = duration(path)

            stamp.write_text(signature)
            mark = ""

        fits = spoken <= budget
        flag = "ok" if fits else f"OVER by {spoken - budget:.1f}s"
        if mark and fits:
            flag = "ok (cached)"
        if not fits:
            words = len(segment["text"].split())
            overruns.append(
                f"{segment['id']} ({segment['title']}): {spoken:.1f}s in "
                f"{segment['window']:.1f}s at speed {speed:.2f} — {words} words, "
                f"cut roughly {int((spoken - budget) * 2.7)}"
            )
        print(
            f"  {segment['id']:<5}{segment['start']:>8.1f}"
            f"{segment['window']:>8.1f}{spoken:>8.1f}{speed:>7.2f}  {flag}"
        )
        clips[segment["id"]] = path

    total = assemble(segments, clips, out)
    print(f"\n  aligned track: {out}  ({total:.1f}s)")
    print(f"  clips cached:  {CLIPS}/")

    if overruns:
        print("\n  These will talk over the next segment:")
        for line in overruns:
            print(f"    - {line}")
        print("\n  Trim the text in segments.json and re-run — only those regenerate.")
        return 1

    print("\n  Every segment fits its window. Mux it onto the video with:")
    print("    ffmpeg -i docs/demo-recording-1.5x.mp4 -i docs/voiceover.mp3 \\")
    print("      -c:v copy -c:a aac -b:a 192k -map 0:v:0 -map 1:a:0 \\")
    print("      -movflags +faststart -y docs/demo-with-voiceover.mp4")
    return 0


if __name__ == "__main__":
    sys.exit(main())
