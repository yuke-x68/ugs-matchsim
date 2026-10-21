"""Rules model, parser and rule evaluation."""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any

from .common import Diagnostics, InputError, ci_keys, fmt, is_num, kind, loads_lenient

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
class CloudSave:
    """A `Players.CustomData.ExternalData.CloudSave.<key>...` source (S44)."""
    key: str
    access_class: str = "Protected"  # N38: checked, not used
    has_default: bool = False
    default: Any = None  # N37: stands in for the whole item of `key`


@dataclass
class Rule:
    name: str
    type: str
    source: str
    path: list[str]  # inside the player's custom data, or inside the Cloud Save item when cloud_save is set
    op: str | None
    reference: Any
    overlap: Any
    not_: bool
    enable: bool
    relaxations: list[Relaxation]
    ignored: bool = False
    scope: str = "match"
    team_name: str | None = None
    cloud_save: CloudSave | None = None

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
    # .mmq only: flow queue key -> (value, path in the rules file); used when the flow omits the key
    queue: dict[str, tuple[Any, str]] = field(default_factory=dict)


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


def _parse_external(raw: Any, ctx: str, cloud: CloudSave | None, diag: Diagnostics) -> str | None:
    """Rule-level ExternalData (S43, S44). Fills `cloud`; returns why the rule is unsupported, if it is."""
    e = ci_keys(raw, {"cloudsave", "leaderboard"}, ctx, diag)
    if "cloudsave" in e:
        c = ci_keys(e["cloudsave"], {"accessclass", "default"}, f"{ctx}.CloudSave", diag)
        access = c.get("accessclass", "Protected")
        if not isinstance(access, str):
            raise InputError(f"{ctx}.CloudSave.AccessClass: got {fmt(access)}; expected a string, e.g. \"Protected\"")
        if cloud is None:
            diag.warn(f"{ctx}.CloudSave: ignored; only a Players.CustomData.ExternalData.CloudSave.<key> "
                      "source reads it")
        else:
            cloud.access_class = access
            cloud.has_default = "default" in c
            cloud.default = c.get("default")
    if "leaderboard" in e:
        return "ExternalData.Leaderboard is not implemented"
    return None


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
    cloud: CloudSave | None = None
    if len(segs) >= 3 and segs[0].lower() == "players" and segs[1].lower() == "customdata":
        path = segs[2:]
        is_cloud = len(path) >= 2 and path[0].lower() == "externaldata" and path[1].lower() == "cloudsave"
        if is_cloud:
            path = path[2:]  # <key>[.<path inside the item>]
            if not path or not path[0]:
                raise InputError(f"{ctx}.Source: '{d['source']}' names no Cloud Save key; "
                                 "expected Players.CustomData.ExternalData.CloudSave.<key>[.<path>]")
        elif path[0].lower() == "externaldata":
            ignored_reason = ignored_reason or "ExternalData sources other than CloudSave (e.g. Leaderboard) are not implemented"
        if len(path) >= 2 and path[-1].lower() in OPS:
            op = OPS[path[-1].lower()]
            path = path[:-1]
        if is_cloud:
            cloud = CloudSave(path[0])
            path = path[1:]
    else:
        low = d["source"].lower()
        if "qos" in low:
            ignored_reason = ignored_reason or "QoS sources are not implemented"
        else:
            ignored_reason = ignored_reason or f"source '{d['source']}' is not implemented (only Players.CustomData.* is)"
    if "externaldata" in d:
        ext_reason = _parse_external(d["externaldata"], f"{ctx}.ExternalData", cloud, diag)
        ignored_reason = ignored_reason or ext_reason
    if cloud is not None and cloud.has_default and not ignored_reason and not resolve(cloud.default, path)[0]:
        diag.warn(f"{ctx}.ExternalData.CloudSave.Default: has no value at '{'.'.join(path)}' (the Source path "
                  f"after the Cloud Save key '{cloud.key}'); a player without that key leaves rule '{name}' "
                  "unsatisfied (N37)")
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
                ignored=ignored_reason is not None, scope=scope, team_name=team_name, cloud_save=cloud)


def _parse_range(raw: Any, ctx: str, diag: Diagnostics) -> Range:
    d = ci_keys(raw, {"min", "max", "relaxations"}, ctx, diag)
    if "min" not in d or "max" not in d:
        raise InputError(f"{ctx}: Min and Max are required")
    mn, mx = _number(d["min"], f"{ctx}.Min"), _number(d["max"], f"{ctx}.Max")
    if mn < 0 or mx < 1 or mn > mx:
        raise InputError(f"{ctx}: need 0 <= Min <= Max and Max >= 1")
    return Range(mn, mx, _parse_relaxations(d.get("relaxations"), ctx, diag, "range", None))


def parse_rules(data: Any, diag: Diagnostics, root: str = "rules") -> Rules:
    top = ci_keys(data, {"name", "matchdefinition", "backfillenabled"}, root, diag)
    md = ci_keys(top.get("matchdefinition"), {"teams", "matchrules"}, f"{root}.MatchDefinition", diag)
    teams_raw = md.get("teams")
    if not isinstance(teams_raw, list) or not teams_raw:
        raise InputError(f"{root}.MatchDefinition.Teams: at least one team definition is required")
    teams: list[TeamDef] = []
    for i, t in enumerate(teams_raw):
        ctx = f"{root}.MatchDefinition.Teams[{i}]"
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
        raise InputError(f"{root}.MatchDefinition.MatchRules must be an array")
    match_rules = [_parse_rule(r, f"{root}.MatchDefinition.MatchRules[{j}]", diag, "match", None, j)
                   for j, r in enumerate(mr_raw)]
    backfill = top.get("backfillenabled", False)
    if not isinstance(backfill, bool):
        raise InputError(f"{root}.BackfillEnabled must be true or false")
    if backfill:
        diag.unsupp(f"{root}.BackfillEnabled = true",
                    "backfill is not simulated; the run behaves as if BackfillEnabled were false "
                    "(no early match with fewer players, no backfill tickets)")
    name = top.get("name") if isinstance(top.get("name"), str) else "(unnamed)"
    return Rules(name, teams, match_rules, backfill)


# ------------------------------------------------------------- queue file

def is_queue_file(data: Any, file: str) -> bool:
    """UGS CLI queue file (S73): named *.mmq, or a top-level `defaultPool` key."""
    return file.lower().endswith(".mmq") or (
        isinstance(data, dict) and any(k.lower() == "defaultpool" for k in data))


def _optional_array(d: dict[str, Any], key: str, ctx: str) -> list[Any]:
    v = d.get(key)
    if v is None:
        return []
    if not isinstance(v, list):
        raise InputError(f"{ctx}: {kind(v)}; expected an array")
    return v


def parse_queue(data: Any, diag: Diagnostics) -> Rules:
    """Queue file: the default pool's matchLogic is the one simulated pool (S73)."""
    top = ci_keys(data, {"$schema", "name", "enabled", "maxplayersperticket", "defaultpool", "filteredpools"},
                  "rules", diag)
    pool = top.get("defaultpool")
    if not isinstance(pool, dict):
        raise InputError(f"rules.DefaultPool: {'missing' if pool is None else kind(pool)}; "
                         "expected an object with matchLogic (UGS CLI queue file)")
    pd = ci_keys(pool, {"variants", "name", "enabled", "timeoutseconds", "matchlogic", "matchhosting"},
                 "rules.DefaultPool", diag)
    queue: dict[str, tuple[Any, str]] = {}
    for d, ctx, what in ((top, "rules", "queue"), (pd, "rules.DefaultPool", "pool")):
        enabled = d.get("enabled", True)
        if not isinstance(enabled, bool):
            raise InputError(f"{ctx}.Enabled: got {fmt(enabled)}; expected true or false")
        if not enabled:
            diag.unsupp(f"{ctx}.Enabled = false",
                        f"a disabled {what} is not simulated; the run behaves as if it were enabled")
    filtered = _optional_array(top, "filteredpools", "rules.FilteredPools")
    if filtered:
        diag.unsupp(f"rules.FilteredPools ({len(filtered)} pool(s))",
                    "filtered pools and their filters are not simulated; every ticket joins the default pool")
    maxp = top.get("maxplayersperticket")
    if maxp is not None:
        if not isinstance(maxp, int) or isinstance(maxp, bool) or maxp < 1:
            raise InputError(f"rules.MaxPlayersPerTicket: got {fmt(maxp)}; expected an integer >= 1")
        queue["maxPlayersPerTicket"] = (maxp, "rules.MaxPlayersPerTicket")
    variants = _optional_array(pd, "variants", "rules.DefaultPool.Variants")
    if variants:
        diag.unsupp(f"rules.DefaultPool.Variants ({len(variants)} variant(s))",
                    "pool variants are not simulated; every ticket uses the default pool's matchLogic")
    timeout = pd.get("timeoutseconds")
    if timeout is not None:
        if not is_num(timeout) or timeout <= 0:
            raise InputError(f"rules.DefaultPool.TimeoutSeconds: got {fmt(timeout)}; expected a number > 0 (seconds)")
        queue["timeoutSeconds"] = (timeout, "rules.DefaultPool.TimeoutSeconds")
    if "matchlogic" not in pd:
        raise InputError("rules.DefaultPool.MatchLogic: missing; "
                         "expected the pool rules object (name, matchDefinition, backfillEnabled)")
    rules = parse_rules(pd["matchlogic"], diag, "rules.DefaultPool.MatchLogic")
    rules.queue = queue
    return rules


def load_rules(text: str, diag: Diagnostics, file: str = "rules file") -> Rules:
    data = loads_lenient(text, file)
    try:
        return parse_queue(data, diag) if is_queue_file(data, file) else parse_rules(data, diag)
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


def player_value(rule: Rule, p: Any) -> tuple[bool, Any, str | None]:
    """The value the rule's source reads for one player: (found, value, why it is missing)."""
    cs = rule.cloud_save
    if cs is None:
        found, v = resolve(p.custom, rule.path)
        return found, v, None if found else f"player {p.id} has no value at Players.CustomData.{'.'.join(rule.path)}"
    if cs.key in p.cloud_save:
        found, v = resolve(p.cloud_save[cs.key], rule.path)
        where = f"player {p.id}'s Cloud Save key '{cs.key}'"
    elif cs.has_default:  # N37: Default stands in for the whole item
        found, v = resolve(cs.default, rule.path)
        where = f"ExternalData.CloudSave.Default (player {p.id} has no Cloud Save key '{cs.key}')"
    else:
        return False, None, (f"player {p.id} has no Cloud Save key '{cs.key}' and the rule has no "
                             "ExternalData.CloudSave.Default")
    return found, v, None if found else f"{where} has no value at '{'.'.join(rule.path)}'"


def source_values(rule: Rule, players: list[Any]) -> tuple[list[Any] | None, str | None]:
    vals = []
    for p in players:
        found, v, missing = player_value(rule, p)
        if not found:
            return None, missing
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
