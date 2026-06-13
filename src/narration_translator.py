import copy
import json
import re

from openai import OpenAI

from src.config import OPENAI_API_KEY, OPENAI_MODEL

TRANSLATE_RETRIES = 2

_CJK_RE = re.compile(r"[一-鿿]")

SYSTEM_PROMPT = """You are a professional translator localizing course video narration from English to Chinese (Simplified, Mandarin).

You will receive one slide: its title, its 3 bullets, and its 4 English narration segments.

Translate ONLY the narration segments into natural, fluent, spoken Mandarin suitable for an educational voiceover. Requirements:
- Return EXACTLY 4 narration segments. Segment 0 is the slide introduction; segments 1, 2 and 3 explain bullets 0, 1 and 2 respectively. Each translated segment must cover the same content as the original segment in the same position.
- Write natural explanatory spoken Chinese, the way a course narrator would actually speak. Do NOT translate word-for-word or produce stiff "translationese".
- Keep company, product and technology names in their original English form (for example Google, Amazon, Meta, AWS, CUDA, TikTok), since they are normally spoken that way in Chinese tech contexts.
- Keep all numbers, amounts and rankings exactly accurate (for example "$60 billion" becomes 600亿美元).
- Do not add new facts and do not drop facts.
- Use Chinese punctuation (。，！？).

Return JSON only, in this exact shape:
{"narration_segments": ["...", "...", "...", "..."]}"""

USER_PROMPT_TEMPLATE = """Slide title: {title}

Bullets:
1. {b0}
2. {b1}
3. {b2}

English narration segments:
0. {s0}
1. {s1}
2. {s2}
3. {s3}

Translate the 4 narration segments to natural spoken Chinese. Return JSON only."""

CORRECTION_PROMPT = (
    "Your previous output was invalid. Return JSON with key narration_segments "
    "containing EXACTLY 4 non-empty Chinese strings, one per original segment, "
    "in the same order. Return JSON only."
)


def translate_narration(course_data: dict) -> dict:
    """
    Create a Chinese-narration copy of the frozen course data.

    Slide structure (slide_index, title, bullets, highlight_plan) is kept
    byte-identical; only narration_segments and speaker_script are replaced
    with natural spoken-Chinese translations produced by the LLM.
    """
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set; translation needs the LLM.")

    client = OpenAI(api_key=OPENAI_API_KEY)

    zh_data = copy.deepcopy(course_data)

    for slide in zh_data["slides"]:
        print(f"      Slide {slide['slide_index']:02d}: translating narration...")
        zh_segments = _translate_slide(client, slide)
        slide["narration_segments"] = zh_segments
        slide["speaker_script"] = _join_segments(zh_segments)

    return zh_data


def _translate_slide(client: OpenAI, slide: dict) -> list:
    """Translate one slide's 4 narration segments; retry on invalid output."""
    user_prompt = USER_PROMPT_TEMPLATE.format(
        title=slide["title"],
        b0=slide["bullets"][0],
        b1=slide["bullets"][1],
        b2=slide["bullets"][2],
        s0=slide["narration_segments"][0],
        s1=slide["narration_segments"][1],
        s2=slide["narration_segments"][2],
        s3=slide["narration_segments"][3],
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    last_problem = None
    for attempt in range(1, TRANSLATE_RETRIES + 1):
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        raw = response.choices[0].message.content

        segments, problem = _parse_segments(raw)
        if segments is not None:
            return segments

        last_problem = problem
        messages.append({"role": "assistant", "content": raw})
        messages.append({"role": "user", "content": CORRECTION_PROMPT})

    raise RuntimeError(
        f"Translation failed for slide {slide['slide_index']} after "
        f"{TRANSLATE_RETRIES} attempts: {last_problem}"
    )


def _parse_segments(raw: str):
    """Return (segments, None) if the LLM output is valid, else (None, problem)."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON ({exc})"

    segments = data.get("narration_segments")
    if not isinstance(segments, list) or len(segments) != 4:
        return None, "narration_segments is not a list of exactly 4 items"
    if not all(isinstance(s, str) and s.strip() for s in segments):
        return None, "a narration segment is empty or not a string"
    if not all(_CJK_RE.search(s) for s in segments):
        return None, "a narration segment contains no Chinese characters"

    return [s.strip() for s in segments], None


def _join_segments(segments: list) -> str:
    """Join Chinese segments into speaker_script without inserting spaces
    after CJK punctuation (but keep a space between Latin-script ends)."""
    script = ""
    for segment in segments:
        if script and not _CJK_RE.search(script[-1]) and script[-1] not in "。！？，；：":
            script += " "
        script += segment
    return script
