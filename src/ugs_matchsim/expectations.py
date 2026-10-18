"""Expectation evaluation against a simulation result."""

from __future__ import annotations

from typing import Any

from .common import num
from .flow import Expect


def _where(out: dict[str, Any], tid: str) -> str:
    if out["status"] == "matched":
        return f"{tid} matched in {out['match']} at t={out['time']} (team {out['team']})"
    return f"{tid} timed out at t={out['time']}"


def actual(exp: Expect, outcome: dict[str, dict[str, Any]], matches: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Structured description of what really happened to the listed tickets (never empty)."""
    tickets: dict[str, Any] = {}
    for i in exp.tickets:
        o = outcome[i]
        if o["status"] == "matched":
            partners = sorted(x for tm in matches[o["match"]]["teams"] for x in tm["tickets"] if x != i)
            tickets[i] = {"status": "matched", "match": o["match"], "time": o["time"], "team": o["team"],
                          "partners": partners}
        else:
            tickets[i] = {"status": "timeout", "time": o["time"]}
    res: dict[str, Any] = {"tickets": tickets}
    mids = {t["match"] for t in tickets.values() if t["status"] == "matched"}
    if exp.kind in ("together", "sameTeam", "opposingTeams"):
        res["sameMatch"] = len(mids) == 1 and all(t["status"] == "matched" for t in tickets.values())
    if exp.kind == "together":
        res["matchTime"] = matches[next(iter(mids))]["time"] if res["sameMatch"] else None
    if exp.kind in ("sameTeam", "opposingTeams"):
        res["teams"] = [t.get("team") for t in tickets.values()]
    if exp.kind == "apart":
        ids = exp.tickets
        res["sharedMatchPairs"] = [[a, b] for n, a in enumerate(ids) for b in ids[n + 1:]
                                   if tickets[a]["status"] == "matched"
                                   and tickets[a]["match"] == tickets[b].get("match")]
    return res


def evaluate(exp: Expect, outcome: dict[str, dict[str, Any]], matches: dict[str, dict[str, Any]]) -> tuple[bool, str]:
    ids = exp.tickets
    states = "; ".join(_where(outcome[i], i) for i in ids)
    matched = [i for i in ids if outcome[i]["status"] == "matched"]
    unmatched = [i for i in ids if outcome[i]["status"] != "matched"]
    mset = {outcome[i]["match"] for i in matched}
    k = exp.kind
    if k == "matched":
        return (not unmatched, states if not unmatched else f"not matched: {', '.join(unmatched)}. {states}")
    if k == "unmatched":
        return (not matched, states if not matched else f"unexpectedly matched: {', '.join(matched)}. {states}")
    if k == "apart":
        shared = [(a, b) for n, a in enumerate(ids) for b in ids[n + 1:]
                  if outcome[a]["status"] == "matched" and outcome[a].get("match") == outcome[b].get("match")]
        if shared:
            return False, f"{shared[0][0]} and {shared[0][1]} ended in the same match {outcome[shared[0][0]]['match']}. {states}"
        return True, f"no two shared a match. {states}"
    # together / sameTeam / opposingTeams need everyone matched
    if unmatched:
        return False, f"not matched: {', '.join(unmatched)}. {states}"
    if len(mset) != 1:
        return False, f"ended in different matches ({', '.join(sorted(mset))}). {states}"
    mid = next(iter(mset))
    if k == "together":
        if exp.by is not None and matches[mid]["time"] > exp.by + 1e-9:
            return False, f"match {mid} formed at t={matches[mid]['time']}, later than by={num(exp.by)}. {states}"
        return True, states
    teams = [outcome[i]["team"] for i in ids]
    if k == "sameTeam":
        if len(set(teams)) != 1:
            return False, f"in the same match but different teams ({', '.join(teams)}). {states}"
        return True, states
    if k == "opposingTeams":
        if len(set(teams)) != len(teams):
            return False, f"in the same match but not all on different teams ({', '.join(teams)}). {states}"
        return True, states
    raise AssertionError(k)
