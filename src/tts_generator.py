import asyncio
import subprocess
import tempfile
from pathlib import Path

import edge_tts
from mutagen.mp3 import MP3

from src.utils import ensure_dir, write_json_file

DEFAULT_VOICE = "en-US-JennyNeural"
SYNTH_RETRIES = 3


def generate_tts(course_data: dict, output_dir: str, voice: str = DEFAULT_VOICE) -> list:
    """
    Generate voiceover audio for every slide of the frozen course data.

    Each narration segment is synthesized as its own MP3 (so we know the
    exact start/end time of every segment - needed for highlight timing),
    then the segments are concatenated into one slide_NN.mp3 per slide.

    Writes:
      <output_dir>/audio/segments/slide_NN_seg_K.mp3   (per segment)
      <output_dir>/audio/slide_NN.mp3                  (per slide)
      <output_dir>/metadata/audio_metadata.json

    Returns the metadata list.
    """
    output_dir = Path(output_dir)
    audio_dir = output_dir / "audio"
    segments_dir = audio_dir / "segments"
    metadata_dir = output_dir / "metadata"
    ensure_dir(segments_dir)
    ensure_dir(metadata_dir)

    metadata = []

    for slide in course_data["slides"]:
        index = slide["slide_index"]
        print(f"      Slide {index:02d}: synthesizing "
              f"{len(slide['narration_segments'])} segments...")

        segment_entries = []
        segment_paths = []
        cursor = 0.0

        for seg_index, text in enumerate(slide["narration_segments"]):
            seg_path = segments_dir / f"slide_{index:02d}_seg_{seg_index}.mp3"
            _synthesize(text, voice, seg_path)
            duration = _mp3_duration(seg_path)

            segment_entries.append(
                {
                    "segment_index": seg_index,
                    "text": text,
                    "audio_path": seg_path.as_posix(),
                    "start": round(cursor, 3),
                    "end": round(cursor + duration, 3),
                    "duration": round(duration, 3),
                }
            )
            segment_paths.append(seg_path)
            cursor += duration

        slide_path = audio_dir / f"slide_{index:02d}.mp3"
        _concat_mp3(segment_paths, slide_path)
        slide_duration = _mp3_duration(slide_path)

        metadata.append(
            {
                "slide_index": index,
                "audio_path": slide_path.as_posix(),
                "duration": round(slide_duration, 3),
                "segments": segment_entries,
            }
        )

    write_json_file(metadata, metadata_dir / "audio_metadata.json")

    return metadata


def _synthesize(text: str, voice: str, out_path: Path) -> None:
    """Synthesize one text snippet to MP3 via edge-tts, with retries."""
    last_error = None

    for attempt in range(1, SYNTH_RETRIES + 1):
        try:
            communicate = edge_tts.Communicate(text, voice)
            asyncio.run(communicate.save(str(out_path)))
            if out_path.exists() and out_path.stat().st_size > 0:
                return
            last_error = RuntimeError("edge-tts produced an empty file")
        except Exception as exc:  # network hiccups etc.
            last_error = exc

    raise RuntimeError(
        f"TTS synthesis failed after {SYNTH_RETRIES} attempts for: "
        f"{text[:60]!r}... ({last_error})"
    )


def _mp3_duration(path: Path) -> float:
    """Return MP3 duration in seconds using mutagen."""
    return MP3(str(path)).info.length


def _concat_mp3(segment_paths: list, out_path: Path) -> None:
    """Concatenate MP3 segments into one file using ffmpeg (re-encoded so
    duration headers stay accurate)."""
    with tempfile.NamedTemporaryFile(
        "w", suffix=".txt", delete=False, encoding="utf-8"
    ) as f:
        for p in segment_paths:
            f.write(f"file '{Path(p).resolve().as_posix()}'\n")
        list_path = f.name

    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", list_path,
                "-c:a", "libmp3lame", "-b:a", "48k",
                str(out_path),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg concat failed for {out_path.name}:\n{result.stderr[-800:]}"
            )
    finally:
        Path(list_path).unlink(missing_ok=True)
