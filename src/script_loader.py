from pathlib import Path
from pypdf import PdfReader


def load_script(input_path: str) -> str:
    """
    Load course script from txt or pdf file.
    """
    path = Path(input_path)

    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    suffix = path.suffix.lower()

    if suffix == ".txt":
        return load_txt(path)

    if suffix == ".pdf":
        return load_pdf(path)

    raise ValueError(
        f"Unsupported file type: {suffix}. Please use .txt or .pdf."
    )


def load_txt(path: Path) -> str:
    """
    Load plain text course script.
    """
    return path.read_text(encoding="utf-8")


def load_pdf(path: Path) -> str:
    """
    Extract text from a PDF course script.
    """
    reader = PdfReader(str(path))
    pages_text = []

    for page_index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        text = text.strip()

        if text:
            pages_text.append(f"\n--- Page {page_index} ---\n{text}")

    full_text = "\n".join(pages_text).strip()

    if not full_text:
        raise ValueError(
            "No text could be extracted from the PDF. "
            "The PDF may be scanned or image-based."
        )

    return full_text