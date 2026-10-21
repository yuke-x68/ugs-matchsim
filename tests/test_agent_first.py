import json

import pytest

from helpers import rules_1v1, simulate, tk
from ugs_matchsim.cli import main
from ugs_matchsim.common import Diagnostics, InputError
from ugs_matchsim.flow import parse_flow


def errors(data):
    with pytest.raises(InputError) as ei:
        parse_flow(data, Diagnostics(), "f.json")
    return str(ei.value).splitlines()


def test_unknown_key_did_you_mean_and_path():
    e = errors({"tickets": [{"id": "A", "time": 0}], "expct": []})
    assert any(x.startswith("f.json: tickets[0].time: unknown key 'time'") and "did you mean 'at'?" in x for x in e)
    assert any("expct" in x and "did you mean 'expect'?" in x for x in e)


def test_all_errors_in_one_pass():
    e = errors({"tickets": [{"id": "A", "at": -1, "customData": 3}, {"at": 0}],
                "expect": [{"togther": ["A", "B"]}]})
    assert len(e) >= 4 and all(x.startswith("f.json: ") and "expected" in x for x in e)


def test_json_syntax_error_position(tmp_path, capsys):
    rules = tmp_path / "r.json"
    rules.write_text(json.dumps(rules_1v1()), encoding="utf-8", newline="\n")
    flow = tmp_path / "f.json"
    flow.write_text('{"tickets": [ // c\n  {"id": "A" "at": 0}\n]}', encoding="utf-8", newline="\n")
    assert main(["run", "--rules", str(rules), "--flow", str(flow)]) == 2
    assert "line 2, column" in capsys.readouterr().err


def test_json_stdout_and_schema(tmp_path, capsys):
    rules = tmp_path / "r.json"
    rules.write_text(json.dumps(rules_1v1()), encoding="utf-8", newline="\n")
    flow = tmp_path / "f.json"
    flow.write_text(json.dumps({"tickets": [tk("A"), tk("B")], "expect": [{"together": ["A", "B"]}]}), encoding="utf-8", newline="\n")
    assert main(["run", "--rules", str(rules), "--flow", str(flow), "--json", "-"]) == 0
    cap = capsys.readouterr()
    d = json.loads(cap.out)
    assert d["schemaVersion"] == 1 and "PASS" in cap.err
    assert d["expectations"][0]["actual"]["tickets"]["A"]["match"] == "M1"


def test_no_duplicate_reasons_per_ticket():
    eq = {"Name": "V", "Type": "Equality", "Source": "Players.CustomData.V"}
    d = simulate(rules_1v1(eq), [tk("A", 0, V="1"), tk("B", 0, V="2"), tk("C", 0, V="2")], timeout=3)
    for t in d["tickets"]:
        keys = [(r["kind"], r["rule"], r["scope"], tuple(r["with"])) for r in t["reasons"]]
        assert len(keys) == len(set(keys))


def test_docs_topics(capsys):
    for t in ("flow", "output", "rules", "interpretations"):
        assert main(["docs", t]) == 0
        assert capsys.readouterr().out.strip()


def test_version(capsys):
    with pytest.raises(SystemExit):
        main(["--version"])
    out = capsys.readouterr().out
    assert "flow-format: 2" in out and "json-schema: 1" in out
