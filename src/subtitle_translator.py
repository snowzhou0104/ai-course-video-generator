import json
import re

from openai import OpenAI

from src.config import OPENAI_API_KEY, OPENAI_MODEL

BATCH_SIZE = 20
TRANSLATE_RETRIES = 2

LANGUAGE_NAMES = {"zh": "Chinese (Simplified)", "en": "English"}

_TIMING_RE = re.compile(
    r"^\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}$"
)

SYSTEM_PROMPT_TEMPLATE = """You are translating video subtitles to {language}.

You receive a JSON object {{"lines": [...]}} with consecutive subtitle lines \
from a course narration, in their original order. Translate each line to \
natural {language} suitable for on-screen subtitles.

Requirements:
- Return EXACTLY the same number of lines, in the same order; output line i \
must be the translation of input line i.
- Each line must stand alone as one subtitle; never merge, split or reorder lines.
- Keep company, product and technology names in English (for example Google, \
Amazon, AWS, CUDA).
- Keep numbers and amounts accurate.
- Keep a similar length where possible so the subtitles stay readable.
- Do not add numbering, quotes or commentary.

Return JSON only: {{"lines": ["...", "..."]}}"""

CORRECTION_PROMPT = (
    "Your previous output was invalid. Return JSON only, shaped "
    '{{"lines": [...]}}, with EXACTLY {n} non-empty translated strings in '
    "the same order as the input lines."
)


def parse_srt(content: str) -> list:
    """Parse SRT text into [{"index", "timing", "text"}]. The timing line is
    kept verbatim so it can be compared and re-emitted byte-identical."""
    entries = []
    for block in re.split(r"\n\s*\n", content.strip()):
        lines = [line.lstrip("﻿").rstrip() for line in block.strip().splitlines()]
        if len(lines) < 3:
            raise ValueError(f"Malformed SRT block: {block!r}")
        if not _TIMING_RE.match(lines[1]):
            raise ValueError(f"Malformed SRT timing line: {lines[1]!r}")
        entries.append(
            {
                "index": int(lines[0]),
                "timing": lines[1],
                "text": " ".join(lines[2:]).strip(),
            }
        )
    return entries


def compose_srt(entries: list) -> str:
    parts = [f"{e['index']}\n{e['timing']}\n{e['text']}" for e in entries]
    return "\n\n".join(parts) + "\n"


def translate_subtitles(content: str, target_language: str) -> str:
    """
    Translate the text of every SRT entry to target_language ("zh" or "en")
    via the LLM, preserving entry numbers and timestamps exactly. Returns
    the translated SRT as a string.
    """
    if target_language not in LANGUAGE_NAMES:
        raise ValueError(f"Unsupported subtitle language: {target_language}")
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set; translation needs the LLM.")

    entries = parse_srt(content)
    client = OpenAI(api_key=OPENAI_API_KEY)

    texts = [e["text"] for e in entries]
    translated = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start:start + BATCH_SIZE]
        print(
            f"      Translating subtitles {start + 1}-{start + len(batch)}"
            f"/{len(texts)}..."
        )
        translated.extend(_translate_batch(client, batch, target_language))

    new_entries = [
        {"index": e["index"], "timing": e["timing"], "text": text}
        for e, text in zip(entries, translated)
    ]
    return compose_srt(new_entries)


def _translate_batch(client: OpenAI, batch: list, target_language: str) -> list:
    """Translate one ordered batch of subtitle lines; retry on bad output."""
    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT_TEMPLATE.format(
                language=LANGUAGE_NAMES[target_language]
            ),
        },
        {"role": "user", "content": json.dumps({"lines": batch}, ensure_ascii=False)},
    ]

    last_problem = None
    for _ in range(TRANSLATE_RETRIES):
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        raw = response.choices[0].message.content

        lines, problem = _parse_lines(raw, len(batch))
        if lines is not None:
            return lines

        last_problem = problem
        messages.append({"role": "assistant", "content": raw})
        messages.append(
            {"role": "user", "content": CORRECTION_PROMPT.format(n=len(batch))}
        )

    raise RuntimeError(
        f"Subtitle translation failed after {TRANSLATE_RETRIES} attempts: "
        f"{last_problem}"
    )


def _parse_lines(raw: str, expected: int):
    """Return (lines, None) if valid, else (None, problem)."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON ({exc})"

    lines = data.get("lines")
    if not isinstance(lines, list) or len(lines) != expected:
        return None, f"expected {expected} lines, got {len(lines) if isinstance(lines, list) else type(lines)}"
    if not all(isinstance(l, str) and l.strip() for l in lines):
        return None, "a translated line is empty or not a string"

    return [l.strip().replace("\n", " ") for l in lines], None
