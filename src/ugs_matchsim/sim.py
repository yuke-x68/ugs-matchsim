"""Deterministic tick-based matchmaking simulation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .common import InputError, fmt, num
from .flow import Flow, Ticket
from .rules import (EPS, Range, Rule, Rules, active_relaxations, age_of, check_rule,
                    effective_min, effective_rule, resolve, triggered)

PRIO = {"arrival": 0, "relaxation": 1, "match": 2, "timeout": 3}
MAX_TICKS = 2_000_000


@dataclass(frozen=True)
class Fail:
    """One blocking cause found while building a candidate match."""
    kind: str  # "rule" | "count" | "player" | "size"
    rule: str | None
    scope: str  # "match" | "team:<name>"
    detail: str
    rule_obj: Rule | None = field(default=None, compare=False)


@dataclass
class Slot:
    d: int
    i: int
    name: str
    cap: int
    tickets: list[Ticket] = field(default_factory=list)

    @property
    def players(self) -> int:
        return sum(t.size for t in self.tickets)


class Simulator:
    def __init__(self, rules: Rules, flow: Flow):
        self.R = rules
        self.F = flow
        self.matches: list[dict[str, Any]] = []
        self.events: list[tuple[float, int, int, dict[str, Any]]] = []
        self.outcome: dict[str, dict[str, Any]] = {}
        self.by_id = {t.id: t for t in flow.tickets}
        # ticket -> (kind, rule, scope) -> {"with": set, "values": {id: value}, "details": set}
        self.reasons: dict[str, dict[tuple, dict[str, Any]]] = {t.id: {} for t in flow.tickets}
        self.relax_state: dict[tuple, bool] = {}
        self.max_cap = max(int(t.player_count.max) for t in rules.teams)
        self.targets = self._relax_targets()

    # ------------------------------------------------------------ helpers
    def _relax_targets(self) -> list[tuple[str, Any]]:
        out = []
        for r in self.R.match_rules:
            if not r.ignored:
                out += [(f"MatchRules.{r.name}", x) for x in r.relaxations]
        for t in self.R.teams:
            for r in t.team_rules:
                if not r.ignored:
                    out += [(f"Teams.{t.name}.TeamRules.{r.name}", x) for x in r.relaxations]
            out += [(f"Teams.{t.name}.TeamCount", x) for x in t.team_count.relaxations]
            out += [(f"Teams.{t.name}.PlayerCount", x) for x in t.player_count.relaxations]
        return out

    def ev(self, time: float, kind: str, **data: Any) -> None:
        self.events.append((round(time, 6), PRIO[kind], len(self.events), {"kind": kind, **data}))

    def _values(self, rule: Rule | None, tid: str) -> Any:
        """The ticket's own source value(s) for a plain (non-aggregated) rule, else None."""
        if rule is None or rule.op is not None:
            return None
        vals = []
        for p in self.by_id[tid].players:
            found, v = resolve(p.custom, rule.path)
            if not found:
                return None
            if v not in vals:
                vals.append(v)
        return vals[0] if len(vals) == 1 else vals

    def note(self, tid: str, fail: Fail, others: list[str] | None = None) -> None:
        e = self.reasons[tid].setdefault((fail.kind, fail.rule, fail.scope),
                                         {"with": set(), "values": {}, "details": set()})
        e["with"].update(others or [])
        e["details"].add(fail.detail)
        for x in [tid, *(others or [])]:
            v = self._values(fail.rule_obj, x)
            if v is not None:
                e["values"][x] = v

    # --------------------------------------------------------------- run
    def run(self) -> dict[str, Any]:
        tickets = sorted(self.F.tickets, key=lambda t: (t.at, t.id))
        for t in tickets:
            self.ev(t.at, "arrival", ticket=t.id, players=[p.id for p in t.players])
            if t.size > self.max_cap:
                self.note(t.id, Fail("size", None, "match",
                                     f"ticket has {t.size} players but the largest PlayerCount.Max is {self.max_cap}: "
                                     "it can never match"))
        pending = list(tickets)
        waiting: list[Ticket] = []
        k = 0
        while pending or waiting:
            if k > MAX_TICKS:
                raise InputError("simulation exceeded the tick limit; check tickSeconds / timeoutSeconds")
            t = round(k * self.F.tick, 6)
            while pending and pending[0].at <= t + EPS:
                waiting.append(pending.pop(0))
            self._timeouts(waiting, t, strict=True)
            if waiting:
                self._relax_events(waiting, t)
                self._match(waiting, t)
            else:
                self.relax_state = {}
            self._timeouts(waiting, t, strict=False)
            k += 1
        events = [e[3] | {"time": num(e[0])} for e in sorted(self.events, key=lambda e: e[:3])]
        return {"matches": self.matches, "outcome": self.outcome, "events": events,
                "reasons": {tid: self._reason_list(tid) for tid in self.reasons}}

    def _reason_list(self, tid: str) -> list[dict[str, Any]]:
        out = []
        for key in sorted(self.reasons[tid], key=lambda k: (k[0], k[1] or "", k[2])):
            kind, rule, scope = key
            e = self.reasons[tid][key]
            with_ = sorted(e["with"])
            values = {k: e["values"][k] for k in sorted(e["values"])}
            where = "" if scope == "match" else f" in {scope.replace(':', ' ')}"
            who = f" together with {', '.join(with_)}" if with_ else ""
            partners = f" (with {', '.join(with_)})" if with_ else ""
            if values and {tid, *with_} <= set(values):
                shown = ", ".join(f"{k}={fmt(v)}" for k, v in values.items())
                text = f"Rule {rule}{where} is not satisfied{who} (values: {shown})."
            else:
                detail = "; ".join(sorted(e["details"]))
                if kind == "rule":
                    text = f"Rule {rule}{where} is not satisfied{who}: {detail}."
                else:
                    text = f"{detail[0].upper()}{detail[1:]}{partners}."
            out.append({"kind": kind, "rule": rule, "scope": scope, "with": with_,
                        "values": values, "text": text})
        return out

    def _timeouts(self, waiting: list[Ticket], t: float, strict: bool) -> None:
        for tk in list(waiting):
            tt = tk.at + self.F.timeout
            if (tt < t - EPS) if strict else (tt <= t + EPS):
                waiting.remove(tk)
                self.outcome[tk.id] = {"status": "timeout", "time": num(tt)}
                self.ev(tt, "timeout", ticket=tk.id, waited=num(self.F.timeout))

    # ------------------------------------------------------- relaxations
    def _relax_events(self, waiting: list[Ticket], t: float) -> None:
        ages = [t - w.at for w in waiting]
        for n, (label, r) in enumerate(self.targets):
            key = (label, r.index, n)
            now = triggered(r, ages)
            if now and not self.relax_state.get(key):
                observed = age_of(ages, r.age_type)
                self.ev(t, "relaxation", target=label, type=r.type, value=r.value, atSeconds=num(r.at_seconds),
                        ageType=r.age_type, observedAge=num(observed),
                        basis="waiting tickets in the queue at this tick")
            self.relax_state[key] = now

    def _in_effect(self, tickets: list[Ticket], t: float) -> list[dict[str, Any]]:
        ages = [t - x.at for x in tickets]
        out = []
        for label, r in self.targets:
            if triggered(r, ages):
                out.append({"target": label, "type": r.type, "value": r.value, "atSeconds": num(r.at_seconds),
                            "ageType": r.age_type, "observedAge": num(age_of(ages, r.age_type))})
        return out

    # ----------------------------------------------------------- matching
    def _match(self, waiting: list[Ticket], t: float) -> None:
        for anchor in list(waiting):
            if anchor not in waiting:
                continue
            pool = [x for x in waiting if x is not anchor]
            m = self._build(anchor, pool, t)
            if m is not None:
                for tk in m:
                    waiting.remove(tk)

    def _new_slots(self) -> list[Slot]:
        slots = []
        for d, td in enumerate(self.R.teams):
            for i in range(int(td.team_count.max)):
                nm = td.name if td.team_count.max == 1 else f"{td.name} #{i + 1}"
                slots.append(Slot(d, i, nm, int(td.player_count.max)))
        return slots

    def _slot_order(self, slots: list[Slot], tk: Ticket, t: float) -> list[Slot]:
        ages = [t - x.at for s in slots for x in s.tickets] + [t - tk.at]
        req = {d: min(effective_min(td.team_count, ages), td.team_count.max) for d, td in enumerate(self.R.teams)}
        required = sorted((s for s in slots if s.i < req[s.d]), key=lambda s: (s.players, s.d, s.i))
        extra = [s for s in slots if s.i >= req[s.d]]
        return required + extra

    def _check(self, slots: list[Slot], t: float, final: bool, touched: Slot | None = None) -> list[Fail]:
        fails: list[Fail] = []
        all_t = [x for s in slots for x in s.tickets]
        ages = [t - x.at for x in all_t]
        players = [p for x in all_t for p in x.players]
        for r in self.R.match_rules:
            if r.ignored or (r.deferred and not final):
                continue
            enabled, ref = effective_rule(r, ages)
            if not enabled:
                continue
            ok, detail = check_rule(r, ref, players)
            if not ok:
                fails.append(Fail("rule", r.name, "match", str(detail), r))
        for s in slots:
            if not s.tickets or (not final and s is not touched):
                continue
            sp = [p for x in s.tickets for p in x.players]
            for r in self.R.teams[s.d].team_rules:
                if r.ignored or (r.deferred and not final):
                    continue
                enabled, ref = effective_rule(r, ages)
                if not enabled:
                    continue
                ok, detail = check_rule(r, ref, sp)
                if not ok:
                    fails.append(Fail("rule", r.name, f"team:{s.name}", str(detail), r))
        if final:
            for d, td in enumerate(self.R.teams):
                ds = [s for s in slots if s.d == d]
                pmin = effective_min(td.player_count, ages)
                tmin = effective_min(td.team_count, ages)
                nonempty = [s for s in ds if s.tickets]
                small = [s for s in nonempty if s.players < pmin]
                if small:
                    low = min(s.players for s in small)
                    fails.append(Fail("count", None, f"team:{td.name}",
                                      f"{td.name}.PlayerCount.Min={fmt(pmin)} not reachable: "
                                      f"smallest team has only {low} compatible player(s)"))
                if len(nonempty) < tmin:
                    fails.append(Fail("count", None, f"team:{td.name}",
                                      f"{td.name}.TeamCount.Min={fmt(tmin)} not reachable: "
                                      f"only {len(all_t)} compatible ticket(s)"))
        return fails

    def _try_add(self, slots: list[Slot], tk: Ticket, t: float) -> tuple[bool, list[Fail]]:
        used = {p.id for s in slots for x in s.tickets for p in x.players}
        dup = sorted(used & {p.id for p in tk.players})
        if dup:
            return False, [Fail("player", None, "match",
                            f"duplicate player id {dup[0]} (player IDs must differ to be matched together)")]
        fails: list[Fail] = []
        for s in self._slot_order(slots, tk, t):
            if s.players + tk.size > s.cap:
                continue
            s.tickets.append(tk)
            f = self._check(slots, t, False, s)
            if not f:
                return True, []
            s.tickets.pop()
            fails.extend(x for x in f if x not in fails)
        return False, fails

    def _build(self, anchor: Ticket, pool: list[Ticket], t: float) -> list[Ticket] | None:
        slots = self._new_slots()
        ok, fails = self._try_add(slots, anchor, t)
        if not ok:
            for f in fails:
                self.note(anchor.id, f)
            return None
        added = [anchor]
        for x in pool:
            if all(s.players >= s.cap for s in slots):
                break
            ok, fails = self._try_add(slots, x, t)
            if ok:
                added.append(x)
            else:
                ids = [y.id for y in added]
                for f in fails:
                    self.note(x.id, f, ids)
                    for y in added:
                        self.note(y.id, f, [x.id])
        first = self._check(slots, t, True)
        before = list(added)
        while first and len(added) > 1 and self._check(slots, t, True):
            last = added.pop()
            for s in slots:
                if last in s.tickets:
                    s.tickets.remove(last)
        final = self._check(slots, t, True)
        if final:
            for f in first:
                for y in before:
                    self.note(y.id, f, [z.id for z in before if z is not y])
            return None
        return self._emit(slots, added, t)

    def _emit(self, slots: list[Slot], added: list[Ticket], t: float) -> list[Ticket]:
        mid = f"M{len(self.matches) + 1}"
        teams = []
        for s in slots:
            if s.tickets:
                teams.append({"name": s.name, "definition": self.R.teams[s.d].name,
                              "tickets": [x.id for x in s.tickets],
                              "players": [p.id for x in s.tickets for p in x.players]})
                for x in s.tickets:
                    self.outcome[x.id] = {"status": "matched", "time": num(t), "match": mid, "team": s.name}
        tickets = [x for s in slots for x in s.tickets]
        match = {"id": mid, "time": num(t), "anchor": added[0].id, "teams": teams,
                 "relaxations": self._in_effect(tickets, t)}
        self.matches.append(match)
        self.ev(t, "match", match=mid, tickets=sorted(x.id for x in tickets))
        return tickets
