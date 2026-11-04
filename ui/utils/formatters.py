import re
from datetime import datetime


def extract_id(value: str) -> str:
    if not value:
        return ""
    value = value.strip()
    if "id=" in value:
        try:
            return value.split("id=")[-1].split("&")[0]
        except Exception:
            pass
    if "/" in value:
        return value.rstrip("/").split("/")[-1]
    return value


def fmt_rupiah(value) -> str:
    try:
        return f"Rp {float(value):,.0f}"
    except (TypeError, ValueError):
        return "Rp 0"


def fmt_datetime(raw: str) -> str:
    if not raw:
        return "-"
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return dt.strftime("%d-%m-%Y %H:%M")
    except Exception:
        return str(raw)


def is_plate(text: str) -> bool:
    t = text.upper().replace(" ", "")
    return bool(re.match(r'^[A-Z]{1,2}[0-9]{1,4}[A-Z]{1,3}$', t))


def unwrap_result(result: dict) -> dict:
    """Unwrap Laravel JsonResource {"data": {...}} -> inner dict."""
    if isinstance(result, dict) and "data" in result:
        inner = result["data"]
        if isinstance(inner, dict):
            return inner
    return result
