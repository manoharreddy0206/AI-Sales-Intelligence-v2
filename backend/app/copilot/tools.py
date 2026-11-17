"""Typed, read-only tools exposed to the language model.

The model can only call names in ``TOOLS``. Inputs are validated with Pydantic
(unknown fields rejected). Handlers call the same analytics functions the
dashboard uses. There is no raw SQL or write access on this interface.
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .. import analytics
from . import glossary, periods


@dataclass
class ToolContext:
    db_path: object
    dashboard: dict = field(default_factory=dict)
    glossary_path: Optional[str] = None


class ToolInputError(Exception):
    pass


PERIOD_HELP = (
    "One of: 'last_month' (calendar month before the dataset's latest order date), 'latest_month', "
    "'dashboard_filter' (the From/To range on the dashboard), a month 'YYYY-MM', or an inclusive range "
    "'YYYY-MM-DD/YYYY-MM-DD'. Never guess a year the user did not give."
)


class RevenueInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    period: str = Field(description=PERIOD_HELP, max_length=40)


class CompareInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current: str = Field(description=PERIOD_HELP, max_length=40)
    previous: Optional[str] = Field(default=None, description="Period to compare against. Omit to use the calendar month before `current` (only when `current` is a month).", max_length=40)


class GlossaryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(description="Metric or term to define, e.g. 'repeat customer'.", min_length=1, max_length=200)


def _dataset(ctx: ToolContext) -> dict:
    info = analytics.dataset_info(ctx.db_path)
    info["as_of"] = info["last_date"]
    info["name"] = getattr(ctx.db_path, "name", str(ctx.db_path))
    return info


def _as_of(info: dict) -> Optional[date]:
    return date.fromisoformat(info["last_date"]) if info["last_date"] else None


def _metrics(ctx: ToolContext, period: periods.Period) -> dict:
    s = analytics.summary(ctx.db_path, period.start, period.end)
    return {
        "period": period.as_dict(),
        "revenue": s["revenue"],
        "orders": s["orders"],
        "customers": s["customers"],
        "average_order": s["average_order"] if s["orders"] else None,
    }


def _delta(current, previous):
    if current is None or previous is None:
        return {"absolute": None, "percent": None, "note": "not defined: a period has no orders"}
    absolute = round(current - previous, 2)
    if previous == 0:
        return {"absolute": absolute, "percent": None, "note": "percent change not defined: previous value is 0"}
    return {"absolute": absolute, "percent": round(absolute / previous * 100, 2)}


def _clarify(question: str, dataset: dict) -> dict:
    return {"status": "needs_clarification", "question": question, "dataset": dataset}


def get_revenue_summary(args: RevenueInput, ctx: ToolContext) -> dict:
    dataset = _dataset(ctx)
    if not dataset["orders"]:
        return {"status": "empty_dataset", "message": "No orders are stored yet.", "dataset": dataset}
    try:
        period = periods.resolve(args.period, _as_of(dataset), ctx.dashboard)
    except periods.NeedsClarification as exc:
        return _clarify(exc.question, dataset)
    result = _metrics(ctx, period)
    result.update(status="ok" if result["orders"] else "empty_period", dataset=dataset)
    return result


def compare_periods(args: CompareInput, ctx: ToolContext) -> dict:
    dataset = _dataset(ctx)
    if not dataset["orders"]:
        return {"status": "empty_dataset", "message": "No orders are stored yet.", "dataset": dataset}
    as_of = _as_of(dataset)
    try:
        current = periods.resolve(args.current, as_of, ctx.dashboard)
        if args.previous:
            previous = periods.resolve(args.previous, as_of, ctx.dashboard)
        elif current.is_month:
            previous = periods.previous_month(current)
        else:
            return _clarify("Which earlier period should I compare this range with?", dataset)
    except periods.NeedsClarification as exc:
        return _clarify(exc.question, dataset)
    cur, prev = _metrics(ctx, current), _metrics(ctx, previous)
    deltas = {key: _delta(cur[key], prev[key]) for key in ("revenue", "orders", "average_order")}
    return {"status": "ok", "current": cur, "previous": prev, "deltas": deltas, "dataset": dataset}


def search_metric_glossary(args: GlossaryInput, ctx: ToolContext) -> dict:
    passages = glossary.search(args.query, path=ctx.glossary_path)
    if not passages:
        return {"status": "not_found", "message": "No glossary entry matches this term.", "passages": []}
    return {"status": "ok", "passages": passages}


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    model: type[BaseModel]
    handler: Callable[[BaseModel, ToolContext], dict]

    def schema(self) -> dict:
        s = self.model.model_json_schema()
        s.pop("title", None)
        return {"name": self.name, "description": self.description, "input_schema": s}


TOOLS = {
    t.name: t
    for t in [
        Tool("get_revenue_summary", "Exact revenue, order count, customer count and average order value for one period, from the sales database.", RevenueInput, get_revenue_summary),
        Tool("compare_periods", "Revenue, order count and average order value for two periods, with absolute and percent deltas.", CompareInput, compare_periods),
        Tool("search_metric_glossary", "Retrieve metric definitions from the checked-in glossary. Returns passages with stable source IDs to cite.", GlossaryInput, search_metric_glossary),
    ]
}


def schemas() -> list[dict]:
    return [t.schema() for t in TOOLS.values()]


def execute(name: str, raw_input, ctx: ToolContext) -> dict:
    """Run one tool call. Unknown tools and invalid inputs are refused, never guessed."""
    tool = TOOLS.get(name)
    if tool is None:
        raise ToolInputError(f"Tool '{name}' is not available. Allowed tools: {', '.join(TOOLS)}.")
    try:
        args = tool.model.model_validate(raw_input if isinstance(raw_input, dict) else {})
    except ValidationError as exc:
        raise ToolInputError(f"Invalid input for {name}: {exc.errors(include_url=False)[0]['msg']}") from exc
    return tool.handler(args, ctx)
