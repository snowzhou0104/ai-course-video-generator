# AI Course Video Generator

An AI-powered pipeline that turns a course script (PDF or TXT) into a complete,
narrated course video. From a single input file it produces:

- an AI-generated course structure (titles, bullet points, narration, highlight plan)
- a generated PowerPoint deck (PPTX)
- rendered 1280x720 slide images
- English or Chinese slide text
- English or Chinese AI narration (Edge TTS)
- selectable subtitle language (independent of slide/speaker language)
- synchronized, bullet-level highlight animations
- a clean MP4 and an optional MP4 with burned-in captions
- a Streamlit web frontend, in addition to a full CLI workflow

**Recommended (assignment) configuration:** Chinese slides + Chinese speaker +
Chinese subtitles + burned-in subtitles, using the `zh-CN-XiaoxiaoNeural` voice.

**Primary deliverable:**

```text
output_cn_slide_cn_speaker/final_video_cn_slides_cn_speaker_subtitled.mp4
```

---

## Table of contents

1. [Assignment requirement coverage](#1-assignment-requirement-coverage)
2. [Key features](#2-key-features)
3. [System architecture](#3-system-architecture)
4. [Canonical demo variants](#4-canonical-demo-variants)
5. [Technology stack](#5-technology-stack)
6. [Project structure](#6-project-structure)
7. [Windows installation](#7-windows-installation)
8. [Streamlit frontend usage](#8-streamlit-frontend-usage)
9. [CLI: full-pipeline usage](#9-cli-full-pipeline-usage)
10. [Fully Chinese slide workflow](#10-fully-chinese-slide-workflow)
11. [Phase-only CLI commands](#11-phase-only-cli-commands)
12. [Language combinations](#12-language-combinations)
13. [Output structure](#13-output-structure)
14. [Validation](#14-validation)
15. [Testing](#15-testing)
16. [AI and API usage](#16-ai-and-api-usage)
17. [TTS service selection](#17-tts-service-selection)
18. [Design decisions](#18-design-decisions)
19. [Known limitations](#19-known-limitations)
20. [Future improvements](#20-future-improvements)
21. [Submission contents](#21-submission-contents)
22. [Files not to submit](#22-files-not-to-submit)

---

## 1. Assignment requirement coverage

| Assignment Requirement | Implementation Status | Project Implementation |
| --- | --- | --- |
| Complete course script input | Completed | `src/script_loader.py` reads `.pdf` (via `pypdf`) and `.txt` input files. |
| Course structure extraction | Completed | `src/llm_parser.py` calls the OpenAI API and validates the result against a Pydantic `CourseStructure` schema: per slide, a title, exactly 3 bullets, exactly 4 narration segments, a speaker script and a 3-entry highlight plan. |
| PPT generation | Completed | `src/ppt_generator.py` builds `course_slides.pptx` (and `course_slides_zh.pptx` for Chinese slide text) with a title slide, numbered content slides and a consistent visual design. |
| Speaker script generation | Completed | The LLM produces a `speaker_script` plus 4 `narration_segments` per slide (1 intro segment + 1 explanation segment per bullet). |
| Natural Chinese AI TTS | Completed | `src/tts_generator.py` uses Microsoft Edge TTS; the recommended voice is `zh-CN-XiaoxiaoNeural`, with 3 additional Chinese voices available. |
| Slide-duration-driven video synthesis | Completed | Per-segment TTS durations (`audio_metadata.json`) drive the highlight timeline and the per-slide video duration in `src/video_generator.py`. |
| Complete MP4 output | Completed | `src/video_generator.py` exports 1280x720, H.264/AAC, 24 fps MP4s via MoviePy/FFmpeg. |
| Visual guidance / highlights | Completed | `src/highlight_generator.py` draws an orange rounded-rectangle highlight around the bullet being narrated, timed from the actual TTS segment durations. |
| Subtitles | Completed | `src/subtitle_generator.py` produces a global `subtitles.srt`; `src/subtitle_translator.py` can translate it to the other language while preserving entry numbers and timestamps exactly; `src/subtitle_burner.py` can burn the SRT into the MP4 with FFmpeg/libass. |
| Frontend | Completed | `app.py` is a Streamlit app that drives the same CLI pipeline as subprocesses. |
| Progress display | Completed | The CLI prints numbered stage markers (e.g. `[3/8] Generating PPT...`); the Streamlit UI streams the same output into a live status panel. |
| Error handling | Completed | `argparse` validates CLI flags; pipeline stages exit with a clear `Validation FAILED: ...` message on `sys.exit` rather than a raw traceback; FFmpeg/ffprobe errors are captured and surfaced. |
| Validation | Completed | Every stage has a dedicated `_validate_*` check in `main.py` (rendering, TTS, subtitles, highlights, video, translations, subtitle burning) - see [Validation](#14-validation). |
| AI coding assistance | Completed | Claude Code was used throughout development for implementation, debugging, test writing and Windows-compatibility fixes - see [AI and API usage](#16-ai-and-api-usage). |
| TTS selection rationale | Completed | Documented in [TTS service selection](#17-tts-service-selection). |

### Improvements beyond the core requirement

- Fully Chinese slide text (titles, bullets, highlights), not just Chinese narration.
- Independent slide language, speaker language and subtitle language controls.
- LLM-based subtitle translation that preserves SRT numbering and timestamps exactly.
- Optional burned-in subtitles (FFmpeg/libass), with the clean MP4 and SRT preserved.
- Three canonical, self-contained output variants generated from one shared base course structure.
- A full Streamlit frontend, including a native Windows folder picker for the output directory.
- `--skip-existing` resume support for the full pipeline.
- An automated validation suite built into the pipeline itself, plus a pytest/AppTest suite for the frontend.

---

## 2. Key features

### Input support

- **PDF** course scripts, extracted with `pypdf`.
- **TXT** course scripts, read directly.

### LLM course structuring (`src/llm_parser.py`)

For each slide, the LLM produces:

- a `title`
- exactly **3 bullets**
- exactly **4 narration segments**: 1 intro segment, then 1 explanation segment per bullet
- a `speaker_script` (the narration segments joined)
- a `highlight_plan` with 3 entries, each mapping `bullet_index` -> `narration_segment_index` (segments 1/2/3) -> the bullet text to highlight

The result is validated against a Pydantic schema (`CourseStructure`) before anything downstream runs.

### PPTX generation (`src/ppt_generator.py`)

- English PPTX (`course_slides.pptx`) and, for the Chinese-slide variant, a Chinese PPTX (`course_slides_zh.pptx`).
- A title slide followed by one content slide per course slide.
- Slide numbers and a consistent visual design across all slides.

### Slide rendering (`src/slide_renderer.py`)

- Renders each slide to a 1280x720 PNG with Pillow.
- Computes and saves the bounding box of each bullet to `metadata/slide_layout.json`, which the highlight generator uses for exact highlight placement.

### Narration translation (`src/narration_translator.py`)

- Translates the 4 narration segments (and `speaker_script`) per slide into natural, spoken Chinese via the LLM.
- Preserves the slide/segment structure exactly (same slide count, same segment-per-slide mapping) so audio and highlight timing stay aligned.

### Slide text translation (`src/slide_translator.py`)

- Translates slide `title`s and `bullets` into Chinese.
- Updates `highlight_plan[*].text` to match the new Chinese bullet text.
- Rendered with Microsoft YaHei so Chinese glyphs display correctly in both the PPTX and the PNG slides.

### TTS (`src/tts_generator.py`)

- Generates narration with **Edge TTS**, one MP3 per narration segment.
- Concatenates the per-segment MP3s into one `slide_NN.mp3` per slide (re-encoded with `ffmpeg`/`libmp3lame`).
- Records per-segment start/end offsets and durations in `metadata/audio_metadata.json`, which drives subtitle timing and highlight timing.
- Supports 4 English voices (default `en-US-JennyNeural`) and 4 Chinese voices (default `zh-CN-XiaoxiaoNeural`).

### Subtitle generation (`src/subtitle_generator.py`)

- Builds a single, global `subtitles.srt` from `audio_metadata.json` using cumulative offsets.
- Splits narration into subtitle-sized fragments with punctuation-aware logic, including Chinese punctuation.
- Accounts for CJK character width when balancing line length, and merges/splits fragments for readable on-screen durations.

### Subtitle translation (`src/subtitle_translator.py`)

- Translates an existing SRT to Chinese or English via the LLM, in batches.
- **Entry numbers and timestamps are preserved exactly** (byte-for-byte) - only the text is translated.
- Output is validated against the source SRT (`_validate_subtitle_translation`).

### Highlights (`src/highlight_generator.py`)

- No highlight is shown during the intro narration segment.
- Bullets 0/1/2 map to narration segments 1/2/3 respectively.
- Each highlight is an orange rounded rectangle drawn at the bullet's exact bounding box from `slide_layout.json`.
- Highlight start/end times come from the real TTS segment durations in `audio_metadata.json`.

### Video generation (`src/video_generator.py`)

- H.264 video, AAC audio, 24 fps, 1280x720.
- Produces the "clean" MP4 (no burned-in captions).

### Subtitle burning (`src/subtitle_burner.py`)

- Burns an SRT into an existing MP4 using FFmpeg's `subtitles` filter (libass), with a style tuned for readability on top of the slide content and Chinese font support (Microsoft YaHei).
- The clean MP4 and the SRT file are **never modified**; burning writes a new `*_subtitled.mp4`.

### Streamlit frontend (`app.py`)

- File upload (PDF/TXT).
- Independent **slide language**, **speaker language** and **subtitle language** selectors.
- Voice selector (depends on speaker language).
- "Burn subtitles into final video" checkbox.
- Output folder text entry **plus** a native Windows folder picker ("Browse...") and an "Open output folder" button.
- Live progress logs streamed from each pipeline stage.
- Video preview and downloads for the MP4(s), SRT(s), PPTX(s) and JSON artifacts.
- A warning when the chosen output folder is one of the three protected canonical demo folders.

---

## 3. System architecture

```text
PDF/TXT Input
    |
    v
Script Loader               (src/script_loader.py)
    |
    v
LLM Course Parser            (src/llm_parser.py)
    |
    v
structured_course.json
    |
    v
PPT Generator                (src/ppt_generator.py)
    |
    v
Slide Renderer                (src/slide_renderer.py)
    |
    v
Optional Narration Translator (src/narration_translator.py)
    |
    v
Optional Slide Translator     (src/slide_translator.py)
    |
    v
TTS Generator                 (src/tts_generator.py)
    |
    v
Subtitle Generator             (src/subtitle_generator.py)
    |
    v
Optional Subtitle Translator   (src/subtitle_translator.py)
    |
    v
Highlight Timeline Generator   (src/highlight_generator.py)
    |
    v
Video Generator                 (src/video_generator.py)
    |
    v
Optional Subtitle Burner        (src/subtitle_burner.py)
    |
    v
Final MP4
```

### The highlight timeline join

The highlight timeline is a deterministic join of three sources - no extra LLM
call is needed to produce it:

```text
highlight_plan (from structured_course.json)
    + audio_metadata.json (per-segment timing from TTS)
    + slide_layout.json (per-bullet bounding boxes from rendering)
    = highlight_timeline.json
```

### Role of each metadata/JSON file

| File | Produced by | Role |
| --- | --- | --- |
| `structured_course.json` | LLM course parser | The canonical course structure: titles, bullets, narration segments, speaker script, highlight plan (English). |
| `structured_course_zh.json` | Narration translator | Same structure, with narration segments and `speaker_script` translated to Chinese. Titles, bullets and `highlight_plan` are unchanged from `structured_course.json`. |
| `structured_course_zh_visual.json` | Slide translator | Same structure again, but with `title`, `bullets` and `highlight_plan[*].text` translated to Chinese, for rendering Chinese slides. |
| `metadata/slide_layout.json` | Slide renderer | Per-slide bullet bounding boxes used to place highlights precisely. |
| `metadata/audio_metadata.json` | TTS generator | Per-slide and per-segment audio durations/offsets, used for subtitle and highlight timing. |
| `metadata/highlight_timeline.json` | Highlight generator | The final per-slide highlight schedule (box, start/end time, narration segment index, bullet text) used by the video generator. |

---

## 4. Canonical demo variants

Three self-contained output folders were generated from the **same 13-slide
base course structure** (one LLM structuring call), so slide count, slide
order, bullet/segment counts and highlight counts are identical across all
three:

| Folder | Slide Language | Speaker Language | Subtitle Language | Main Subtitled Video |
| --- | --- | --- | --- | --- |
| `output_en_slide_en_speaker` | English | English | English | `final_video_en_slides_en_speaker_subtitled.mp4` |
| `output_en_slide_cn_speaker` | English | Chinese | Chinese | `final_video_en_slides_cn_speaker_subtitled.mp4` |
| `output_cn_slide_cn_speaker` | Chinese | Chinese | Chinese | `final_video_cn_slides_cn_speaker_subtitled.mp4` |

All three variants have:

- 13 slides, with sequential `slide_index` 1-13
- exactly 3 bullets per slide
- exactly 4 narration segments per slide
- exactly 3 highlights per slide

Approximate durations (current build):

- `output_en_slide_en_speaker`: ~400.6 seconds
- `output_en_slide_cn_speaker`: ~411.2 seconds
- `output_cn_slide_cn_speaker`: ~411.2 seconds

Future runs may produce slightly different slide counts and durations,
because both the LLM course-structuring step and the TTS engine can produce
different (but still schema-valid) output between runs.

---

## 5. Technology stack

### Language and configuration

- **Python** 3.10+ (developed and tested with Python 3.14.5)
- **python-dotenv** - loads `OPENAI_API_KEY` / `OPENAI_MODEL` from `.env`
- **Pydantic** - validates the LLM course-structure response

### AI

- **OpenAI API** - course structuring, narration translation, slide-text translation, subtitle translation

### Document processing

- **pypdf** - PDF text extraction
- **python-pptx** - PPTX generation

### Image rendering

- **Pillow (PIL)** - slide PNG rendering, highlight overlays

### Audio

- **edge-tts** - narration synthesis (Microsoft Edge neural voices)
- **mutagen** - reading MP3 duration metadata

### Video

- **MoviePy** - composing per-slide video clips into the final MP4
- **FFmpeg / ffprobe** - audio re-encoding, media probing/validation, subtitle burning
- **libass** (via FFmpeg's `subtitles` filter) - burned-in caption rendering

### Frontend

- **Streamlit** - web UI
- **tkinter** (Python standard library) - native folder picker for the local Streamlit app

### Testing

- **pytest**
- **Streamlit AppTest** (`streamlit.testing.v1`) - frontend tests without a running server

---

## 6. Project structure

```text
ai-course-video-generator/
├── app.py                  # Streamlit frontend
├── main.py                  # CLI: full pipeline + phase-only modes
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
├── input/
│   └── Core Departments in Tech Companies.pdf   # sample course script
├── src/
│   ├── config.py               # loads OPENAI_API_KEY / OPENAI_MODEL from .env
│   ├── script_loader.py         # reads .pdf / .txt input
│   ├── llm_parser.py             # LLM course structuring + Pydantic validation
│   ├── ppt_generator.py           # PPTX generation (English/Chinese)
│   ├── slide_renderer.py           # PIL slide PNG rendering + layout metadata
│   ├── narration_translator.py      # narration -> Chinese (structured_course_zh.json)
│   ├── slide_translator.py           # slide text -> Chinese (structured_course_zh_visual.json)
│   ├── tts_generator.py               # Edge TTS narration + audio_metadata.json
│   ├── subtitle_generator.py           # subtitles.srt
│   ├── subtitle_translator.py           # SRT translation, preserving timing/numbers
│   ├── highlight_generator.py            # highlight_timeline.json
│   ├── video_generator.py                 # final MP4 assembly (MoviePy)
│   ├── subtitle_burner.py                  # burn SRT into MP4 (FFmpeg/libass)
│   └── utils.py                             # ensure_dir / read_json_file / write_json_file
├── tests/
│   └── test_app.py            # Streamlit AppTest suite for app.py
├── output_en_slide_en_speaker/    # canonical demo variant 1
├── output_en_slide_cn_speaker/     # canonical demo variant 2
└── output_cn_slide_cn_speaker/      # canonical demo variant 3 (primary submission)
```

---

## 7. Windows installation

All commands below are PowerShell, run from the project root
(`D:\ai-course-video-generator` in this environment).

### Create the virtual environment

```powershell
python -m venv venv
```

### Activate it

```powershell
.\venv\Scripts\Activate.ps1
```

If PowerShell blocks the activation script:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Install dependencies

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Verify FFmpeg / ffprobe

FFmpeg must be on `PATH` - the pipeline uses it for audio re-encoding, video
export, media validation and subtitle burning.

```powershell
ffmpeg -version
ffprobe -version
```

If these are not found, install FFmpeg (e.g. `winget install ffmpeg` or
`choco install ffmpeg`) and restart the terminal.

### Create your `.env`

```powershell
Copy-Item .env.example .env
```

Then edit `.env` and set:

```dotenv
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o-mini
```

`.env` is listed in `.gitignore` and must **never** be committed.

### Recommended Python version

This project was developed and tested with **Python 3.14.5** inside `venv`.
Any Python 3.10+ should work; `tkinter` (used for the Streamlit folder
picker) ships with the standard python.org Windows installer.

---

## 8. Streamlit frontend usage

### Start the app

```powershell
.\venv\Scripts\python.exe -m streamlit run app.py
```

Then open:

```text
http://127.0.0.1:8501
```

### Controls

| Control | Purpose |
| --- | --- |
| Course script uploader | Upload a `.pdf` or `.txt` course script. |
| Slide language | Controls the visible PPT/slide text (English or Chinese). |
| Speaker language | Controls narration, TTS voice and (by default) subtitles. |
| Subtitle language | "Same as speaker", Chinese, or English - controls the SRT and burned-in captions independently. |
| Voice | TTS voice; options depend on the selected speaker language. |
| Burn subtitles into final video | When checked, also produces a `*_subtitled.mp4` with captions rendered into the picture. |
| Output folder (text input) | Manual path entry - relative paths are created inside the project directory, absolute paths are used as-is. |
| Browse... | Opens a native Windows folder picker on the machine running Streamlit and fills in the output folder. |
| Open output folder | Opens the resolved output folder in File Explorer (shown only if it already exists). |
| Skip existing files | Resumes an interrupted run by skipping stages whose outputs already exist and look valid (full pipeline only). |
| Video filename | Name of the exported MP4; defaults follow the slide/speaker language combination. |

### Recommended defaults (assignment configuration)

- Slide language: **Chinese**
- Speaker language: **Chinese**
- Subtitle language: **Same as speaker**
- Voice: **`zh-CN-XiaoxiaoNeural`**
- Burn subtitles into final video: **checked**
- Output folder: **`output_streamlit`**

These are the app's defaults, so simply uploading a script and clicking
**Generate Course Video** reproduces the assignment configuration.

### How the three language controls interact

- **Slide language** controls only the visible text on the PPTX/PNG slides.
- **Speaker language** controls the narration audio (TTS voice) and, unless
  overridden, the subtitle language.
- **Subtitle language** controls the SRT file and burned-in captions
  independently. If it differs from the speaker language, only the subtitle
  **text** is translated via the LLM - the narration audio and all
  timestamps remain unchanged (the translated SRT is validated to have the
  same entry count and byte-identical timing lines as the original).

### Native folder picker - local vs. remote use

"Browse..." opens a native Tkinter directory dialog **on the machine running
the Streamlit server**. For this local Windows demo, that machine is your own
PC, so it behaves like a normal "choose folder" dialog. If this app were
deployed to a remote server, the dialog would open on the *server's* desktop,
not the browser visitor's computer - so it would not let a remote user pick a
folder on their own PC. Manual path entry always remains available and works
in every environment.

### Protected canonical output folders

The following folder names are treated as protected - if the output folder
resolves to one of these (as a relative name, or as the last path component
of an absolute path), the UI shows a warning that the folder contains
canonical demo deliverables and may be overwritten. This is a warning only;
it does not block generation.

```text
output_en_slide_en_speaker
output_en_slide_cn_speaker
output_cn_slide_cn_speaker
```

---

## 9. CLI: full-pipeline usage

When none of the `--*-only` / `--translate-*` / `--burn-subtitles` flags are
given, `main.py` runs the full 8-stage pipeline (course structuring -> PPTX
-> slide rendering -> optional narration translation -> TTS -> subtitles +
highlights -> video export).

### English slides + Chinese speaker

```powershell
.\venv\Scripts\python.exe main.py `
  --input "input/Core Departments in Tech Companies.pdf" `
  --output output_new `
  --language zh `
  --voice zh-CN-XiaoxiaoNeural `
  --video-name final_video.mp4
```

### English slides + English speaker

```powershell
.\venv\Scripts\python.exe main.py `
  --input "input/Core Departments in Tech Companies.pdf" `
  --output output_new_en `
  --language en `
  --voice en-US-JennyNeural `
  --video-name final_video_en.mp4
```

### Resuming an interrupted run

```powershell
.\venv\Scripts\python.exe main.py `
  --input "input/Core Departments in Tech Companies.pdf" `
  --output output_new `
  --language zh `
  --voice zh-CN-XiaoxiaoNeural `
  --video-name final_video.mp4 `
  --skip-existing
```

Notes:

- No `--*-only` flag means **full pipeline mode**.
- `--language en` keeps the LLM's English narration; `--language zh` adds a
  narration-translation step before TTS (writing `structured_course_zh.json`).
- `--skip-existing` skips a stage only if its expected output files already
  exist **and** pass a quick validity check.
- Defaults if omitted: `--input "input/Core Departments in Tech Companies.pdf"`,
  `--output output`, `--voice en-US-JennyNeural`, `--video-name
  final_course_video.mp4`, `--language en`.
- A fresh run calls the LLM again for course structuring, so the resulting
  slide count may differ slightly from a previous run (both are valid against
  the schema).

---

## 10. Fully Chinese slide workflow

Chinese **slide text** (titles, bullets, highlights) is produced in a
separate stage from Chinese **narration**, because the slide images,
highlight timeline and video must all be regenerated against the translated
text. This example uses a non-canonical folder, `output_demo_cn`, to avoid
touching the canonical demo folders.

### Step 1 - base Chinese narration pipeline

```powershell
.\venv\Scripts\python.exe main.py `
  --input "input/Core Departments in Tech Companies.pdf" `
  --output output_demo_cn `
  --language zh `
  --voice zh-CN-XiaoxiaoNeural `
  --video-name final_video_cn.mp4
```

This produces `structured_course.json` (English), `structured_course_zh.json`
(Chinese narration) and a complete English-slide video.

### Step 2 - translate the visible slide text

```powershell
.\venv\Scripts\python.exe main.py `
  --translate-slides-only `
  --output output_demo_cn `
  --course-json output_demo_cn\structured_course_zh.json
```

Writes `structured_course_zh_visual.json`, `course_slides_zh.pptx`, and
re-renders the slide PNGs (and `slide_layout.json`) with Chinese text.

### Step 3 - regenerate the highlight timeline

```powershell
.\venv\Scripts\python.exe main.py `
  --highlights-only `
  --output output_demo_cn `
  --course-json output_demo_cn\structured_course_zh_visual.json
```

The highlight boxes must be recomputed against the **new** Chinese
`slide_layout.json`, since translated bullet text changes line wrapping and
box positions.

### Step 4 - regenerate the video

```powershell
.\venv\Scripts\python.exe main.py `
  --video-only `
  --output output_demo_cn `
  --video-name final_video_cn.mp4
```

### Step 5 - burn subtitles

```powershell
.\venv\Scripts\python.exe main.py `
  --burn-subtitles `
  --output output_demo_cn `
  --video-name final_video_cn.mp4
```

### Why each step is needed

Translating the slide text changes the bullet strings, which changes:

1. **New slide images** - the rendered PNGs must show the Chinese text (`--translate-slides-only`).
2. **New layout metadata** - Chinese text wraps differently, so bullet bounding boxes move (`slide_layout.json`, produced as part of step 2).
3. **New highlight timeline** - highlight boxes must follow the new layout (`--highlights-only`).
4. **New video assembly** - the final MP4 must be re-composed from the new slide images and highlight timeline (`--video-only`).

---

## 11. Phase-only CLI commands

All flag names below come from `main.py --help`. Run that command yourself
to confirm against the current code:

```powershell
.\venv\Scripts\python.exe main.py --help
```

| Flag | Purpose | Main Inputs | Main Outputs |
| --- | --- | --- | --- |
| `--render-only` | Re-render slide images without re-running the LLM/PPTX steps. | `<output>/structured_course.json` | `<output>/slide_images/*.png`, `<output>/metadata/slide_layout.json` |
| `--tts-only` | Generate TTS audio without re-running the LLM/PPTX/rendering steps. | `structured_course.json` (or `--course-json`) | `<output>/audio/slide_NN.mp3`, `<output>/audio/segments/`, `<output>/metadata/audio_metadata.json` |
| `--subtitles-only` | Generate `subtitles.srt` from existing audio metadata. | `<output>/metadata/audio_metadata.json` | `<output>/subtitles.srt` |
| `--highlights-only` | Generate the highlight timeline from existing course data, audio metadata and slide layout. | `structured_course.json` (or `--course-json`), `audio_metadata.json`, `slide_layout.json` (or `--layout-json`) | `<output>/metadata/highlight_timeline.json`, `<output>/debug_highlights/` |
| `--video-only` | Assemble the final MP4 from existing slide images, audio and highlight timeline. | `<output>/slide_images/`, `<output>/audio/`, `<output>/metadata/highlight_timeline.json` | `<output>/<video-name>` |
| `--translate-only` | Translate narration (segments + speaker script) to Chinese. Titles/bullets/highlight_plan unchanged. | `<output>/structured_course.json` | `<output>/structured_course_zh.json` |
| `--translate-slides-only` | Translate slide titles/bullets to Chinese, then regenerate the Chinese PPTX and slide images. | `--course-json` (e.g. `structured_course_zh.json`) | `<output>/structured_course_zh_visual.json`, `<output>/course_slides_zh.pptx`, `<output>/slide_images/*.png`, `<output>/metadata/slide_layout.json` |
| `--translate-subtitles` | Translate an existing SRT to `--subtitle-language`, preserving entry numbers and timestamps. | `<output>/subtitles.srt` (or `--subtitle-input`) | `<output>/subtitles_<lang>.srt` (or `--subtitle-output`) |
| `--burn-subtitles` | Burn an SRT into an existing MP4 with FFmpeg. Clean MP4 and SRT are kept unchanged. | `<output>/<video-name>` (or `--input-video`), `<output>/subtitles.srt` (or `--subtitle-file`) | `<output>/<video-name stem>_subtitled.mp4` (or `--subtitle-video-name`) |

### Examples

```powershell
# Re-render slide images only
.\venv\Scripts\python.exe main.py --render-only --output output_demo_cn

# Generate TTS audio only
.\venv\Scripts\python.exe main.py --tts-only --output output_demo_cn --voice zh-CN-XiaoxiaoNeural

# Generate subtitles only
.\venv\Scripts\python.exe main.py --subtitles-only --output output_demo_cn

# Recompute the highlight timeline only
.\venv\Scripts\python.exe main.py --highlights-only --output output_demo_cn

# Re-export the video only
.\venv\Scripts\python.exe main.py --video-only --output output_demo_cn --video-name final_video_cn.mp4

# Translate narration to Chinese only
.\venv\Scripts\python.exe main.py --translate-only --output output_demo_cn

# Translate slide visuals to Chinese only
.\venv\Scripts\python.exe main.py --translate-slides-only --output output_demo_cn --course-json output_demo_cn\structured_course_zh.json

# Translate subtitles to English only
.\venv\Scripts\python.exe main.py --translate-subtitles --output output_demo_cn --subtitle-language en

# Burn subtitles into the existing video only
.\venv\Scripts\python.exe main.py --burn-subtitles --output output_demo_cn --video-name final_video_cn.mp4
```

---

## 12. Language combinations

| Slide | Speaker | Subtitle | Status |
| --- | --- | --- | --- |
| Chinese | Chinese | Chinese | Recommended |
| English | Chinese | Chinese | Supported |
| English | English | English | Supported |
| Chinese | English | English | Supported but experimental |
| Chinese | English | Chinese | Supported but experimental |
| English | Chinese | English | Supported |

Notes:

- Subtitles can match the speaker language or differ from it; a translated
  SRT preserves the original entry numbers and timestamps exactly - only the
  text changes.
- Chinese slides + English narration is functionally supported by the
  pipeline but has had less end-to-end testing than the other combinations.

---

## 13. Output structure

Not every mode generates every file - this tree shows the full set of
artifacts a complete run (full pipeline + Chinese slide workflow + subtitle
translation + subtitle burning) can produce:

```text
output_folder/
├── structured_course.json
├── structured_course_zh.json
├── structured_course_zh_visual.json
├── course_slides.pptx
├── course_slides_zh.pptx
├── subtitles.srt
├── subtitles_en.srt
├── subtitles_zh.srt
├── final_video.mp4
├── final_video_subtitled.mp4
├── slide_images/
│   └── slide_01.png ...
├── audio/
│   ├── slide_01.mp3 ...
│   └── segments/
├── metadata/
│   ├── slide_layout.json
│   ├── audio_metadata.json
│   └── highlight_timeline.json
└── debug_highlights/
```

---

## 14. Validation

Every pipeline stage is validated automatically; on failure, `main.py` exits
with a `Validation FAILED: ...` message instead of continuing with bad data.

### Course data (`llm_parser.py` / Pydantic schema)

- Valid slide count, sequential `slide_index`.
- Exactly 3 bullets and 4 narration segments per slide.
- Exactly 3 highlight-plan entries per slide.

### Slide rendering

- One PNG per slide.
- 1280x720 resolution.
- Exactly 3 bullet bounding boxes per slide, each within the slide bounds.

### TTS

- One MP3 per slide (and per segment).
- Every audio duration > 0.
- `audio_metadata.json` entry count matches the slide count.

### Subtitles

- Timestamps strictly non-decreasing.
- First subtitle starts near `00:00:00,000`.
- Last subtitle ends near the total narration duration.
- Every entry has non-empty text.
- Translated subtitles: entry numbers and timing lines are byte-identical to
  the source; text is non-empty and in the target language (checked via a
  CJK-character ratio).

### Highlights

- Exactly 3 highlights per slide.
- Valid boxes (`w > 0`, `h > 0`).
- `start < end`, and both within the slide's audio duration.
- `narration_segment_index` is 1, 2 or 3.
- Highlight text matches the corresponding bullet text.

### Video

- MP4 file exists.
- 1280x720 video stream, H.264.
- Audio stream present.
- Duration matches the sum of per-slide narration durations (within 2.0s).
- File size sanity check (>= 1 MB).
- Subtitled video: duration matches the clean video within 0.5s, plus the
  same resolution/audio/size checks.

---

## 15. Testing

```powershell
.\venv\Scripts\python.exe -m pytest tests\ -v
```

All tests currently pass. The suite (`tests/test_app.py`, using
`streamlit.testing.v1.AppTest`) covers:

- The app renders without exceptions.
- Default slide/speaker/subtitle language and voice selections.
- Voice list switching when the speaker language changes.
- Video filename selection for every slide/speaker language combination.
- The "Selected mode: ..." summary line, including subtitle language.
- The experimental-combination warning (Chinese slides + English speaker).
- Pipeline stage construction for English-slide and Chinese-slide runs.
- Burn-subtitles checkbox default, stage insertion, and output filename
  suffixes.
- Subtitle-language selection, the cross-language warning, and the resulting
  `--translate-subtitles` / `--burn-subtitles` stages and filenames.
- Output-folder picker behavior: default value, "Browse..." button, applying
  a (mocked) picker selection on rerun via session state, preserving the
  current value when a selection is cancelled, and the native picker's
  fallback behavior when unavailable - all without invoking a real Tkinter
  dialog.
- Protected-folder warnings for both relative and absolute paths, and that
  ordinary folders show no warning.
- Output-folder validation errors for empty paths, invalid Windows path
  characters, and a path that already exists as a file.

---

## 16. AI and API usage

### OpenAI API

Used for every step that requires language understanding or generation:

- **Course structuring** (`src/llm_parser.py`) - turns raw script text into
  the structured course JSON (titles, bullets, narration segments, highlight
  plan), validated by Pydantic.
- **Narration translation** (`src/narration_translator.py`) - translates
  narration segments and the speaker script to natural spoken Chinese.
- **Slide text translation** (`src/slide_translator.py`) - translates titles
  and bullets, and updates highlight text accordingly.
- **Subtitle translation** (`src/subtitle_translator.py`) - translates SRT
  text in batches while preserving numbering and timestamps exactly.

### Edge TTS

`src/tts_generator.py` uses Microsoft Edge's neural text-to-speech voices
(via the `edge-tts` package) to synthesize narration audio per segment, which
is then concatenated per slide and re-encoded with FFmpeg.

### AI coding assistants

This project was implemented with the help of **Claude Code** (Anthropic's
CLI coding agent) for implementation, debugging, writing the pytest/AppTest
suite, and resolving Windows-specific issues (path handling, console
encoding for Chinese text, PowerShell quirks). Prompts were iterated
interactively with human review of every change.

### Deterministic vs. non-deterministic stages

- **Deterministic**: slide rendering, PPTX generation, the highlight-timeline
  join, video assembly, subtitle burning - given the same JSON/audio/layout
  inputs, these always produce the same structure.
- **Non-deterministic (LLM/TTS-backed)**: course structuring, narration
  translation, slide-text translation, and subtitle translation (LLM calls);
  TTS audio (Edge TTS voice synthesis). These can vary slightly between runs
  (e.g. slide count, exact wording, exact audio duration) while still
  satisfying the schema/validation checks.

---

## 17. TTS service selection

**Edge TTS was selected** for this project because it best matched the needs
of an MVP course-narration pipeline:

- **Natural Mandarin** - the `zh-CN-XiaoxiaoNeural` voice produces clear,
  natural-sounding Mandarin narration suitable for course content.
- **Easy Python integration** - the `edge-tts` package is a thin async
  wrapper with no API key or account required.
- **MP3 output** - works directly with the existing
  `ffmpeg`/`mutagen`/MoviePy audio pipeline.
- **Multiple voices** - 4 English and 4 Chinese voices are available out of
  the box, enough to give the frontend a meaningful voice picker.
- **Low MVP complexity, stable local workflow** - no extra billing account,
  rate limits, or cloud setup beyond the OpenAI key already needed for the
  LLM steps.

### Alternatives considered

| Service | Notes |
| --- | --- |
| OpenAI TTS | Good quality and same API key as the LLM steps, but adds per-character cost on top of the LLM usage and was not necessary for an MVP. |
| MiniMax Speech | Strong Mandarin voice quality and emotion control, but requires a separate account/API key and was unnecessary for the MVP scope. |
| Azure Speech | Production-grade SSML, emotion and voice-cloning support, but requires an Azure subscription and more setup/SLA management. |
| Google/Gemini speech services | Competitive quality, but again a separate cloud account and billing setup. |
| ElevenLabs | Best-in-class voice cloning and expressive styles, but a paid commercial service with its own API and pricing model. |

### Trade-offs

Edge TTS does not offer fine-grained emotion/style controls, voice cloning,
or a commercial SLA. For a production deployment with paid users, a service
like Azure Speech, OpenAI TTS or ElevenLabs would be worth the extra API
complexity and cost in exchange for those controls and support guarantees.
For this assignment's scope - a free, natural-sounding, easily-integrated
voice for course narration - Edge TTS was the most pragmatic choice.

---

## 18. Design decisions

- **Pillow instead of PowerPoint export-to-image**: rendering slides directly
  with Pillow gives pixel-exact control over layout, fonts and bullet
  bounding boxes (needed for highlight placement), without depending on a
  PowerPoint/LibreOffice install to rasterize PPTX files.
- **Fixed 3-bullet / 4-segment schema**: a fixed shape (3 bullets, 1 intro +
  3 explanation segments, 3 highlight entries) keeps the highlight-timeline
  join, subtitle generation and video assembly simple and fully validateable,
  at the cost of flexibility in slide content density.
- **Segment-level TTS timing**: synthesizing and timing narration per
  segment (rather than per slide as one blob) is what makes bullet-level
  highlight synchronization possible.
- **Rendered bullet boxes from the actual slide image**: highlight boxes come
  from `slide_layout.json`, computed from the same rendering pass that
  produces the slide PNG - so highlights always line up with what's on
  screen, even after text changes (e.g. translation).
- **Separate language folders**: slide language, speaker language and
  subtitle language each have their own JSON/PPTX/SRT artifacts
  (`structured_course.json` / `_zh.json` / `_zh_visual.json`,
  `subtitles.srt` / `_en.srt` / `_zh.srt`), so any combination can be
  regenerated independently without recomputing the others.
- **Separate clean video, SRT, and subtitled video**: burning captions never
  overwrites the clean MP4 or the SRT - both remain available as independent
  deliverables alongside the subtitled MP4.
- **FFmpeg/libass instead of MoviePy `TextClip`/ImageMagick**: avoids an
  ImageMagick dependency and its Windows policy-file issues, and produces
  crisper, GPU-accelerated-friendly subtitle rendering via `libass`.
- **Streamlit-over-subprocess architecture**: the frontend calls `main.py` as
  a subprocess for each stage, so the CLI and the web UI share exactly the
  same code path and validation - there is no separate "frontend pipeline" to
  maintain.
- **Local Tkinter folder picker**: for a local Windows demo, a native folder
  dialog is the simplest way to let a user pick an output directory; it is
  explicitly documented as a local-only convenience (see
  [Streamlit frontend usage](#8-streamlit-frontend-usage)).
- **Canonical output folder protection**: the three canonical demo folders
  are checked by name (not blocked) so the same UI can be used to regenerate
  them deliberately, while warning against accidental overwrites during
  normal use.

---

## 19. Known limitations

- LLM course-structuring output can vary between runs (wording, sometimes
  slide count), even though it always satisfies the schema.
- One main visual template is used for all slides; there is no
  template-selection UI yet.
- The Chinese-slide workflow requires additional sequential stages (slide
  translation -> highlights -> video) beyond the base pipeline.
- The Chinese-slide Streamlit flow runs several subprocess stages in
  sequence, which adds wall-clock time compared to the single-stage
  English-slide flow.
- Translated subtitles may wrap or break differently on screen than the
  original-language subtitles, since translated text has different length.
- Subtitle-to-narration phrase alignment may be imperfect after translation,
  since only the subtitle text (not the audio) is translated.
- Chinese slides + English narration has had less end-to-end testing than
  the other combinations.
- The Streamlit app runs pipeline stages synchronously (one subprocess at a
  time); there is no background job queue.
- Full-pipeline generation takes several minutes; this is expected given the
  LLM, TTS and video-encoding steps involved.
- An internet connection is required (OpenAI API, Edge TTS).
- OpenAI API usage incurs cost per run.
- The native folder picker only browses the filesystem of the machine
  running the Streamlit server - not a remote browser client's filesystem.
- Streamlit Community Cloud (or similar shared hosting) is not the primary
  deployment target, given the folder-picker and local-filesystem-output
  design.
- Output quality (transcription accuracy, slide content) depends on the
  quality and clarity of the input course script.

---

## 20. Future improvements

- Deterministic/configurable slide count instead of leaving it to the LLM.
- Multiple visual slide templates, selectable from the frontend.
- A single "slide language" full-pipeline CLI argument that runs the Chinese
  slide-translation stages automatically.
- Skip-video-re-encode optimization when only metadata changes.
- Subtitle re-segmentation tuned specifically for translated text length.
- Subtitle font/style controls exposed in the frontend.
- TTS rate, pitch and emotion controls.
- Pronunciation dictionaries for technical terms/acronyms.
- Better automatic scoring of generated content quality.
- Support for more input formats (DOCX, Markdown, etc.).
- OCR support for scanned/image-based PDFs.
- Caching of LLM/TTS results to avoid redundant API calls on reruns.
- Background job processing for long-running generations.
- Cloud deployment with per-user storage and a browser-side folder/file
  picker.
- A progress-callback API for finer-grained UI progress reporting.
- Multi-user isolation (separate sessions/output namespaces).
- Persistent generation history.
- Cloud storage integration for outputs.
- Hardware-accelerated video encoding.
- Visual regression tests for slide rendering and highlight placement.

---

## 21. Submission contents

Recommended contents for submission:

```text
README.md
requirements.txt
.env.example
.gitignore
main.py
app.py
src/
tests/
input/Core Departments in Tech Companies.pdf
output_en_slide_en_speaker/
output_en_slide_cn_speaker/
output_cn_slide_cn_speaker/
```

**Primary deliverable:**

```text
output_cn_slide_cn_speaker/final_video_cn_slides_cn_speaker_subtitled.mp4
```

**Supporting deliverables:**

```text
output_en_slide_cn_speaker/final_video_en_slides_cn_speaker_subtitled.mp4
output_en_slide_en_speaker/final_video_en_slides_en_speaker_subtitled.mp4
```

---

## 22. Files not to submit

```text
.env
venv/
__pycache__/
*.pyc
.pytest_cache/
.DS_Store

input/streamlit_uploads/
output_streamlit/
output_streamlit*/
output_backup_*/
output_subtest/

temp_subtitles.srt
check.png
```

Also exclude any local scratch folders or extracted-frame directories created
during ad-hoc debugging.
