import argparse
import sys
from pathlib import Path

# Chinese narration text would crash prints on the default cp1252 console.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.script_loader import load_script
from src.ppt_generator import generate_ppt
from src.slide_renderer import render_slides
from src.tts_generator import generate_tts
from src.subtitle_generator import generate_subtitles
from src.highlight_generator import generate_highlights
from src.utils import read_json_file, write_json_file


def main():
    parser = argparse.ArgumentParser(
        description="AI Course Video Generator"
    )

    parser.add_argument(
        "--input",
        type=str,
        default="input/Core Departments in Tech Companies.pdf",
        help="Path to the input course script file. Supports .txt and .pdf.",
    )

    parser.add_argument(
        "--output",
        type=str,
        default="output",
        help="Output directory for all generated artifacts.",
    )

    parser.add_argument(
        "--voice",
        type=str,
        default="en-US-JennyNeural",
        help="TTS voice for narration (used in later pipeline phases).",
    )

    parser.add_argument(
        "--render-only",
        action="store_true",
        help="Skip the LLM and PPTX steps; reuse the existing "
             "structured_course.json and only run slide image rendering.",
    )

    parser.add_argument(
        "--tts-only",
        action="store_true",
        help="Skip the LLM, PPTX, and rendering steps; reuse the existing "
             "structured_course.json and only generate TTS audio.",
    )

    parser.add_argument(
        "--subtitles-only",
        action="store_true",
        help="Reuse the existing audio_metadata.json and only generate "
             "the global subtitles.srt file.",
    )

    parser.add_argument(
        "--highlights-only",
        action="store_true",
        help="Reuse the existing structured_course.json, audio_metadata.json "
             "and slide_layout.json to generate highlight_timeline.json.",
    )

    parser.add_argument(
        "--video-only",
        action="store_true",
        help="Reuse the existing slide images, audio and highlight timeline "
             "to assemble the final MP4 video.",
    )

    parser.add_argument(
        "--translate-only",
        action="store_true",
        help="Translate the narration of the frozen course JSON to Chinese "
             "via the LLM and write structured_course_zh.json. Slide titles, "
             "bullets and highlight_plan stay unchanged.",
    )

    parser.add_argument(
        "--translate-slides-only",
        action="store_true",
        help="Translate slide titles/bullets to Chinese via the LLM (from "
             "--course-json, e.g. the Chinese narration JSON), then generate "
             "the Chinese PPTX and rendered slide images into --output.",
    )

    parser.add_argument(
        "--course-json",
        type=str,
        default=None,
        help="Path to the course JSON to use (default: "
             "<output>/structured_course.json). Pass "
             "output/structured_course_zh.json for the Chinese narration.",
    )

    parser.add_argument(
        "--layout-json",
        type=str,
        default=None,
        help="Path to the slide layout metadata (default: "
             "<output>/metadata/slide_layout.json). The Chinese pipeline "
             "reuses the English layout since the slides are identical.",
    )

    parser.add_argument(
        "--video-name",
        type=str,
        default="final_course_video.mp4",
        help="Filename for the exported MP4 inside the output directory.",
    )

    parser.add_argument(
        "--language",
        type=str,
        choices=["en", "zh"],
        default="en",
        help="Narration language for the full pipeline: en keeps the LLM "
             "narration, zh adds a translation step before TTS.",
    )

    parser.add_argument(
        "--burn-subtitles",
        action="store_true",
        help="Burn an SRT into an existing MP4 with ffmpeg, writing a new "
             "*_subtitled.mp4 next to it. The clean MP4 and the SRT are "
             "kept unchanged.",
    )

    parser.add_argument(
        "--input-video",
        type=str,
        default=None,
        help="Source MP4 for --burn-subtitles "
             "(default: <output>/<video-name>).",
    )

    parser.add_argument(
        "--subtitle-file",
        type=str,
        default=None,
        help="SRT file for --burn-subtitles (default: <output>/subtitles.srt).",
    )

    parser.add_argument(
        "--subtitle-video-name",
        type=str,
        default=None,
        help="Filename for the subtitled MP4 inside the output directory "
             "(default: <video-name stem>_subtitled.mp4).",
    )

    parser.add_argument(
        "--translate-subtitles",
        action="store_true",
        help="Translate an existing SRT to --subtitle-language via the LLM, "
             "preserving entry numbers and timestamps exactly. The original "
             "SRT is kept unchanged.",
    )

    parser.add_argument(
        "--subtitle-language",
        type=str,
        choices=["en", "zh"],
        default=None,
        help="Target language for --translate-subtitles.",
    )

    parser.add_argument(
        "--subtitle-input",
        type=str,
        default=None,
        help="Source SRT for --translate-subtitles "
             "(default: <output>/subtitles.srt).",
    )

    parser.add_argument(
        "--subtitle-output",
        type=str,
        default=None,
        help="Destination SRT for --translate-subtitles "
             "(default: <output>/subtitles_<language>.srt).",
    )

    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="In the full pipeline, skip a stage when its output files "
             "already exist and pass a quick validity check.",
    )

    args = parser.parse_args()

    output_dir = Path(args.output)
    json_path = (
        Path(args.course_json) if args.course_json
        else output_dir / "structured_course.json"
    )
    layout_path = (
        Path(args.layout_json) if args.layout_json
        else output_dir / "metadata" / "slide_layout.json"
    )
    pptx_path = output_dir / "course_slides.pptx"

    if args.translate_subtitles:
        if not args.subtitle_language:
            sys.exit(
                "--translate-subtitles requires --subtitle-language en or zh."
            )
        subtitle_input = (
            Path(args.subtitle_input) if args.subtitle_input
            else output_dir / "subtitles.srt"
        )
        subtitle_output = (
            Path(args.subtitle_output) if args.subtitle_output
            else output_dir / f"subtitles_{args.subtitle_language}.srt"
        )
        if not subtitle_input.exists():
            sys.exit(f"Cannot translate subtitles: {subtitle_input} does not exist.")

        print(f"[1/3] Translating {subtitle_input} to "
              f"'{args.subtitle_language}' via the LLM...")
        source_content = subtitle_input.read_text(encoding="utf-8")

        from src.subtitle_translator import translate_subtitles

        translated_content = translate_subtitles(
            source_content, args.subtitle_language
        )
        subtitle_output.parent.mkdir(parents=True, exist_ok=True)
        subtitle_output.write_text(translated_content, encoding="utf-8")

        print("[2/3] Validating translated subtitles...")
        _validate_subtitle_translation(
            source_content, subtitle_output, args.subtitle_language
        )

        print("[3/3] Done.")
        print(f"Original SRT (unchanged): {subtitle_input}")
        print(f"Translated SRT saved:     {subtitle_output}")
        return

    if args.burn_subtitles:
        input_video = (
            Path(args.input_video) if args.input_video
            else output_dir / args.video_name
        )
        subtitle_file = (
            Path(args.subtitle_file) if args.subtitle_file
            else output_dir / "subtitles.srt"
        )
        subtitled_name = (
            args.subtitle_video_name
            if args.subtitle_video_name
            else f"{input_video.stem}_subtitled.mp4"
        )
        subtitled_path = output_dir / subtitled_name

        if not input_video.exists():
            sys.exit(f"Cannot burn subtitles: {input_video} does not exist.")
        if not subtitle_file.exists():
            sys.exit(f"Cannot burn subtitles: {subtitle_file} does not exist.")

        print(f"[1/3] Burning {subtitle_file} into {input_video} (ffmpeg)...")
        from src.subtitle_burner import burn_subtitles

        burn_subtitles(input_video, subtitle_file, subtitled_path)

        print("[2/3] Validating subtitled video...")
        _validate_subtitled_video(input_video, subtitled_path)

        print("[3/3] Done.")
        print(f"Clean video (unchanged): {input_video}")
        print(f"Subtitles (unchanged):   {subtitle_file}")
        print(f"Subtitled video saved:   {subtitled_path}")
        return

    if args.translate_slides_only:
        if not args.course_json or not json_path.exists():
            sys.exit(
                "Cannot use --translate-slides-only: pass --course-json with "
                "the Chinese narration JSON, e.g. "
                "--course-json output/structured_course_zh.json"
            )
        print("[1/4] Reading course JSON and translating slide text (LLM)...")
        course_data = read_json_file(json_path)

        from src.slide_translator import translate_slide_text

        visual_data = translate_slide_text(course_data)
        visual_path = output_dir / "structured_course_zh_visual.json"
        write_json_file(visual_data, visual_path)
        _validate_slide_translation(course_data, visual_data, visual_path)

        print("[2/4] Generating Chinese PPTX...")
        pptx_zh_path = output_dir / "course_slides_zh.pptx"
        generate_ppt(visual_data, str(pptx_zh_path))

        print("[3/4] Rendering Chinese slide images...")
        layout = render_slides(visual_data, str(output_dir))
        _validate_rendering(visual_data, layout, output_dir)

        print("[4/4] Done.")
        print(f"Chinese slide JSON:   {visual_path}")
        print(f"Chinese PPTX:         {pptx_zh_path}")
        print(f"Chinese slide images: {output_dir / 'slide_images'}")
        print(f"Layout metadata:      {output_dir / 'metadata' / 'slide_layout.json'}")
        return

    if args.translate_only:
        if not json_path.exists():
            sys.exit(f"Cannot use --translate-only: {json_path} does not exist.")
        print("[1/3] Reading frozen structured course JSON...")
        course_data = read_json_file(json_path)

        # The only permitted LLM call outside Phase 1: narration translation.
        from src.narration_translator import translate_narration

        print("[2/3] Translating narration to Chinese via the LLM...")
        zh_data = translate_narration(course_data)
        zh_path = json_path.with_name("structured_course_zh.json")
        write_json_file(zh_data, zh_path)
        _validate_translation(course_data, zh_data, zh_path)

        print("[3/3] Done.")
        print(f"Chinese narration JSON saved to: {zh_path}")
        print(f"Sample (slide 1, segment 0): {zh_data['slides'][0]['narration_segments'][0]}")
        return

    if args.video_only:
        timeline_path = output_dir / "metadata" / "highlight_timeline.json"
        if not timeline_path.exists():
            sys.exit(
                f"Cannot use --video-only: {timeline_path} does not exist. "
                "Run with --highlights-only first."
            )
        print("[1/3] Reusing frozen highlight timeline, slide images and audio "
              "(no LLM call)...")
        highlight_timeline = read_json_file(timeline_path)

        # video_generator imports moviepy/numpy; keep the import local so the
        # other pipeline modes work even if those packages are missing.
        from src.video_generator import generate_video

        print("[2/3] Assembling final video...")
        result = generate_video(highlight_timeline, str(output_dir), args.video_name)
        _validate_video(highlight_timeline, Path(result["path"]))

        print("[3/3] Done.")
        print(f"Slide clips:     {result['n_clips']}")
        print(f"Total duration:  {result['duration']:.1f}s")
        print(f"Video saved:     {result['path']}")
        print("Export status:   OK")
        return

    if args.highlights_only:
        audio_metadata_path = output_dir / "metadata" / "audio_metadata.json"
        for required in (json_path, audio_metadata_path, layout_path):
            if not required.exists():
                sys.exit(f"Cannot use --highlights-only: {required} does not exist.")

        print("[1/3] Reusing frozen JSON, audio metadata and slide layout (no LLM call)...")
        course_data = read_json_file(json_path)
        audio_metadata = read_json_file(audio_metadata_path)
        slide_layout = read_json_file(layout_path)

        print("[2/3] Generating highlight timeline...")
        timeline = generate_highlights(
            course_data, audio_metadata, slide_layout, str(output_dir)
        )
        _validate_highlights(course_data, timeline, output_dir)

        total_highlights = sum(len(e["highlights"]) for e in timeline)
        print("[3/3] Done.")
        print(f"Slides:             {len(timeline)}")
        print(f"Highlight entries:  {total_highlights}")
        print(f"Timeline saved:     {output_dir / 'metadata' / 'highlight_timeline.json'}")
        print(f"Debug images:       {output_dir / 'debug_highlights'}")
        return

    if args.subtitles_only:
        audio_metadata_path = output_dir / "metadata" / "audio_metadata.json"
        if not audio_metadata_path.exists():
            sys.exit(
                f"Cannot use --subtitles-only: {audio_metadata_path} does not "
                "exist. Run with --tts-only first."
            )
        print("[1/3] Reusing frozen audio metadata (no LLM call)...")
        audio_metadata = read_json_file(audio_metadata_path)

        print("[2/3] Generating subtitles...")
        entries = generate_subtitles(audio_metadata, str(output_dir))
        _validate_subtitles(entries, audio_metadata, output_dir)

        srt_path = output_dir / "subtitles.srt"
        total_duration = sum(s["duration"] for s in audio_metadata)
        print("[3/3] Done.")
        print(f"Subtitle entries:  {len(entries)}")
        print(f"Total duration:    {total_duration:.1f}s")
        print(f"Subtitles saved:   {srt_path}")
        return

    if args.tts_only:
        if not json_path.exists():
            sys.exit(f"Cannot use --tts-only: {json_path} does not exist.")
        print("[1/3] Reusing frozen structured course JSON (no LLM call)...")
        course_data = read_json_file(json_path)

        print(f"[2/3] Generating TTS audio (voice: {args.voice})...")
        audio_metadata = generate_tts(course_data, str(output_dir), args.voice)
        _validate_tts(course_data, audio_metadata, output_dir)

        print("[3/3] Done.")
        print(f"Audio files saved to:   {output_dir / 'audio'}")
        print(f"Audio metadata saved:   {output_dir / 'metadata' / 'audio_metadata.json'}")
        return

    if args.render_only:
        if not json_path.exists():
            sys.exit(f"Cannot use --render-only: {json_path} does not exist.")
        print("[1/3] Reusing frozen structured course JSON (no LLM call)...")
        course_data = read_json_file(json_path)

        print("[2/3] Rendering slide images...")
        layout = render_slides(course_data, str(output_dir))
        _validate_rendering(course_data, layout, output_dir)

        print("[3/3] Done.")
        print(f"Slide images saved to:  {output_dir / 'slide_images'}")
        print(f"Layout metadata saved:  {output_dir / 'metadata' / 'slide_layout.json'}")
        return

    # Full pipeline: input script -> final video. Calls the LLM for course
    # structuring and (for --language zh) narration translation. All paths
    # derive from --output, so the frozen output/ artifacts stay untouched
    # as long as a different output directory is used.
    voice = args.voice
    if args.language == "zh" and voice == "en-US-JennyNeural":
        voice = "zh-CN-XiaoxiaoNeural"
        print(f"Note: --language zh, switching default voice to {voice}.")

    json_path = output_dir / "structured_course.json"
    pptx_path = output_dir / "course_slides.pptx"
    audio_metadata_path = output_dir / "metadata" / "audio_metadata.json"
    timeline_path = output_dir / "metadata" / "highlight_timeline.json"
    srt_path = output_dir / "subtitles.srt"
    video_path = output_dir / args.video_name

    print(f"[1/8] Loading input: {args.input}")
    course_script = load_script(args.input)

    print("[2/8] Structuring course (LLM)...")
    course_data = None
    if args.skip_existing and json_path.exists():
        existing = read_json_file(json_path)
        if _course_data_ok(existing):
            print(f"      Skipping: {json_path} exists and is valid.")
            course_data = existing
    if course_data is None:
        if json_path.exists():
            print(f"      Overwriting {json_path}")
        from src.llm_parser import parse_course_script
        course_data = parse_course_script(course_script)
        write_json_file(course_data, json_path)

    print("[3/8] Generating PPT...")
    if args.skip_existing and pptx_path.exists() and pptx_path.stat().st_size > 0:
        print(f"      Skipping: {pptx_path} exists.")
    else:
        if pptx_path.exists():
            print(f"      Overwriting {pptx_path}")
        generate_ppt(course_data, str(pptx_path))

    print("[4/8] Rendering slides...")
    layout_file = output_dir / "metadata" / "slide_layout.json"
    if args.skip_existing and _rendering_ok(course_data, output_dir):
        print(f"      Skipping: slide images and {layout_file} exist and are valid.")
    else:
        if layout_file.exists():
            print(f"      Overwriting slide images and {layout_file}")
        layout = render_slides(course_data, str(output_dir))
        _validate_rendering(course_data, layout, output_dir)

    print("[5/8] Translating narration...")
    if args.language == "zh":
        zh_path = output_dir / "structured_course_zh.json"
        narration_data = None
        if args.skip_existing and zh_path.exists():
            existing = read_json_file(zh_path)
            if _translation_ok(course_data, existing):
                print(f"      Skipping: {zh_path} exists and is valid.")
                narration_data = existing
        if narration_data is None:
            if zh_path.exists():
                print(f"      Overwriting {zh_path}")
            from src.narration_translator import translate_narration
            narration_data = translate_narration(course_data)
            write_json_file(narration_data, zh_path)
            _validate_translation(course_data, narration_data, zh_path)
    else:
        print("      Skipped (--language en uses the original narration).")
        narration_data = course_data

    print(f"[6/8] Generating TTS (voice: {voice})...")
    audio_metadata = None
    if args.skip_existing and audio_metadata_path.exists():
        existing = read_json_file(audio_metadata_path)
        if _tts_ok(narration_data, existing, output_dir):
            print(f"      Skipping: audio files and {audio_metadata_path} exist and are valid.")
            audio_metadata = existing
    if audio_metadata is None:
        if audio_metadata_path.exists():
            print(f"      Overwriting audio files and {audio_metadata_path}")
        audio_metadata = generate_tts(narration_data, str(output_dir), voice)
        _validate_tts(narration_data, audio_metadata, output_dir)

    print("[7/8] Generating subtitles and highlight timeline...")
    if args.skip_existing and srt_path.exists() and srt_path.stat().st_size > 0:
        print(f"      Skipping: {srt_path} exists.")
    else:
        if srt_path.exists():
            print(f"      Overwriting {srt_path}")
        entries = generate_subtitles(audio_metadata, str(output_dir))
        _validate_subtitles(entries, audio_metadata, output_dir)

    slide_layout = read_json_file(layout_file)
    highlight_timeline = None
    if args.skip_existing and timeline_path.exists():
        existing = read_json_file(timeline_path)
        if len(existing) == len(narration_data["slides"]):
            print(f"      Skipping: {timeline_path} exists.")
            highlight_timeline = existing
    if highlight_timeline is None:
        if timeline_path.exists():
            print(f"      Overwriting {timeline_path}")
        highlight_timeline = generate_highlights(
            narration_data, audio_metadata, slide_layout, str(output_dir)
        )
        _validate_highlights(narration_data, highlight_timeline, output_dir)

    print("[8/8] Exporting video...")
    if args.skip_existing and video_path.exists() and video_path.stat().st_size > 1024 * 1024:
        print(f"      Skipping: {video_path} exists.")
    else:
        if video_path.exists():
            print(f"      Overwriting {video_path}")
        from src.video_generator import generate_video
        result = generate_video(highlight_timeline, str(output_dir), args.video_name)
        _validate_video(highlight_timeline, Path(result["path"]))

    print("Done. Outputs:")
    print(f"Structured course JSON: {json_path}")
    if args.language == "zh":
        print(f"Chinese narration JSON: {output_dir / 'structured_course_zh.json'}")
    print(f"PPT slides:             {pptx_path}")
    print(f"Slide images:           {output_dir / 'slide_images'}")
    print(f"Audio:                  {output_dir / 'audio'}")
    print(f"Subtitles:              {srt_path}")
    print(f"Highlight timeline:     {timeline_path}")
    print(f"Final video:            {video_path}")


def _course_data_ok(data: dict) -> bool:
    """Quick validity check of a structured course JSON (for --skip-existing)."""
    try:
        slides = data["slides"]
        return bool(slides) and all(
            len(s["bullets"]) == 3
            and len(s["narration_segments"]) == 4
            and len(s["highlight_plan"]) == 3
            for s in slides
        )
    except (KeyError, TypeError):
        return False


def _rendering_ok(course_data: dict, output_dir: Path) -> bool:
    """Quick validity check of rendered slides (for --skip-existing)."""
    layout_file = output_dir / "metadata" / "slide_layout.json"
    if not layout_file.exists():
        return False
    try:
        layout = read_json_file(layout_file)
        return len(layout) == len(course_data["slides"]) and all(
            len(entry["bullet_boxes"]) == 3 and Path(entry["image_path"]).exists()
            for entry in layout
        )
    except (KeyError, TypeError, ValueError):
        return False


def _translation_ok(en_data: dict, zh_data: dict) -> bool:
    """Quick validity check of a Chinese narration JSON (for --skip-existing)."""
    import re

    cjk = re.compile(r"[一-鿿]")
    try:
        if len(zh_data["slides"]) != len(en_data["slides"]):
            return False
        for en_slide, zh_slide in zip(en_data["slides"], zh_data["slides"]):
            if any(
                zh_slide[f] != en_slide[f]
                for f in ("slide_index", "title", "bullets", "highlight_plan")
            ):
                return False
            segments = zh_slide["narration_segments"]
            if len(segments) != 4 or not all(cjk.search(s) for s in segments):
                return False
        return True
    except (KeyError, TypeError):
        return False


def _tts_ok(course_data: dict, audio_metadata: list, output_dir: Path) -> bool:
    """Quick validity check of generated TTS audio (for --skip-existing)."""
    try:
        return len(audio_metadata) == len(course_data["slides"]) and all(
            entry["duration"] > 0
            and len(entry["segments"]) == 4
            and (output_dir / "audio" / f"slide_{entry['slide_index']:02d}.mp3").exists()
            for entry in audio_metadata
        )
    except (KeyError, TypeError):
        return False


def _validate_slide_translation(source: dict, visual: dict, visual_path: Path) -> None:
    """Validate the Chinese slide-text JSON: titles/bullets/highlight texts
    translated, everything else (incl. narration) unchanged. Exit on failure."""
    import re

    if not visual_path.exists():
        sys.exit(f"Validation FAILED: {visual_path} was not created.")

    if len(visual["slides"]) != len(source["slides"]):
        sys.exit(
            f"Validation FAILED: {len(visual['slides'])} slides, expected "
            f"{len(source['slides'])}."
        )

    cjk = re.compile(r"[一-鿿]")

    for src_slide, vis_slide in zip(source["slides"], visual["slides"]):
        index = src_slide["slide_index"]

        if vis_slide["slide_index"] != index:
            sys.exit(f"Validation FAILED: slide_index changed on slide {index}.")
        if vis_slide["narration_segments"] != src_slide["narration_segments"]:
            sys.exit(
                f"Validation FAILED: slide {index} narration_segments changed; "
                "they must stay identical (audio is reused)."
            )

        if not cjk.search(vis_slide["title"]):
            sys.exit(f"Validation FAILED: slide {index} title is not Chinese.")
        if len(vis_slide["bullets"]) != 3 or not all(
            cjk.search(b) for b in vis_slide["bullets"]
        ):
            sys.exit(
                f"Validation FAILED: slide {index} does not have 3 Chinese bullets."
            )

        if len(vis_slide["highlight_plan"]) != 3:
            sys.exit(f"Validation FAILED: slide {index} highlight_plan size changed.")
        for src_plan, vis_plan in zip(
            src_slide["highlight_plan"], vis_slide["highlight_plan"]
        ):
            if (
                vis_plan["bullet_index"] != src_plan["bullet_index"]
                or vis_plan["narration_segment_index"] != src_plan["narration_segment_index"]
            ):
                sys.exit(
                    f"Validation FAILED: slide {index} highlight_plan index "
                    "mapping changed."
                )
            if vis_plan["text"] != vis_slide["bullets"][vis_plan["bullet_index"]]:
                sys.exit(
                    f"Validation FAILED: slide {index} highlight_plan text does "
                    "not match the translated bullet."
                )

    print(
        f"      Validation OK: {len(visual['slides'])} slides, Chinese "
        "titles/bullets, highlight_plan remapped, narration unchanged."
    )


def _validate_translation(en_data: dict, zh_data: dict, zh_path: Path) -> None:
    """Validate the Chinese narration JSON against the frozen English one:
    identical structure, translated narration only. Exit on failure."""
    import re

    if not zh_path.exists():
        sys.exit(f"Validation FAILED: {zh_path} was not created.")

    if len(zh_data["slides"]) != len(en_data["slides"]):
        sys.exit(
            f"Validation FAILED: {len(zh_data['slides'])} slides in the "
            f"translation, expected {len(en_data['slides'])}."
        )

    cjk = re.compile(r"[一-鿿]")

    for en_slide, zh_slide in zip(en_data["slides"], zh_data["slides"]):
        index = en_slide["slide_index"]

        for field in ("slide_index", "title", "bullets", "highlight_plan"):
            if zh_slide[field] != en_slide[field]:
                sys.exit(
                    f"Validation FAILED: slide {index} field '{field}' was "
                    "modified by the translation; it must stay identical."
                )

        segments = zh_slide["narration_segments"]
        if len(segments) != 4:
            sys.exit(
                f"Validation FAILED: slide {index} has {len(segments)} "
                "narration segments, expected 4."
            )
        for i, segment in enumerate(segments):
            if not segment.strip() or not cjk.search(segment):
                sys.exit(
                    f"Validation FAILED: slide {index} segment {i} is empty "
                    "or contains no Chinese characters."
                )
        if not zh_slide["speaker_script"].strip():
            sys.exit(f"Validation FAILED: slide {index} speaker_script is empty.")

    print(
        f"      Validation OK: {len(zh_data['slides'])} slides, structure "
        "identical, 4 Chinese narration segments each."
    )


def _validate_subtitle_translation(
    source_content: str, translated_path: Path, language: str
) -> None:
    """Validate a translated SRT against its source: same entry count,
    byte-identical numbers and timestamps, non-empty text in the target
    language. Exit on failure."""
    import re

    from src.subtitle_translator import parse_srt

    if not translated_path.exists():
        sys.exit(f"Validation FAILED: {translated_path} was not created.")

    source = parse_srt(source_content)
    translated = parse_srt(translated_path.read_text(encoding="utf-8"))

    if len(translated) != len(source):
        sys.exit(
            f"Validation FAILED: {len(translated)} entries, expected "
            f"{len(source)}."
        )

    for src, out in zip(source, translated):
        if out["index"] != src["index"]:
            sys.exit(
                f"Validation FAILED: entry number changed "
                f"({src['index']} -> {out['index']})."
            )
        if out["timing"] != src["timing"]:
            sys.exit(
                f"Validation FAILED: timestamps changed on entry "
                f"{src['index']}: {src['timing']!r} -> {out['timing']!r}."
            )
        if not out["text"].strip():
            sys.exit(f"Validation FAILED: entry {src['index']} text is empty.")

    cjk = re.compile(r"[一-鿿]")
    n_cjk = sum(1 for e in translated if cjk.search(e["text"]))
    if language == "zh" and n_cjk < len(translated) * 0.5:
        sys.exit(
            f"Validation FAILED: only {n_cjk}/{len(translated)} entries "
            "contain Chinese text."
        )
    if language == "en" and n_cjk > len(translated) * 0.05:
        sys.exit(
            f"Validation FAILED: {n_cjk}/{len(translated)} entries still "
            "contain Chinese text."
        )

    print(
        f"      Validation OK: {len(translated)} entries, numbers and "
        f"timestamps unchanged, text in '{language}'."
    )


def _validate_subtitled_video(clean_path: Path, subtitled_path: Path) -> None:
    """Validate the subtitled MP4 against the clean one with ffprobe:
    same duration (within 0.5s), 1280x720, audio present. Exit on failure."""
    if not subtitled_path.exists():
        sys.exit(f"Validation FAILED: {subtitled_path} was not created.")

    clean = _probe_media(clean_path)
    subtitled = _probe_media(subtitled_path)

    clean_duration = float(clean["format"]["duration"])
    duration = float(subtitled["format"]["duration"])
    if abs(duration - clean_duration) > 0.5:
        sys.exit(
            f"Validation FAILED: subtitled duration {duration:.2f}s differs "
            f"from clean video {clean_duration:.2f}s by more than 0.5s."
        )

    streams = {s["codec_type"]: s for s in subtitled["streams"]}
    video_stream = streams.get("video")
    if video_stream is None:
        sys.exit("Validation FAILED: no video stream found.")
    if (video_stream["width"], video_stream["height"]) != (1280, 720):
        sys.exit(
            f"Validation FAILED: resolution is "
            f"{video_stream['width']}x{video_stream['height']}, expected 1280x720."
        )
    if "audio" not in streams:
        sys.exit("Validation FAILED: no audio stream found.")

    size_mb = subtitled_path.stat().st_size / (1024 * 1024)
    if size_mb < 1:
        sys.exit(f"Validation FAILED: file size {size_mb:.1f} MB is suspiciously small.")

    print(
        f"      Validation OK: duration {duration:.1f}s (clean video "
        f"{clean_duration:.1f}s), 1280x720, audio present, {size_mb:.1f} MB."
    )


def _probe_media(path: Path) -> dict:
    """Run ffprobe on a media file and return the parsed JSON; exit on error."""
    import json
    import subprocess

    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration:stream=codec_type,width,height",
            "-of", "json", str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.exit(f"Validation FAILED: ffprobe error:\n{result.stderr[-500:]}")
    return json.loads(result.stdout)


def _validate_video(highlight_timeline: list, video_path: Path) -> None:
    """Validate the exported MP4 with ffprobe; exit on failure."""
    import json
    import subprocess

    if not video_path.exists():
        sys.exit(f"Validation FAILED: {video_path} was not created.")

    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration:stream=codec_type,width,height",
            "-of", "json", str(video_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.exit(f"Validation FAILED: ffprobe error:\n{result.stderr[-500:]}")

    probe = json.loads(result.stdout)
    duration = float(probe["format"]["duration"])
    streams = {s["codec_type"]: s for s in probe["streams"]}

    expected = sum(entry["audio_duration"] for entry in highlight_timeline)
    if abs(duration - expected) > 2.0:
        sys.exit(
            f"Validation FAILED: video duration {duration:.1f}s, expected "
            f"about {expected:.1f}s."
        )

    video_stream = streams.get("video")
    if video_stream is None:
        sys.exit("Validation FAILED: no video stream found.")
    if (video_stream["width"], video_stream["height"]) != (1280, 720):
        sys.exit(
            f"Validation FAILED: resolution is "
            f"{video_stream['width']}x{video_stream['height']}, expected 1280x720."
        )

    if "audio" not in streams:
        sys.exit("Validation FAILED: no audio stream found.")

    size_mb = video_path.stat().st_size / (1024 * 1024)
    if size_mb < 1:
        sys.exit(f"Validation FAILED: file size {size_mb:.1f} MB is suspiciously small.")

    print(
        f"      Validation OK: duration {duration:.1f}s (expected ~{expected:.1f}s), "
        f"1280x720, audio present, {size_mb:.1f} MB."
    )


def _validate_highlights(course_data: dict, timeline: list, output_dir: Path) -> None:
    """Validate the highlight timeline against the frozen data; exit on failure."""
    timeline_path = output_dir / "metadata" / "highlight_timeline.json"
    if not timeline_path.exists():
        sys.exit(f"Validation FAILED: {timeline_path} was not created.")

    n_slides = len(course_data["slides"])
    if len(timeline) != n_slides:
        sys.exit(
            f"Validation FAILED: {len(timeline)} timeline entries, "
            f"expected {n_slides}."
        )

    bullets_by_slide = {
        slide["slide_index"]: slide["bullets"] for slide in course_data["slides"]
    }

    for entry in timeline:
        index = entry["slide_index"]
        highlights = entry["highlights"]

        if len(highlights) != 3:
            sys.exit(
                f"Validation FAILED: slide {index} has {len(highlights)} "
                "highlights, expected 3."
            )

        for h in highlights:
            box = h["box"]
            if box["w"] <= 0 or box["h"] <= 0:
                sys.exit(
                    f"Validation FAILED: slide {index} bullet "
                    f"{h['bullet_index']} has an invalid box: {box}."
                )
            if h["start"] >= h["end"]:
                sys.exit(
                    f"Validation FAILED: slide {index} bullet "
                    f"{h['bullet_index']} has start >= end "
                    f"({h['start']} -> {h['end']})."
                )
            if h["start"] < 0 or h["end"] > entry["audio_duration"] + 0.1:
                sys.exit(
                    f"Validation FAILED: slide {index} highlight times "
                    f"({h['start']} -> {h['end']}) exceed the slide audio "
                    f"duration ({entry['audio_duration']})."
                )
            if h["narration_segment_index"] not in (1, 2, 3):
                sys.exit(
                    f"Validation FAILED: slide {index} has "
                    f"narration_segment_index {h['narration_segment_index']}, "
                    "expected 1, 2 or 3."
                )
            if h["text"] != bullets_by_slide[index][h["bullet_index"]]:
                sys.exit(
                    f"Validation FAILED: slide {index} bullet "
                    f"{h['bullet_index']} highlight text does not match the "
                    "bullet text."
                )

    print(
        f"      Validation OK: {n_slides} slides, 3 highlights each, valid "
        "boxes, start < end, times within slide audio, texts match bullets."
    )


def _validate_subtitles(entries: list, audio_metadata: list, output_dir: Path) -> None:
    """Validate the generated SRT entries against audio timing; exit on failure."""
    srt_path = output_dir / "subtitles.srt"
    if not srt_path.exists():
        sys.exit(f"Validation FAILED: {srt_path} was not created.")

    if not entries:
        sys.exit("Validation FAILED: no subtitle entries were generated.")

    previous_start = -1.0
    for entry in entries:
        if not entry["text"].strip():
            sys.exit(
                f"Validation FAILED: subtitle {entry['index']} has empty text."
            )
        if entry["end"] <= entry["start"]:
            sys.exit(
                f"Validation FAILED: subtitle {entry['index']} ends at or "
                f"before its start ({entry['start']} -> {entry['end']})."
            )
        if entry["start"] < previous_start:
            sys.exit(
                f"Validation FAILED: subtitle {entry['index']} starts at "
                f"{entry['start']}, earlier than the previous subtitle."
            )
        previous_start = entry["start"]

    first_start = entries[0]["start"]
    if first_start > 1.0:
        sys.exit(
            f"Validation FAILED: first subtitle starts at {first_start}s, "
            "expected near 00:00:00,000."
        )

    total_duration = sum(s["duration"] for s in audio_metadata)
    last_end = entries[-1]["end"]
    if abs(last_end - total_duration) > 1.0:
        sys.exit(
            f"Validation FAILED: last subtitle ends at {last_end}s, but "
            f"total audio duration is {total_duration:.3f}s."
        )

    print(
        f"      Validation OK: {len(entries)} entries, timestamps increasing, "
        f"first starts at {first_start:.3f}s, last ends at {last_end:.3f}s "
        f"(audio total {total_duration:.3f}s)."
    )


def _validate_tts(course_data: dict, audio_metadata: list, output_dir: Path) -> None:
    """Validate TTS audio files and duration metadata; exit on failure."""
    n_slides = len(course_data["slides"])

    mp3_files = sorted((output_dir / "audio").glob("slide_*.mp3"))
    if len(mp3_files) != n_slides:
        sys.exit(
            f"Validation FAILED: {len(mp3_files)} MP3 files found, "
            f"expected {n_slides}."
        )

    if len(audio_metadata) != n_slides:
        sys.exit(
            f"Validation FAILED: {len(audio_metadata)} audio metadata entries, "
            f"expected {n_slides}."
        )

    for entry in audio_metadata:
        if entry["duration"] <= 0:
            sys.exit(
                f"Validation FAILED: slide {entry['slide_index']} audio has "
                f"duration {entry['duration']}, expected > 0."
            )

    total_duration = sum(entry["duration"] for entry in audio_metadata)
    print(
        f"      Validation OK: {n_slides} MP3s, {n_slides} metadata entries, "
        f"all durations > 0 (total {total_duration:.1f}s)."
    )


def _validate_rendering(course_data: dict, layout: list, output_dir: Path) -> None:
    """Validate slide images and layout metadata; exit on failure."""
    n_slides = len(course_data["slides"])

    png_files = sorted((output_dir / "slide_images").glob("slide_*.png"))
    if len(png_files) != n_slides:
        sys.exit(
            f"Validation FAILED: {len(png_files)} PNG files found, "
            f"expected {n_slides}."
        )

    if len(layout) != n_slides:
        sys.exit(
            f"Validation FAILED: {len(layout)} metadata entries, "
            f"expected {n_slides}."
        )

    for entry in layout:
        if len(entry["bullet_boxes"]) != 3:
            sys.exit(
                f"Validation FAILED: slide {entry['slide_index']} has "
                f"{len(entry['bullet_boxes'])} bullet boxes, expected 3."
            )

    print(
        f"      Validation OK: {n_slides} PNGs, {n_slides} metadata entries, "
        "3 bullet boxes each."
    )


if __name__ == "__main__":
    main()
