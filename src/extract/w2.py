from __future__ import annotations

import re

from src.extract.text_utils import extract_amount_after_label, normalize_extracted_text, parse_amount_token
from src.models import W2Data


def parse_w2_text(text: str) -> W2Data:
    data = W2Data()
    text = normalize_extracted_text(text)

    year_match = re.search(r"\b(20\d{2})\b", text)
    if year_match:
        data.year = int(year_match.group(1))

    ein_match = re.search(r"\b(\d{2}-\d{7})\b", text)
    if ein_match:
        data.employer_ein = ein_match.group(1)

    employer_match = re.search(r"Employer(?:'s)?\s+name[^\n:]*[:\s]+(.+)", text, re.IGNORECASE)
    if employer_match:
        data.employer_name = employer_match.group(1).strip()[:120]

    data.box1_wages = extract_amount_after_label(r"(?:Box\s*[1Il]|1\.?\s*Wages)", text)
    data.box2_fed_withholding = extract_amount_after_label(r"(?:2\.?\s*Federa[l1](?:\s+income\s+tax)?\s+with(?:held|holding)?|Box\s*2\s+Federa[l1](?:\s+income\s+tax)?\s+with(?:held|holding)?)", text)
    data.box3_ss_wages = extract_amount_after_label(r"(?:Box\s*3|3\.?\s*Social\s*security\s*wages)", text)
    data.box4_ss_tax = extract_amount_after_label(r"(?:Box\s*4|4\.?\s*Social\s*security\s*tax)", text)
    data.box5_medicare_wages = extract_amount_after_label(r"(?:Box\s*5|5\.?\s*Medicare\s*wages)", text)
    data.box6_medicare_tax = extract_amount_after_label(r"(?:Box\s*6|6\.?\s*Medicare\s*tax)", text)
    data.box16_state_wages = extract_amount_after_label(r"(?:Box\s*16|16\.?\s*State\s*wages)", text)
    data.box17_state_tax = extract_amount_after_label(r"(?:Box\s*17|17\.?\s*State\s*income\s*tax)", text)

    for code, amount in re.findall(r"12\s*([A-Z])\s*(\(?-?\$?[\d,]+(?:\.\d{2})?\)?)", text, flags=re.IGNORECASE):
        value = parse_amount_token(amount)
        if value is not None:
            data.box12[code.upper()] = value

    states = re.findall(r"\b([A-Z]{2})\b", text)
    data.states = sorted({s for s in states if s in {"AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","IA","ID","IL","IN","KS","KY","LA","MA","MD","ME","MI","MN","MO","MS","MT","NC","ND","NE","NH","NJ","NM","NV","NY","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VA","VT","WA","WI","WV","WY"}})

    populated = sum(
        1
        for v in [
            data.employer_name,
            data.employer_ein,
            data.box1_wages,
            data.box2_fed_withholding,
            data.box3_ss_wages,
            data.box4_ss_tax,
            data.box5_medicare_wages,
            data.box6_medicare_tax,
        ]
        if v not in (None, "")
    )
    data.confidence = round(min(1.0, populated / 8 + 0.2), 2)
    return data
