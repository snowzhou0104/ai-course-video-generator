from pathlib import Path

from PIL import Image, ImageDraw

from src.utils import ensure_dir, write_json_file

ACCENT_ORANGE = (245, 130, 32)
DEBUG_OUTLINE_WIDTH = 4

# Slides/highlights to render as debug verification images.
DEBUG_TARGETS = [(1, 0), (1, 1), (1, 2), (12, 0)]


def generate_highlights(
    course_data: dict,
    audio_metadata: list,
    slide_layout: list,
    output_dir: str,
) -> list:
    """
    Build the highlight timeline by joining the frozen course data
    (highlight_plan), audio metadata (segment timing), and slide layout
    (bullet bounding boxes).

    Times are local to each slide's audio, since the video generator
    builds one clip per slide.

    Writes <output_dir>/metadata/highlight_timeline.json and returns
    the timeline list: one entry per slide, each with 3 highlights.
    """
    output_dir = Path(output_dir)
    metadata_dir = output_dir / "metadata"
    ensure_dir(metadata_dir)

    audio_by_slide = {entry["slide_index"]: entry for entry in audio_metadata}
    layout_by_slide = {entry["slide_index"]: entry for entry in slide_layout}

    timeline = []

    for slide in course_data["slides"]:
        index = slide["slide_index"]
        audio = audio_by_slide[index]
        layout = layout_by_slide[index]
        boxes_by_bullet = {
            box["bullet_index"]: box for box in layout["bullet_boxes"]
        }
        segments_by_index = {
            seg["segment_index"]: seg for seg in audio["segments"]
        }

        highlights = []
        for plan in slide["highlight_plan"]:
            segment = segments_by_index[plan["narration_segment_index"]]
            box = boxes_by_bullet[plan["bullet_index"]]

            highlights.append(
                {
                    "bullet_index": plan["bullet_index"],
                    "narration_segment_index": plan["narration_segment_index"],
                    "start": segment["start"],
                    "end": segment["end"],
                    "duration": segment["duration"],
                    "box": {
                        "x": box["x"],
                        "y": box["y"],
                        "w": box["w"],
                        "h": box["h"],
                    },
                    "text": plan["text"],
                }
            )

        timeline.append(
            {
                "slide_index": index,
                "image_path": layout["image_path"],
                "audio_duration": audio["duration"],
                "highlights": highlights,
            }
        )

    write_json_file(timeline, metadata_dir / "highlight_timeline.json")

    _render_debug_images(timeline, output_dir)

    return timeline


def _render_debug_images(timeline: list, output_dir: Path) -> None:
    """Draw the highlight rectangle for a few slide/highlight pairs on
    copies of the rendered slide images (originals are not modified)."""
    debug_dir = output_dir / "debug_highlights"
    ensure_dir(debug_dir)

    by_slide = {entry["slide_index"]: entry for entry in timeline}

    for slide_index, highlight_index in DEBUG_TARGETS:
        entry = by_slide.get(slide_index)
        if entry is None:
            continue

        highlight = entry["highlights"][highlight_index]
        box = highlight["box"]

        img = Image.open(entry["image_path"]).convert("RGB")
        draw = ImageDraw.Draw(img)
        draw.rectangle(
            [box["x"], box["y"], box["x"] + box["w"], box["y"] + box["h"]],
            outline=ACCENT_ORANGE,
            width=DEBUG_OUTLINE_WIDTH,
        )

        out_path = (
            debug_dir / f"slide_{slide_index:02d}_highlight_{highlight_index}.png"
        )
        img.save(out_path)
