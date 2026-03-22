"""Parser for OFX-format 1099 XML exports (e.g. Schwab TAX1099 OFX files).

Structure:
  <OFX>
    <TAX1099MSGSRSV1>
      <TAX1099TRNRS>
        <TAX1099RS>
          <FIDIRECTDEPOSITINFO> ... </FIDIRECTDEPOSITINFO>
          <TAX1099DIV_V100> ... </TAX1099DIV_V100>
          <TAX1099INT_V100> ... </TAX1099INT_V100>
          <TAX1099B_V100>
            <EXTDBINFO_V100>
              <PROCDET_V100> ... </PROCDET_V100>
              ...
            </EXTDBINFO_V100>
            <PAYERADDR> ... </PAYERADDR>
            <RECACCT>...</RECACCT>
          </TAX1099B_V100>
        </TAX1099RS>
      </TAX1099TRNRS>
    </TAX1099MSGSRSV1>
  </OFX>
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Optional, Tuple

from src.models import Brokerage1099Data, Brokerage1099Trade


def _text(element: Optional[ET.Element], tag: str) -> str:
    """Return stripped text of a child element, or ''."""
    if element is None:
        return ""
    child = element.find(tag)
    if child is None or child.text is None:
        return ""
    return child.text.strip()


def _float(element: Optional[ET.Element], tag: str) -> Optional[float]:
    """Return float value of a child element, or None."""
    raw = _text(element, tag)
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _parse_ofx_date(raw: str) -> Optional[str]:
    """Convert OFX date YYYYMMDD to YYYY-MM-DD. Returns None if blank."""
    raw = raw.strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y%m%d").strftime("%Y-%m-%d")
    except ValueError:
        return None


def _parse_root(content: str) -> ET.Element:
    """Parse OFX XML content. The file may have a leading PI comment line."""
    # Strip the non-standard OFX processing instruction if present
    lines = []
    for line in content.splitlines():
        if line.strip().startswith("<?OFX "):
            continue
        lines.append(line)
    return ET.fromstring("\n".join(lines))


def parse_brokerage_1099_xml(
    content: str,
    source_file: str = "",
    source_sha256: str = "",
) -> Tuple[Brokerage1099Data, List[Brokerage1099Trade]]:
    """Parse a Schwab OFX 1099 XML file.

    Returns a (Brokerage1099Data, list[Brokerage1099Trade]) tuple.
    """
    root = _parse_root(content)

    tax1099rs = root.find(".//TAX1099RS")

    # --- broker name from FIDIRECTDEPOSITINFO ---
    fi_info = root.find(".//FIDIRECTDEPOSITINFO")
    broker_name = _text(fi_info, "FINAME_DIRECTDEPOSIT") or "Charles Schwab & Co., Inc."

    # --- DIV data ---
    div_el = root.find(".//TAX1099DIV_V100")
    year: Optional[int] = None
    if div_el is not None:
        raw_year = _text(div_el, "TAXYEAR")
        if raw_year:
            try:
                year = int(raw_year)
            except ValueError:
                pass

    div_ordinary = _float(div_el, "ORDDIV")
    div_qualified = _float(div_el, "QUALIFIEDDIV")
    div_cap_gain = _float(div_el, "TOTCAPGAIN")
    div_foreign_tax = _float(div_el, "FORTAXPD")
    div_sec199a = _float(div_el, "SEC199A")

    # Account number from DIV element; fallback to B element
    account_number = _text(div_el, "RECACCT") or None

    # --- INT data ---
    int_el = root.find(".//TAX1099INT_V100")
    if year is None and int_el is not None:
        raw_year = _text(int_el, "TAXYEAR")
        if raw_year:
            try:
                year = int(raw_year)
            except ValueError:
                pass
    int_income = _float(int_el, "INTINCOME")
    int_us_treasury = _float(int_el, "USGOVTOBLSINT")

    if account_number is None and int_el is not None:
        account_number = _text(int_el, "RECACCT") or None

    # --- B payer/account ---
    b_el = root.find(".//TAX1099B_V100")
    if year is None and b_el is not None:
        raw_year = _text(b_el, "TAXYEAR")
        if raw_year:
            try:
                year = int(raw_year)
            except ValueError:
                pass
    if account_number is None and b_el is not None:
        account_number = _text(b_el, "RECACCT") or None

    # --- build Brokerage1099Data ---
    data = Brokerage1099Data()
    data.broker_name = broker_name
    data.account_number = account_number
    data.year = year
    data.div_ordinary = div_ordinary
    data.div_qualified = div_qualified
    data.div_cap_gain_distributions = div_cap_gain
    data.div_foreign_tax_paid = div_foreign_tax
    data.div_section_199a = div_sec199a
    data.int_interest_income = int_income
    data.int_us_treasury = int_us_treasury
    data.extraction_source = "xml"

    checkable = [
        data.div_ordinary, data.div_qualified, data.div_cap_gain_distributions,
        data.div_foreign_tax_paid, data.div_section_199a,
        data.int_interest_income, data.int_us_treasury,
    ]
    populated = sum(1 for v in checkable if v is not None)
    data.confidence = round(min(1.0, populated / max(len(checkable), 1)), 2)

    # --- build trades from PROCDET_V100 elements ---
    trades: List[Brokerage1099Trade] = []
    for proc in root.findall(".//PROCDET_V100"):
        form8949_code = _text(proc, "FORM8949CODE")
        description = _text(proc, "SALEDESCRIPTION")
        security_id = _text(proc, "SECNAME")

        # Date acquired: DTAQD (specific date) or DTVAR=Y (Various)
        dt_var = _text(proc, "DTVAR")
        dtaqd_raw = _text(proc, "DTAQD")
        date_acquired: Optional[str] = None
        if dt_var.upper() == "Y":
            date_acquired = None  # "Various"
        elif dtaqd_raw:
            date_acquired = _parse_ofx_date(dtaqd_raw)

        dtsale_raw = _text(proc, "DTSALE")
        date_sold = _parse_ofx_date(dtsale_raw)

        proceeds = _float(proc, "SALESPR")
        cost = _float(proc, "COSTBASIS")
        wash = _float(proc, "WASHSALELOSSDISALLOWED")
        fed_tax = _float(proc, "TAXWITHHELD")

        longshort = _text(proc, "LONGSHORT").upper()
        if longshort == "LONG":
            holding_period = "long"
        elif longshort == "SHORT":
            holding_period = "short"
        else:
            holding_period = "unknown"

        noncovered = _text(proc, "NONCOVEREDSECURITY").upper() == "Y"
        basis_not_shown = _text(proc, "BASISNOTSHOWN").upper() == "Y"
        basis_reported = "noncovered" if (noncovered or basis_not_shown) else "covered"

        realized: Optional[float] = None
        if proceeds is not None and cost is not None:
            realized = round(proceeds - cost + (wash or 0.0), 2)

        trade = Brokerage1099Trade(
            broker_name=broker_name,
            source_file=source_file,
            source_sha256=source_sha256,
            description=description,
            security_identifier=security_id if security_id else None,
            date_acquired=date_acquired,
            date_sold_or_disposed=date_sold,
            proceeds_gross=proceeds,
            cost_basis=cost,
            wash_sale_amount=wash if wash else None,
            federal_income_tax_withheld=fed_tax,
            holding_period=holding_period,
            basis_reported_to_irs=basis_reported,
            adjustment_code=form8949_code if form8949_code else None,
            form_8949_box=form8949_code,
            realized_gain_loss=realized,
        )
        trades.append(trade)

    return data, trades
