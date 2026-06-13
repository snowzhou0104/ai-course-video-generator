import copy
import json
import re

from openai import OpenAI

from src.config import OPENAI_API_KEY, OPENAI_MODEL

TRANSLATE_RETRIES = 2

# Soft readability limit; longer bullets trigger one shortening retry.
MAX_BULLET_CHARS = 24

_CJK_RE = re.compile(r"[一-鿿]")

SYSTEM_PROMPT = """You are a professional translator localizing presentation slides from English to Chinese (Simplified) for a course video.

You will receive one slide: its English title, its 3 English bullets, and the slide's existing Chinese narration (for terminology context).

Translate the title and the 3 bullets into natural, concise written Chinese. Requirements:
- Return EXACTLY 3 bullets, in the same order, each covering the same point as the original bullet in the same position.
- Slide bullets must be SHORT: ideally 18 Chinese characters or fewer, never more than 24. Compress aggressively like real slide text; the narration carries the detail.
- The title must be short and natural (around 6-14 characters).
- Use the same terminology as the provided Chinese narration.
- Keep company, product and technology names in their original English form (for example Google, Amazon, Meta, AWS, CUDA, TikTok).
- Keep numbers and amounts accurate (for example "$60 billion" becomes 600亿美元), but you may drop a number from a bullet if it must be shortened - never change one.
- No ending punctuation on bullets.

Return JSON only, in this exact shape:
{"title": "...", "bullets": ["...", "...", "..."]}"""

USER_PROMPT_TEMPLATE = """English title: {title}

English bullets:
1. {b0}
2. {b1}
3. {b2}

Chinese narration (terminology context):
{narration}

Translate the title and the 3 bullets to concise slide-style Chinese. Return JSON only."""

CORRECTION_PROMPT = (
    "Your previous output was invalid. Return JSON with a Chinese 'title' "
    "string and a 'bullets' list of EXACTLY 3 concise Chinese strings (18 "
    "characters or fewer each if possible, never more than 24), in the same "
    "order as the originals. Return JSON only."
)

TITLE_PROMPT = (
    "Translate this course title to natural, concise Chinese. Keep company "
    "and technology names in English. Return JSON only: "
    '{{"course_title": "..."}}\n\nCourse title: {title}'
)


def translate_slide_text(course_data: dict) -> dict:
    """
    Create a Chinese-slide-text copy of the (Chinese-narration) course data.

    Titles, bullets and highlight_plan texts are replaced with concise
    Chinese translations; slide_index, narration_segments, speaker_script
    and the highlight_plan index mappings stay unchanged.
    """
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set; translation needs the LLM.")

    client = OpenAI(api_key=OPENAI_API_KEY)

    zh_data = copy.deepcopy(course_data)
    zh_data["course_title"] = _translate_course_title(client, course_data["course_title"])

    for slide in zh_data["slides"]:
        print(f"      Slide {slide['slide_index']:02d}: translating slide text...")
        title, bullets = _translate_slide(client, slide)

        slide["title"] = title
        slide["bullets"] = bullets
        for plan in slide["highlight_plan"]:
            plan["text"] = bullets[plan["bullet_index"]]

        for bullet in bullets:
            if len(bullet) > MAX_BULLET_CHARS + 4:
                print(
                    f"      Warning: slide {slide['slide_index']} bullet is "
                    f"long ({len(bullet)} chars): {bullet}"
                )

    return zh_data


def _translate_slide(client: OpenAI, slide: dict):
    """Translate one slide's title and bullets; retry on invalid output."""
    user_prompt = USER_PROMPT_TEMPLATE.format(
        title=slide["title"],
        b0=slide["bullets"][0],
        b1=slide["bullets"][1],
        b2=slide["bullets"][2],
        narration=" ".join(slide["narration_segments"]),
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

        result, problem = _parse_slide(raw)
        if result is not None:
            title, bullets = result
            # One extra roll if a bullet came back too long for the slide.
            if attempt < TRANSLATE_RETRIES and any(
                len(b) > MAX_BULLET_CHARS for b in bullets
            ):
                problem = "a bullet exceeds the length limit"
            else:
                return title, bullets

        last_problem = problem
        messages.append({"role": "assistant", "content": raw})
        messages.append({"role": "user", "content": CORRECTION_PROMPT})

    raise RuntimeError(
        f"Slide text translation failed for slide {slide['slide_index']} "
        f"after {TRANSLATE_RETRIES} attempts: {last_problem}"
    )


def _parse_slide(raw: str):
    """Return ((title, bullets), None) if valid, else (None, problem)."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON ({exc})"

    title = data.get("title")
    bullets = data.get("bullets")

    if not isinstance(title, str) or not _CJK_RE.search(title):
        return None, "title is missing or not Chinese"
    if not isinstance(bullets, list) or len(bullets) != 3:
        return None, "bullets is not a list of exactly 3 items"
    if not all(isinstance(b, str) and b.strip() and _CJK_RE.search(b) for b in bullets):
        return None, "a bullet is empty or not Chinese"

    return (title.strip(), [b.strip() for b in bullets]), None


def _translate_course_title(client: OpenAI, course_title: str) -> str:
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": TITLE_PROMPT.format(title=course_title)}],
        response_format={"type": "json_object"},
        temperature=0.3,
    )
    data = json.loads(response.choices[0].message.content)
    translated = data.get("course_title", "")
    if isinstance(translated, str) and _CJK_RE.search(translated):
        return translated.strip()
    return course_title  # keep the original rather than fail the whole run
