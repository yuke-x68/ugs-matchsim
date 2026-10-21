"""Glue: parse inputs, simulate, evaluate expectations, build the result document."""

from __future__ import annotations

import json
import os
from typing import Any

from . import FLOW_FORMAT, JSON_SCHEMA, __version__
from .common import Diagnostics, num
from .expectations import actual, evaluate
from .flow import Flow
from .rules import Rules
from .sim import Simulator

INTERP = {
    "N1": "A match forms as soon as every count Min is satisfied; it is filled greedily up to Max, never held back.",
    "N2": "Matches form only on simulation ticks (tickSeconds, default 1 s); relaxations are evaluated at tick time.",
    "N3": "Tickets are considered oldest first (arrival, then ticket id); each match is anchored on the oldest ticket that can form one.",
    "N4": "Feasibility only: the first valid match in that deterministic order wins; no scoring.",
    "N5": "AgeType Average = mean age of the tickets (not players) in the candidate match; Oldest = max, Youngest = min.",
    "N6": "A relaxation is evaluated per candidate match: active if the candidate's age statistic >= AtSeconds (inclusive).",
    "N7": "Ticket age = simulated seconds since the ticket's arrival time.",
    "N8": "Several triggered relaxations on one field apply in ascending AtSeconds order (ties: list order); the last wins.",
    "N9": "Omitted AgeType defaults to Oldest; Value is ignored for RuleControl.Enable/Disable.",
    "N10": "Difference holds when max - min <= Reference (inclusive).",
    "N11": "A comparison rule on a per-player list must hold for every player; with an operation suffix it applies to the single result.",
    "N12": "Not negates the whole rule result (Not + Equality = 'not all equal').",
    "N13": "Equality/Difference over a single value are trivially true.",
    "N14": "Equality with a Reference: every value must equal the Reference.",
    "N15": "Intersection: size of the common items across all players (and the Reference, if given) must be >= Overlap.",
    "N16": "A player without the referenced custom-data field makes an enabled rule unsatisfiable (even with Not).",
    "N17": "Operation suffixes flatten the players' values (arrays expand) and aggregate across all players in scope.",
    "N18": "A ticket is atomic: its players always land on the same team of the same match.",
    "N19": "Tickets go to the required team slots (TeamCount.Min) with the fewest players first; extra slots up to TeamCount.Max are used only when required ones are full or rule-incompatible.",
    "N20": "Every team definition contributes TeamCount.Min..Max teams of PlayerCount.Min..Max players.",
    "N21": "A match needs >= TeamCount.Min non-empty teams, each with >= PlayerCount.Min players.",
    "N23": "A ticket times out when age >= timeoutSeconds; a match formed on the same tick wins; the timeout is stamped at arrival + timeout.",
    "N27": "A ticket with more players than queue.maxPlayersPerTicket is an input error; one larger than every team's PlayerCount.Max can never match.",
    "N31": "Defaults when the inputs omit them (the flow, else a .mmq rules file): timeoutSeconds 60, maxPlayersPerTicket 150, tickSeconds 1.",
    "N32": "A trailing source segment named Count/Median/Avg/Sum/Min/Max (after at least one field segment) is always read as an operation.",
    "N33": "Count counts values that are neither null nor false.",
    "N34": "Rules with Not or an operation suffix are not monotone; they are checked on the finished candidate only (tickets are then trimmed from the end until valid).",
    "N36": "Two tickets sharing a player id are never put into the same match.",
}


def used_interpretations(rules: Rules, flow: Flow) -> list[str]:
    all_rules = list(rules.match_rules) + [r for t in rules.teams for r in t.team_rules]
    live = [r for r in all_rules if not r.ignored]
    has_relax = any(t.team_count.relaxations or t.player_count.relaxations for t in rules.teams) or any(
        r.relaxations for r in live)
    relaxations = [x for r in live for x in r.relaxations] + [
        x for t in rules.teams for x in t.team_count.relaxations + t.player_count.relaxations]
    used = {"N1", "N2", "N3", "N4", "N7", "N18", "N19", "N20", "N21", "N23", "N27", "N31", "N36"}
    if has_relax:
        used |= {"N6", "N8", "N9"}
    if any(x.age_type == "Average" for x in relaxations):
        used.add("N5")
    types = {r.type for r in live}
    if "Difference" in types:
        used.add("N10")
    if types & {"LessThan", "LessThanEqual", "GreaterThan", "GreaterThanEqual"}:
        used.add("N11")
    if any(r.not_ for r in live):
        used.add("N12")
    if types & {"Equality", "Difference"}:
        used.add("N13")
    if any(r.type == "Equality" and r.reference is not None for r in live):
        used.add("N14")
    if "Intersection" in types:
        used.add("N15")
    if live:
        used.add("N16")
    if any(r.op for r in live):
        used |= {"N17", "N32", "N34"}
    if any(r.op == "Count" for r in live):
        used.add("N33")
    if any(r.not_ for r in live):
        used.add("N34")
    return sorted(used, key=lambda s: int(s[1:]))


def run(rules: Rules, flow: Flow, diag: Diagnostics, rules_file: str, flow_file: str) -> dict[str, Any]:
    res = Simulator(rules, flow).run()
    outcome, matches = res["outcome"], res["matches"]
    by_id = {m["id"]: m for m in matches}
    exps = []
    for n, e in enumerate(flow.expects):
        ok, why = evaluate(e, outcome, by_id)
        exps.append({"index": n, "name": e.description, "kind": e.kind, "tickets": e.tickets,
                     "by": None if e.by is None else num(e.by), "passed": ok,
                     "actual": actual(e, outcome, by_id), "text": why})
    tickets = []
    for t in sorted(flow.tickets, key=lambda t: (t.at, t.id)):
        o = outcome[t.id]
        item = {"id": t.id, "arrival": num(t.at), "players": [p.id for p in t.players],
                "outcome": o["status"], "time": o["time"], "waited": num(o["time"] - t.at)}
        if o["status"] == "matched":
            item["match"] = o["match"]
            item["team"] = o["team"]
            item["with"] = sorted(x for tm in by_id[o["match"]]["teams"] for x in tm["tickets"] if x != t.id)
        reasons = list(res["reasons"][t.id]) if (o["time"] > t.at + 1e-9 or o["status"] != "matched") else []
        if o["status"] != "matched":
            reasons.append({"kind": "timeout", "rule": None, "scope": "match", "with": [], "values": {},
                            "text": f"Timed out at t={o['time']} after waiting {num(flow.timeout)} s "
                                    f"({flow.timeout_from}) without forming a match."})
        item["reasons"] = reasons
        tickets.append(item)
    n_match = sum(1 for t in tickets if t["outcome"] == "matched")
    return {
        "schemaVersion": JSON_SCHEMA,
        "tool": {"name": "ugs-matchsim", "version": __version__, "flowFormat": FLOW_FORMAT, "unofficial": True},
        "rules": {"name": rules.name, "file": os.path.basename(rules_file)},
        "flow": {"file": os.path.basename(flow_file), "tickSeconds": num(flow.tick),
                 "timeoutSeconds": num(flow.timeout)},
        "summary": {"tickets": len(tickets), "matches": len(matches), "ticketsMatched": n_match,
                    "ticketsTimedOut": len(tickets) - n_match,
                    "expectationsPassed": sum(1 for e in exps if e["passed"]),
                    "expectationsFailed": sum(1 for e in exps if not e["passed"])},
        "expectations": exps, "matches": matches, "tickets": tickets, "events": res["events"],
        "warnings": diag.warnings, "unsupported": diag.unsupported,
        "interpretations": [{"id": i, "text": INTERP[i]} for i in used_interpretations(rules, flow)],
    }


def dumps(doc: dict[str, Any]) -> str:
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
