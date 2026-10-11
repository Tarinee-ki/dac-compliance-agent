import csv
import re
import sys
import unicodedata
from typing import Literal
 
try:
    import pymupdf as fitz          # newer PyMuPDF
except ImportError:
    import fitz                     # older PyMuPDF
import instructor
from anthropic import Anthropic
from dotenv import load_dotenv
from pydantic import BaseModel, Field
 
load_dotenv()
 
PDF_PATH = "crcf_regulation.pdf"
DOC_ID = "CRCF"
ARTICLES = [4, 5, 6, 7]
# NOTE: Instructor forces a tool call. Haiku 5.5 accepts that. If you switch to Sonnet 5.5 and get a 400 error
# about tool_choice, that is the reason (use an Instructor mode without forced tool choice).
EXTRACT_MODEL = "claude-haiku-5-5"
AUDIT_MODEL = "claude-haiku-5-5"
 
 
# ----------------------------------------------------------------------------- schemas
class ExtractedRule(BaseModel):
    compliance_category: str = Field(description="Short topic label, e.g. Quantification, Additionality, Storage, Liability, Sustainability")
    extracted_rule: str = Field(description=(
        "ONE plain-English sentence stating ONE requirement. Use only meaning that is in the quote. "
        "Do not add words such as 'only' or 'must' and do not add conditions that the text does not contain."))
    obligation_type: Literal["shall", "shall_not", "should", "may"]
    verbatim_quote: str = Field(description=(
        "Text copied EXACTLY from the paragraph, character for character. If the requirement is a sub-point "
        "(a), (b)..., write the lead-in sentence, then ' [...] ', then the sub-point. Never paraphrase."))
 
 
class ExtractedRules(BaseModel):
    rules: list[ExtractedRule]
 
 
class AuditResult(BaseModel):
    is_valid: bool = Field(description="True only if the rule is fully supported by the source paragraph and quote.")
    reasoning: str = Field(description="One sentence explaining the decision.")
 
 
# ----------------------------------------------------------------------------- text helpers
_TRANSLATE = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"',
                            "–": "-", "—": "-", "−": "-", " ": " ", "​": ""})
 
 
def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_TRANSLATE)
    return re.sub(r"\s+", " ", text).strip()
 
 
def quote_in_source(quote: str, source: str) -> bool:
    """Every part of the quote (parts are separated by [...]) must appear in the source paragraph."""
    parts = [p for p in re.split(r"\[\.\.\.\]|\[…\]", quote) if normalize(p)]
    src = normalize(source)
    return bool(parts) and all(normalize(p) in src for p in parts)
 
 
# ----------------------------------------------------------------------------- PDF -> paragraphs
_FURNITURE = [re.compile(r"^EN$"), re.compile(r"^OJ L, \d{1,2}\.\d{1,2}\.\d{4}$"),
              re.compile(r"^\d+/\d+$"), re.compile(r"^ELI: https?://\S+$")]
_ARTICLE = re.compile(r"^Article (\d+)$")
_PARA = re.compile(r"^(\d{1,2})\.(?:\s+(\S.*))?$")                 # "1." alone on a line, or "1.  text"
_SUBPOINT = re.compile(r"^\((?:[a-z]{1,2}|[ivx]{1,5}|\d{1,2})\)(?:\s|$)")
 
 
def read_lines(pdf_path):
    """[(line, pdf_page)] without the page headers/footers that cut through sentences."""
    out = []
    with fitz.open(pdf_path) as doc:
        for i, page in enumerate(doc, start=1):
            for raw in page.get_text("text").splitlines():
                line = raw.strip()
                if line and not any(p.match(line) for p in _FURNITURE):
                    out.append((line, i))
    return out
 
 
def join_lines(lines):
    parts = []
    for ln in lines:
        if parts and _SUBPOINT.match(ln):
            parts.append("\n" + ln)
        elif parts and not parts[-1].endswith("\n"):
            parts.append(" " + ln)
        else:
            parts.append(ln)
    return "".join(parts).strip()
 
 
def parse_paragraphs(pdf_path, articles):
    lines = read_lines(pdf_path)
    start = next(i for i, (t, _) in enumerate(lines) if t == "CHAPTER 1")
    end = next(i for i, (t, _) in enumerate(lines) if i > start and t.startswith("ANNEX"))
    heads, expected = [], 1
    for i in range(start, end):                                    # headings must appear in order 1,2,3...
        m = _ARTICLE.match(lines[i][0])
        if m and int(m.group(1)) == expected:
            heads.append((expected, i))
            expected += 1
    chunks = []
    for k, (art, idx) in enumerate(heads):
        if art not in articles:
            continue
        stop = heads[k + 1][1] if k + 1 < len(heads) else end
        while stop > idx and lines[stop - 1][0].startswith("CHAPTER"):          # drop chapter title lines
            stop -= 1
        while stop - 2 > idx and lines[stop - 2][0].startswith("CHAPTER"):
            stop -= 2
        title, body = lines[idx + 1][0], lines[idx + 2:stop]
        paras, nxt = [], 1
        for text, page in body:
            m = _PARA.match(text)
            if m and int(m.group(1)) == nxt:                       # numbers must run 1,2,3...
                paras.append((nxt, [(m.group(2), page)] if m.group(2) else []))
                nxt += 1
            elif paras:
                paras[-1][1].append((text, page))
        for num, plines in paras:
            if plines:
                p0, p1 = plines[0][1], plines[-1][1]
                chunks.append({"chunk_id": f"Art{art}({num})", "article": art, "title": title, "paragraph": num,
                               "text": join_lines([t for t, _ in plines]),
                               "pages": str(p0) if p0 == p1 else f"{p0}-{p1}"})
    return chunks
 
 
# ----------------------------------------------------------------------------- AI steps
def extract(client, chunk):
    prompt = f"""You are reading ONE paragraph of an official EU regulation: Article {chunk['article']}({chunk['paragraph']}) "{chunk['title']}".
 
List every distinct requirement in it: obligations (shall), prohibitions (shall not), recommendations (should) and permissions (may).
 
Rules:
- One requirement per entry. Do not merge two requirements into one entry.
- verbatim_quote must be copied exactly from the paragraph, never paraphrased. For a sub-point (a), (b)..., start the quote with the lead-in sentence, then ' [...] ', then the sub-point, so the quote shows who must do what.
- extracted_rule uses only what the quote says. Never add words like 'only' or 'must'.
- Ignore definitions, formulas without an obligation, and background text.
- If the paragraph contains no requirement, return an empty list.
 
<paragraph>
{chunk['text']}
</paragraph>"""
    return client.messages.create(model=EXTRACT_MODEL, max_tokens=4096,
                                  messages=[{"role": "user", "content": prompt}],
                                  response_model=ExtractedRules, max_retries=2)
 
 
def audit(client, chunk, rule):
    prompt = f"""You are a strict, independent auditor. Check whether an extracted rule is fully supported by the source text.
 
Reject (is_valid = false) if the rule adds, drops or changes meaning compared with the source, for example:
'only', 'must' or extra conditions that the text does not contain, 'may' turned into 'shall' (or the reverse),
a wrong subject or scope. Also reject if the quote does not state the requirement.
When in doubt, reject.
 
<source_paragraph reference="Article {chunk['article']}({chunk['paragraph']})">
{chunk['text']}
</source_paragraph>
 
Extracted rule: {rule.extracted_rule}
Obligation type: {rule.obligation_type}
Quote: {rule.verbatim_quote}"""
    return client.messages.create(model=AUDIT_MODEL, max_tokens=500,
                                  messages=[{"role": "user", "content": prompt}],
                                  response_model=AuditResult, max_retries=2)
 
 
def process(client, chunks):
    accepted, rejected = [], []
    for chunk in chunks:
        print(f"Processing {chunk['chunk_id']} (page {chunk['pages']})...")
        try:
            result = extract(client, chunk)
        except Exception as e:                                       # one failure must not stop everything
            print(f"   [!] extraction failed: {e}")
            rejected.append({"rule_id": f"{DOC_ID}-{chunk['chunk_id']}-ERR", "article": chunk["article"],
                             "paragraph": chunk["paragraph"], "page_number": chunk["pages"],
                             "status": "extraction_failed", "audit_reasoning": repr(e)})
            continue
        for n, rule in enumerate(result.rules, start=1):
            row = {"rule_id": f"{DOC_ID}-{chunk['chunk_id']}-{n:02d}",       # ID made by code, never by the AI
                   "article": chunk["article"], "paragraph": chunk["paragraph"], "page_number": chunk["pages"],
                   "compliance_category": rule.compliance_category, "obligation_type": rule.obligation_type,
                   "extracted_rule": rule.extracted_rule, "verbatim_quote": rule.verbatim_quote}
            if not quote_in_source(rule.verbatim_quote, chunk["text"]):     # code check, free and exact
                row.update(status="rejected_quote_not_found", audit_reasoning="Quote not found in the source paragraph.")
                rejected.append(row)
                print(f"   [!] {row['rule_id']}: quote not found in source, rejected")
                continue
            try:
                verdict = audit(client, chunk, rule)
            except Exception as e:
                row.update(status="needs_review", audit_reasoning=f"Auditor call failed: {e!r}")
                rejected.append(row)
                continue
            row["audit_reasoning"] = verdict.reasoning
            if verdict.is_valid:
                row["status"] = "passed_checks"
                accepted.append(row)
            else:
                row["status"] = "rejected_by_auditor"
                rejected.append(row)
                print(f"   [!] {row['rule_id']} rejected by auditor: {verdict.reasoning}")
    return accepted, rejected
 
 
FIELDS = ["rule_id", "article", "paragraph", "page_number", "compliance_category", "obligation_type",
          "extracted_rule", "verbatim_quote", "status", "audit_reasoning"]
 
 
def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:       # utf-8-sig: Excel shows dashes correctly
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
 
 
def main(client=None, pdf_path=PDF_PATH, limit=None):
    import os
    if not os.path.exists(pdf_path):
        print(f"Error: {pdf_path} not found in the current folder.")
        return
    print("Parsing document...")
    chunks = parse_paragraphs(pdf_path, ARTICLES)
    if limit:
        chunks = chunks[:limit]
    print(f"{len(chunks)} paragraphs to process.")
    client = client or instructor.from_anthropic(Anthropic())
    accepted, rejected = process(client, chunks)
    write_csv("compliance_register.csv", accepted)
    write_csv("rejected_rules.csv", rejected)
    print(f"\n{len(accepted)} rules passed the checks -> compliance_register.csv")
    print(f"{len(rejected)} rules rejected or failed -> rejected_rules.csv (read the reasons!)")
    print("These are machine-checked, NOT expert-approved. A human must review before use.")
 
 
if __name__ == "__main__":
    main(limit=int(sys.argv[1]) if len(sys.argv) > 1 else None)
 