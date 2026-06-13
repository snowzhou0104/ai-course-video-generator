import json
from typing import List, Optional, Tuple

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from src import config


TARGET_BULLET_COUNT = 3
TARGET_NARRATION_COUNT = TARGET_BULLET_COUNT + 1

SYSTEM_PROMPT = (
    "You are an expert instructional designer and curriculum writer. "
    "You convert a raw course script into a structured slide-by-slide outline "
    "for a presentation video.\n\n"
    "CRITICAL REQUIREMENT - narration_segments:\n"
    "Every slide must have EXACTLY 4 narration_segments:\n"
    "- narration_segments[0] is a slide-level introduction (1-2 sentences). "
    "It sets up the topic and does not restate a specific bullet.\n"
    "- narration_segments[1] explains bullets[0] (1-3 sentences).\n"
    "- narration_segments[2] explains bullets[1] (1-3 sentences).\n"
    "- narration_segments[3] explains bullets[2] (1-3 sentences).\n"
    "Do NOT return only one narration segment per bullet. "
    "Do NOT omit the intro segment. "
    "A slide with 3 narration_segments is INVALID.\n\n"
    "CONTENT QUALITY:\n"
    "Preserve the specific facts, numbers, mechanisms, and examples from the "
    "source script, and keep every example attached to the topic it supports "
    "in the source. Never pad a slide with vague filler.\n\n"
    "Always respond with a single valid JSON object and nothing else - "
    "no markdown, no code fences, no commentary."
)

ONE_SHOT_EXAMPLE = """{
  "slide_index": 1,
  "title": "Why Cloud Computing Matters",
  "bullets": [
    "Cloud replaces upfront hardware costs with pay-as-you-go pricing",
    "Teams can scale capacity up or down in minutes",
    "Major providers include AWS, Azure, and Google Cloud"
  ],
  "narration_segments": [
    "Let's start by looking at why cloud computing has become the default choice for modern software teams.",
    "First, the economics. Instead of buying expensive servers upfront, companies pay only for the computing resources they actually use, which turns a large capital expense into a flexible operating cost.",
    "Second, elasticity. When traffic spikes, teams can add capacity in minutes instead of waiting weeks for new hardware, and they can scale back down just as quickly to save money.",
    "Finally, the market is dominated by three major providers - Amazon Web Services, Microsoft Azure, and Google Cloud - each offering hundreds of managed services."
  ],
  "speaker_script": "Let's start by looking at why cloud computing has become the default choice for modern software teams. First, the economics. Instead of buying expensive servers upfront, companies pay only for the computing resources they actually use, which turns a large capital expense into a flexible operating cost. Second, elasticity. When traffic spikes, teams can add capacity in minutes instead of waiting weeks for new hardware, and they can scale back down just as quickly to save money. Finally, the market is dominated by three major providers - Amazon Web Services, Microsoft Azure, and Google Cloud - each offering hundreds of managed services.",
  "highlight_plan": [
    {"bullet_index": 0, "narration_segment_index": 1, "text": "Cloud replaces upfront hardware costs with pay-as-you-go pricing"},
    {"bullet_index": 1, "narration_segment_index": 2, "text": "Teams can scale capacity up or down in minutes"},
    {"bullet_index": 2, "narration_segment_index": 3, "text": "Major providers include AWS, Azure, and Google Cloud"}
  ]
}"""

USER_PROMPT_TEMPLATE = """Convert the course script below into structured JSON matching exactly this shape:

{{
  "course_title": "string",
  "slides": [
    {{
      "slide_index": 1,
      "title": "string",
      "bullets": ["string", "string", "string"],
      "narration_segments": ["string", "string", "string", "string"],
      "speaker_script": "string",
      "highlight_plan": [
        {{"bullet_index": 0, "narration_segment_index": 1, "text": "string"}},
        {{"bullet_index": 1, "narration_segment_index": 2, "text": "string"}},
        {{"bullet_index": 2, "narration_segment_index": 3, "text": "string"}}
      ]
    }}
  ]
}}

Rules:
1. Split the script into logical topics/sections, one per slide. Produce between 6 and 15 slides depending on how much content the script contains.
2. "title": a short, descriptive slide title (max 8 words).
3. "bullets": EXACTLY 3 short phrases (max 14 words each) with the key facts for that slide, written for on-screen display.
4. "narration_segments": EXACTLY 4 strings, written in a friendly teacher tone:
   - narration_segments[0]: a 1-2 sentence introduction for the slide (not tied to any bullet).
   - narration_segments[1]: explains bullets[0].
   - narration_segments[2]: explains bullets[1].
   - narration_segments[3]: explains bullets[2].
   Each explanation can include details from the script that are not shown on the slide.
5. "speaker_script": all 4 narration_segments joined with single spaces.
6. "highlight_plan": EXACTLY 3 entries as shown above, where "text" is a copy of the corresponding bullet.
7. Together, the narration across all slides should cover the important content of the script - do not drop information.
8. "course_title": a short, descriptive title for the whole course, based on the script.

Content quality rules (apply to every slide, for any course document):

A. Source-grounded bullets. Each bullet must preserve a concrete insight from the source document. Avoid vague bullets such as "X is important", "X exists", "X is useful", or "Companies invest in X" - unless the source provides a specific reason, mechanism, example, metric, or consequence, in which case state it.

B. Mechanism over generic statement. Prefer bullets that explain HOW or WHY something works.
   Prefer: "A/B testing guides product decisions"
   Over:   "Experimentation is important"

C. Keep examples attached to the correct topic. If the source gives examples, keep each example under the concept it supports. Do not move examples across unrelated sections, even if the same entity appears in multiple sections - use the aspect that belongs to the current slide's topic.

D. Preserve specific mechanisms. If the source mentions concrete mechanisms, tools, workflows, metrics, or systems, include them concisely in bullets when relevant. Mechanism categories include things like: ranking, retrieval, attribution, bidding, A/B testing, model serving, compliance, payments, fraud detection, user lifecycle, infrastructure, evaluation. (These are categories of what to look for, not required terms.)

E. Avoid shallow example bullets. Do not write bullets that only say an entity has or does something, with no substance.
   Bad:    "Growth teams exist at major companies."
   Better: "Growth combines product, data, experimentation, and lifecycle optimization."

F. Preserve source hierarchy. If the source has sections, tiers, stages, or categories, preserve that structure when creating slides. Do not merge unrelated concepts just to reduce slide count.

G. Bullet quality. Each of the 3 bullets must be: concise, information-rich, specific to the slide topic, useful for teaching, and grounded in the source.

H. Narration quality. Each narration segment must explain its bullet with ADDITIONAL context from the source - reasons, consequences, examples, or details that did not fit on the slide. Do not simply repeat or rephrase the bullet.

I. Preserve concrete numbers. When the source provides important numbers, metrics, dates, rankings, percentages, revenue figures, growth rates, counts, tiers, or quantitative comparisons, preserve the most relevant ones in the bullets or narration if they support the slide topic. Do not invent numbers. Do not force numbers onto every slide. Use numbers only when they are source-grounded and helpful for teaching.

J. Avoid bullets that only say a topic or department exists, is crucial, or receives investment. Prefer bullets that explain the mechanism, business impact, or a concrete source-backed example.

K. Coverage of final sections. If the source document contains explicit final sections such as rankings, comparisons, summary tables, tier lists, company-specific breakdowns, step-by-step frameworks, or final takeaways, preserve them as dedicated slides when they are substantial. Do not drop source sections that represent the document's conclusion, hierarchy, or comparison framework.

Quality self-check - before returning the JSON, verify for every slide:
- Are any bullets too generic? Rewrite them with a concrete source insight.
- Are any bullets merely saying something exists? Rewrite them to say how or why it matters.
- Is every example attached to the topic it supports in the source?
- Does each bullet preserve a concrete insight from the source?
- Does each narration segment add explanation beyond its bullet?
- If the source contains important numbers or rankings, did the output preserve the most relevant ones?
Fix any violations before responding.

9. Respond with ONLY the JSON object described above.

Here is an example of ONE correctly structured slide:

{example}

Course script:
\"\"\"
{script_text}
\"\"\"
"""

CORRECTION_PROMPT = (
    "Your previous output did not follow the narration_segments requirement. "
    "Fix the JSON so every slide has exactly 4 narration_segments: one intro "
    "plus one explanation per bullet. Return JSON only."
)

# Words whose capitalization must be preserved when they start a fallback
# narration sentence (proper nouns, company/product names, acronyms).
PRESERVE_CAPITALIZATION = {
    "Amazon", "Google", "Meta", "Apple", "Microsoft", "Nvidia", "Netflix",
    "TikTok", "YouTube", "AWS", "Azure", "CUDA", "iOS", "Android",
    "AI", "ML", "LLM", "GPU",
}


# --- Models: the raw shape from the LLM (lenient) ------------------------


class _RawSlide(BaseModel):
    slide_index: int
    title: str
    bullets: List[str]
    narration_segments: List[str]
    speaker_script: Optional[str] = None
    highlight_plan: Optional[list] = None


class _RawCourse(BaseModel):
    course_title: str
    slides: List[_RawSlide]


# --- Models: the canonical shape this module returns (strict) ------------


class HighlightPlanEntry(BaseModel):
    bullet_index: int
    narration_segment_index: int
    text: str


class SlideContent(BaseModel):
    slide_index: int
    title: str
    bullets: List[str]
    narration_segments: List[str]
    speaker_script: str
    highlight_plan: List[HighlightPlanEntry]


class CourseStructure(BaseModel):
    course_title: str
    slides: List[SlideContent]


def parse_course_script(script_text: str) -> dict:
    """
    Send the raw course script to the OpenAI API and return a structured
    course outline: a course title plus a list of slides, each with bullet
    points for display, narration segments for voiceover, a joined speaker
    script, and a highlight plan mapping bullets to narration segments.

    If the model returns slides with the wrong number of narration segments,
    it is retried once with a correction prompt. A templated fallback is used
    only as a last resort for any segments still missing after the retry.
    """
    if not config.OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Copy .env.example to .env and add your "
            "OpenAI API key before running the parser."
        )

    client = OpenAI(api_key=config.OPENAI_API_KEY)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": USER_PROMPT_TEMPLATE.format(
                example=ONE_SHOT_EXAMPLE, script_text=script_text
            ),
        },
    ]

    raw_content, raw_course = _call_llm(client, messages)

    bad_slides = _slides_with_wrong_narration_count(raw_course)
    if bad_slides:
        print(
            f"[llm_parser] {len(bad_slides)} slide(s) had wrong narration count "
            f"(slides {bad_slides}); retrying once with correction prompt..."
        )
        retry_messages = messages + [
            {"role": "assistant", "content": raw_content},
            {"role": "user", "content": CORRECTION_PROMPT},
        ]
        try:
            retry_content, retry_course = _call_llm(client, retry_messages)
            retry_bad = _slides_with_wrong_narration_count(retry_course)
            if len(retry_bad) < len(bad_slides):
                raw_course = retry_course
                bad_slides = retry_bad
            print(
                f"[llm_parser] After retry: {len(bad_slides)} slide(s) still "
                "have wrong narration count."
            )
        except ValueError as exc:
            print(f"[llm_parser] Retry failed, keeping first response: {exc}")

    course, fallback_count = _normalize(raw_course)

    print(f"[llm_parser] Fallback narration segments used: {fallback_count}")

    return course.model_dump()


def _call_llm(client: OpenAI, messages: list) -> Tuple[str, _RawCourse]:
    """Call the chat API and parse/validate the JSON response."""
    response = client.chat.completions.create(
        model=config.OPENAI_MODEL,
        temperature=0.3,
        response_format={"type": "json_object"},
        messages=messages,
    )

    raw_content = response.choices[0].message.content

    try:
        raw_data = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"The model did not return valid JSON: {exc}\n\nRaw response:\n{raw_content}"
        ) from exc

    try:
        raw_course = _RawCourse.model_validate(raw_data)
    except ValidationError as exc:
        raise ValueError(
            f"The model's JSON did not match the expected schema:\n{exc}\n\n"
            f"Raw response:\n{raw_content}"
        ) from exc

    return raw_content, raw_course


def _slides_with_wrong_narration_count(raw_course: _RawCourse) -> List[int]:
    """Return slide indices whose narration_segments count is not exactly 4."""
    return [
        slide.slide_index
        for slide in raw_course.slides
        if len(slide.narration_segments) != TARGET_NARRATION_COUNT
    ]


def _bullet_to_fallback_narration(bullet: str) -> str:
    """Turn a bullet into a simple explanatory narration sentence.

    Last-resort fallback for when the LLM doesn't return enough narration
    segments even after the retry, so the result doesn't just repeat the
    bullet text verbatim.
    """
    point = bullet.strip().rstrip(".")

    # Lowercase the first letter so it reads naturally mid-sentence, unless
    # it looks like an acronym (e.g. "AWS") or is a known proper noun
    # (including possessive forms like "Amazon's").
    first_word = point.split(" ", 1)[0].rstrip(",;:")
    if first_word.endswith("'s"):
        first_word = first_word[:-2]

    is_protected = first_word in PRESERVE_CAPITALIZATION
    looks_like_acronym = not (len(point) > 1 and point[0].isupper() and point[1].islower())

    if not is_protected and not looks_like_acronym:
        point = point[0].lower() + point[1:]

    return f"This point matters because it shows how {point}."


def _normalize(raw_course: _RawCourse) -> Tuple[CourseStructure, int]:
    """Convert the raw LLM output into the canonical course schema.

    Guarantees, for every slide:
    - exactly TARGET_BULLET_COUNT bullets
    - exactly TARGET_NARRATION_COUNT narration segments (intro + one per bullet)
    - a speaker_script joining all narration segments
    - a highlight_plan with one entry per bullet

    speaker_script and highlight_plan are always recomputed locally so they
    stay consistent with bullets/narration even if the LLM got them wrong.

    Returns the course plus the number of fallback narration segments used.
    """
    slides = []
    fallback_count = 0

    for index, raw_slide in enumerate(raw_course.slides, start=1):
        bullets = list(raw_slide.bullets)
        narration = list(raw_slide.narration_segments)

        if len(bullets) > TARGET_BULLET_COUNT:
            bullets = bullets[:TARGET_BULLET_COUNT]
        while len(bullets) < TARGET_BULLET_COUNT:
            bullets.append(f"{raw_slide.title} - key point {len(bullets) + 1}")

        if not narration:
            narration = [raw_slide.title]
        if len(narration) > TARGET_NARRATION_COUNT:
            narration = narration[:TARGET_NARRATION_COUNT]
        while len(narration) < TARGET_NARRATION_COUNT:
            bullet_index = len(narration) - 1
            narration.append(_bullet_to_fallback_narration(bullets[bullet_index]))
            fallback_count += 1

        speaker_script = " ".join(narration)

        highlight_plan = [
            HighlightPlanEntry(
                bullet_index=i,
                narration_segment_index=i + 1,
                text=bullet,
            )
            for i, bullet in enumerate(bullets)
        ]

        slides.append(
            SlideContent(
                slide_index=index,
                title=raw_slide.title,
                bullets=bullets,
                narration_segments=narration,
                speaker_script=speaker_script,
                highlight_plan=highlight_plan,
            )
        )

    return CourseStructure(course_title=raw_course.course_title, slides=slides), fallback_count
