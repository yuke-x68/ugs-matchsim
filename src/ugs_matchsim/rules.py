"""Rules model, parser and rule evaluation."""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any

from .common import Diagnostics, InputError, ci_keys, fmt, is_num, loads_lenient

RULE_TYPES = {
    t.lower(): t
    for t in (
        "Equality", "Difference", "LessThan", "LessThanEqual",
        "GreaterThan", "GreaterThanEqual", "InList", "Intersection",
    )
}
OPS = {o.lower(): o for o in ("Count", "Median", "Avg", "Sum", "Min", "Max")}
AGE_TYPES = {a.lower(): a for a in ("Oldest", "Average", "Youngest")}
RELAX_TYPES = {
    t.lower(): t
    for t in ("RuleControl.Enable", "RuleControl.Disable", "ReferenceControl.Replace", "RangeControl.ReplaceMin")
}
COMPARATORS = {
    "LessThan": ("<", lambda a, b: a < b),
    "LessThanEqual": ("<=", lambda a, b: a <= b),
    "GreaterThan": (">", lambda a, b: a > b),
    "GreaterThanEqual": (">=", lambda a, b: a >= b),
}
EPS = 1e-9


@dataclass
class Relaxation:
    type: str
    value: Any
    at_seconds: float
    age_type: str
    index: int


@dataclass
class Range:
    min: float
    max: float
    relaxations: list[Relaxation] = field(default_factory=list)


@dataclass
class Rule:
    name: str
    type: str
    source: str
    path: list[str]
    op: str | None
    reference: Any
    overlap: Any
    not_: bool
    enable: bool
    relaxations: list[Relaxation]
    ignored: bool = False
    scope: str = "match"
    team_name: str | None = None

    @property
    def display(self) -> str:
        base = self.name
        if self.scope == "team":
            return f"{base} (team rule of '{self.team_name}')"
        return base

    @property
    def deferred(self) -> bool:
        """Non-hereditary rules are checked only on the finished candidate (N34)."""
        return self.not_ or self.op is not None


@dataclass
class TeamDef:
    name: str
    team_count: Range
    player_count: Range
    team_rules: list[Rule]


@dataclass
class Rules:
    name: str
    teams: list[TeamDef]
    match_rules: list[Rule]
    backfill: bool


# ---------------------------------------------------------------- parsing

def _number(v: Any, ctx: str) -> float:
    if not is_num(v):
        raise InputError(f"{ctx}: expected a number")
    return v


def _validate_ref(rtype: str, ref: Any, ctx: str, required: bool) -> None:
    if ref is None:
        if required:
            raise InputError(f"{ctx}: rule type {rtype} requires a Reference")
        return
    if rtype in ("Difference", *COMPARATORS):
        if not is_num(ref):
            raise InputError(f"{ctx}: Reference for {rtype} must be a number")
    elif rtype == "InList":
        if not isinstance(ref, list):
            raise InputError(f"{ctx}: Reference for InList must be a list")
    elif rtype == "Intersection":
        if not isinstance(ref, list):
            raise InputError(f"{ctx}: Reference for Intersection must be a list")
    elif rtype == "Equality":
        if isinstance(ref, (list, dict)):
            raise InputError(f"{ctx}: Reference for Equality must be a string or number")


def _parse_relaxations(raw: Any, ctx: str, diag: Diagnostics, kind: str, rtype: str | None) -> list[Relaxation]:
    """kind: 'rule' or 'range'."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise InputError(f"{ctx}: Relaxations must be an array")
    out: list[Relaxation] = []
    for i, r in enumerate(raw):
        rc = f"{ctx}.Relaxations[{i}]"
        d = ci_keys(r, {"type", "value", "atseconds", "agetype"}, rc, diag)
        if "type" not in d or not isinstance(d["type"], str):
            raise InputError(f"{rc}: Type is required")
        canon = RELAX_TYPES.get(d["type"].lower())
        if canon is None:
            diag.unsupp(f"{rc} Type '{d['type']}'",
                        "unknown relaxation type is ignored; the field keeps its configured value, "
                        "so matches may be slower or impossible compared with the real service")
            continue
        if canon.startswith("RangeControl") and kind != "range":
            raise InputError(f"{rc}: {canon} is only valid on TeamCount/PlayerCount")
        if not canon.startswith("RangeControl") and kind == "range":
            raise InputError(f"{rc}: {canon} is not valid on TeamCount/PlayerCount")
        if "atseconds" not in d:
            raise InputError(f"{rc}: AtSeconds is required")
        at = _number(d["atseconds"], f"{rc}.AtSeconds")
        age = "Oldest"
        if "agetype" in d:
            age = AGE_TYPES.get(str(d["agetype"]).lower())  # type: ignore[assignment]
            if age is None:
                raise InputError(f"{rc}: AgeType must be Oldest, Average or Youngest")
        val = d.get("value")
        if canon in ("ReferenceControl.Replace", "RangeControl.ReplaceMin") and "value" not in d:
            raise InputError(f"{rc}: Value is required for {canon}")
        if canon == "ReferenceControl.Replace" and rtype:
            _validate_ref(rtype, val, f"{rc}.Value", True)
        if canon == "RangeControl.ReplaceMin":
            _number(val, f"{rc}.Value")
        out.append(Relaxation(canon, val, float(at), age, i))
    return out


def _parse_rule(raw: Any, ctx: str, diag: Diagnostics, scope: str, team_name: str | None, idx: int) -> Rule:
    d = ci_keys(raw, {"name", "type", "source", "reference", "overlap", "not", "enablerule",
                      "relaxations", "externaldata"}, ctx, diag)
    if "type" not in d or not isinstance(d["type"], str):
        raise InputError(f"{ctx}: Type is required")
    if "source" not in d or not isinstance(d["source"], str):
        raise InputError(f"{ctx}: Source is required")
    name = d.get("name")
    name = name if isinstance(name, str) and name else f"{scope}Rule{idx + 1}"
    for key in ("not", "enablerule"):
        if key in d and not isinstance(d[key], bool):
            raise InputError(f"{ctx}: {key} must be true or false")
    rtype_raw = d["type"]
    rtype = RULE_TYPES.get(rtype_raw.lower())
    ignored_reason: str | None = None
    if rtype is None:
        ignored_reason = f"rule type '{rtype_raw}' is not implemented"
    segs = d["source"].split(".")
    path: list[str] = []
    op: str | None = None
    if len(segs) >= 3 and segs[0].lower() == "players" and segs[1].lower() == "customdata":
        path = segs[2:]
        if path[0].lower() == "externaldata":
            ignored_reason = ignored_reason or "ExternalData sources (Leaderboard/CloudSave) are not implemented"
        if len(path) >= 2 and path[-1].lower() in OPS:
            op = OPS[path[-1].lower()]
            path = path[:-1]
    else:
        low = d["source"].lower()
        if "qos" in low:
            ignored_reason = ignored_reason or "QoS sources are not implemented"
        else:
            ignored_reason = ignored_reason or f"source '{d['source']}' is not implemented (only Players.CustomData.* is)"
    if "externaldata" in d:
        ignored_reason = ignored_reason or "rule-level ExternalData is not implemented"
    ref = d.get("reference")
    overlap = d.get("overlap")
    if rtype is not None:
        _validate_ref(rtype, ref, f"{ctx}.Reference", rtype in ("Difference", "InList", *COMPARATORS))
        if rtype == "Intersection":
            if overlap is None:
                raise InputError(f"{ctx}: Intersection requires Overlap")
            _number(overlap, f"{ctx}.Overlap")
    relax = _parse_relaxations(d.get("relaxations"), ctx, diag, "rule", rtype)
    if ignored_reason:
        diag.unsupp(f"{ctx} '{name}'",
                    f"{ignored_reason}; the rule is ignored (treated as always satisfied), "
                    "so matches may form that the real service would reject")
    return Rule(name, rtype or rtype_raw, d["source"], path, op, ref, overlap,
                bool(d.get("not", False)), bool(d.get("enablerule", True)), relax,
                ignored=ignored_reason is not None, scope=scope, team_name=team_name)


def _parse_range(raw: Any, ctx: str, diag: Diagnostics) -> Range:
    d = ci_keys(raw, {"min", "max", "relaxations"}, ctx, diag)
    if "min" not in d or "max" not in d:
        raise InputError(f"{ctx}: Min and Max are required")
    mn, mx = _number(d["min"], f"{ctx}.Min"), _number(d["max"], f"{ctx}.Max")
    if mn < 0 or mx < 1 or mn > mx:
        raise InputError(f"{ctx}: need 0 <= Min <= Max and Max >= 1")
    return Range(mn, mx, _parse_relaxations(d.get("relaxations"), ctx, diag, "range", None))


def parse_rules(data: Any, diag: Diagnostics) -> Rules:
    top = ci_keys(data, {"name", "matchdefinition", "backfillenabled"}, "rules", diag)
    md = ci_keys(top.get("matchdefinition"), {"teams", "matchrules"}, "rules.MatchDefinition", diag)
    teams_raw = md.get("teams")
    if not isinstance(teams_raw, list) or not teams_raw:
        raise InputError("rules.MatchDefinition.Teams: at least one team definition is required")
    teams: list[TeamDef] = []
    for i, t in enumerate(teams_raw):
        ctx = f"rules.MatchDefinition.Teams[{i}]"
        d = ci_keys(t, {"name", "teamcount", "playercount", "teamrules"}, ctx, diag)
        name = d.get("name") if isinstance(d.get("name"), str) and d.get("name") else f"Team{i + 1}"
        if "teamcount" not in d or "playercount" not in d:
            raise InputError(f"{ctx}: TeamCount and PlayerCount are required")
        tr_raw = d.get("teamrules") or []
        if not isinstance(tr_raw, list):
            raise InputError(f"{ctx}.TeamRules must be an array")
        rules = [_parse_rule(r, f"{ctx}.TeamRules[{j}]", diag, "team", name, j) for j, r in enumerate(tr_raw)]
        teams.append(TeamDef(name, _parse_range(d["teamcount"], f"{ctx}.TeamCount", diag),
                             _parse_range(d["playercount"], f"{ctx}.PlayerCount", diag), rules))
    mr_raw = md.get("matchrules") or []
    if not isinstance(mr_raw, list):
        raise InputError("rules.MatchDefinition.MatchRules must be an array")
    match_rules = [_parse_rule(r, f"rules.MatchDefinition.MatchRules[{j}]", diag, "match", None, j)
                   for j, r in enumerate(mr_raw)]
    backfill = top.get("backfillenabled", False)
    if not isinstance(backfill, bool):
        raise InputError("rules.BackfillEnabled must be true or false")
    if backfill:
        diag.unsupp("rules.BackfillEnabled = true",
                    "backfill is not simulated; the run behaves as if BackfillEnabled were false "
                    "(no early match with fewer players, no backfill tickets)")
    name = top.get("name") if isinstance(top.get("name"), str) else "(unnamed)"
    return Rules(name, teams, match_rules, backfill)


def load_rules(text: str, diag: Diagnostics, file: str = "rules file") -> Rules:
    data = loads_lenient(text, file)
    try:
        return parse_rules(data, diag)
    except InputError as ex:
        raise InputError(f"{file}: {ex}") from None


# ------------------------------------------------------------ relaxations

def age_of(ages: list[float], age_type: str) -> float:
    if age_type == "Oldest":
        return max(ages)
    if age_type == "Youngest":
        return min(ages)
    return sum(ages) / len(ages)


def triggered(r: Relaxation, ages: list[float]) -> bool:
    return bool(ages) and age_of(ages, r.age_type) >= r.at_seconds - EPS


def active_relaxations(relaxations: list[Relaxation], ages: list[float]) -> list[Relaxation]:
    """Triggered relaxations in ascending AtSeconds order, ties by list order (N8)."""
    return [r for r in sorted(relaxations, key=lambda r: (r.at_seconds, r.index)) if triggered(r, ages)]


def effective_rule(rule: Rule, ages: list[float]) -> tuple[bool, Any]:
    enabled, ref = rule.enable, rule.reference
    for r in active_relaxations(rule.relaxations, ages):
        if r.type == "RuleControl.Enable":
            enabled = True
        elif r.type == "RuleControl.Disable":
            enabled = False
        elif r.type == "ReferenceControl.Replace":
            ref = r.value
    return enabled and not rule.ignored, ref


def effective_min(rng: Range, ages: list[float]) -> float:
    mn = rng.min
    for r in active_relaxations(rng.relaxations, ages):
        mn = r.value
    return mn


# ------------------------------------------------------------- evaluation

def norm(v: Any) -> tuple:
    if isinstance(v, bool):
        return ("b", v)
    if is_num(v):
        return ("n", float(v))
    if isinstance(v, str):
        return ("s", v)
    return ("j", fmt(v))


def _distinct(vals: list[Any]) -> list[Any]:
    seen: set[tuple] = set()
    out = []
    for v in vals:
        k = norm(v)
        if k not in seen:
            seen.add(k)
            out.append(v)
    return out


def resolve(data: Any, path: list[str]) -> tuple[bool, Any]:
    cur = data
    for seg in path:
        if isinstance(cur, dict) and seg in cur:
            cur = cur[seg]
        else:
            return False, None
    return True, cur


def source_values(rule: Rule, players: list[Any]) -> tuple[list[Any] | None, str | None]:
    vals = []
    for p in players:
        found, v = resolve(p.custom, rule.path)
        if not found:
            return None, f"player {p.id} has no value at Players.CustomData.{'.'.join(rule.path)}"
        vals.append(v)
    if rule.op is None:
        return vals, None
    flat: list[Any] = []
    for v in vals:
        flat.extend(v if isinstance(v, list) else [v])
    if rule.op == "Count":
        return [sum(1 for v in flat if v is not None and v is not False)], None
    if not flat:
        return None, f"no values for {rule.op}"
    if not all(is_num(v) for v in flat):
        return None, f"non-numeric values for {rule.op}: {', '.join(fmt(v) for v in _distinct(flat))}"
    fn = {"Sum": sum, "Min": min, "Max": max, "Avg": lambda x: sum(x) / len(x), "Median": statistics.median}[rule.op]
    return [fn(flat)], None


def _eval(rule: Rule, vals: list[Any], ref: Any) -> tuple[bool, str]:
    t = rule.type
    shown = ", ".join(fmt(v) for v in _distinct(vals))
    if t == "Equality":
        if ref is not None:
            bad = [v for v in vals if norm(v) != norm(ref)]
            return not bad, f"{', '.join(fmt(v) for v in _distinct(bad))} vs Reference {fmt(ref)}"
        return len(_distinct(vals)) <= 1, " vs ".join(fmt(v) for v in _distinct(vals))
    if t in ("Difference", *COMPARATORS) and not all(is_num(v) for v in vals):
        return False, f"non-numeric value(s): {shown}"
    if t == "Difference":
        spread = max(vals) - min(vals)
        return spread <= ref, f"spread {fmt(spread)} > {fmt(ref)} (values {fmt(min(vals))}..{fmt(max(vals))})"
    if t in COMPARATORS:
        sym, fn = COMPARATORS[t]
        bad = [v for v in vals if not fn(v, ref)]
        return not bad, f"{', '.join(fmt(v) for v in _distinct(bad))} not {sym} {fmt(ref)}"
    if t == "InList":
        allowed = {norm(r) for r in ref}
        bad = [v for v in vals if norm(v) not in allowed]
        return not bad, f"{', '.join(fmt(v) for v in _distinct(bad))} not in [{', '.join(fmt(r) for r in ref)}]"
    if t == "Intersection":
        sets = [{norm(x) for x in (v if isinstance(v, list) else [v])} for v in vals]
        if ref is not None:
            sets.append({norm(x) for x in ref})
        common = set.intersection(*sets) if sets else set()
        need = rule.overlap
        return len(common) >= need, f"{len(common)} common item(s) < Overlap {fmt(need)}"
    raise InputError(f"unimplemented rule type {t}")


def check_rule(rule: Rule, ref: Any, players: list[Any]) -> tuple[bool, str | None]:
    """Evaluate a rule over the players in scope. Returns (ok, violation detail)."""
    vals, problem = source_values(rule, players)
    if vals is None:
        return False, problem  # N16: unsatisfiable regardless of Not
    ok, detail = _eval(rule, vals, ref)
    if rule.not_:
        if ok:
            return False, f"Not=true but {rule.type} holds (values {', '.join(fmt(v) for v in _distinct(vals))})"
        return True, None
    return (True, None) if ok else (False, detail)
