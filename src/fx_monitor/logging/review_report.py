"""Aggregate draft AI review JSONL logs into Markdown + JSON reports.

Offline analysis only. The output is for engineers studying which steps
the dual-AI reviewers tend to mark as missing / disagreeing — it is never
fed back into the rule engine, the notifier, or any trading path.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .review_log import read_review_log


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(x) for x in value]
    if value is None:
        return []
    return [str(value)]


def summarize_review_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    mode_counts: Counter[str] = Counter(str(r.get("mode", "unknown")) for r in records)

    symbol_counts: Counter[str] = Counter()
    timeframe_counts: Counter[str] = Counter()
    rule_verdicts: Counter[str] = Counter()
    openai_verdicts: Counter[str] = Counter()
    claude_verdicts: Counter[str] = Counter()
    compare_results: Counter[str] = Counter()
    decisions: Counter[str] = Counter()

    openai_missing: Counter[str] = Counter()
    claude_missing: Counter[str] = Counter()
    openai_disagreements: Counter[str] = Counter()
    claude_disagreements: Counter[str] = Counter()
    openai_reasons: Counter[str] = Counter()
    claude_reasons: Counter[str] = Counter()

    rough_patterns: Counter[str] = Counter()
    pivots_stats: list[int] = []
    zones_stats: list[int] = []

    invalid_records = 0

    for r in records:
        if r.get("mode") == "invalid_json":
            invalid_records += 1
            continue

        symbol_counts[str(r.get("symbol", "UNKNOWN"))] += 1
        timeframe_counts[str(r.get("timeframe", "UNKNOWN"))] += 1

        rule = r.get("rule") or {}
        openai = r.get("openai") or {}
        claude = r.get("claude") or {}
        cmp_block = r.get("compare") or {}

        rule_verdicts[str(rule.get("verdict", "UNKNOWN"))] += 1
        openai_verdicts[str(openai.get("verdict", "UNKNOWN"))] += 1
        claude_verdicts[str(claude.get("verdict", "UNKNOWN"))] += 1
        compare_results[str(cmp_block.get("result", "UNKNOWN"))] += 1
        decisions[str(r.get("decision", "UNKNOWN"))] += 1

        for x in _as_list(openai.get("missing")):
            openai_missing[x] += 1
        for x in _as_list(claude.get("missing")):
            claude_missing[x] += 1
        for x in _as_list(openai.get("disagreements")):
            openai_disagreements[x] += 1
        for x in _as_list(claude.get("disagreements")):
            claude_disagreements[x] += 1
        for x in _as_list(openai.get("reasons")):
            openai_reasons[x] += 1
        for x in _as_list(claude.get("reasons")):
            claude_reasons[x] += 1

        rough_patterns[str(r.get("rough_pattern", "unknown"))] += 1

        try:
            pivots_stats.append(int(r.get("pivots", 0)))
        except (TypeError, ValueError):
            pass
        try:
            zones_stats.append(int(r.get("zones", 0)))
        except (TypeError, ValueError):
            pass

    def top(counter: Counter[str], n: int = 10) -> list[dict[str, Any]]:
        return [{"value": k, "count": v} for k, v in counter.most_common(n)]

    def stats(values: list[int]) -> dict[str, Any]:
        if not values:
            return {"count": 0, "min": None, "max": None, "avg": None}
        return {
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / len(values),
        }

    return {
        "total_records": total,
        "invalid_records": invalid_records,
        "mode_counts": dict(mode_counts),
        "symbol_counts": dict(symbol_counts),
        "timeframe_counts": dict(timeframe_counts),
        "rule_verdicts": dict(rule_verdicts),
        "openai_verdicts": dict(openai_verdicts),
        "claude_verdicts": dict(claude_verdicts),
        "compare_results": dict(compare_results),
        "decisions": dict(decisions),
        "rough_patterns": dict(rough_patterns),
        "pivots": stats(pivots_stats),
        "zones": stats(zones_stats),
        "top_openai_missing": top(openai_missing),
        "top_claude_missing": top(claude_missing),
        "top_openai_disagreements": top(openai_disagreements),
        "top_claude_disagreements": top(claude_disagreements),
        "top_openai_reasons": top(openai_reasons),
        "top_claude_reasons": top(claude_reasons),
        "safety": {
            "used_for_notification": False,
            "used_for_ready": False,
            "offline_analysis_only": True,
        },
    }


def _bullets(items: list[dict[str, Any]]) -> list[str]:
    if not items:
        return ["- (none)"]
    return [f"- {item['value']}: {item['count']}" for item in items]


def build_review_report_markdown(summary: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# FX Monitor Draft AI Review Report")
    lines.append("")
    lines.append("## Safety")
    lines.append("")
    lines.append("- Offline analysis only")
    lines.append("- Not used for READY")
    lines.append("- Not used for notification")
    lines.append("- Not used for trading or order execution")
    lines.append("")
    lines.append("## Overview")
    lines.append("")
    lines.append(f"- total_records: {summary.get('total_records')}")
    lines.append(f"- invalid_records: {summary.get('invalid_records')}")
    lines.append(f"- decisions: {summary.get('decisions')}")
    lines.append(f"- compare_results: {summary.get('compare_results')}")
    lines.append("")
    lines.append("## Verdicts")
    lines.append("")
    lines.append(f"- rule: {summary.get('rule_verdicts')}")
    lines.append(f"- openai: {summary.get('openai_verdicts')}")
    lines.append(f"- claude: {summary.get('claude_verdicts')}")
    lines.append("")
    lines.append("## Draft quality")
    lines.append("")
    lines.append(f"- rough_patterns: {summary.get('rough_patterns')}")
    lines.append(f"- pivots: {summary.get('pivots')}")
    lines.append(f"- zones: {summary.get('zones')}")
    lines.append("")
    lines.append("## Top OpenAI missing")
    lines.append("")
    lines.extend(_bullets(summary.get("top_openai_missing", [])))
    lines.append("")
    lines.append("## Top Claude missing")
    lines.append("")
    lines.extend(_bullets(summary.get("top_claude_missing", [])))
    lines.append("")
    lines.append("## Top OpenAI disagreements")
    lines.append("")
    lines.extend(_bullets(summary.get("top_openai_disagreements", [])))
    lines.append("")
    lines.append("## Top Claude disagreements")
    lines.append("")
    lines.extend(_bullets(summary.get("top_claude_disagreements", [])))
    lines.append("")
    lines.append("## Top OpenAI reasons")
    lines.append("")
    lines.extend(_bullets(summary.get("top_openai_reasons", [])))
    lines.append("")
    lines.append("## Top Claude reasons")
    lines.append("")
    lines.extend(_bullets(summary.get("top_claude_reasons", [])))
    lines.append("")
    return "\n".join(lines)


def write_review_report(
    *,
    log_path: str | Path,
    markdown_path: str | Path,
    json_path: str | Path,
) -> dict[str, Any]:
    records = read_review_log(log_path)
    summary = summarize_review_records(records)

    md = build_review_report_markdown(summary)

    md_path = Path(markdown_path)
    js_path = Path(json_path)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    js_path.parent.mkdir(parents=True, exist_ok=True)

    md_path.write_text(md, encoding="utf-8")
    js_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return summary


__all__ = [
    "summarize_review_records",
    "build_review_report_markdown",
    "write_review_report",
]
