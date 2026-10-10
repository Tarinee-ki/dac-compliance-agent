import os
import fitz  # PyMuPDF
import csv
import instructor
from anthropic import Anthropic
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load the API key from your .env file
load_dotenv()

# Initialise the Anthropic client wrapped with Instructor for guaranteed JSON
client = instructor.from_anthropic(Anthropic())

class ComplianceRule(BaseModel):
    rule_id: str = Field(description="Generate a unique ID, e.g., CRCF-Art4-1")
    compliance_category: str = Field(description="e.g., Quantification, Additionality, Storage")
    extracted_rule: str = Field(description="The engineering or reporting obligation")
    verbatim_quote: str = Field(description="The exact, unedited source text snippet")
    page_number: int = Field(default=0)
    
class ExtractedRules(BaseModel):
    rules: list[ComplianceRule]
    
class AuditResult(BaseModel):
    is_valid: bool = Field(description="True if the extracted rule is strictly supported by the quote, False otherwise.")
    reasoning: str = Field(description="One sentence explaining the validation decision.")

def extract_pdf_pages(pdf_path, start_page=14, end_page=19):
    """
    Extracts text from specific pages covering the core engineering quality criteria.
    """
    doc = fitz.open(pdf_path)
    pages = []
    
    # PyMuPDF uses zero-based indexing for pages
    for page_num in range(start_page - 1, end_page):
        text = doc[page_num].get_text("text")
        if text.strip():
            pages.append({
                "page_number": page_num + 1, 
                "text": text.strip()
            })
    return pages

def extract_and_audit(pages):
    verified_rules = []
    
    for page in pages:
        print(f"Processing Page {page['page_number']}...")
        
        extraction_prompt = f"""
        Extract all mandatory compliance obligations from the text below. 
        Ignore background context. Focus on imperative verbs ('shall', 'must').
        Ensure verbatim quotes are complete and include all relevant sub-clauses, bullet points, and mathematical formulas required to support the rule.
        
        <document_text>
        {page['text']}
        </document_text>
        """
        
        try:
            # 1. THE EXTRACTOR AGENT
            extraction = client.messages.create(
                model="claude-haiku-5-5",
                max_tokens=8192,
                messages=[{"role": "user", "content": extraction_prompt}],
                response_model=ExtractedRules
            )
            
            # 2. THE AUDITOR AGENT
            for rule in extraction.rules:
                rule.page_number = page['page_number']
                
                audit_prompt = f"""
                Verify if this extracted rule is strictly supported by the source quote.
                Ensure no extra engineering requirements were hallucinated.
                
                Rule: {rule.extracted_rule}
                Source Quote: {rule.verbatim_quote}
                """
                
                audit = client.messages.create(
                    model="claude-haiku-5-5",
                    max_tokens=500,
                    messages=[{"role": "user", "content": audit_prompt}],
                    response_model=AuditResult
                )
                
                if audit.is_valid:
                    verified_rules.append(rule)
                else:
                    print(f"   [!] Hallucination caught and discarded: {rule.rule_id}")
                    print(f"       Reason: {audit.reasoning}")
                    
        except Exception as e:
            print(f"Error processing page {page['page_number']}: {e}")
                
    return verified_rules

def main():
    pdf_path = "crcf_regulation.pdf"
    
    if not os.path.exists(pdf_path):
        print(f"Error: {pdf_path} not found in the current folder.")
        return
        
    print("Parsing document...")
    pages = extract_pdf_pages(pdf_path)
    
    print("Running AI Extractor and Auditor...")
    final_rules = extract_and_audit(pages)
    
    print(f"Exporting {len(final_rules)} audit-verified rules to CSV...")
    
    # Save the verified data to a CSV file
    if final_rules:
        with open("compliance_register.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=ComplianceRule.model_fields.keys())
            writer.writeheader()
            for rule in final_rules:
                writer.writerow(rule.model_dump())
        print("Done. Check your folder for compliance_register.csv.")
    else:
        print("No valid rules were extracted.")
            
if __name__ == "__main__":
    main()