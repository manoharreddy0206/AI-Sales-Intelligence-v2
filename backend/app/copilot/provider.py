"""LLM providers for the copilot.

``AnthropicProvider`` calls the Anthropic Messages API with tool definitions
(standard library HTTP, so no SDK dependency). ``StubProvider`` is a labelled,
rule-based stand-in for tests and keyless local development: it emits the same
tool_use / text blocks, so the real tool loop still runs, but no model chooses
the tools.
"""
import json
import re
import socket
import urllib.error
import urllib.request

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"


class ProviderError(Exception):
    pass


class AnthropicProvider:
    mode = "anthropic"

    def __init__(self, api_key: str, model: str, max_tokens: int = 600):
        self.api_key, self.model, self.max_tokens = api_key, model, max_tokens

    def complete(self, system: str, messages: list, tools: list, timeout: float) -> dict:
        body = json.dumps({"model": self.model, "max_tokens": self.max_tokens, "system": system, "tools": tools, "messages": messages}).encode()
        request = urllib.request.Request(
            ANTHROPIC_URL,
            data=body,
            method="POST",
            headers={"content-type": "application/json", "x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            # Report the status only; response bodies can echo request content.
            raise ProviderError(f"provider returned HTTP {exc.code}") from None
        except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
            raise ProviderError(f"provider unreachable or timed out ({type(exc).__name__})") from None
        except ValueError:
            raise ProviderError("provider returned invalid JSON") from None


MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"], 1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})


def stub_period(question: str) -> str:
    q = question.lower()
    m = re.search(r"(\d{4}-\d{2}-\d{2})\s*(?:to|and|-|/|until|through)\s*(\d{4}-\d{2}-\d{2})", q)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    m = re.search(r"\b(\d{4}-\d{2})\b", q)
    if m:
        return m.group(1)
    if re.search(r"\b(last|previous|prior) month\b", q):
        return "last_month"
    if re.search(r"\b(this|latest|current) month\b", q):
        return "latest_month"
    if re.search(r"\b(selected|filter|filtered|dashboard)\b", q):
        return "dashboard_filter"
    for word in re.findall(r"[a-z]+", q):
        if word in MONTHS:
            y = re.search(r"\b(19|20)\d{2}\b", q)
            return f"{y.group(0)}-{MONTHS[word]:02d}" if y else word
    return ""


class StubProvider:
    """Deterministic keyword router. Clearly labelled as stub mode in every response."""

    mode = "stub"
    model = "rule-based stub (no LLM)"

    def complete(self, system: str, messages: list, tools: list, timeout: float) -> dict:
        last = messages[-1]
        if isinstance(last["content"], list) and any(b.get("type") == "tool_result" for b in last["content"]):
            results = [json.loads(b["content"]) for m in messages if isinstance(m["content"], list)
                       for b in m["content"] if b.get("type") == "tool_result"]
            useful = [r for r in results if r.get("status") != "error"] or results
            return {"stop_reason": "end_turn", "content": [{"type": "text", "text": self._summarise(useful[-1])}]}
        question = messages[0]["content"] if isinstance(messages[0]["content"], str) else ""
        question = question.split("\n\nDashboard context:")[0]
        call = self._route(question)
        if call is None:
            return {"stop_reason": "end_turn", "content": [{"type": "text", "text": "I can answer revenue for a period, compare a period with the one before, or define a metric. Which would you like?"}]}
        return {"stop_reason": "tool_use", "content": [{"type": "tool_use", "id": "stub_1", "name": call[0], "input": call[1]}]}

    @staticmethod
    def _route(question: str):
        q = question.lower()
        if re.search(r"\b(define|defined|definition|mean|meaning|calculated|computed|counted|measured|handled)\b", q):
            return "search_metric_glossary", {"query": question}
        period = stub_period(question)
        if re.search(r"\b(change|changed|compare|compared|versus|vs\.?|growth|difference|differ)\b", q):
            return "compare_periods", {"current": period or "last_month"}
        if re.search(r"\b(revenue|sales|orders?|average order|aov|customers?)\b", q):
            return "get_revenue_summary", {"period": period}
        return None

    @staticmethod
    def _summarise(r: dict) -> str:
        status = r.get("status")
        if status == "error":
            return f"The tool call failed: {r.get('message')}"
        if status == "needs_clarification":
            return r["question"]
        if status == "empty_dataset":
            return "No orders are stored yet, so there is nothing to report. Upload a CSV or Excel file first."
        if status == "not_found":
            return "The metrics glossary has no entry for that term, so I can't give a sourced definition."
        if "passages" in r:
            p = r["passages"][0]
            return f"{p['text']} [{p['source_id']}]"
        if "deltas" in r:
            c, p = r["current"], r["previous"]
            return f"Compared {c['period']['label']} with {p['period']['label']}. The figures and deltas below come straight from the database."
        p = r["period"]
        if status == "empty_period":
            return f"There are no orders between {p['start']} and {p['end']} in this dataset."
        return f"Revenue for {p['label']} ({p['start']} to {p['end']}) was {r['revenue']} from {r['orders']} orders."
