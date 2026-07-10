"""Pure evaluation core: (NormalizedRecords, Transform doc, prompt answers,
pinned value maps) -> resolved target values.

No AI, no network, no clock, no randomness — Constitution II. Imports here are
guarded by tests/invariants/test_no_ai_in_apply.py.

Two modes share one resolver:
- preview (strict=False): unresolvable values render as visible markers for the
  HIL exemplar check (FR-008).
- apply (strict=True): unresolvable values become exception dicts, never
  guesses (FR-012); T030 layers batch semantics on top.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

_DATE_IN_FORMATS = ["%b %d, %Y", "%B %d, %Y", "%Y-%m-%d", "%d/%m/%Y"]


class ResolveError(ValueError):
    def __init__(self, reason: str, suggestion: str = ""):
        self.reason = reason
        self.suggestion = suggestion
        super().__init__(reason)


def to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " | ".join(str(v) for v in value)
    return str(value)


def resolve_path(path: str, context: dict) -> Any:
    scope, _, key = path.partition(".")
    if scope not in context:
        raise ResolveError(f"unknown source scope '{scope}' in path '{path}'")
    source = context[scope]
    if not isinstance(source, dict) or key not in source:
        raise ResolveError(f"source field '{path}' not present in extracted record")
    return source[key]


def _parse_date(text: str) -> datetime:
    for fmt in _DATE_IN_FORMATS:
        try:
            return datetime.strptime(text.strip(), fmt)
        except ValueError:
            continue
    raise ResolveError(
        f"date value {text!r} matches no supported input format",
        suggestion="add the observed format to the transform's date_format handling",
    )


def _arg_value(arg: dict, context: dict) -> Any:
    if "lit" in arg:
        return arg["lit"]
    if "field" in arg:
        return resolve_path(arg["field"], context)
    if "prompt" in arg:
        answers = context.get("prompt", {})
        if arg["prompt"] not in answers:
            raise ResolveError(f"missing per-batch prompt answer '{arg['prompt']}'")
        return answers[arg["prompt"]]
    raise ResolveError(f"argument outside grammar: {arg!r}")


def eval_formula(spec: dict, context: dict) -> str:
    fn, args = spec["fn"], [(_arg_value(a, context)) for a in spec["args"]]
    if fn == "concat":
        return "".join(to_text(a) for a in args)
    if fn == "substring":
        text = to_text(args[0])
        start = int(args[1]) if len(args) > 1 else 0
        end = int(args[2]) if len(args) > 2 else len(text)
        return text[start:end]
    if fn == "regex_extract":
        m = re.search(str(args[1]), to_text(args[0]))
        if not m:
            raise ResolveError(f"regex {args[1]!r} matched nothing in {to_text(args[0])!r}")
        return m.group(1) if m.groups() else m.group(0)
    if fn == "date_format":
        return _parse_date(to_text(args[0])).strftime(str(args[1]))
    if fn == "number_format":
        return format(float(to_text(args[0])), str(args[1]))
    if fn == "arith":
        lhs, op, rhs = float(to_text(args[0])), str(args[1]), float(to_text(args[2]))
        ops = {"+": lhs + rhs, "-": lhs - rhs, "*": lhs * rhs, "/": lhs / rhs if rhs else None}
        if op not in ops or ops[op] is None:
            raise ResolveError(f"arith cannot evaluate {lhs} {op} {rhs}")
        result = ops[op]
        return str(int(result)) if result == int(result) else str(result)
    raise ResolveError(f"formula fn '{fn}' outside the closed set")  # unreachable post-schema


def lookup_value_map(raw: Any, entries: list[dict]) -> str:
    text = to_text(raw)
    for entry in entries:
        if str(entry["source_value"]) == text:
            return str(entry["target_value"])
    raise ResolveError(
        f"value {text!r} not covered by the approved value map",
        suggestion=f"review and add a mapping for {text!r} as a new value-map version",
    )


def resolve_field(
    field: str, doc: dict, context: dict, value_maps: dict[tuple[str, int], list[dict]]
) -> str:
    """Resolve one target field from routes/constants/formulas/prompts."""
    routes = doc.get("routes", {})
    if field in routes:
        route = routes[field]
        raw = resolve_path(route["from"], context)
        ref = route.get("value_map")
        if ref:
            entries = value_maps.get((ref["name"], ref["version"]))
            if entries is None:
                raise ResolveError(f"value map {ref['name']}@{ref['version']} not loaded")
            return lookup_value_map(raw, entries)
        return to_text(raw)
    if field in doc.get("constants", {}):
        return to_text(doc["constants"][field])
    if field in doc.get("formulas", {}):
        return eval_formula(doc["formulas"][field], context)
    for prompt in doc.get("prompts", []):
        if (prompt.get("target_field") or prompt["key"]) == field:
            return to_text(_arg_value({"prompt": prompt["key"]}, context))
    raise ResolveError(f"target field '{field}' has no route/constant/formula/prompt")


def resolve_record(
    fields: list[str],
    doc: dict,
    context: dict,
    value_maps: dict[tuple[str, int], list[dict]],
    strict: bool = True,
) -> tuple[dict[str, str], list[dict]]:
    """Resolve `fields` for one record. Returns (values, problems).

    strict=True: problems are exception dicts (FR-012).
    strict=False: problems also render inline as «...» preview markers.
    """
    values: dict[str, str] = {}
    problems: list[dict] = []
    for field in fields:
        try:
            values[field] = resolve_field(field, doc, context, value_maps)
        except ResolveError as err:
            problems.append(
                {
                    "field": field,
                    "reason": err.reason,
                    "suggestion": err.suggestion,
                }
            )
            if not strict:
                values[field] = f"<<unresolved: {err.reason}>>"
    return values, problems
