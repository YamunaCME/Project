"""
Medical Prescription and Clinical Document Extraction Service.

Extracts structured prescription fields (Patient, Doctor, Date, Medications)
from OCR transcripts for human review.

Safety rules strictly enforced:
- Preserves raw recognized text alongside normalized fields.
- Flags uncertain or ambiguous medications/dosages for human verification ("Needs human review").
- Never hallucinates, infers, or automatically corrects unfamiliar medicine names.
- Never generates clinical advice or medical recommendations.
"""

import re
from typing import Dict, Any, List


class MedicalPrescriptionExtractor:
    # Common medical dosage forms and frequency indicators
    DOSAGE_PATTERN = re.compile(
        r'\b(\d+(?:\.\d+)?\s*(?:mg|g|mcg|ml|iu|tablets?|tabs?|caps?|capsules?|drops?|pills?))\b',
        re.IGNORECASE
    )
    FREQUENCY_PATTERN = re.compile(
        r'\b(OD|BD|BID|TDS|TID|QID|Q4H|Q6H|Q8H|HS|SOS|PRN|once\s+daily|twice\s+daily|thrice\s+daily|[01]-[01]-[01](?:-[01])?)\b',
        re.IGNORECASE
    )
    ROUTE_PATTERN = re.compile(
        r'\b(oral|p\.o\.|po|topical|i\.v\.|iv|i\.m\.|im|sublingual|inhalation|ophthalmic|nasal)\b',
        re.IGNORECASE
    )
    DURATION_PATTERN = re.compile(
        r'\b(\d+\s*(?:days?|weeks?|months?|d|w|m)|for\s+\d+\s+days?)\b',
        re.IGNORECASE
    )
    INSTRUCTION_PATTERN = re.compile(
        r'\b(after\s+food|before\s+food|with\s+food|empty\s+stomach|after\s+meals?|before\s+meals?|at\s+bedtime|pc|ac)\b',
        re.IGNORECASE
    )
    DATE_PATTERN = re.compile(
        r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})\b',
        re.IGNORECASE
    )

    @classmethod
    def extract(cls, transcript: str, confidence_details: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Extracts structured prescription data and flags uncertain fields.
        """
        if not transcript or not transcript.strip():
            return {
                'patient_name': None,
                'doctor_name': None,
                'date': None,
                'medications': [],
                'instructions': '',
                'flagged_count': 0,
                'status': 'empty',
                'disclaimer': 'Automated extraction for human review only. Not for clinical decision-making.'
            }

        lines = [line.strip() for line in transcript.split('\n') if line.strip()]

        patient_name = None
        doctor_name = None
        prescription_date = None
        medications: List[Dict[str, Any]] = []
        general_instructions: List[str] = []
        flagged_count = 0

        # Scan for metadata
        for line in lines:
            # Prescriber / Doctor detection
            if not doctor_name:
                doc_match = re.search(r'\b(?:Dr\.?|Doctor|Physician)\s+([A-Za-z\.\s]+?)(?:,\s*[A-Z]{2,}|MBBS|MD|MS|$)', line, re.IGNORECASE)
                if doc_match:
                    doctor_name = f"Dr. {doc_match.group(1).strip()}"

            # Patient Name detection
            if not patient_name:
                pt_match = re.search(r'\b(?:Patient|Pt\.?|Name|Patient\s+Name)\s*[:\-]?\s*([A-Za-z\s]{2,30})\b', line, re.IGNORECASE)
                if pt_match:
                    name_candidate = pt_match.group(1).strip()
                    # Exclude common non-name tokens
                    if name_candidate.lower() not in ('age', 'sex', 'gender', 'date', 'address', 'male', 'female'):
                        patient_name = name_candidate

            # Date detection
            if not prescription_date:
                dt_match = cls.DATE_PATTERN.search(line)
                if dt_match:
                    prescription_date = dt_match.group(1)

        # Medication line extraction
        # Look for lines containing Rx, numbers followed by drug name, or dosage indicators
        for idx, line in enumerate(lines):
            # Skip lines that are purely doctor or patient headers
            if doctor_name and doctor_name.lower() in line.lower():
                continue
            if patient_name and patient_name.lower() in line.lower():
                continue

            dosage_match = cls.DOSAGE_PATTERN.search(line)
            freq_match = cls.FREQUENCY_PATTERN.search(line)
            route_match = cls.ROUTE_PATTERN.search(line)
            dur_match = cls.DURATION_PATTERN.search(line)
            inst_match = cls.INSTRUCTION_PATTERN.search(line)

            # Check if this line looks like a prescription item
            is_med_line = False
            raw_drug_candidate = line

            if line.startswith(('1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.', '•', '-', '*')):
                is_med_line = True
                raw_drug_candidate = re.sub(r'^[\d\.\-\*•]+\s*', '', line)
            elif dosage_match or freq_match:
                is_med_line = True

            if is_med_line:
                # Isolate drug name candidate by stripping dosage, freq, duration
                name_clean = raw_drug_candidate
                if dosage_match:
                    name_clean = name_clean.replace(dosage_match.group(0), ' ')
                if freq_match:
                    name_clean = name_clean.replace(freq_match.group(0), ' ')
                if dur_match:
                    name_clean = name_clean.replace(dur_match.group(0), ' ')
                if route_match:
                    name_clean = name_clean.replace(route_match.group(0), ' ')
                if inst_match:
                    name_clean = name_clean.replace(inst_match.group(0), ' ')

                name_clean = re.sub(r'\s+', ' ', name_clean).strip(' :-–')

                # Verification flags
                needs_review = False
                review_reasons = []

                if len(name_clean) < 3:
                    needs_review = True
                    review_reasons.append("Short or unreadable medicine name")
                elif re.search(r'[^a-zA-Z0-9\s\.\-]', name_clean):
                    needs_review = True
                    review_reasons.append("Special characters detected in medicine name")

                if not dosage_match:
                    needs_review = True
                    review_reasons.append("Dosage strength not detected")

                if not freq_match:
                    needs_review = True
                    review_reasons.append("Frequency (OD/BD/TID) uncertain")

                if needs_review:
                    flagged_count += 1

                medications.append({
                    'item_number': len(medications) + 1,
                    'raw_line': line,
                    'medicine_name': name_clean if name_clean else "(Unclear medicine name)",
                    'dosage': dosage_match.group(1) if dosage_match else "Unspecified / Needs review",
                    'frequency': freq_match.group(1).upper() if freq_match else "Unspecified / Needs review",
                    'route': route_match.group(1).upper() if route_match else "Oral (typical / unstated)",
                    'duration': dur_match.group(1) if dur_match else "Unspecified",
                    'instructions': inst_match.group(1) if inst_match else "",
                    'needs_review': needs_review,
                    'review_reasons': review_reasons,
                })
            elif inst_match:
                general_instructions.append(line)

        return {
            'patient_name': patient_name or "Not detected (Needs human review)",
            'doctor_name': doctor_name or "Not detected",
            'date': prescription_date or "Not detected",
            'medications': medications,
            'instructions': " \n".join(general_instructions),
            'flagged_count': flagged_count,
            'total_items': len(medications),
            'status': 'review_ready',
            'disclaimer': (
                "IMPORTANT MEDICAL NOTICE: This automated extraction is an assistive preview only. "
                "Always verify medicine names, dosages, and instructions against the original prescription "
                "before dispensing or clinical use."
            )
        }
