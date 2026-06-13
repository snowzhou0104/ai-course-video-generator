"""Streamlit frontend for the AI Course Video Generator.

Runs the existing CLI pipeline (main.py) as subprocesses so the web UI
and the command line share exactly the same code path. Slide language
and speaker (narration) language are chosen independently; Chinese
slides add extra pipeline stages on top of the base run.

Start with:  streamlit run app.py
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent
UPLOAD_DIR = PROJECT_ROOT / "input" / "streamlit_uploads"

# The canonical demo deliverables; warn before letting a run overwrite them.
PROTECTED_DIRS = {
    "output_en_slide_en_speaker",
    "output_en_slide_cn_speaker",
    "output_cn_slide_cn_speaker",
}

VOICES = {
    "Chinese": [
        "zh-CN-XiaoxiaoNeural",
        "zh-CN-XiaoyiNeural",
        "zh-CN-YunxiNeural",
        "zh-CN-YunjianNeural",
    ],
    "English": [
        "en-US-JennyNeural",
        "en-US-GuyNeural",
        "en-US-AriaNeural",
        "en-US-DavisNeural",
    ],
}

# (slide language, speaker language) -> default final video filename
DEFAULT_VIDEO_NAME = {
    ("Chinese", "Chinese"): "final_course_video_zh_cn_slides.mp4",
    ("English", "Chinese"): "final_course_video_zh.mp4",
    ("English", "English"): "final_course_video.mp4",
    ("Chinese", "English"): "final_course_video_cn_slides_en_voice.mp4",
}
LANGUAGE_CODE = {"Chinese": "zh", "English": "en"}

# Characters that are never valid anywhere in a Windows path (a leading
# drive letter's colon, e.g. "D:", is allowed and checked separately).
_INVALID_PATH_CHARS = '<>"|?*'


def select_output_directory(initial_dir: str):
    """Open a native folder picker on the machine running the Streamlit
    server and return the chosen path.

    NOTE: this dialog opens on the SERVER's desktop, not the browser
    visitor's machine. For this local Windows demo the server and the
    browser are the same computer, so that's fine - but if this app were
    deployed remotely, the picker would browse the *server's* filesystem,
    not the visitor's. Manual path entry therefore always remains available.

    Returns:
        - the selected absolute path (non-empty string) if the user picked
          a folder,
        - "" if the dialog opened but the user cancelled,
        - None if the native picker could not be used at all (no tkinter,
          no display, TclError, ...), so the caller can show a fallback
          message.
    """
    try:
        from tkinter import Tk, filedialog
    except ImportError:
        return None

    root = None
    try:
        root = Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(
            initialdir=initial_dir,
            title="Select output folder",
        )
        return selected or ""
    except Exception:
        # Covers tkinter.TclError (no display / Tcl unavailable) and any
        # other native-dialog failure.
        return None
    finally:
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass


def _resolve_initial_dir(output_folder: str) -> str:
    """Pick a sensible starting directory for the folder picker: the
    current value if it exists (resolved against the project root when
    relative), otherwise the project root."""
    folder = (output_folder or "").strip()
    if folder:
        candidate = Path(folder)
        if candidate.is_absolute():
            if candidate.exists():
                return str(candidate)
        else:
            resolved = PROJECT_ROOT / candidate
            if resolved.exists():
                return str(resolved)
    return str(PROJECT_ROOT)


def _resolve_output_path(output_folder: str) -> Path:
    """Normalize the chosen output folder: absolute paths are used as-is,
    relative paths are resolved against the project root."""
    path = Path((output_folder or "").strip())
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _is_protected_dir(output_folder: str) -> bool:
    """True if the folder's final path component matches one of the
    canonical demo output folders, whether output_folder is given as a
    relative name or an absolute path."""
    folder = (output_folder or "").strip().strip("/\\")
    if not folder:
        return False
    return Path(folder).name in PROTECTED_DIRS


def _validate_output_folder(output_folder: str) -> list:
    """Return user-facing problem messages for output_folder; an empty
    list means the path is usable (it does not need to exist yet)."""
    folder = (output_folder or "").strip()
    if not folder:
        return ["Output folder cannot be empty."]

    # Allow a leading drive letter ("D:") but reject other characters that
    # are invalid anywhere in a Windows path.
    body = re.sub(r"^[A-Za-z]:", "", folder)
    if any(ch in _INVALID_PATH_CHARS for ch in body):
        return [
            f"'{folder}' contains characters that are not allowed in a "
            "Windows path."
        ]

    try:
        resolved = _resolve_output_path(folder)
    except (OSError, ValueError) as exc:
        return [f"'{folder}' is not a valid path ({exc})."]

    if resolved.exists() and resolved.is_file():
        return [f"'{resolved}' already exists as a file, not a folder."]

    existing = resolved
    while not existing.exists():
        parent = existing.parent
        if parent == existing:
            break
        existing = parent

    if not os.access(existing, os.W_OK):
        return [f"'{existing}' is not writable."]

    return []


def main():
    st.set_page_config(page_title="AI Course Video Generator", page_icon="🎬")
    st.title("AI Course Video Generator")

    # Apply any pending Browse selection before the output_folder widget is
    # created below - mutating a widget's session_state key after the
    # widget has been instantiated in the same run raises a
    # StreamlitAPIException, so this must happen first.
    if "output_folder" not in st.session_state:
        st.session_state.output_folder = "output_streamlit"
    if "_pending_output_folder" in st.session_state:
        st.session_state.output_folder = st.session_state.pop("_pending_output_folder")

    st.markdown(
        """
**How to use**
1. Upload a course PDF or text script.
2. Choose the **slide language** (visible PPT/slide text) and the
   **speaker language** (narration voice and subtitles) separately.
3. Click **Generate Course Video** and wait a few minutes.
4. Preview the video and download the MP4, PPTX and subtitles below.
"""
    )

    # ---------- Sidebar settings ----------
    st.sidebar.header("Settings")

    slide_language = st.sidebar.selectbox(
        "Slide language",
        ["Chinese", "English"],
        key="slide_language",
        help="Controls the visible PPT/slide text.",
    )
    speaker_language = st.sidebar.selectbox(
        "Speaker language",
        ["Chinese", "English"],
        key="speaker_language",
        help="Controls narration, TTS voice and subtitles.",
    )
    voice = st.sidebar.selectbox(
        "Voice",
        VOICES[speaker_language],
        key=f"voice_{speaker_language}",
    )
    subtitle_choice = st.sidebar.selectbox(
        "Subtitle language",
        ["Same as speaker", "Chinese", "English"],
        key="subtitle_language",
        help="Language of the SRT file and the burned-in captions.",
    )
    st.sidebar.caption(
        "Slide language = visible slide text. Speaker language = narration "
        "and TTS voice. Subtitle language controls the SRT file and "
        "burned-in captions; for final submission, Chinese subtitles are "
        "recommended. For the assignment requirement, a Chinese speaker is "
        "recommended; for the most polished result, choose Chinese slides + "
        "Chinese speaker."
    )

    col_path, col_browse = st.sidebar.columns([3, 1])
    with col_path:
        output_folder = st.text_input("Output folder", key="output_folder")
    with col_browse:
        st.write("")  # nudge the button down to align with the text input
        if st.button("Browse...", key="browse_output_folder"):
            initial_dir = _resolve_initial_dir(st.session_state.output_folder)
            selected = select_output_directory(initial_dir)
            if selected:
                st.session_state["_pending_output_folder"] = selected
                st.rerun()
            elif selected is None:
                st.session_state["_picker_unavailable"] = True

    if st.session_state.pop("_picker_unavailable", False):
        st.sidebar.info(
            "The native folder picker is unavailable in this environment. "
            "Please enter the output path manually."
        )

    st.sidebar.caption(
        "Enter a path manually or use Browse to select a folder on this "
        "computer. Relative paths are created inside the project directory."
    )

    output_folder_errors = _validate_output_folder(output_folder)
    for error in output_folder_errors:
        st.sidebar.error(error)

    resolved_output_dir = _resolve_output_path(output_folder)
    if not output_folder_errors:
        if Path(output_folder.strip()).is_absolute():
            st.sidebar.caption(f"Files will be generated in: {resolved_output_dir}")

        if resolved_output_dir.exists():
            if st.sidebar.button("Open output folder", key="open_output_folder"):
                try:
                    os.startfile(str(resolved_output_dir))
                except Exception as exc:
                    st.sidebar.error(f"Could not open folder: {exc}")

    video_name = st.sidebar.text_input(
        "Video filename",
        value=DEFAULT_VIDEO_NAME[(slide_language, speaker_language)],
        key=f"video_name_{slide_language}_{speaker_language}",
    )
    skip_existing = st.sidebar.checkbox(
        "Skip existing files",
        value=False,
        help="Resume an interrupted run: stages whose output files already "
             "exist and look valid are skipped (base pipeline only).",
    )
    burn_subtitles = st.sidebar.checkbox(
        "Burn subtitles into final video",
        value=True,
        key="burn_subtitles",
        help="Adds a *_subtitled.mp4 with the subtitles rendered into the "
             "picture. The clean MP4 and subtitles.srt are still produced.",
    )

    # ---------- Mode display ----------
    subtitle_language = (
        speaker_language if subtitle_choice == "Same as speaker" else subtitle_choice
    )
    st.markdown(
        f"**Selected mode:** {slide_language} slides + {speaker_language} "
        f"speaker + {subtitle_language} subtitles"
    )
    if (slide_language, speaker_language) == ("Chinese", "English"):
        st.warning(
            "Chinese slides with English narration is experimental. The "
            "recommended modes are Chinese+Chinese or English+Chinese."
        )
    if subtitle_language != speaker_language:
        st.warning(
            "Subtitle language differs from speaker language. Subtitles "
            "will be translated while audio remains unchanged."
        )

    # ---------- Preflight checks ----------
    problems = _preflight_problems()
    for problem in problems:
        st.error(problem)

    if _is_protected_dir(output_folder):
        st.warning(
            f"'{output_folder}' contains canonical demo deliverables. "
            "Generating here may overwrite them - use a different folder "
            "unless that is really what you want."
        )

    # ---------- File upload ----------
    uploaded = st.file_uploader("Course script (.pdf or .txt)", type=["pdf", "txt"])

    input_path = None
    if uploaded is not None:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        input_path = UPLOAD_DIR / Path(uploaded.name).name
        input_path.write_bytes(uploaded.getbuffer())
        st.caption(f"Uploaded: {uploaded.name} ({uploaded.size / 1024:.1f} KB)")

    # ---------- Run ----------
    run_disabled = uploaded is None or bool(problems) or bool(output_folder_errors)
    if st.button("Generate Course Video", type="primary", disabled=run_disabled):
        resolved_output_dir.mkdir(parents=True, exist_ok=True)
        stages = _build_stages(
            input_path=input_path,
            output_folder=str(resolved_output_dir),
            slide_language=slide_language,
            speaker_language=speaker_language,
            voice=voice,
            video_name=video_name.strip(),
            skip_existing=skip_existing,
            burn_subtitles=burn_subtitles,
            subtitle_language=subtitle_choice,
        )
        success = _run_stages(stages)
        st.session_state["last_run"] = {
            "ok": success,
            "output_folder": str(resolved_output_dir),
            "video_name": video_name.strip(),
            "slide_language": slide_language,
            "speaker_language": speaker_language,
            "burn_subtitles": burn_subtitles,
            "subtitle_language": subtitle_language,
        }

    # ---------- Output preview (survives Streamlit reruns, e.g. downloads) ----------
    last_run = st.session_state.get("last_run")
    if last_run and last_run["ok"]:
        _show_outputs(last_run)


def _build_stages(
    input_path: Path,
    output_folder: str,
    slide_language: str,
    speaker_language: str,
    voice: str,
    video_name: str,
    skip_existing: bool,
    burn_subtitles: bool = False,
    subtitle_language: str = "Same as speaker",
) -> list:
    """Return the ordered list of (stage label, main.py command) pairs for
    the selected slide/speaker language combination."""
    python = sys.executable
    main_py = str(PROJECT_ROOT / "main.py")

    base_cmd = [
        python, main_py,
        "--input", str(input_path),
        "--output", output_folder,
        "--language", LANGUAGE_CODE[speaker_language],
        "--voice", voice,
        "--video-name", video_name,
    ]
    if skip_existing:
        base_cmd.append("--skip-existing")

    stages = [("[1] Generate base course video/narration", base_cmd)]

    if slide_language == "Chinese":
        # The base run leaves English slide visuals; translate them, then
        # rebuild the layout-dependent artifacts. The narration JSON the
        # slide translation reads from depends on the speaker language.
        source_json = (
            "structured_course_zh.json"
            if speaker_language == "Chinese"
            else "structured_course.json"
        )
        stages += [
            (
                "[2] Translate slide visuals",
                [
                    python, main_py, "--translate-slides-only",
                    "--output", output_folder,
                    "--course-json", f"{output_folder}/{source_json}",
                ],
            ),
            (
                "[3] Rebuild highlights",
                [
                    python, main_py, "--highlights-only",
                    "--output", output_folder,
                    "--course-json",
                    f"{output_folder}/structured_course_zh_visual.json",
                ],
            ),
            (
                "[4] Export final video",
                [
                    python, main_py, "--video-only",
                    "--output", output_folder,
                    "--video-name", video_name,
                ],
            ),
        ]

    # An explicit subtitle language that differs from the speaker needs a
    # translated SRT; "Same as speaker" reuses subtitles.srt directly.
    effective_subtitle = (
        speaker_language
        if subtitle_language == "Same as speaker"
        else subtitle_language
    )
    subtitle_code = (
        LANGUAGE_CODE[effective_subtitle]
        if effective_subtitle != speaker_language
        else None
    )

    if subtitle_code:
        stages.append(
            (
                f"[{len(stages) + 1}] Translate subtitles",
                [
                    python, main_py, "--translate-subtitles",
                    "--output", output_folder,
                    "--subtitle-language", subtitle_code,
                ],
            )
        )

    if burn_subtitles:
        burn_cmd = [
            python, main_py, "--burn-subtitles",
            "--output", output_folder,
            "--video-name", video_name,
        ]
        if subtitle_code:
            burn_cmd += [
                "--subtitle-file", f"{output_folder}/subtitles_{subtitle_code}.srt",
                "--subtitle-video-name", _subtitled_name(video_name, subtitle_code),
            ]
        stages.append(
            (f"[{len(stages) + 1}] Burn subtitles into video", burn_cmd)
        )

    return stages


def _subtitled_name(video_name: str, subtitle_code: str = None) -> str:
    """Filename main.py --burn-subtitles produces for a given clean MP4.
    Translated subtitles get a language suffix (e.g. *_subtitled_en.mp4)."""
    suffix = f"_subtitled_{subtitle_code}" if subtitle_code else "_subtitled"
    return f"{Path(video_name).stem}{suffix}.mp4"


def _preflight_problems() -> list:
    """Return user-facing error messages for missing prerequisites."""
    problems = []

    if shutil.which("ffmpeg") is None:
        problems.append(
            "FFmpeg was not found on PATH. Install it (e.g. `winget install "
            "ffmpeg`) and restart the app - audio and video generation need it."
        )

    load_dotenv(PROJECT_ROOT / ".env")
    if not os.getenv("OPENAI_API_KEY"):
        problems.append(
            "OPENAI_API_KEY is not set. Copy .env.example to .env and add "
            "your OpenAI API key - course structuring and translation need it."
        )

    return problems


def _run_stages(stages: list) -> bool:
    """Run each (label, command) stage as a subprocess, streaming its logs
    into the UI. Stops at the first failure. Returns True on success."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    n_stages = len(stages)

    log_lines = []
    with st.status("Starting pipeline...", expanded=True) as status:
        log_box = st.empty()

        for stage_label, cmd in stages:
            status.update(label=stage_label)
            log_lines.append(f"=== {stage_label} ===")

            process = subprocess.Popen(
                cmd,
                cwd=str(PROJECT_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )

            for line in process.stdout:
                line = line.rstrip()
                if not line:
                    continue
                log_lines.append(line)
                # Inner stage markers like "[3/8] Generating PPT..."
                if line.startswith("["):
                    if n_stages > 1:
                        status.update(label=f"{stage_label}  {line}")
                    else:
                        status.update(label=line)
                log_box.code("\n".join(log_lines[-20:]), language=None)

            returncode = process.wait()
            if returncode != 0:
                status.update(label=f"Failed during {stage_label}.", state="error")
                break
        else:
            status.update(label="Pipeline finished successfully.", state="complete")
            return True

    st.error("Generation failed. Full log below.")
    with st.expander("Error log", expanded=False):
        st.code("\n".join(log_lines), language=None)
    return False


def _show_outputs(last_run: dict) -> None:
    """Preview the final video and offer downloads for all deliverables."""
    output_dir = PROJECT_ROOT / last_run["output_folder"]
    clean_path = output_dir / last_run["video_name"]

    subtitle_language = last_run.get(
        "subtitle_language", last_run["speaker_language"]
    )
    subtitle_code = (
        LANGUAGE_CODE[subtitle_language]
        if subtitle_language != last_run["speaker_language"]
        else None
    )
    subtitled_path = output_dir / _subtitled_name(
        last_run["video_name"], subtitle_code
    )

    prefer_subtitled = bool(last_run.get("burn_subtitles")) and subtitled_path.exists()
    video_path = subtitled_path if prefer_subtitled else clean_path

    st.subheader("Generated outputs")

    if video_path.exists():
        st.video(str(video_path))
        main_label = (
            f"Download final video with {subtitle_language} subtitles (MP4)"
            if prefer_subtitled
            else "Download final video (MP4)"
        )
        st.download_button(
            main_label,
            data=video_path.read_bytes(),
            file_name=video_path.name,
            mime="video/mp4",
        )
        if prefer_subtitled and clean_path.exists():
            st.download_button(
                "Download clean video without subtitles (MP4)",
                data=clean_path.read_bytes(),
                file_name=clean_path.name,
                mime="video/mp4",
            )
    else:
        st.warning(f"Video not found: {video_path}")

    pptx_mime = (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )
    downloads = [
        ("Download slides (PPTX)", output_dir / "course_slides.pptx", pptx_mime),
        ("Download Chinese slides (PPTX)", output_dir / "course_slides_zh.pptx",
         pptx_mime),
        ("Download subtitles (SRT)", output_dir / "subtitles.srt", "text/plain"),
        ("Download translated Chinese subtitles (SRT)",
         output_dir / "subtitles_zh.srt", "text/plain"),
        ("Download translated English subtitles (SRT)",
         output_dir / "subtitles_en.srt", "text/plain"),
        ("Download course structure (JSON)", output_dir / "structured_course.json",
         "application/json"),
        ("Download Chinese narration (JSON)",
         output_dir / "structured_course_zh.json", "application/json"),
        ("Download Chinese slide text (JSON)",
         output_dir / "structured_course_zh_visual.json", "application/json"),
    ]

    for label, path, mime in downloads:
        if path.exists():
            st.download_button(
                label,
                data=path.read_bytes(),
                file_name=path.name,
                mime=mime,
            )


if __name__ == "__main__":
    main()
