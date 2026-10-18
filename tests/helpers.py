from ugs_matchsim.common import Diagnostics
from ugs_matchsim.flow import parse_flow
from ugs_matchsim.rules import parse_rules
from ugs_matchsim.runner import run


def rules_1v1(*match_rules, team_rules=(), pc=(1, 1), tc=(2, 2), pc_relax=(), tc_relax=()):
    return {
        "Name": "t",
        "MatchDefinition": {
            "Teams": [{"Name": "Main",
                       "TeamCount": {"Min": tc[0], "Max": tc[1], "Relaxations": list(tc_relax)},
                       "PlayerCount": {"Min": pc[0], "Max": pc[1], "Relaxations": list(pc_relax)},
                       "TeamRules": list(team_rules)}],
            "MatchRules": list(match_rules),
        },
        "BackfillEnabled": False,
    }


def tk(tid, at=0, **custom):
    return {"id": tid, "at": at, "customData": custom}


def simulate(rules, tickets, expect=(), **flow_extra):
    diag = Diagnostics()
    r = parse_rules(rules, diag)
    f = parse_flow({"queue": {"timeoutSeconds": flow_extra.pop("timeout", 20)}, "tickets": tickets,
                    "expect": list(expect), **flow_extra}, diag)
    return run(r, f, diag, "rules.json", "flow.json")


def matched_sets(doc):
    return sorted(sorted(t for tm in m["teams"] for t in tm["tickets"]) for m in doc["matches"])


def outcome(doc, tid):
    return next(t for t in doc["tickets"] if t["id"] == tid)
