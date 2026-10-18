import pytest

from helpers import matched_sets, outcome, rules_1v1, simulate, tk
from ugs_matchsim.common import Diagnostics, InputError
from ugs_matchsim.rules import parse_rules


def rule(type_, source, **kw):
    return {"Name": "R", "Type": type_, "Source": f"Players.CustomData.{source}", **kw}


def pair(r, a, b, **kw):
    d = simulate(rules_1v1(r, **kw), [tk("A", **a), tk("B", 0, **b)])
    return d, bool(d["matches"])


def test_equality():
    assert pair(rule("Equality", "V"), {"V": 1}, {"V": 1})[1]
    assert not pair(rule("Equality", "V"), {"V": 1}, {"V": 2})[1]


def test_equality_reference_and_not():
    assert pair(rule("Equality", "V", Reference="x"), {"V": "x"}, {"V": "x"})[1]
    assert not pair(rule("Equality", "V", Reference="x"), {"V": "x"}, {"V": "y"})[1]
    assert pair(rule("Equality", "V", Not=True), {"V": 1}, {"V": 2})[1]
    assert not pair(rule("Equality", "V", Not=True), {"V": 1}, {"V": 1})[1]


def test_nested_path_and_missing_field():
    r = rule("Equality", "Prefs.Mode")
    assert pair(r, {"Prefs": {"Mode": "a"}}, {"Prefs": {"Mode": "a"}})[1]
    d, ok = pair(r, {"Prefs": {"Mode": "a"}}, {})
    assert not ok and any("no value" in x["text"] for x in outcome(d, "B")["reasons"])


def test_difference_inclusive():
    r = rule("Difference", "S", Reference=100)
    assert pair(r, {"S": 1000}, {"S": 1100})[1]
    assert not pair(r, {"S": 1000}, {"S": 1101})[1]
    assert not pair(rule("Difference", "S", Reference=100, Not=True), {"S": 1000}, {"S": 1050})[1]


@pytest.mark.parametrize("t,ok_vals,bad_vals", [
    ("LessThan", (4, 4), (5, 4)),
    ("LessThanEqual", (5, 5), (6, 5)),
    ("GreaterThan", (6, 6), (5, 6)),
    ("GreaterThanEqual", (5, 5), (4, 5)),
])
def test_comparators_every_player(t, ok_vals, bad_vals):
    r = rule(t, "S", Reference=5)
    assert pair(r, {"S": ok_vals[0]}, {"S": ok_vals[1]})[1]
    assert not pair(r, {"S": bad_vals[0]}, {"S": bad_vals[1]})[1]


def test_comparator_not():
    r = rule("GreaterThan", "S", Reference=5, Not=True)
    assert pair(r, {"S": 1}, {"S": 2})[1]
    assert not pair(r, {"S": 9}, {"S": 8})[1]  # N12: Not negates the whole result (all > 5)


def test_inlist_and_not():
    r = rule("InList", "C", Reference=["a", "b"])
    assert pair(r, {"C": "a"}, {"C": "b"})[1]
    assert not pair(r, {"C": "a"}, {"C": "z"})[1]
    rn = rule("InList", "C", Reference=["banned"], Not=True)
    assert pair(rn, {"C": "ok"}, {"C": "fine"})[1]
    assert not pair(rn, {"C": "banned"}, {"C": "banned"})[1]  # N12: whole-rule negation


def test_intersection_overlap():
    r = rule("Intersection", "M", Overlap=2)
    assert pair(r, {"M": [1, 2, 3]}, {"M": [2, 3, 4]})[1]
    assert not pair(r, {"M": [1, 2, 3]}, {"M": [3, 4]})[1]
    rr = rule("Intersection", "M", Overlap=1, Reference=["x"])
    assert pair(rr, {"M": ["x", "y"]}, {"M": ["x"]})[1]
    assert not pair(rr, {"M": ["y"]}, {"M": ["x"]})[1]
    rn = rule("Intersection", "M", Overlap=1, Not=True)
    assert pair(rn, {"M": [1]}, {"M": [2]})[1]


def test_operations_in_team_scope():
    # two players on one team, Avg over players
    rules = rules_1v1(pc=(2, 2), tc=(1, 1),
                      team_rules=[rule("GreaterThanEqual", "L.Avg", Reference=10)])
    d = simulate(rules, [tk("A", L=5), tk("B", L=15), tk("C", L=1)])
    assert matched_sets(d) == [["A", "B"]]
    for op, ref, expected in [("Sum", 20, True), ("Min", 5, True), ("Max", 15, True), ("Median", 10, True),
                              ("Count", 2, True), ("Count", 1, False)]:
        r = rules_1v1(pc=(2, 2), tc=(1, 1), team_rules=[rule("LessThanEqual", f"L.{op}", Reference=ref)])
        got = simulate(r, [tk("A", L=5), tk("B", L=15)])["matches"]
        assert bool(got) == expected, op


def test_enable_rule_false_means_not_applied():
    assert pair(rule("Equality", "V", EnableRule=False), {"V": 1}, {"V": 2})[1]


def test_match_vs_team_rule_scope():
    # team rule only constrains players inside one team
    team = rules_1v1(pc=(2, 2), tc=(2, 2), team_rules=[rule("Equality", "Clan")])
    t = [tk("A", Clan="x"), tk("B", Clan="x"), tk("C", Clan="y"), tk("D", Clan="y")]
    d = simulate(team, t)
    assert matched_sets(d) == [["A", "B", "C", "D"]]
    assert sorted(sorted(x["tickets"]) for x in d["matches"][0]["teams"]) == [["A", "B"], ["C", "D"]]
    match = rules_1v1(rule("Equality", "Clan"), pc=(2, 2), tc=(2, 2))
    assert simulate(match, t)["matches"] == []


def test_invalid_rules_are_input_errors():
    with pytest.raises(InputError):
        parse_rules(rules_1v1({"Type": "Difference", "Source": "Players.CustomData.S"}), Diagnostics())
    with pytest.raises(InputError):
        parse_rules({"Name": "x"}, Diagnostics())


def test_case_insensitive_keys_and_unknown_key_warning():
    diag = Diagnostics()
    r = {"name": "x", "matchdefinition": {"teams": [{"name": "T", "teamcount": {"min": 1, "max": 1},
         "playercount": {"min": 1, "max": 1}}], "matchrules": [], "Bogus": 1}}
    parse_rules(r, diag)
    assert any("Bogus" in w for w in diag.warnings)


def test_unsupported_elements_collected():
    diag = Diagnostics()
    r = rules_1v1({"Name": "Q", "Type": "LessThanEqual", "Source": "Players.QoSResults.Latency", "Reference": 100},
                  {"Name": "D", "Type": "DoubleDifference", "Source": "Players.CustomData.S", "Reference": 1},
                  {"Name": "E", "Type": "Equality", "Source": "Players.CustomData.ExternalData.Leaderboard.Tier"})
    r["BackfillEnabled"] = True
    parse_rules(r, diag)
    text = " ".join(u["element"] + u["effect"] for u in diag.unsupported)
    assert "QoS" in text and "DoubleDifference" in text and "ExternalData" in text and "BackfillEnabled" in text
