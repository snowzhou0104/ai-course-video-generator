import math
import re
from pathlib import Path

# Maximum display width per subtitle entry (roughly two readable lines).
# CJK characters count as width 2, so this allows about 42 Chinese chars.
MAX_SUBTITLE_CHARS = 84

# Chunks narrower than this flash by too quickly to read; merge them
# with a neighboring chunk instead.
MIN_SUBTITLE_CHARS = 20

# CJK ideographs, kana, fullwidth forms and CJK punctuation.
_CJK_RE = re.compile(r"[　-ヿ一-鿿＀-￯]")


def _width(text: str) -> int:
    """Display width: CJK characters count double (they render wider and
    carry more meaning per character than Latin letters)."""
    return sum(2 if _CJK_RE.match(ch) else 1 for ch in text)


def _join(a: str, b: str) -> str:
    """Join two text pieces: no space at a CJK boundary, space otherwise."""
    if not a:
        return b
    if not b:
        return a
    if _CJK_RE.match(a[-1]) or _CJK_RE.match(b[0]):
        return a + b
    return f"{a} {b}"


def generate_subtitles(audio_metadata: list, output_dir: str) -> list:
    """
    Generate one global SRT file from the frozen audio metadata.

    The final video concatenates slide audio in slide order, so each
    segment's local start/end time is shifted by the total duration of
    all previous slides to get global video timestamps.

    Writes <output_dir>/subtitles.srt and returns the subtitle entries
    as a list of {index, start, end, text} dicts (times in seconds).
    """
    output_dir = Path(output_dir)
    srt_path = output_dir / "subtitles.srt"

    entries = []
    offset = 0.0

    for slide in audio_metadata:
        for segment in slide["segments"]:
            global_start = offset + segment["start"]
            global_end = offset + segment["end"]

            for text, start, end in _split_segment(
                segment["text"], global_start, global_end
            ):
                entries.append(
                    {
                        "index": len(entries) + 1,
                        "start": round(start, 3),
                        "end": round(end, 3),
                        "text": text,
                    }
                )

        # Next slide's audio starts where this slide's audio ends.
        offset += slide["duration"]

    lines = []
    for entry in entries:
        lines.append(str(entry["index"]))
        lines.append(
            f"{_format_timestamp(entry['start'])} --> "
            f"{_format_timestamp(entry['end'])}"
        )
        lines.append(entry["text"])
        lines.append("")

    srt_path.write_text("\n".join(lines), encoding="utf-8")

    return entries


def _split_segment(text: str, start: float, end: float) -> list:
    """
    Split a narration segment into readable subtitle chunks, allocating
    the segment's time span proportionally to each chunk's length.

    Returns a list of (text, start, end) tuples.
    """
    chunks = _split_text(text.strip())

    total_width = sum(_width(c) for c in chunks)
    duration = end - start

    result = []
    cursor = start
    for i, chunk in enumerate(chunks):
        if i == len(chunks) - 1:
            chunk_end = end  # avoid rounding drift on the last chunk
        else:
            chunk_end = cursor + duration * (_width(chunk) / total_width)
        result.append((chunk, cursor, chunk_end))
        cursor = chunk_end

    return result


def _split_text(text: str) -> list:
    """Split text into chunks of at most MAX_SUBTITLE_CHARS display width,
    preferring punctuation boundaries (Latin and CJK), then word/character
    boundaries. Words are never split and the text is never altered."""
    if _width(text) <= MAX_SUBTITLE_CHARS:
        return [text]

    # Pieces ending in punctuation (sentence enders first, then commas etc.).
    # CJK punctuation is not followed by a space, so split right after it.
    pieces = [p for p in re.split(r"(?<=[.!?])\s+|(?<=[。！？])\s*", text) if p]
    if len(pieces) == 1:
        pieces = [p for p in re.split(r"(?<=[,;:])\s+|(?<=[，；：、])\s*", text) if p]
    if len(pieces) == 1:
        return _balanced_word_split(text)

    # Greedily pack pieces into chunks within the limit.
    chunks = []
    current = ""
    for piece in pieces:
        candidate = _join(current, piece)
        if _width(candidate) <= MAX_SUBTITLE_CHARS or not current:
            current = candidate
        else:
            chunks.append(current)
            current = piece
    if current:
        chunks.append(current)

    # A single piece may itself still be too long; recurse on those.
    final = []
    for chunk in chunks:
        if _width(chunk) > MAX_SUBTITLE_CHARS:
            final.extend(_split_text(chunk))
        else:
            final.append(chunk)

    return _merge_short_chunks(final)


def _balanced_word_split(text: str) -> list:
    """Split text into chunks of roughly equal display width, each within
    MAX_SUBTITLE_CHARS, so no chunk ends up as a tiny orphan. Splits at
    word boundaries; for space-free text (Chinese) at character boundaries."""
    units = text.split() if " " in text else list(text)

    n_chunks = math.ceil(_width(text) / MAX_SUBTITLE_CHARS)
    target = _width(text) / n_chunks

    chunks = []
    current = ""
    for unit in units:
        candidate = _join(current, unit)
        if current and _width(candidate) > target and len(chunks) < n_chunks - 1:
            chunks.append(current)
            current = unit
        else:
            current = candidate
    if current:
        chunks.append(current)

    return chunks


def _merge_short_chunks(chunks: list) -> list:
    """Merge chunks narrower than MIN_SUBTITLE_CHARS into a neighbor.
    If the merged text exceeds the limit, rebalance it at word level."""
    result = list(chunks)

    while len(result) > 1:
        short = next(
            (i for i, c in enumerate(result) if _width(c) < MIN_SUBTITLE_CHARS),
            None,
        )
        if short is None:
            break

        # Merge with the shorter adjacent chunk.
        if short == 0:
            neighbor = 1
        elif short == len(result) - 1:
            neighbor = short - 1
        else:
            neighbor = short - 1 if _width(result[short - 1]) <= _width(result[short + 1]) else short + 1

        first, second = min(short, neighbor), max(short, neighbor)
        merged = _join(result[first], result[second])

        if _width(merged) <= MAX_SUBTITLE_CHARS:
            replacement = [merged]
        else:
            replacement = _balanced_word_split(merged)

        result[first:second + 1] = replacement

    return result


def _format_timestamp(seconds: float) -> str:
    """Format seconds as an SRT timestamp: HH:MM:SS,mmm"""
    millis = int(round(seconds * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1_000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
