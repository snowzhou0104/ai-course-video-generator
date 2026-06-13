import shutil
import subprocess
from pathlib import Path

# libass style: white text on a semi-transparent black box (BorderStyle=3),
# bottom center, sized for 1280x720 with a margin that stays clear of the
# bullet highlight area. YaHei covers both Chinese and Latin glyphs.
FORCE_STYLE = (
    "FontName=Microsoft YaHei,FontSize=24,PrimaryColour=&H00FFFFFF,"
    "OutlineColour=&H80000000,BackColour=&H80000000,BorderStyle=3,"
    "Outline=1,Shadow=0,Alignment=2,MarginV=32"
)

TEMP_SRT_NAME = "temp_subtitles.srt"


def burn_subtitles(video_path, subtitle_path, output_path) -> dict:
    """
    Re-encode video_path with subtitle_path burned in via ffmpeg's
    subtitles filter, writing output_path. The audio stream is copied
    unchanged. Returns {"path": output_path}.

    The SRT is copied next to the output as a plain temp filename and
    ffmpeg runs from that directory, so the subtitles filter never sees
    a Windows drive letter or backslash (those need fragile escaping).
    """
    video_path = Path(video_path).resolve()
    subtitle_path = Path(subtitle_path).resolve()
    output_path = Path(output_path).resolve()

    if not video_path.exists():
        raise FileNotFoundError(f"Input video not found: {video_path}")
    if not subtitle_path.exists():
        raise FileNotFoundError(f"Subtitle file not found: {subtitle_path}")

    workdir = output_path.parent
    workdir.mkdir(parents=True, exist_ok=True)
    temp_srt = workdir / TEMP_SRT_NAME

    if subtitle_path != temp_srt:
        shutil.copyfile(subtitle_path, temp_srt)

    try:
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vf", f"subtitles={TEMP_SRT_NAME}:force_style='{FORCE_STYLE}'",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-c:a", "copy",
            output_path.name,
        ]
        result = subprocess.run(
            cmd,
            cwd=str(workdir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg subtitle burn failed:\n{result.stderr[-800:]}"
            )
    finally:
        if subtitle_path != temp_srt and temp_srt.exists():
            temp_srt.unlink()

    return {"path": output_path}
