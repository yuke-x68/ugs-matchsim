import json
from pathlib import Path

import pytest

from helpers import matched_sets, outcome, rules_1v1, simulate
from ugs_matchsim.cli import main
from ugs_matchsim.common import Diagnostics, InputError
from ugs_matchsim.flow import parse_flow
from ugs_matchsim.rules import parse_rules

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
SRC = "Players.CustomData.ExternalData.CloudSave.progress.rating"


def cs_rule(source=SRC, type_="Difference", reference=100, **cloud_save):
    r = {"Name": "Rating", "Type": type_, "Source": source, "Reference": reference}
    if cloud_save:
        r["ExternalData"] = {"CloudSave": cloud_save}
    return r


def ct(tid, at=0, rating=None, **custom):
    """One-player ticket; rating goes to Cloud Save key 'progress'."""
    t = {"id": tid, "at": at, "customData": custom}
    if rating is not None:
        t["externalData"] = {"cloudSave": {"progress": {"rating": rating}}}
    return t


def rule_reasons(doc, tid):
    return [r["text"] for r in outcome(doc, tid)["reasons"] if r["kind"] == "rule"]


def test_values_come_from_external_data_not_custom_data():
    d = simulate(rules_1v1(cs_rule()), [ct("A", rating=1000), ct("B", rating=1050)])
    assert matched_sets(d) == [["A", "B"]] and d["unsupported"] == []
    # the same path written into customData is not read (N29)
    b = ct("B", rating=1500, ExternalData={"CloudSave": {"progress": {"rating": 1000}}})
    d = simulate(rules_1v1(cs_rule()), [ct("A", rating=1000), b], timeout=3)
    assert d["matches"] == []
    assert any("A=1000" in x and "B=1500" in x for x in rule_reasons(d, "A"))


def test_default_replaces_the_whole_item():
    rule = cs_rule(Default={"rating": 1000, "season": 1})
    assert matched_sets(simulate(rules_1v1(rule), [ct("A", rating=1000), ct("B")])) == [["A", "B"]]
    d = simulate(rules_1v1(rule), [ct("A", rating=1300), ct("B")], timeout=3)
    assert d["matches"] == [] and any("B=1000" in x for x in rule_reasons(d, "B"))
    assert matched_sets(simulate(rules_1v1(rule), [ct("A"), ct("B")])) == [["A", "B"]]
    ids = [i["id"] for i in d["interpretations"]]
    assert {"N29", "N37", "N38"} <= set(ids)


def test_source_that_is_the_whole_item_uses_default_as_is():
    rule = cs_rule("Players.CustomData.ExternalData.CloudSave.level", type_="GreaterThanEqual", reference=5,
                   Default=5)
    t = [{"id": "A", "externalData": {"cloudSave": {"level": 7}}}, {"id": "B"}]
    assert matched_sets(simulate(rules_1v1(rule), t)) == [["A", "B"]]


def test_default_without_the_path_warns_and_leaves_the_rule_unsatisfied():
    d = simulate(rules_1v1(cs_rule(Default=1000)), [ct("A", rating=1000), ct("B")], timeout=3)
    assert any("ExternalData.CloudSave.Default: has no value at 'rating'" in w for w in d["warnings"])
    assert d["matches"] == [] and outcome(d, "B")["outcome"] == "timeout"
    assert any("Default (player B has no Cloud Save key 'progress') has no value at 'rating'" in x
               for x in rule_reasons(d, "B"))
    # a Default that fits the path does not warn
    assert simulate(rules_1v1(cs_rule(Default={"rating": 1})), [ct("A")])["warnings"] == []


def test_no_key_and_no_default_is_unsatisfied():
    d = simulate(rules_1v1(cs_rule(AccessClass="Public")), [ct("A", rating=1000), ct("B")], timeout=3)
    assert d["matches"] == []
    assert any("player B has no Cloud Save key 'progress' and the rule has no ExternalData.CloudSave.Default" in x
               for x in rule_reasons(d, "A"))
    assert "N37" not in [i["id"] for i in d["interpretations"]]


def test_item_without_the_path_is_unsatisfied_even_with_default():
    t = [ct("A", rating=1000), {"id": "B", "externalData": {"cloudSave": {"progress": {"other": 1}}}}]
    d = simulate(rules_1v1(cs_rule(Default={"rating": 1000})), t, timeout=3)
    assert d["matches"] == []
    assert any("player B's Cloud Save key 'progress' has no value at 'rating'" in x for x in rule_reasons(d, "B"))


def test_players_each_carry_external_data_and_operations_apply():
    rule = cs_rule("Players.CustomData.ExternalData.CloudSave.progress.rating.Avg", type_="GreaterThanEqual",
                   reference=1000, Default={"rating": 500})
    party = {"id": "P", "players": [
        {"id": "p1", "externalData": {"cloudSave": {"progress": {"rating": 1600}}}},
        {"id": "p2"}]}  # Default 500 -> average 1050
    rules = rules_1v1(pc=(2, 2), tc=(1, 1), team_rules=[rule])
    assert matched_sets(simulate(rules, [party])) == [["P"]]
    party["players"][0]["externalData"]["cloudSave"]["progress"]["rating"] = 1400  # average 950
    assert simulate(rules, [party], timeout=3)["matches"] == []


def test_source_segments_are_case_insensitive_key_and_path_are_not():
    rule = cs_rule("Players.CustomData.externaldata.cloudsave.progress.rating")
    assert matched_sets(simulate(rules_1v1(rule), [ct("A", rating=1), ct("B", rating=2)])) == [["A", "B"]]
    t = [{"id": "A", "externalData": {"cloudSave": {"Progress": {"rating": 1}}}}, ct("B", rating=1)]
    assert simulate(rules_1v1(cs_rule()), t, timeout=3)["matches"] == []


def test_custom_data_external_data_key_warns():
    t = [ct("A", rating=1, ExternalData={"CloudSave": {"progress": {"rating": 1}}}),
         {"id": "B", "players": [{"id": "b1", "customData": {"externalData": "x"}}]}]
    d = simulate(rules_1v1(), t)
    assert any(w.startswith("tickets[0].customData.ExternalData: not read by any rule") for w in d["warnings"])
    assert any(w.startswith("tickets[1].players[0].customData.externalData:") for w in d["warnings"])


def flow_errors(tickets):
    with pytest.raises(InputError) as ei:
        parse_flow({"tickets": tickets}, Diagnostics(), "f.json")
    return str(ei.value).splitlines()


def test_flow_external_data_input_errors():
    e = flow_errors([{"id": "A", "players": [{"id": "a"}], "externalData": {}}])
    assert e[0].startswith("f.json: tickets[0]: both players and externalData given; expected")
    e = flow_errors([{"id": "A", "externalData": {"leaderboard": {}}}])
    assert e[0].startswith("f.json: tickets[0].externalData.leaderboard: unknown key 'leaderboard'")
    e = flow_errors([{"id": "A", "externalData": {"cloudSave": [1]}}])
    assert e[0].startswith("f.json: tickets[0].externalData.cloudSave: array; expected an object")
    e = flow_errors([{"id": "A", "players": [{"id": "a", "externalData": 3}]}])
    assert e[0].startswith("f.json: tickets[0].players[0].externalData: number; expected an object")
    e = flow_errors([{"id": "A", "cloudSave": {}}])
    assert "did you mean 'externalData.cloudSave'?" in e[0]


def test_rules_external_data_checks():
    with pytest.raises(InputError, match=r"AccessClass: got 1; expected a string"):
        parse_rules(rules_1v1(cs_rule(AccessClass=1)), Diagnostics())
    with pytest.raises(InputError, match=r"names no Cloud Save key"):
        parse_rules(rules_1v1(cs_rule("Players.CustomData.ExternalData.CloudSave")), Diagnostics())
    diag = Diagnostics()
    r = parse_rules(rules_1v1(cs_rule(AccessClass="Private", Bogus=1)), diag)
    assert not r.match_rules[0].ignored and r.match_rules[0].cloud_save.access_class == "Private"
    assert any("CloudSave: unknown key 'Bogus'" in w for w in diag.warnings)


def test_cloud_save_block_without_cloud_save_source_warns():
    diag = Diagnostics()
    r = parse_rules(rules_1v1(cs_rule("Players.CustomData.Skill", Default=1)), diag)
    assert not r.match_rules[0].ignored and diag.unsupported == []
    assert any("ExternalData.CloudSave: ignored" in w for w in diag.warnings)


def test_leaderboard_stays_unsupported():
    for rule in ({"Name": "L", "Type": "Equality", "Source": "Players.CustomData.ExternalData.Leaderboard.Tier"},
                 {**cs_rule(), "ExternalData": {"Leaderboard": {"Id": "x"}}},
                 {"Name": "O", "Type": "Equality", "Source": "Players.CustomData.ExternalData.Other.x"}):
        diag = Diagnostics()
        parse_rules(rules_1v1(rule), diag)
        assert len(diag.unsupported) == 1 and "ExternalData" in diag.unsupported[0]["effect"]


def test_cli_sample(tmp_path, capsys):
    s = SAMPLES / "cloudsave-default"
    code = main(["run", "--rules", str(s / "rules.json"), "--flow", str(s / "flow.json"),
                 "--report", str(tmp_path / "r.html"), "--json", "-"])
    doc = json.loads(capsys.readouterr().out)
    assert code == 0 and doc["tool"]["flowFormat"] == 2 and doc["warnings"] == []
    assert {"N29", "N37", "N38"} <= {i["id"] for i in doc["interpretations"]}
