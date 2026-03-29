from datetime import date, datetime, timedelta

from app.Services.dispatch_service import DispatchService
from app.Services.erp_service import ERPService
from app.Services.samsara_service import SamsaraService

dispatch_service = DispatchService()
erp_service = ERPService()
samsara_service = SamsaraService()


def _add_business_days(start_date: date, days: int) -> date:
    result = start_date
    sign = 1 if days >= 0 else -1
    remaining = abs(days)
    while remaining > 0:
        result += timedelta(days=sign)
        if result.weekday() < 5:  # Mon-Fri
            remaining -= 1
    return result


def _parse_iso_date(value: str, fallback: date) -> date:
    try:
        return datetime.fromisoformat(value).date()
    except Exception:
        return fallback
