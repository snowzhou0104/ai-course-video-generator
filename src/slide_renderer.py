import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from src.utils import ensure_dir, write_json_file

# Canvas: 1280x720 = 13.333in x 7.5in at 96 DPI, so the PPT layout
# (defined in inches in ppt_generator.py) maps 1:1 using inches * 96.
WIDTH = 1280
HEIGHT = 720

# Colors (match ppt_generator.py)
BG_COLOR = (255, 255, 255)
ACCENT_ORANGE = (245, 130, 32)
TITLE_DARK = (33, 33, 33)
BODY_GRAY = (64, 64, 64)
FOOTER_GRAY = (166, 166, 166)

FOOTER_TEXT = "AI Course Video Generator"
SECTION_LABEL = "KEY CONCEPTS"
SECTION_LABEL_CJK = "核心要点"

# CJK ideographs, kana, fullwidth forms and CJK punctuation.
_CJK_RE = re.compile(r"[　-ヿ一-鿿＀-￯]")

# Layout in pixels (PPT inches * 96)
MARGIN_LEFT = 77            # 0.8 in
ACCENT_BAR = (77, 67, 115, 6)   # x, y, w, h
LABEL_POS = (77, 82)
TITLE_POS = (77, 115)
TITLE_MAX_WIDTH = 1126      # 11.7 in
BULLET_X = 96               # 1.0 in
BULLET_START_Y = 250        # 2.6 in
BULLET_TEXT_MAX_WIDTH = 1000
BULLET_LINE_HEIGHT = 38
BULLET_LINE_HEIGHT_CJK = 44   # extra leading for CJK readability
BULLET_GAP = 28
FOOTER_Y = 667              # 6.95 in
NUMBER_RIGHT_X = 1203       # right edge of slide-number text

# Font sizes in px (pt * 96/72)
TITLE_SIZE = 40             # 30 pt
BULLET_SIZE = 27            # 20 pt
LABEL_SIZE = 15             # 11 pt
FOOTER_SIZE = 13            # 10 pt

_FONT_CANDIDATES_REGULAR = ["calibri.ttf", "arial.ttf"]
_FONT_CANDIDATES_BOLD = ["calibrib.ttf", "arialbd.ttf"]
# Microsoft YaHei first, SimHei as fallback (both ship with Windows).
_FONT_CANDIDATES_REGULAR_CJK = ["msyh.ttc", "simhei.ttf", "arial.ttf"]
_FONT_CANDIDATES_BOLD_CJK = ["msyhbd.ttc", "msyh.ttc", "simhei.ttf"]


def _load_font(candidates, size):
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def _wrap_text(draw, text, font, max_width):
    """Greedy wrap; returns a list of lines that fit within max_width.
    Latin text wraps at spaces; CJK text wraps at character boundaries
    (Chinese has no spaces), keeping embedded Latin words intact."""
    if _CJK_RE.search(text):
        # Tokens: single CJK characters, or runs of non-CJK text.
        tokens = re.findall(r"[　-ヿ一-鿿＀-￯]|[^　-ヿ一-鿿＀-￯]+", text)
        joiner = ""
    else:
        tokens = text.split()
        joiner = " "

    lines = []
    current = ""

    for token in tokens:
        candidate = f"{current}{joiner}{token}".strip() if current else token
        if draw.textlength(candidate, font=font) <= max_width or not current:
            current = candidate
        else:
            lines.append(current.rstrip())
            current = token.lstrip()

    if current:
        lines.append(current.rstrip())

    return lines


def render_slides(course_data: dict, output_dir: str) -> list:
    """
    Render one 1280x720 PNG per content slide of the frozen course data,
    visually matching the PPTX style. Writes images to
    <output_dir>/slide_images/slide_NN.png and bullet bounding-box metadata
    to <output_dir>/metadata/slide_layout.json. Returns the metadata list.
    """
    output_dir = Path(output_dir)
    images_dir = output_dir / "slide_images"
    metadata_dir = output_dir / "metadata"
    ensure_dir(images_dir)
    ensure_dir(metadata_dir)

    cjk = any(
        _CJK_RE.search(slide["title"]) or any(_CJK_RE.search(b) for b in slide["bullets"])
        for slide in course_data["slides"]
    )

    if cjk:
        font_title = _load_font(_FONT_CANDIDATES_BOLD_CJK, TITLE_SIZE)
        font_bullet = _load_font(_FONT_CANDIDATES_REGULAR_CJK, BULLET_SIZE)
        font_label = _load_font(_FONT_CANDIDATES_BOLD_CJK, LABEL_SIZE)
        section_label = SECTION_LABEL_CJK
        bullet_line_height = BULLET_LINE_HEIGHT_CJK
        title_line_height = int(TITLE_SIZE * 1.3)
    else:
        font_title = _load_font(_FONT_CANDIDATES_BOLD, TITLE_SIZE)
        font_bullet = _load_font(_FONT_CANDIDATES_REGULAR, BULLET_SIZE)
        font_label = _load_font(_FONT_CANDIDATES_BOLD, LABEL_SIZE)
        section_label = SECTION_LABEL
        bullet_line_height = BULLET_LINE_HEIGHT
        title_line_height = int(TITLE_SIZE * 1.2)

    # The marker is a plain square glyph; the Latin bold font always has it.
    font_marker = _load_font(_FONT_CANDIDATES_BOLD, BULLET_SIZE)
    font_footer = _load_font(_FONT_CANDIDATES_REGULAR, FOOTER_SIZE)

    total = len(course_data["slides"])
    layout_metadata = []

    for slide in course_data["slides"]:
        index = slide["slide_index"]
        image_path = images_dir / f"slide_{index:02d}.png"

        img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
        draw = ImageDraw.Draw(img)

        # Orange accent bar
        x, y, w, h = ACCENT_BAR
        draw.rectangle([x, y, x + w, y + h], fill=ACCENT_ORANGE)

        # Section label
        draw.text(LABEL_POS, section_label, font=font_label, fill=ACCENT_ORANGE)

        # Title (wrapped if needed)
        title_lines = _wrap_text(draw, slide["title"], font_title, TITLE_MAX_WIDTH)
        ty = TITLE_POS[1]
        for line in title_lines:
            draw.text((TITLE_POS[0], ty), line, font=font_title, fill=TITLE_DARK)
            ty += title_line_height

        # Bullets with bounding boxes
        marker = "▪"  # small black square, rendered orange
        marker_width = int(draw.textlength(marker + "  ", font=font_marker))
        bullet_boxes = []
        by = BULLET_START_Y

        for bullet_index, bullet in enumerate(slide["bullets"]):
            lines = _wrap_text(draw, bullet, font_bullet, BULLET_TEXT_MAX_WIDTH)

            box_top = by
            max_line_width = 0

            draw.text((BULLET_X, by), marker, font=font_marker, fill=ACCENT_ORANGE)
            for line in lines:
                draw.text(
                    (BULLET_X + marker_width, by),
                    line,
                    font=font_bullet,
                    fill=BODY_GRAY,
                )
                line_width = int(draw.textlength(line, font=font_bullet))
                max_line_width = max(max_line_width, line_width)
                by += bullet_line_height

            box_height = by - box_top
            # Small padding so the highlight box doesn't hug the glyphs
            pad = 6
            bullet_boxes.append(
                {
                    "bullet_index": bullet_index,
                    "x": BULLET_X - pad,
                    "y": box_top - pad,
                    "w": marker_width + max_line_width + pad * 2,
                    "h": box_height + pad * 2,
                }
            )

            by += BULLET_GAP

        # Footer and slide number
        draw.text((MARGIN_LEFT, FOOTER_Y), FOOTER_TEXT, font=font_footer, fill=FOOTER_GRAY)

        number_text = f"{index:02d} / {total:02d}"
        number_width = draw.textlength(number_text, font=font_footer)
        draw.text(
            (NUMBER_RIGHT_X - number_width, FOOTER_Y),
            number_text,
            font=font_footer,
            fill=FOOTER_GRAY,
        )

        img.save(image_path)

        layout_metadata.append(
            {
                "slide_index": index,
                "image_path": image_path.as_posix(),
                "width": WIDTH,
                "height": HEIGHT,
                "bullet_boxes": bullet_boxes,
            }
        )

    write_json_file(layout_metadata, metadata_dir / "slide_layout.json")

    return layout_metadata
