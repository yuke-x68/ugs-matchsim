import pytest

from helpers import matched_sets, outcome, rules_1v1, simulate, tk
from ugs_matchsim.common import Diagnostics, InputError, loads_lenient
from ugs_matchsim.flow import parse_flow
from ugs_matchsim.runner import dumps

EQ = {"Name": "V", "Type": "Equality", "Source": "Players.CustomData.V"}
DIFF = {"Name": "S", "Type": "Difference", "Source": "Players.CustomData.S", "Reference": 100}


def relax(type_, at, value=None, age="Oldest"):
    r = {"Type": type_, "AtSeconds": at, "AgeType": age}
    if value is not None:
        r["Value"] = value
    return r


def test_reference_replace_after_oldest_age():
    rule = {**DIFF, "Relaxations": [relax("ReferenceControl.Replace", 5, 500)]}
    d = simulate(rules_1v1(rule), [tk("A", 0, S=1000), tk("B", 1, S=1400)])
    assert d["matches"][0]["time"] == 5
    assert d["matches"][0]["relaxations"][0]["type"] == "ReferenceControl.Replace"
    assert any(e["kind"] == "relaxation" and e["time"] == 5 for e in d["events"])


def test_age_types():
    # A at 0, B at 4: at t=6 oldest 6, average 4, youngest 2
    for age, expected in [("Oldest", 6), ("Average", 8), ("Youngest", 10)]:
        rule = {**DIFF, "Relaxations": [relax("ReferenceControl.Replace", 4 if age != "Youngest" else 2, 500, age)]}
        d = simulate(rules_1v1(rule), [tk("A", 0, S=1000), tk("B", 4, S=1400)])
        # Oldest>=4 -> t=4; Average>=4 -> (t+t-4)/2>=4 -> t=6; Youngest>=2 -> t=6
        want = {"Oldest": 4, "Average": 6, "Youngest": 6}[age]
        assert d["matches"][0]["time"] == want, age


def test_rule_control_enable_and_disable():
    en = {**EQ, "EnableRule": False, "Relaxations": [relax("RuleControl.Enable", 3)]}
    d = simulate(rules_1v1(en), [tk("A", 0, V=1), tk("B", 0, V=2)])
    assert d["matches"][0]["time"] == 0  # not applied before relaxation
    dis = {**EQ, "Relaxations": [relax("RuleControl.Disable", 3)]}
    d = simulate(rules_1v1(dis), [tk("A", 0, V=1), tk("B", 0, V=2)])
    assert d["matches"][0]["time"] == 3


def test_player_count_replace_min_and_team_count_replace_min():
    pc = rules_1v1(pc=(3, 3), tc=(1, 1), pc_relax=[relax("RangeControl.ReplaceMin", 4, 1)])
    d = simulate(pc, [tk("A"), tk("B")])
    assert d["matches"][0]["time"] == 4 and matched_sets(d) == [["A", "B"]]
    tc = rules_1v1(pc=(1, 1), tc=(2, 2), tc_relax=[relax("RangeControl.ReplaceMin", 5, 1)])
    d = simulate(tc, [tk("A")])
    assert d["matches"][0]["time"] == 5 and matched_sets(d) == [["A"]]


def test_counts_not_reached_reason_and_timeout():
    d = simulate(rules_1v1(), [tk("A")], timeout=5)
    a = outcome(d, "A")
    assert a["outcome"] == "timeout" and a["time"] == 5
    assert any("TeamCount.Min=2 not reachable: only 1 compatible ticket" in r["text"] for r in a["reasons"])


def test_blocked_reason_names_rule_values_and_tickets():
    d = simulate(rules_1v1(EQ), [tk("A", 0, V="1.2.0"), tk("B", 0, V="1.1.0")], timeout=3)
    r = next(x for x in outcome(d, "A")["reasons"] if x["kind"] == "rule")
    assert (r["rule"], r["scope"], r["with"], r["values"]) == ("V", "match", ["B"], {"A": "1.2.0", "B": "1.1.0"})


def test_timeout_boundary_match_wins_same_tick():
    d = simulate(rules_1v1(), [tk("A", 0), tk("B", 5)], timeout=5)
    assert matched_sets(d) == [["A", "B"]]  # B arrives exactly when A would time out


def test_max_fill_and_leftover():
    d = simulate(rules_1v1(pc=(1, 3), tc=(1, 1)), [tk(x) for x in "ABCDE"])
    assert matched_sets(d) == [["A", "B", "C"], ["D", "E"]]


def test_multi_player_ticket_stays_together():
    rules = rules_1v1(pc=(2, 2), tc=(2, 2))
    party = {"id": "P", "at": 0, "players": [{"id": "p1", "customData": {}}, {"id": "p2", "customData": {}}]}
    d = simulate(rules, [party, tk("S1", 1), tk("S2", 2)])
    teams = {tuple(sorted(t["tickets"])) for t in d["matches"][0]["teams"]}
    assert teams == {("P",), ("S1", "S2")}


def test_ticket_too_big_never_matches():
    rules = rules_1v1(pc=(1, 1), tc=(2, 2))
    party = {"id": "P", "at": 0, "players": [{"id": "p1"}, {"id": "p2"}]}
    d = simulate(rules, [party, tk("S")], timeout=3)
    assert d["matches"] == [] and any("can never match" in r["text"] for r in outcome(d, "P")["reasons"])


def test_duplicate_player_ids_not_matched_together():
    a = {"id": "A", "at": 0, "players": [{"id": "same"}]}
    b = {"id": "B", "at": 0, "players": [{"id": "same"}]}
    assert simulate(rules_1v1(), [a, b], timeout=3)["matches"] == []


def test_multiple_team_definitions():
    rules = rules_1v1()
    rules["MatchDefinition"]["Teams"] = [
        {"Name": "Red", "TeamCount": {"Min": 1, "Max": 1}, "PlayerCount": {"Min": 1, "Max": 1}},
        {"Name": "Blue", "TeamCount": {"Min": 1, "Max": 1}, "PlayerCount": {"Min": 1, "Max": 1}}]
    d = simulate(rules, [tk("A"), tk("B")])
    assert sorted(t["name"] for t in d["matches"][0]["teams"]) == ["Blue", "Red"]


def test_determinism_byte_identical():
    rules = rules_1v1(DIFF)
    tickets = [tk(c, i % 3, S=1000 + 70 * i) for i, c in enumerate("ABCDEFG")]
    assert dumps(simulate(rules, tickets)) == dumps(simulate(rules, tickets))
    assert "20" not in dumps(simulate(rules, tickets)).split('"tool"')[0]


def test_tiebreak_by_ticket_id():
    d = simulate(rules_1v1(pc=(1, 1), tc=(2, 2)), [tk("B"), tk("A"), tk("C")])
    assert d["matches"][0]["anchor"] == "A"


# ------------------------------------------------------------ flow parsing

def test_flow_comments_trailing_commas_and_shorthand():
    text = """{ // c
      "tickets": [ { "id": "A", "customData": {"V": "http://x//y"}, }, /* b */ { "id": "B", "at": 1.5 }, ],
      "expect": [ {"together": ["A","B"],}, ],
    }"""
    f = __import__("ugs_matchsim.flow", fromlist=["x"]).parse_flow(loads_lenient(text, "f"), Diagnostics())
    assert f.tickets[0].players[0].id == "A" and f.tickets[0].players[0].custom["V"] == "http://x//y"
    assert f.tickets[1].at == 1.5 and f.expects[0].kind == "together"


@pytest.mark.parametrize("bad", [
    {"tickets": [{"id": "A"}], "expect": [{"bogus": ["A"]}]},
    {"tickets": [{"id": "A"}], "expect": [{"matched": ["Z"]}]},
    {"tickets": [{"id": "A"}, {"id": "A"}]},
    {"tickets": [{"id": "A"}], "expect": [{"matched": ["A"], "by": 3}]},
    {"tickets": [{"id": "A", "players": [{"id": "a"}], "customData": {}}]},
    {"queue": {"maxPlayersPerTicket": 1}, "tickets": [{"id": "A", "players": [{"id": "a"}, {"id": "b"}]}]},
])
def test_flow_input_errors(bad):
    with pytest.raises(InputError):
        parse_flow(bad, Diagnostics())
