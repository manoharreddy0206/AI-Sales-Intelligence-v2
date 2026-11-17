"""Deterministic period resolution for copilot tools.

The model never does date arithmetic. It passes a period token and the backend
resolves it here. Relative periods are anchored to the dataset's as-of date
(the latest order date), the same anchor the customer-segment panel uses, so a
historical dataset is not compared against today's wall-clock date.

Accepted tokens:
  last_month        calendar month before the as-of month
  latest_month      the as-of month (flagged partial if as-of is before month end)
  YYYY-MM           a calendar month
  YYYY-MM-DD/YYYY-MM-DD   an inclusive date range
  dashboard_filter  the From/To range currently set on the dashboard
"""
import calendar
import re
from dataclasses import dataclass
from datetime import date


class NeedsClarification(Exception):
    def __init__(self, question: str):
        super().__init__(question)
        self.question = question


@dataclass(frozen=True)
class Period:
    start: date
    end: date
    label: str
    partial: bool = False
    is_month: bool = False

    def as_dict(self):
        return {"start": self.start.isoformat(), "end": self.end.isoformat(), "label": self.label, "partial": self.partial}


def month_period(year: int, month: int, as_of: date | None = None) -> Period:
    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])
    partial = bool(as_of and start <= as_of < end)
    return Period(start, end, start.strftime("%B %Y"), partial=partial, is_month=True)


def previous_month(period: Period) -> Period:
    year, month = (period.start.year - 1, 12) if period.start.month == 1 else (period.start.year, period.start.month - 1)
    return month_period(year, month)


MONTH_NAMES = {calendar.month_name[i].lower() for i in range(1, 13)} | {calendar.month_abbr[i].lower() for i in range(1, 13)}
MONTH_RE =re.compile(r"^(\d{4})-(\d{2})$")
RANGE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})/(\d{4}-\d{2}-\d{2})$")


def resolve(token: str, as_of: date | None, dashboard: dict | None = None) -> Period:
    token = (token or "").strip().lower()
    if as_of is None:
        raise NeedsClarification("The dataset is empty. Upload orders before asking about a period.")
    if token == "last_month":
        anchor = month_period(as_of.year, as_of.month)
        return previous_month(anchor)
    if token == "latest_month":
        return month_period(as_of.year, as_of.month, as_of)
    if token == "dashboard_filter":
        dashboard = dashboard or {}
        start, end = dashboard.get("start"), dashboard.get("end")
        if not start or not end:
            raise NeedsClarification("No complete From/To range is set on the dashboard. Which dates should I use?")
        start, end = _as_date(start), _as_date(end)
        if start > end:
            raise NeedsClarification("The dashboard range ends before it starts. Which dates should I use?")
        return Period(start, end, f"{start.isoformat()} to {end.isoformat()}")
    match = MONTH_RE.match(token)
    if match:
        year, month = int(match.group(1)), int(match.group(2))
        if not 1 <= month <= 12:
            raise NeedsClarification(f"{token} is not a valid month. Which month did you mean?")
        return month_period(year, month, as_of)
    match = RANGE_RE.match(token)
    if match:
        try:
            start, end = date.fromisoformat(match.group(1)), date.fromisoformat(match.group(2))
        except ValueError:
            raise NeedsClarification(f"{token} contains an invalid date. Which dates did you mean?") from None
        if start > end:
            raise NeedsClarification("That range ends before it starts. Which dates did you mean?")
        return Period(start, end, f"{start.isoformat()} to {end.isoformat()}")
    if token in MONTH_NAMES:
        raise NeedsClarification(f"Which year do you mean for {token.title()}? The latest order in the dataset is dated {as_of.isoformat()}.")
    raise NeedsClarification(
        "Which period do you mean? Give a month such as 2025-07, a date range, or say 'last month' "
        f"(the month before the latest order date, {as_of.isoformat()})."
    )


def _as_date(value) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))
