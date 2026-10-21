"""Flow (ticket stream + expectations) model and parser."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .common import Diagnostics, InputError, did_you_mean, is_num, loads_lenient, num
from .common import kind as _kind

DEFAULT_TIMEOUT = 60.0  # N31
DEFAULT_MAX_PLAYERS = 150  # N31
DEFAULT_TICK = 1.0

KINDS = {k.lower(): k for k in ("together", "apart", "matched", "unmatched", "sameTeam", "opposingTeams")}
MIN_IDS = {"together": 2, "apart": 2, "matched": 1, "unmatched": 1, "sameTeam": 2, "opposingTeams": 2}


@dataclass
class Player:
    id: str
    custom: dict[str, Any]
    cloud_save: dict[str, Any] = field(default_factory=dict)  # Cloud Save key -> item (externalData.cloudSave)


@dataclass
class Ticket:
    id: str
    at: float
    players: list[Player]
    attributes: dict[str, Any] | None = None

    @property
    def size(self) -> int:
        return len(self.players)


@dataclass
class Expect:
    kind: str
    tickets: list[str]
    by: float | None = None
    name: str | None = None

    @property
    def description(self) -> str:
        if self.name:
            return self.name
        s = f"{self.kind} {', '.join(self.tickets)}"
        if self.by is not None:
            from .common import num
            s += f" by {num(self.by)}"
        return s


@dataclass
class Flow:
    timeout: float
    max_players: int
    tick: float
    tickets: list[Ticket]
    expects: list[Expect] = field(default_factory=list)
    timeout_from: str = "queue.timeoutSeconds"  # where the timeout value came from (shown in reasons)


TOP_KEYS = ["queue", "tickSeconds", "tickets", "expect"]
QUEUE_KEYS = ["timeoutSeconds", "maxPlayersPerTicket"]
TICKET_KEYS = ["id", "at", "players", "customData", "externalData", "attributes"]
PLAYER_KEYS = ["id", "customData", "externalData"]
EXTERNAL_KEYS = ["cloudSave"]
EXPECT_KEYS = [*KINDS.values(), "by", "name"]
ALIASES = {
    "top": {"ticket": "tickets", "expectations": "expect", "expects": "expect", "expected": "expect",
            "tick": "tickSeconds", "ticks": "tickSeconds", "timeoutseconds": "queue.timeoutSeconds",
            "timeout": "queue.timeoutSeconds"},
    "queue": {"timeout": "timeoutSeconds", "maxplayers": "maxPlayersPerTicket"},
    "ticket": {"time": "at", "arrival": "at", "arrive": "at", "arrives": "at", "t": "at", "start": "at",
               "timestamp": "at", "name": "id", "ticketid": "id", "player": "players", "custom": "customData",
               "data": "customData", "customdatas": "customData", "external": "externalData",
               "cloudsave": "externalData.cloudSave"},
    "player": {"playerid": "id", "name": "id", "custom": "customData", "data": "customData",
               "external": "externalData", "cloudsave": "externalData.cloudSave"},
    "external": {"cloud": "cloudSave", "cloud_save": "cloudSave", "cloudsaves": "cloudSave"},
    "expect": {"togther": "together", "same_team": "sameTeam", "sameteams": "sameTeam", "opposing": "opposingTeams",
               "opposingteam": "opposingTeams", "match": "matched", "notmatched": "unmatched",
               "deadline": "by", "description": "name"},
}


class _Errors:
    def __init__(self, file: str):
        self.file = file
        self.items: list[str] = []

    def add(self, path: str, what: str, expected: str) -> None:
        self.items.append(f"{self.file}: {path}: {what}; expected {expected}")

    def obj(self, v: Any, path: str, keys: list[str], aliases: dict[str, str]) -> dict[str, Any] | None:
        """Strict, case-insensitive object view: lower-case key -> value. Unknown keys are errors."""
        if not isinstance(v, dict):
            self.add(path, f"{_kind(v)}", "an object")
            return None
        out: dict[str, Any] = {}
        for k, val in v.items():
            lk = k.lower()
            if lk in {x.lower() for x in keys}:
                if lk in out:
                    self.add(f"{path}.{k}", f"duplicate key (keys are case-insensitive)", "each key once")
                out[lk] = val
                continue
            hint = did_you_mean(k, keys, aliases)
            more = f"; did you mean '{hint}'?" if hint else ""
            self.add(f"{path}.{k}" if path else k, f"unknown key '{k}'",
                     f"one of {', '.join(keys)}{more}")
        return out


def _is_id(v: Any) -> bool:
    return isinstance(v, (str, int)) and not isinstance(v, bool) and str(v) != ""


def _player_data(er: _Errors, d: dict[str, Any], ctx: str, diag: Diagnostics) -> tuple[dict[str, Any], dict[str, Any]]:
    """customData and externalData.cloudSave of one player (a players[] entry or the ticket shorthand)."""
    cd = d.get("customdata", {})
    if not isinstance(cd, dict):
        er.add(f"{ctx}.customData", _kind(cd), "an object, e.g. {\"GameVersion\": \"1.2.0\"}")
        cd = {}
    for k in cd:
        if k.lower() == "externaldata":
            diag.warn(f"{ctx}.customData.{k}: not read by any rule; a Players.CustomData.ExternalData.CloudSave.* "
                      f"source reads {ctx}.externalData.cloudSave instead")
    cloud: Any = {}
    if "externaldata" in d:
        ext = er.obj(d["externaldata"], f"{ctx}.externalData", EXTERNAL_KEYS, ALIASES["external"]) or {}
        cloud = ext.get("cloudsave", {})
    if not isinstance(cloud, dict):
        er.add(f"{ctx}.externalData.cloudSave", _kind(cloud),
               "an object of Cloud Save key -> item, e.g. {\"progress\": {\"rating\": 1200}}")
        cloud = {}
    return cd, cloud


def parse_flow(data: Any, diag: Diagnostics, file: str = "flow",
               queue_defaults: dict[str, tuple[Any, str]] | None = None) -> Flow:
    """Strict flow parser. Collects every error and raises one InputError (one line per error).

    queue_defaults: values from a .mmq rules file (Rules.queue); a key written in the flow wins.
    """
    er = _Errors(file)
    top = er.obj(data, "(root)", TOP_KEYS, ALIASES["top"]) or {}
    q = er.obj(top["queue"], "queue", QUEUE_KEYS, ALIASES["queue"]) if "queue" in top else {}
    q = q or {}
    rq = queue_defaults or {}

    def source(key: str) -> str:
        return f"queue.{key}" if key.lower() in q or key not in rq else rq[key][1]

    timeout = q.get("timeoutseconds", rq.get("timeoutSeconds", (DEFAULT_TIMEOUT,))[0])
    maxp = q.get("maxplayersperticket", rq.get("maxPlayersPerTicket", (DEFAULT_MAX_PLAYERS,))[0])
    tick = top.get("tickseconds", DEFAULT_TICK)
    if not is_num(timeout) or timeout <= 0:
        er.add("queue.timeoutSeconds", f"got {timeout!r}", "a number > 0 (seconds)")
        timeout = DEFAULT_TIMEOUT
    if not isinstance(maxp, int) or isinstance(maxp, bool) or maxp < 1:
        er.add("queue.maxPlayersPerTicket", f"got {maxp!r}", "an integer >= 1")
        maxp = DEFAULT_MAX_PLAYERS
    if not is_num(tick) or tick <= 0:
        er.add("tickSeconds", f"got {tick!r}", "a number > 0 (seconds)")
        tick = DEFAULT_TICK
    raw = top.get("tickets")
    tickets: list[Ticket] = []
    seen: set[str] = set()
    if not isinstance(raw, list) or not raw:
        er.add("tickets", "missing" if raw is None else f"{_kind(raw)}{' (empty)' if raw == [] else ''}",
               "a non-empty array of ticket objects")
        raw = []
    for i, t in enumerate(raw):
        ctx = f"tickets[{i}]"
        d = er.obj(t, ctx, TICKET_KEYS, ALIASES["ticket"])
        if d is None:
            continue
        tid = None
        if "id" not in d:
            er.add(f"{ctx}.id", "missing", "a non-empty string (unique ticket id)")
        elif not _is_id(d["id"]):
            er.add(f"{ctx}.id", f"got {d['id']!r}", "a non-empty string (unique ticket id)")
        else:
            tid = str(d["id"])
            if tid in seen:
                er.add(f"{ctx}.id", f"duplicate ticket id '{tid}'", "ids unique across tickets")
            seen.add(tid)
        at = d.get("at", 0)
        if not is_num(at) or at < 0:
            er.add(f"{ctx}.at", f"got {at!r}", "a number >= 0 (seconds from the start of the run)")
            at = 0
        shorthand = [k for k in ("customData", "externalData") if k.lower() in d]
        if "players" in d and shorthand:
            er.add(ctx, f"both players and {' and '.join(shorthand)} given",
                   "either players (list; each player has its own customData/externalData) "
                   "or the one-player customData/externalData shorthand, not both")
            continue
        players: list[Player] = []
        if "players" in d:
            pl = d["players"]
            if not isinstance(pl, list) or not pl:
                er.add(f"{ctx}.players", _kind(pl) if not isinstance(pl, list) else "empty array",
                       "a non-empty array of {id, customData, externalData} objects")
            else:
                for j, p in enumerate(pl):
                    pctx = f"{ctx}.players[{j}]"
                    pd = er.obj(p, pctx, PLAYER_KEYS, ALIASES["player"])
                    if pd is None:
                        continue
                    if "id" not in pd or not _is_id(pd["id"]):
                        er.add(f"{pctx}.id", "missing" if "id" not in pd else f"got {pd['id']!r}",
                               "a non-empty string (player id)")
                        continue
                    players.append(Player(str(pd["id"]), *_player_data(er, pd, pctx, diag)))
        elif tid is not None:
            players.append(Player(tid, *_player_data(er, d, ctx, diag)))
        if len(players) > maxp:
            er.add(f"{ctx}.players", f"ticket '{tid}' has {len(players)} players",
                   f"at most {source('maxPlayersPerTicket')}={maxp} players")
        attrs = d.get("attributes")
        if attrs is not None:
            if not isinstance(attrs, dict):
                er.add(f"{ctx}.attributes", _kind(attrs), "an object")
            else:
                diag.unsupp(f"ticket '{tid}' attributes",
                            "attributes are only used by queue pool filters, which are not simulated; "
                            "they are ignored and the ticket joins the single pool described by the rules file")
        if tid is not None and players:
            tickets.append(Ticket(tid, float(at), players, attrs))
    expects: list[Expect] = []
    raw_exp = top.get("expect")
    if raw_exp is None:
        raw_exp = []
    if not isinstance(raw_exp, list):
        er.add("expect", _kind(raw_exp), "an array of expectation objects")
        raw_exp = []
    for i, e in enumerate(raw_exp):
        ctx = f"expect[{i}]"
        d = er.obj(e, ctx, EXPECT_KEYS, ALIASES["expect"])
        if d is None:
            continue
        kinds = [k for k in d if k in KINDS]
        if len(kinds) != 1:
            er.add(ctx, f"{len(kinds)} expectation kinds given",
                   f"exactly one kind key of {', '.join(KINDS.values())}")
            continue
        kind = KINDS[kinds[0]]
        ids = d[kinds[0]]
        path = f"{ctx}.{kind}"
        if not isinstance(ids, list) or not all(_is_id(x) for x in ids):
            er.add(path, _kind(ids) if not isinstance(ids, list) else "array with non-id items",
                   "an array of ticket ids, e.g. [\"A\", \"B\"]")
            continue
        ids = [str(x) for x in ids]
        if len(ids) < MIN_IDS[kind]:
            er.add(path, f"{len(ids)} id(s)", f"at least {MIN_IDS[kind]} ticket id(s)")
        for x in ids:
            if x not in seen:
                hint = did_you_mean(x, sorted(seen))
                er.add(path, f"unknown ticket id '{x}'",
                       "an id defined in tickets" + (f"; did you mean '{hint}'?" if hint else ""))
        by = None
        if "by" in d:
            if kind != "together":
                er.add(f"{ctx}.by", f"not valid with {kind}", "'by' only together with 'together'")
            elif not is_num(d["by"]):
                er.add(f"{ctx}.by", f"got {d['by']!r}", "a number (seconds from t=0)")
            else:
                by = float(d["by"])
        name = d.get("name")
        if name is not None and not isinstance(name, str):
            er.add(f"{ctx}.name", _kind(name), "a string")
            name = None
        expects.append(Expect(kind, ids, by, name))
    if er.items:
        raise InputError("\n".join(er.items))
    for key, val in (("timeoutSeconds", timeout), ("maxPlayersPerTicket", maxp)):
        if key.lower() in q and key in rq and val != rq[key][0]:
            rv, where = rq[key]
            diag.warn(f"queue.{key}: the flow sets {num(val)} but the rules file sets {num(rv)} ({where}); "
                      f"the flow value {num(val)} is used")
    return Flow(float(timeout), maxp, float(tick), tickets, expects, source("timeoutSeconds"))


def load_flow(text: str, diag: Diagnostics, file: str = "flow file",
              queue_defaults: dict[str, tuple[Any, str]] | None = None) -> Flow:
    return parse_flow(loads_lenient(text, file), diag, file, queue_defaults)
