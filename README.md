# AI-Assisted Regulatory Compliance Extraction Pipeline

A prototype that reads an official EU legal text, extracts the compliance obligations it contains into a structured register, and checks every item against the source before it reaches a human reviewer.

It processes **Regulation (EU) 2024/3012** (EU framework for certifying permanent carbon removals, carbon farming and carbon storage in products; Official Journal L, 6.12.2024), **Articles 4–7** ("Quality criteria": quantification, additionality, storage/monitoring/liability, sustainability). That is 25 numbered paragraphs on PDF pages 14–19.

> **Status: prototype.** Output is machine-checked, **not expert-approved**. Every row needs review by a compliance expert before use.

## Architecture: Maker / Checker plus code checks

Two AI calls with exact code checks between them:

1. **Parser (code):** PDF to numbered legal paragraphs (Article 4(7), page 16, ...). Page headers and footers that cut through sentences are removed.
2. **Extractor agent (AI):** one call per paragraph. It returns each requirement as a Pydantic object: category, obligation type (shall / may / ...), a plain-English rule, and the **verbatim quote** that supports it.
3. **Quote check (code):** every quote must appear word for word in that paragraph. If not, the rule is rejected. A quote cannot be invented.
4. **Code flags (code):** a rule is sent to review if it uses "must", "only", "always", "never" or "exclusively" when the source paragraph does not, or if its obligation type ("shall", "may") does not appear in its quote.
5. **Auditor agent (AI):** a second call that sees the **source paragraph**, the rule and the quote, and rejects rules that change the meaning, drop or add a limit ("only", "unless", "where feasible"), or state something the quote does not contain.

Rule IDs are made by the code from the document structure (`CRCF-Art4(9)-03` = Article 4, paragraph 9, rule 3), never by the AI.

Passing rules go to `compliance_register.csv`. Everything else goes to `rules_for_review.csv` with the reason in the `status` column, so nothing disappears silently.

## Technical stack

* **Language:** Python 3
* **PDF text extraction:** `PyMuPDF`, plus own code to remove the Official Journal's repeated headers and footers and to split into articles and numbered paragraphs
* **LLM:** Anthropic Claude Haiku 5.5 (extractor and auditor)
* **Structured output:** `instructor` and `Pydantic`

## Results (run 2, current version)

54 candidate rules from 25 paragraphs: **45 passed all checks, 9 need review** (1 code flag, 5 rejected by the auditor, 3 quote not found).

* All 45 passed quotes appear word for word in their paragraph (enforced by the script).
* No passed rule uses "must" in place of the text's "shall".
* Against a **draft** answer key of 44 requirements (written with AI assistance, **not yet reviewed by a person**), 40 are covered by the passed file and all 44 are covered when the review file is included. Coverage is based on quote overlap and was measured with a separate script that is not in this repository, so treat it as indicative.

How the script improved:

| Version | Passed | Review/rejected | Main finding |
|---|---|---|---|
| Original (pages as chunks, AI-made IDs, auditor sees only rule + quote) | 48 | no review file | Quotes were verbatim, but one duplicate ID, three rules labelled Article 3 that are Article 4, a quote starting mid-sentence, and 13 rows from outside Articles 4–7 |
| Run 1 (paragraph chunks, code IDs, code quote check, auditor sees source) | 47 | 13 | Four "must" rules and one definition turned into an obligation still passed the auditor |
| **Run 2 (this version)** | **45** | **9** | Code flags catch both problems; no "must" in passed rules |

## Sample output (real rows, run 2)

**Passed (`compliance_register.csv`)**

| Rule ID | Category | Extracted rule | Verbatim source quote |
| :--- | :--- | :--- | :--- |
| **CRCF-Art4(9)-03** | Quantification | The updated standardised baseline shall apply only to an activity for which the activity period starts after the entry into force of the applicable certification methodology. | *"The updated standardised baseline shall apply only to an activity for which the activity period starts after the entry into force of the applicable certification methodology."* |
| **CRCF-Art4(11)-01** | Quantification | The activity-specific baselines shall be periodically updated at the beginning of each activity period, unless otherwise stated in the applicable certification methodologies set out in the delegated acts adopted pursuant to Article 8. | *"The activity-specific baselines shall be periodically updated, at the beginning of each activity period, unless otherwise stated in the applicable certification methodologies set out in the delegated acts adopted pursuant to Article 8."* |
| **CRCF-Art6(3)-01** | Monitoring | The monitoring rules referred to in paragraph 2, point (a), shall, for permanent carbon removals, be consistent with the rules set out in Articles 13 to 16 of Directive 2009/31/EC. | *"The monitoring rules referred to in paragraph 2, point (a), shall: [...] (a) for permanent carbon removals, be consistent with the rules set out in Articles 13 to 16 of Directive 2009/31/EC;"* |
| **CRCF-Art7(2)-01** | Sustainability | A carbon farming activity shall at least generate co-benefits for the sustainability objective referred to in paragraph 1, point (f). | *"A carbon farming activity shall at least generate co-benefits for the sustainability objective referred to in paragraph 1, point (f)."* |

The `[...]` marks text skipped between a lead-in sentence and a sub-point, so the quote still shows who must do what.

**Sent to review (`rules_for_review.csv`)**

| Rule ID | Status | Reason |
| :--- | :--- | :--- |
| **CRCF-Art4(1)-03** | needs_review | Code check: the obligation type is "shall" but the quote contains no such modal verb (the source is a definition of GHGassociated, not an obligation) |
| **CRCF-Art5(1)-02** | rejected_by_auditor | The rule says the activity must meet "both" criteria but states only criterion (a); criterion (b) is missing |

## Known limitations

* **Not complete.** Four requirements from the draft key are missing from the passed file: the two cumulative additionality criteria in Article 5(1), Article 6(2)(b) and Article 7(3)(c). They are in `rules_for_review.csv`.
* **Coverage can be overstated.** It is measured on quotes, not rule text. Some passed rules cover only half of a sentence (for example Article 4(8)), and two permissions ("may" in Articles 6(4)(c) and 7(1)) are in the review file.
* **The auditor is not reliable on its own.** It is the same small model as the extractor and is inconsistent about rules that cover only part of a paragraph. The code checks exist for that reason.
* **No precision figure.** Whether each passed rule is correct was not measured. Only the quote and the flagged words are checked exactly.
* **The answer key is a draft** and has not been reviewed by a person.
* **One document, one version.** The text is the original Official Journal publication. Corrections, consolidated versions and the detailed methodologies for Direct Air Capture (delegated acts under Article 8) are not covered.
* **Cross-references** ("Article 8", "paragraph 2, point (a)") are not resolved.
* **Layout-specific parser.** It assumes this document's structure. Scanned PDFs are not supported.
* **Small scale.** Only 25 paragraphs; token use and cost were not recorded.

## How to run the pipeline

**Step 1: Clone the repository and open the project folder** (replace the URL with your own):
```bash
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>
```

**Step 2: Create a virtual environment and install the dependencies:**
```bash
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
pip install -r requirements.txt
```

**Step 3: Add your Anthropic API key.** Create a `.env` file in the project folder (never commit it):
```env
ANTHROPIC_API_KEY=your_api_key_here
```

**Step 4: Run it.** `crcf_regulation.pdf` must be in the same folder.
```bash
python main.py 3      # first 3 paragraphs only (cheap test)
python main.py        # all 25 paragraphs
```
The terminal shows each paragraph and every rejection with its reason. Results are written to `compliance_register.csv` and `rules_for_review.csv`.

## Next steps

1. Have the draft answer key reviewed by a person, then report recall and precision.
2. Insert a missing `[...]` marker automatically when a quote skips a sub-point (prototyped on stored outputs, not run).
3. Treat sub-points under "both of the following" as one rule.
4. Try a different or stronger model for the auditor and compare.
5. Process the whole regulation and the CO2 storage directive; log token use and cost.
6. Resolve cross-references and keep source documents in a versioned library (for example SharePoint) with metadata and a file hash.

---
*Built with AI assistance (Claude).*