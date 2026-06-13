from pathlib import Path

import numpy as np
from moviepy import AudioFileClip, VideoClip, concatenate_videoclips
from PIL import Image, ImageDraw

FPS = 24

# Highlight style (matches the slide accent color)
ACCENT_ORANGE = (245, 130, 32)
HIGHLIGHT_FILL_ALPHA = 28      # light transparent orange fill
HIGHLIGHT_BORDER_WIDTH = 5
HIGHLIGHT_CORNER_RADIUS = 10

VIDEO_FILENAME = "final_course_video.mp4"


def generate_video(
    highlight_timeline: list,
    output_dir: str,
    video_name: str = VIDEO_FILENAME,
) -> dict:
    """
    Assemble the final MP4 from the frozen slide images, slide audio and
    highlight timeline: one clip per slide (image + audio, with the orange
    highlight rectangle shown during the matching narration segment),
    concatenated in slide order.

    Returns {"path", "n_clips", "duration"}.
    """
    output_dir = Path(output_dir)
    video_path = output_dir / video_name

    clips = []
    audio_clips = []

    for entry in highlight_timeline:
        index = entry["slide_index"]
        print(f"      Slide {index:02d}: building clip...")

        audio = AudioFileClip(str(output_dir / "audio" / f"slide_{index:02d}.mp3"))
        audio_clips.append(audio)

        clip = _build_slide_clip(entry, audio)
        clips.append(clip)

    final = concatenate_videoclips(clips, method="chain")

    print(f"      Encoding {final.duration:.1f}s of video at {FPS} fps "
          "(this takes a few minutes)...")
    final.write_videofile(
        str(video_path),
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        threads=4,
        logger=None,
    )

    for audio in audio_clips:
        audio.close()

    return {
        "path": str(video_path),
        "n_clips": len(clips),
        "duration": final.duration,
    }


def _build_slide_clip(entry: dict, audio: AudioFileClip) -> VideoClip:
    """
    Build one slide clip: the slide image as the base frame, with the
    orange highlight rectangle drawn (via PIL) during each highlight's
    local time window. The 4 possible frame states (no highlight +
    one per bullet) are pre-composed once; the frame function then just
    selects the state for the current time.
    """
    base_img = Image.open(entry["image_path"]).convert("RGB")
    base_frame = np.asarray(base_img)

    # (start, end, frame) per highlight, in local slide time.
    states = []
    for highlight in entry["highlights"]:
        highlighted = _draw_highlight(base_img, highlight["box"])
        states.append((highlight["start"], highlight["end"], np.asarray(highlighted)))

    def frame_function(t):
        for start, end, frame in states:
            if start <= t < end:
                return frame
        return base_frame

    clip = VideoClip(frame_function, duration=audio.duration)
    return clip.with_audio(audio)


def _draw_highlight(base_img: Image.Image, box: dict) -> Image.Image:
    """Return a copy of the slide image with a rounded orange rectangle
    (light transparent fill + solid border) around the given bullet box."""
    img = base_img.convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    rect = [box["x"], box["y"], box["x"] + box["w"], box["y"] + box["h"]]
    draw.rounded_rectangle(
        rect,
        radius=HIGHLIGHT_CORNER_RADIUS,
        fill=ACCENT_ORANGE + (HIGHLIGHT_FILL_ALPHA,),
        outline=ACCENT_ORANGE + (255,),
        width=HIGHLIGHT_BORDER_WIDTH,
    )

    return Image.alpha_composite(img, overlay).convert("RGB")
