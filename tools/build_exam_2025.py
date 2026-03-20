# -*- coding: utf-8 -*-
"""Build EXAM_2025 JSON from 2025 ABFM ITE PDFs."""
import json
import re
import sys
from pathlib import Path

from pypdf import PdfReader

Q_PDF = Path(
    r"C:\Users\justi\AppData\Roaming\Cursor\User\workspaceStorage\f05389709a681362eb79f484e88a63df\pdfs\3839e047-6a7c-43f2-b2f9-169958c77d32\2025ITEMultChoice.pdf"
)
C_PDF = Path(
    r"C:\Users\justi\AppData\Roaming\Cursor\User\workspaceStorage\f05389709a681362eb79f484e88a63df\pdfs\945bd2a5-4ceb-4ceb-8bd1-ed25f9fb98e2\2025ITECritique.pdf"
)
OUT_JSON = Path(__file__).resolve().parent.parent / "exam_2025.json"


def pdf_text(path: Path) -> str:
    r = PdfReader(str(path))
    parts = []
    for page in r.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def fix_questions_pdf_artifacts(text: str) -> str:
    """Fix common pypdf line-break splits in the exam PDF."""
    # m2 with period or space after (GFR, BMI m2)
    text = re.sub(r"m\s*\n\s*2(\.\s|\s)", r"m2\1", text)
    text = re.sub(r"/m\s*\n\s*2", "/m2", text)
    text = re.sub(r"kg/m\s*\n\s*2", "kg/m2", text)
    text = re.sub(r"free T\s*\n\s*3", "free T3", text)
    text = re.sub(r"and T\s*\n\s*4", "and T4", text)
    text = re.sub(r"vitamin B\s*\n\s*12", "vitamin B12", text)
    text = re.sub(r"S\s*\n\s*1 and S2", "S1 and S2", text)
    text = re.sub(r"normal S\s*\n\s*1 and S2", "normal S1 and S2", text)
    text = re.sub(r"normal S\s*\n\s*1 and S\s*\n\s*2", "normal S1 and S2", text)
    text = re.sub(r"PHQ-\s*\n\s*9", "PHQ-9", text)
    text = re.sub(r"β\s*\n\s*3", "β3", text)
    text = re.sub(r"H2\s*\n\s*O", "H2 O", text)
    # "duplex ultrasound \nof" -> one line
    text = re.sub(r"ultrasound\s*\n\s*of the", "ultrasound of the", text)
    text = re.sub(r"Glasg\s*\n\s*ow", "Glasgow", text)
    # GCS score line break (e.g. "score of\n15. On examination" is not a new question)
    text = re.sub(
        r"Coma Scale score of\s*\n\s*(\d{1,2}\. On examination)",
        r"Coma Scale score of \1",
        text,
    )
    return text


def fix_critique_pdf_artifacts(text: str) -> str:
    text = re.sub(r"It\s*\n\s*em\s+", "Item ", text)
    text = re.sub(r"\bR\s*\n\s*eferences\b", "References", text)
    text = re.sub(r"Plan-Do-Study-\s*\n\s*Act", "Plan-Do-Study-Act", text)
    # Hyphenated word wraps at line ends (common in critiques)
    text = re.sub(r"-\s*\n\s*", "", text)
    return text


def clean_questions_raw(text: str) -> str:
    text = fix_questions_pdf_artifacts(text)
    lines = text.splitlines()
    out = []
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if s.startswith("American Board of"):
            continue
        if s == "Family Medicine":
            continue
        if "IN-TRAINING EXAMINATION" in s and "Publication" not in s:
            continue
        if "Publication or reproduction" in s:
            continue
        if "Copyright" in s and "American Board of Family Medicine" in s:
            continue
        if re.match(r"^--\s*\d+\s+of\s+\d+\s+--$", s):
            continue
        out.append(ln)
    return "\n".join(out)


def split_questions(text: str) -> list[tuple[int, str]]:
    text = text.replace("\t", " ")
    parts = re.split(r"(?m)^(?=(?:[1-9]|[1-9]\d|1\d\d|200)\.\s)", text)
    blocks = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        m = re.match(r"^((?:[1-9]|[1-9]\d|1\d\d|200))\.\s*(.*)$", p, re.DOTALL)
        if not m:
            continue
        n = int(m.group(1))
        rest = m.group(2)
        blocks.append((n, rest))
    blocks.sort(key=lambda x: x[0])
    return blocks


OPTION_START = re.compile(r"(?m)^([A-E])\)\s+(.*)$")


def parse_question_block(n: int, block: str) -> dict:
    lines = block.splitlines()
    opt_indices = []
    for i, ln in enumerate(lines):
        m = re.match(r"^([A-E])\)\s+(.*)$", ln.strip())
        if m:
            opt_indices.append(i)
    if not opt_indices:
        raise ValueError(f"Q{n}: no options found")
    first_opt = opt_indices[0]
    stem_lines = lines[:first_opt]
    stem_raw = "\n".join(stem_lines)
    stem_raw = re.sub(r"^(?:[1-9]|[1-9]\d|1\d\d|200)\.\s+", "", stem_raw.strip(), count=1)

    def is_tableish(line: str) -> bool:
        t = line.strip()
        if not t:
            return False
        if "\t" in line:
            return True
        if re.match(
            r"^(Sodium|Potassium|Chloride|Creatinine|BUN|Calcium|Hemoglobin|Glucose|WBCs|Platelets|AST|ALT|"
            r"Serum|Urine|Laboratory Findings|Alkaline phosphatase|Total bilirubin|Antimitochondrial|"
            r"Anion gap|Bicarbonate|Estimated glomerular|Hemoglobin A1c|Erythrocyte|C-reactive|"
            r"Antinuclear antibody|Creatine kinase|Arterial pH|Urine ketones|Laboratory)",
            t,
        ):
            return True
        if re.match(r"^[A-Za-z].{2,40}?\s{2,}\S", line):
            return True
        return False

    stem_parts: list[str] = []
    buf: list[str] = []
    slines = stem_raw.split("\n")
    i = 0
    while i < len(slines):
        line = slines[i]
        if is_tableish(line):
            if buf:
                stem_parts.append(" ".join(x.strip() for x in buf if x.strip()))
                buf = []
            tbl = [line]
            i += 1
            while i < len(slines):
                nxt = slines[i]
                if not nxt.strip():
                    i += 1
                    break
                if is_tableish(nxt) or (
                    nxt.startswith(" ") and len(nxt) - len(nxt.lstrip()) >= 2
                ):
                    tbl.append(nxt)
                    i += 1
                    continue
                break
            stem_parts.append("\n".join(tbl))
            continue
        buf.append(line)
        i += 1
    if buf:
        stem_parts.append(" ".join(x.strip() for x in buf if x.strip()))
    q = "\n".join(stem_parts)
    q = re.sub(r" +", " ", q)
    q = q.replace(" \n ", "\n").strip()

    options_lines = lines[first_opt :]
    opt_text = "\n".join(options_lines)
    opts = []
    for mm in OPTION_START.finditer(opt_text):
        letter = mm.group(1)
        rest = mm.group(2)
        start = mm.end()
        next_m = OPTION_START.search(opt_text, pos=start)
        chunk_end = next_m.start() if next_m else len(opt_text)
        chunk = opt_text[start:chunk_end]
        full = (rest + chunk).strip()
        full = re.sub(r"\s+", " ", full).strip()
        opts.append({"l": letter, "t": full})
    if not opts:
        raise ValueError(f"Q{n}: failed to parse options")
    return {"n": n, "stem": q, "opts": opts}


def normalize_critique_body(s: str) -> str:
    s = s.strip()
    lines = []
    for ln in s.splitlines():
        t = ln.strip()
        if re.match(r"^--\s*\d+\s+of\s+\d+\s+--$", t):
            continue
        if t.startswith("2025 ITE RATIONALE BOOK"):
            continue
        lines.append(ln)
    s = "\n".join(lines)
    # References as its own paragraph (matches PDF structure)
    s = re.sub(r"\s*References\s+", "\n\nReferences\n\n", s, count=1)
    # Paragraphs: blank line separates remaining blocks
    parts = re.split(r"\n\s*\n", s)
    merged = []
    for para in parts:
        plines = [x.strip() for x in para.splitlines() if x.strip()]
        merged.append(" ".join(plines))
    return "\n\n".join(merged).strip()


def parse_critiques(text: str) -> dict[int, tuple[str, str]]:
    text = fix_critique_pdf_artifacts(text)
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"^.*?(?=Item\s+1\s)", "", text, flags=re.DOTALL)
    items = re.split(r"(?m)^Item\s+(\d+)\s*$", text)
    out = {}
    i = 1
    while i < len(items):
        try:
            num = int(items[i])
        except ValueError:
            i += 1
            continue
        body = items[i + 1] if i + 1 < len(items) else ""
        i += 2
        body = body.strip()
        m = re.match(r"^ANSWER:\s*([A-E])\s*\n(.*)$", body, re.DOTALL | re.IGNORECASE)
        if not m:
            continue
        letter = m.group(1).upper()
        rest = normalize_critique_body(m.group(2))
        rest = re.sub(r"\n--\s*\d+\s+of\s+\d+\s+--\s*$", "", rest)
        out[num] = (letter, rest)
    return out


def main():
    q_raw = pdf_text(Q_PDF)
    c_raw = pdf_text(C_PDF)
    Path("tools/questions_extracted.txt").write_text(q_raw, encoding="utf-8")
    Path("tools/critique_extracted.txt").write_text(c_raw, encoding="utf-8")

    q_clean = clean_questions_raw(q_raw)
    blocks = split_questions(q_clean)
    if len(blocks) != 200:
        print(f"WARNING: expected 200 question blocks, got {len(blocks)}", file=sys.stderr)
    crit = parse_critiques(c_raw)
    if len(crit) != 200:
        print(f"WARNING: expected 200 critiques, got {len(crit)}", file=sys.stderr)

    exam = []
    for n, block in blocks:
        if n > 200:
            continue
        pq = parse_question_block(n, block)
        if n not in crit:
            print(f"MISSING critique for item {n}", file=sys.stderr)
            letter, etext = "?", "MISSING CRITIQUE"
        else:
            letter, etext = crit[n]
        exam.append(
            {
                "n": pq["n"],
                "q": pq["stem"],
                "o": pq["opts"],
                "a": letter,
                "e": etext,
            }
        )

    exam.sort(key=lambda x: x["n"])
    OUT_JSON.write_text(json.dumps(exam, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(exam)} items to {OUT_JSON}")


if __name__ == "__main__":
    main()
