import argparse

from src.script_loader import load_script
from src.llm_parser import parse_course_script
from src.utils import write_json_file


def main():
    parser = argparse.ArgumentParser(
        description="AI Course Video Generator - Course Structure Parser"
    )

    parser.add_argument(
        "--input",
        type=str,
        default="input/Core Departments in Tech Companies.pdf",
        help="Path to the input course script file. Supports .txt and .pdf.",
    )

    parser.add_argument(
        "--output",
        type=str,
        default="output/structured_course.json",
        help="Path to save the structured course JSON.",
    )

    args = parser.parse_args()

    print("[1/3] Loading course script...")
    course_script = load_script(args.input)

    print("[2/3] Generating structured course JSON...")
    course_data = parse_course_script(course_script)

    print("[3/3] Saving structured output...")
    write_json_file(course_data, args.output)

    print("\nDone.")
    print(f"Structured course JSON saved to: {args.output}")


if __name__ == "__main__":
    main()