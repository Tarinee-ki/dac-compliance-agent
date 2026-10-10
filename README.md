# AI-Driven Regulatory Compliance Extraction Pipeline

An automated, dual-agent AI pipeline designed to parse complex EU legislation and extract mandatory compliance obligations into a structured, verifiable database. 

This project specifically processes the **EU Carbon Removal Certification Framework (Regulation (EU) 2024/3012)**, transforming unstructured legal text into a strict `compliance_register.csv` suitable for regulatory technology, audit trails, and compliance engineering.

## Architecture & Dual-Agent System

This system uses a strict "Maker/Checker" architecture to guarantee data fidelity and completely eliminate AI hallucinations:

* **The Extractor Agent:** Parses raw text extracted from the PDF and maps imperative legal commands ('shall', 'must') into a structured JSON schema using Pydantic. It captures the operational rule, categorises it, and extracts the *exact verbatim quote* that supports it.
* **The Auditor Agent:** Acts as an independent compliance reviewer. It evaluates the Extractor's output by comparing the generated rule strictly against the captured verbatim quote. If a rule contains unsupported conditions, assumptions, or truncates a vital mathematical formula, the Auditor instantly rejects it.

Only rules that pass the Auditor's strict boolean validation are exported to the final CSV register.

## Technical Stack

* **Language:** Python 3
* **PDF Parsing:** `PyMuPDF` (capable of handling dense, multi-column EU journal formats)
* **LLM Engine:** Anthropic Claude Haiku 5.5
* **Validation & Structuring:** `instructor` and `Pydantic`

## Sample Output (Audit-Verified Data)

The pipeline successfully processes highly complex legal clauses, including multi-variable quantification formulas and strict eligibility criteria. Below is a sample of the automated extraction:

| Rule ID | Category | Extracted Rule | Verbatim Source Quote (Audit Trail) |
| :--- | :--- | :--- | :--- |
| **CRCF-Art4-2-2** | Quantification | The temporary net carbon removal benefit shall be quantified as CRbaseline – CRtotal – GHGassociated, and must be greater than 0... | *"(a) temporary net carbon removal benefit = CRbaseline – CRtotal – GHGassociated > 0, where: (i) CRbaseline is the amount of carbon removals under the baseline; (ii) CRtotal is the total amount of carbon removals of the activity..."* |
| **CRCF-Art5-1** | Additionality | Any activity shall be additional and shall meet both criteria: (a) it goes beyond Union and national statutory requirements... (b) the incentive effect is needed for financial viability. | *"Any activity shall be additional. To that end, it shall meet both of the following criteria: (a) it goes beyond Union and national statutory requirements at the level of an individual operator..."* |
| **CRCF-Art7-1** | Sustainability | An activity shall do no significant harm to the environment, and may generate co-benefits for one or more of the listed sustainability objectives. | *"An activity shall do no significant harm to the environment and may generate co-benefits for one or more of the following sustainability objectives: (a) climate change mitigation..."* |

## How to Run the Pipeline

**Step 1: Clone the repository and navigate to the project directory:**
```bash
git clone https://github.com/yourusername/dac-compliance-agent.git
cd dac-compliance-agent
```

**Step 2: Set up a virtual environment and install dependencies:**
```bash
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
pip install -r requirements.txt
```

**Step 3: Configure API Keys:**
Create a `.env` file in the root directory and add your Anthropic API key:
```env
ANTHROPIC_API_KEY=your_api_key_here
```

**Step 4: Execute the extraction:**
```bash
python main.py
```
The terminal will output the real-time agent audit logs, and the verified rules will be saved to `compliance_register.csv`.