# -*- coding: utf-8 -*-
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JSX = ROOT / "abfm-board-prep.jsx"
JSON_PATH = ROOT / "exam_2025.json"


def main():
    exam = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    new_const = "const EXAM_2025 = " + json.dumps(
        exam, ensure_ascii=False, separators=(",", ":")
    )
    if "\n" in new_const or "\r" in new_const:
        raise SystemExit("invalid new_const: json.dumps should be a single line")

    content = JSX.read_text(encoding="utf-8")

    m_start = re.search(r"const EXAM_2025 = ", content)
    m_end = re.search(r"\r?\nconst ALL_EXAMS\s*=", content)
    if not m_start or not m_end:
        raise SystemExit("could not find EXAM_2025 / ALL_EXAMS anchors")

    content = content[: m_start.start()] + new_const + content[m_end.start() :]
    JSX.write_text(content, encoding="utf-8", newline="\n")
    print(f"Updated {JSX}")


if __name__ == "__main__":
    main()
