import re
from decimal import Decimal, InvalidOperation
from typing import Optional

def parse_vin(raw):
    if not raw: return None
    vin = raw.upper().strip().replace("-","").replace(" ","")
    if len(vin) != 17: return None
    if not re.match(r"^[A-HJ-NPR-Z0-9]{17}$", vin): return None
    return vin

def parse_date(raw):
    if not raw: return None
    raw = raw.strip()
    patterns = [
        (r"(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})", "mdy"),
        (r"(\d{4})[/\-\.](\d{1,2})[/\-\.](\d{1,2})", "ymd"),
    ]
    for pattern, fmt in patterns:
        m = re.search(pattern, raw)
        if m:
            try:
                g = m.groups()
                if fmt == "mdy": mo,d,y = int(g[0]),int(g[1]),int(g[2])
                else: y,mo,d = int(g[0]),int(g[1]),int(g[2])
                return f"{y:04d}-{mo:02d}-{d:02d}"
            except: continue
    return None

def parse_currency(raw):
    if not raw: return None
    cleaned = re.sub(r"[^\d.]", "", raw.strip())
    try: return f"{Decimal(cleaned):.2f}"
    except: return None

def parse_labor_op_code(raw):
    if not raw: return None
    raw = raw.upper().strip()
    m = re.search(r"\d{2}-\d{2}[A-Z]?", raw)
    if m: return m.group(0)
    if re.match(r"^[A-Z0-9\-]{4,12}$", raw): return raw
    return None

def parse_part_number(raw):
    if not raw: return None
    cleaned = raw.upper().strip().replace(" ","-")
    if re.match(r"^[A-Z0-9\-]{6,20}$", cleaned): return cleaned
    return None

def parse_mileage(raw):
    if not raw: return None
    digits = re.sub(r"[^\d]","",raw.strip())
    try:
        m = int(digits)
        if 0 < m < 1000000: return m
    except: pass
    return None
