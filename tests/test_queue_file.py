import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from helpers import rules_1v1, tk
from ugs_matchsim.common import Diagnostics, InputError
from ugs_matchsim.flow import parse_flow
from ugs_matchsim.rules import is_queue_file, load_rules, parse_queue
from ugs_matchsim.runner import run

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def cli(*args):
    return subprocess.run([sys.executable, "-m", "ugs_matchsim.cli", *args], capture_output=True, text=True, encoding="utf-8")


def s(name, f):
    return str(SAMPLES / name / f)


def queue_file(timeout=12, max_players=2, **pool_extra):
    """UGS CLI queue file shape (camelCase) around the 1v1 test rules."""
    logic = json.loads(json.dumps(rules_1v1({"Name": "V", "Type": "Equality", "Source": "Players.CustomData.V"})))
    return {
        "$schema": "https://ugs-config-schemas.unity3d.com/v1/matchmaker/matchmaker-queue.schema.json",
        "name": "q", "enabled": True, "maxPlayersPerTicket": max_players,
        "defaultPool": {"variants": [], "name": "p", "enabled": True, "timeoutSeconds": timeout,
                        "matchLogic": logic, "matchHosting": {"type": "MatchId"}, **pool_extra},
        "filteredPools": [],
    }


def load(data, file="q.mmq"):
    diag = Diagnostics()
    return load_rules(json.dumps(data), diag, file), diag


def test_detected_by_extension_or_default_pool_key():
    assert is_queue_file({}, "dir/Q.MMQ")
    assert is_queue_file({"DefaultPool": {}}, "q.json")
    assert not is_queue_file(rules_1v1(), "rules.json")
    r, _ = load(queue_file(), "renamed.json")
    assert r.name == "t"


def test_match_logic_read_like_rules_json():
    r, diag = load(queue_file())
    assert r.name == "t" and [t.name for t in r.teams] == ["Main"] and [x.name for x in r.match_rules] == ["V"]
    assert r.queue == {"maxPlayersPerTicket": (2, "rules.MaxPlayersPerTicket"),
                       "timeoutSeconds": (12, "rules.DefaultPool.TimeoutSeconds")}
    assert diag.warnings == [] and diag.unsupported == []


def flow_with(r, queue=None, tickets=None):
    diag = Diagnostics()
    data = {"tickets": tickets or [tk("A", 0, V=1), tk("B", 0, V=1)]}
    if queue is not None:
        data["queue"] = queue
    return parse_flow(data, diag, "f.json", r.queue), diag


def test_queue_values_are_flow_defaults():
    r, _ = load(queue_file(timeout=12, max_players=2))
    f, diag = flow_with(r)
    assert (f.timeout, f.max_players) == (12, 2) and diag.warnings == []
    doc = run(r, f, diag, "q.mmq", "f.json")
    assert doc["flow"]["timeoutSeconds"] == 12 and doc["rules"] == {"name": "t", "file": "q.mmq"}


def test_flow_value_wins_with_warning_when_different():
    r, _ = load(queue_file(timeout=12, max_players=2))
    f, diag = flow_with(r, {"timeoutSeconds": 5, "maxPlayersPerTicket": 2})
    assert (f.timeout, f.max_players) == (5, 2)
    assert diag.warnings == ["queue.timeoutSeconds: the flow sets 5 but the rules file sets 12 "
                             "(rules.DefaultPool.TimeoutSeconds); the flow value 5 is used"]
    f, diag = flow_with(r, {"timeoutSeconds": 12.0})
    assert f.timeout == 12 and diag.warnings == []


def test_ticket_size_checked_against_queue_file_limit():
    r, _ = load(queue_file(max_players=1))
    party = {"id": "P", "players": [{"id": "p1"}, {"id": "p2"}]}
    with pytest.raises(InputError, match=r"at most rules\.MaxPlayersPerTicket=1 players"):
        flow_with(r, tickets=[party])


def test_missing_queue_values_fall_back_to_defaults():
    data = queue_file()
    del data["maxPlayersPerTicket"], data["defaultPool"]["timeoutSeconds"]
    r, _ = load(data)
    f, _ = flow_with(r)
    assert (f.timeout, f.max_players) == (60, 150)


@pytest.mark.parametrize("path,value,element", [
    (("filteredPools",), [{"name": "eu"}], "rules.FilteredPools (1 pool(s))"),
    (("defaultPool", "variants"), [{"name": "v"}], "rules.DefaultPool.Variants (1 variant(s))"),
    (("enabled",), False, "rules.Enabled = false"),
    (("defaultPool", "enabled"), False, "rules.DefaultPool.Enabled = false"),
])
def test_unsupported_queue_elements(path, value, element):
    data = queue_file()
    target = data
    for k in path[:-1]:
        target = target[k]
    target[path[-1]] = value
    _, diag = load(data)
    assert [u["element"] for u in diag.unsupported] == [element]


def test_rule_paths_and_unknown_keys_name_the_queue_file_location():
    data = queue_file(bogus=1)
    data["defaultPool"]["matchLogic"]["BackfillEnabled"] = True
    _, diag = load(data)
    assert diag.warnings == ["rules.DefaultPool: unknown key 'bogus' was ignored"]
    assert [u["element"] for u in diag.unsupported] == ["rules.DefaultPool.MatchLogic.BackfillEnabled = true"]
    bad = queue_file()
    del bad["defaultPool"]["matchLogic"]["MatchDefinition"]["Teams"][0]["TeamCount"]
    with pytest.raises(InputError, match=r"^q\.mmq: rules\.DefaultPool\.MatchLogic\.MatchDefinition\.Teams\[0\]: "):
        load(bad)


@pytest.mark.parametrize("mutate,message", [
    (lambda d: d.pop("defaultPool"), "q.mmq: rules.DefaultPool: missing; expected an object"),
    (lambda d: d["defaultPool"].pop("matchLogic"), "q.mmq: rules.DefaultPool.MatchLogic: missing; expected"),
    (lambda d: d["defaultPool"].update(timeoutSeconds=0), "q.mmq: rules.DefaultPool.TimeoutSeconds: got 0; expected"),
    (lambda d: d.update(maxPlayersPerTicket=1.5), "q.mmq: rules.MaxPlayersPerTicket: got 1.5; expected"),
    (lambda d: d.update(filteredPools={}), "q.mmq: rules.FilteredPools: object; expected an array"),
    (lambda d: d.update(defaultPool=[]), "q.mmq: rules.DefaultPool: array; expected an object"),
    (lambda d: d.update(enabled="yes"), "q.mmq: rules.Enabled: got yes; expected true or false"),
])
def test_invalid_queue_file_is_input_error(mutate, message):
    data = queue_file()
    mutate(data)
    with pytest.raises(InputError) as ei:
        load(data)
    assert str(ei.value).startswith(message)


def test_parse_queue_does_not_touch_input():
    data = queue_file()
    before = copy.deepcopy(data)
    parse_queue(data, Diagnostics())
    assert data == before


def test_cli_sample_queue_file_matches_rules_json(tmp_path):
    outs = []
    for rules in ("rules.json", "queue.mmq"):
        js = tmp_path / f"{rules}.out.json"
        p = cli("run", "--rules", s("1v1-version", rules), "--flow", s("1v1-version", "flow.json"),
                "--report", str(tmp_path / "r.html"), "--json", str(js))
        assert p.returncode == 0, p.stderr
        assert "warning" not in p.stderr
        outs.append(json.loads(js.read_text(encoding="utf-8")))
    a, b = outs
    assert b["rules"] == {"name": "Default1v1", "file": "queue.mmq"}
    for key in ("flow", "summary", "expectations", "matches", "tickets", "events", "warnings", "unsupported",
                "interpretations"):
        assert a[key] == b[key], key


def test_cli_queue_file_timeout_used_without_flow_queue(tmp_path):
    flow = tmp_path / "f.json"
    flow.write_text(json.dumps({"tickets": [tk("A", 0, GameVersion="1"), tk("B", 3, GameVersion="2")],
                                "expect": [{"unmatched": ["A", "B"]}]}), encoding="utf-8", newline="\n")
    js = tmp_path / "o.json"
    p = cli("run", "--rules", s("1v1-version", "queue.mmq"), "--flow", str(flow),
            "--report", str(tmp_path / "r.html"), "--json", str(js))
    assert p.returncode == 0, p.stderr
    doc = json.loads(js.read_text(encoding="utf-8"))
    assert doc["flow"]["timeoutSeconds"] == 10
    assert [t["time"] for t in doc["tickets"]] == [10, 13]
    assert "(rules.DefaultPool.TimeoutSeconds)" in doc["tickets"][0]["reasons"][-1]["text"]
