"""Streamlit AppTest tests for the frontend (app.py).

Run with:  .\\venv\\Scripts\\python.exe -m pytest tests/test_app.py -v

These exercise the UI logic only (defaults, language/voice/filename
coupling); they never click "Generate Course Video", so no subprocess,
LLM call or file generation happens.
"""

import sys
import types
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP_PATH = str(Path(__file__).parent.parent / "app.py")


def _app() -> AppTest:
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    return at


def _video_name_value(at: AppTest) -> str:
    inputs = [t for t in at.text_input if t.key.startswith("video_name_")]
    assert len(inputs) == 1, "expected exactly one video filename input"
    return inputs[0].value


def test_renders_without_exception():
    at = _app()
    assert not at.exception


def test_default_slide_and_speaker_language_are_chinese():
    at = _app()
    assert at.selectbox(key="slide_language").value == "Chinese"
    assert at.selectbox(key="speaker_language").value == "Chinese"


def test_default_voice_is_xiaoxiao():
    at = _app()
    assert at.selectbox(key="voice_Chinese").value == "zh-CN-XiaoxiaoNeural"


def test_english_speaker_switches_voice_default_to_jenny():
    at = _app()
    at.selectbox(key="speaker_language").select("English").run()
    assert not at.exception
    voice = at.selectbox(key="voice_English")
    assert voice.value == "en-US-JennyNeural"
    assert voice.options == [
        "en-US-JennyNeural",
        "en-US-GuyNeural",
        "en-US-AriaNeural",
        "en-US-DavisNeural",
    ]


@pytest.mark.parametrize(
    "slide_language, speaker_language, expected_name",
    [
        ("Chinese", "Chinese", "final_course_video_zh_cn_slides.mp4"),
        ("English", "Chinese", "final_course_video_zh.mp4"),
        ("English", "English", "final_course_video.mp4"),
        ("Chinese", "English", "final_course_video_cn_slides_en_voice.mp4"),
    ],
)
def test_video_filename_follows_language_combination(
    slide_language, speaker_language, expected_name
):
    at = _app()
    at.selectbox(key="slide_language").select(slide_language)
    at.selectbox(key="speaker_language").select(speaker_language)
    at.run()
    assert not at.exception
    assert _video_name_value(at) == expected_name


def test_selected_mode_is_displayed():
    at = _app()
    texts = [m.value for m in at.markdown]
    assert any("Selected mode:" in t and "Chinese slides" in t for t in texts)


def test_experimental_warning_for_chinese_slides_english_speaker():
    at = _app()
    at.selectbox(key="speaker_language").select("English").run()
    warnings = " ".join(w.value for w in at.warning)
    assert "experimental" in warnings

    # The recommended combinations show no experimental warning.
    at.selectbox(key="speaker_language").select("Chinese").run()
    warnings = " ".join(w.value for w in at.warning)
    assert "experimental" not in warnings


def test_protected_output_folder_shows_warning():
    at = _app()
    at.text_input(key="output_folder").set_value("output_cn_slide_cn_speaker").run()
    warnings = " ".join(w.value for w in at.warning)
    assert "canonical demo deliverables" in warnings

    at.text_input(key="output_folder").set_value("output_streamlit").run()
    warnings = " ".join(w.value for w in at.warning)
    assert "canonical demo deliverables" not in warnings


def test_all_canonical_folders_are_protected():
    import app

    assert app.PROTECTED_DIRS == {
        "output_en_slide_en_speaker",
        "output_en_slide_cn_speaker",
        "output_cn_slide_cn_speaker",
    }


def test_default_output_folder():
    at = _app()
    assert at.text_input(key="output_folder").value == "output_streamlit"


# ---------- stage builder (no UI) ----------

def _stages(slide_language, speaker_language, burn_subtitles=False,
            subtitle_language="Same as speaker"):
    import app

    return app._build_stages(
        input_path=Path("input/sample.pdf"),
        output_folder="output_streamlit",
        slide_language=slide_language,
        speaker_language=speaker_language,
        voice="zh-CN-XiaoxiaoNeural",
        video_name="video.mp4",
        skip_existing=False,
        burn_subtitles=burn_subtitles,
        subtitle_language=subtitle_language,
    )


def test_english_slides_run_single_stage():
    for speaker in ("Chinese", "English"):
        stages = _stages("English", speaker)
        assert len(stages) == 1
        cmd = stages[0][1]
        assert "--language" in cmd
        assert cmd[cmd.index("--language") + 1] == ("zh" if speaker == "Chinese" else "en")
        assert "--translate-slides-only" not in cmd


def test_chinese_slides_add_translate_highlight_video_stages():
    stages = _stages("Chinese", "Chinese")
    assert [label for label, _ in stages] == [
        "[1] Generate base course video/narration",
        "[2] Translate slide visuals",
        "[3] Rebuild highlights",
        "[4] Export final video",
    ]
    translate_cmd = stages[1][1]
    assert translate_cmd[translate_cmd.index("--course-json") + 1] == (
        "output_streamlit/structured_course_zh.json"
    )
    highlights_cmd = stages[2][1]
    assert highlights_cmd[highlights_cmd.index("--course-json") + 1] == (
        "output_streamlit/structured_course_zh_visual.json"
    )


def test_chinese_slides_english_speaker_translates_from_english_json():
    stages = _stages("Chinese", "English")
    assert len(stages) == 4
    translate_cmd = stages[1][1]
    assert translate_cmd[translate_cmd.index("--course-json") + 1] == (
        "output_streamlit/structured_course.json"
    )


# ---------- burned-in subtitles ----------

def test_burn_subtitles_checkbox_renders_and_defaults_on():
    at = _app()
    assert at.checkbox(key="burn_subtitles").value is True


def test_burn_subtitles_appends_stage():
    stages = _stages("Chinese", "Chinese", burn_subtitles=True)
    assert stages[-1][0] == "[5] Burn subtitles into video"
    assert "--burn-subtitles" in stages[-1][1]

    stages = _stages("English", "English", burn_subtitles=True)
    assert stages[-1][0] == "[2] Burn subtitles into video"
    assert "--burn-subtitles" in stages[-1][1]

    stages = _stages("English", "English", burn_subtitles=False)
    assert all("--burn-subtitles" not in cmd for _, cmd in stages)


def test_subtitled_video_filename():
    import app

    assert app._subtitled_name("final_course_video_zh_cn_slides.mp4") == (
        "final_course_video_zh_cn_slides_subtitled.mp4"
    )
    assert app._subtitled_name("final_course_video_zh_cn_slides.mp4", "en") == (
        "final_course_video_zh_cn_slides_subtitled_en.mp4"
    )
    assert app._subtitled_name("final_course_video.mp4", "zh") == (
        "final_course_video_subtitled_zh.mp4"
    )


# ---------- subtitle language ----------

def test_subtitle_language_selectbox_renders_with_default():
    at = _app()
    box = at.selectbox(key="subtitle_language")
    assert box.value == "Same as speaker"
    assert box.options == ["Same as speaker", "Chinese", "English"]


def test_mode_line_includes_subtitle_language():
    at = _app()
    texts = " ".join(m.value for m in at.markdown)
    assert "Chinese slides + Chinese speaker + Chinese subtitles" in texts

    # "Same as speaker" follows the speaker language.
    at.selectbox(key="speaker_language").select("English").run()
    texts = " ".join(m.value for m in at.markdown)
    assert "English speaker + English subtitles" in texts


def test_warning_when_subtitle_language_differs_from_speaker():
    at = _app()
    at.selectbox(key="subtitle_language").select("English").run()
    warnings = " ".join(w.value for w in at.warning)
    assert "Subtitle language differs from speaker language" in warnings

    # Explicit Chinese with a Chinese speaker matches: no warning.
    at.selectbox(key="subtitle_language").select("Chinese").run()
    warnings = " ".join(w.value for w in at.warning)
    assert "Subtitle language differs" not in warnings


def test_translated_subtitles_add_stage_and_burn_uses_translated_file():
    stages = _stages("Chinese", "Chinese", burn_subtitles=True,
                     subtitle_language="English")
    labels = [label for label, _ in stages]
    assert labels[-2] == "[5] Translate subtitles"
    assert labels[-1] == "[6] Burn subtitles into video"

    translate_cmd = stages[-2][1]
    assert "--translate-subtitles" in translate_cmd
    assert translate_cmd[translate_cmd.index("--subtitle-language") + 1] == "en"

    burn_cmd = stages[-1][1]
    assert burn_cmd[burn_cmd.index("--subtitle-file") + 1] == (
        "output_streamlit/subtitles_en.srt"
    )
    assert burn_cmd[burn_cmd.index("--subtitle-video-name") + 1] == (
        "video_subtitled_en.mp4"
    )


def test_same_as_speaker_burn_uses_default_srt():
    stages = _stages("Chinese", "Chinese", burn_subtitles=True,
                     subtitle_language="Same as speaker")
    assert all("--translate-subtitles" not in cmd for _, cmd in stages)
    burn_cmd = stages[-1][1]
    assert "--subtitle-file" not in burn_cmd
    assert "--subtitle-video-name" not in burn_cmd

    # An explicit choice matching the speaker also needs no translation.
    stages = _stages("Chinese", "Chinese", burn_subtitles=True,
                     subtitle_language="Chinese")
    assert all("--translate-subtitles" not in cmd for _, cmd in stages)


def test_translated_subtitles_without_burn_still_translate():
    stages = _stages("English", "English", burn_subtitles=False,
                     subtitle_language="Chinese")
    assert stages[-1][0] == "[2] Translate subtitles"
    cmd = stages[-1][1]
    assert cmd[cmd.index("--subtitle-language") + 1] == "zh"


# ---------- output folder picker ----------

def _fake_tkinter(selected, tk_init_error=None):
    """Build a fake `tkinter` module for monkeypatching sys.modules, so
    `from tkinter import Tk, filedialog` inside select_output_directory
    never opens a real dialog."""

    class FakeTk:
        def __init__(self):
            if tk_init_error is not None:
                raise tk_init_error

        def withdraw(self):
            pass

        def attributes(self, *args, **kwargs):
            pass

        def destroy(self):
            pass

    module = types.ModuleType("tkinter")
    module.Tk = FakeTk
    module.filedialog = types.SimpleNamespace(askdirectory=lambda **kw: selected)
    return module


def test_select_output_directory_returns_selected_path(monkeypatch):
    import app

    monkeypatch.setitem(sys.modules, "tkinter", _fake_tkinter("D:\\Chosen\\Folder"))
    assert app.select_output_directory("D:\\start") == "D:\\Chosen\\Folder"


def test_select_output_directory_returns_empty_string_on_cancel(monkeypatch):
    import app

    monkeypatch.setitem(sys.modules, "tkinter", _fake_tkinter(""))
    assert app.select_output_directory("D:\\start") == ""


def test_select_output_directory_returns_none_when_unavailable(monkeypatch):
    import app

    # sys.modules[name] = None makes `import tkinter` raise ImportError.
    monkeypatch.setitem(sys.modules, "tkinter", None)
    assert app.select_output_directory("D:\\start") is None


def test_select_output_directory_returns_none_on_picker_error(monkeypatch):
    import app

    monkeypatch.setitem(
        sys.modules, "tkinter", _fake_tkinter("", tk_init_error=RuntimeError("no display"))
    )
    assert app.select_output_directory("D:\\start") is None


def test_default_output_folder_is_output_streamlit():
    at = _app()
    assert at.text_input(key="output_folder").value == "output_streamlit"
    assert at.session_state["output_folder"] == "output_streamlit"


def test_browse_button_renders():
    at = _app()
    assert at.button(key="browse_output_folder").label == "Browse..."


def test_pending_selection_updates_output_folder_on_rerun():
    # Simulates the result of clicking Browse and picking a folder: the
    # picker stores its result under "_pending_output_folder", and the
    # next run must apply it to the output_folder widget before that
    # widget is instantiated.
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.session_state["_pending_output_folder"] = "D:\\CourseVideoOutputs\\test_run"
    at.run()
    assert not at.exception
    assert at.text_input(key="output_folder").value == "D:\\CourseVideoOutputs\\test_run"
    assert "_pending_output_folder" not in at.session_state


def test_cancelling_selection_preserves_existing_value():
    at = _app()
    at.text_input(key="output_folder").set_value("my_custom_output").run()
    assert at.text_input(key="output_folder").value == "my_custom_output"

    # No "_pending_output_folder" is set when Browse is cancelled, and an
    # unrelated control change must not disturb the chosen folder.
    at.selectbox(key="speaker_language").select("English").run()
    assert at.text_input(key="output_folder").value == "my_custom_output"


def test_relative_protected_folder_shows_warning():
    at = _app()
    at.text_input(key="output_folder").set_value("output_en_slide_en_speaker").run()
    warnings = " ".join(w.value for w in at.warning)
    assert "canonical demo deliverables" in warnings


def test_absolute_protected_folder_shows_warning():
    at = _app()
    abs_path = str(Path(__file__).parent.parent / "output_cn_slide_cn_speaker")
    at.text_input(key="output_folder").set_value(abs_path).run()
    warnings = " ".join(w.value for w in at.warning)
    assert "canonical demo deliverables" in warnings


def test_ordinary_custom_folder_shows_no_protected_warning():
    at = _app()
    at.text_input(key="output_folder").set_value("my_custom_output").run()
    warnings = " ".join(w.value for w in at.warning)
    assert "canonical demo deliverables" not in warnings


def test_empty_output_folder_shows_validation_error():
    at = _app()
    at.text_input(key="output_folder").set_value("").run()
    errors = " ".join(e.value for e in at.error)
    assert "cannot be empty" in errors


def test_invalid_path_characters_show_validation_error():
    at = _app()
    at.text_input(key="output_folder").set_value("bad?name").run()
    errors = " ".join(e.value for e in at.error)
    assert "not allowed in a Windows path" in errors


def test_validate_output_folder_rejects_existing_file(tmp_path):
    import app

    file_path = tmp_path / "not_a_folder.txt"
    file_path.write_text("x")

    errors = app._validate_output_folder(str(file_path))
    assert errors
    assert "file" in errors[0]


def test_resolve_output_path_relative_vs_absolute():
    import app

    assert app._resolve_output_path("output_streamlit") == (
        app.PROJECT_ROOT / "output_streamlit"
    )

    abs_path = str(Path(__file__).parent.parent / "output_cn_slide_cn_speaker")
    assert app._resolve_output_path(abs_path) == Path(abs_path)
