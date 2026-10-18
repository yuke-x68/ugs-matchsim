import json
import re
import subprocess
import sys
from pathlib import Path

from helpers import rules_1v1, simulate, tk

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"


def exp_result(expect, tickets=None, rules=None):
    tickets = tickets or [tk("A", 0), tk("B", 0), tk("C", 1), tk("D", 9)]
    d = simulate(rules or rules_1v1(), tickets, [expect], timeout=4)
    return d["expectations"][0]


def test_together_by():
    assert exp_result({"together": ["A", "B"], "by": 0})["passed"]
    assert exp_result({"together": ["A", "B"], "by": 5})["passed"]
    r = exp_result({"together": ["A", "B"], "by": -1})
    assert not r["passed"] and "later than" in r["text"]
    assert not exp_result({"together": ["A", "C"]})["passed"]


def test_apart():
    assert exp_result({"apart": ["A", "C"]})["passed"]
    assert exp_result({"apart": ["A", "D"]})["passed"]  # unmatched counts as apart
    assert not exp_result({"apart": ["A", "B"]})["passed"]


def test_matched_unmatched():
    assert exp_result({"matched": ["A", "B"]})["passed"]
    assert not exp_result({"matched": ["A", "D"]})["passed"]
    assert exp_result({"unmatched": ["D"]})["passed"]
    assert not exp_result({"unmatched": ["A"]})["passed"]


def test_team_expectations_and_names():
    assert exp_result({"opposingTeams": ["A", "B"], "name": "n"})["name"] == "n"
    assert exp_result({"opposingTeams": ["A", "B"]})["passed"]
    assert not exp_result({"sameTeam": ["A", "B"]})["passed"]
    team = rules_1v1(pc=(2, 2), tc=(1, 1))
    assert exp_result({"sameTeam": ["A", "B"]}, rules=team)["passed"]
    assert not exp_result({"opposingTeams": ["A", "B"]}, rules=team)["passed"]
    assert not exp_result({"sameTeam": ["A", "D"]})["passed"]


# ----------------------------------------------------------------- CLI

def cli(*args):
    return subprocess.run([sys.executable, "-m", "ugs_matchsim.cli", *args], capture_output=True, text=True, encoding="utf-8")


def s(name, f):
    return str(SAMPLES / name / f)


def test_exit_0_and_outputs(tmp_path):
    rep, js = tmp_path / "r.html", tmp_path / "r.json"
    p = cli("run", "--rules", s("1v1-version", "rules.json"), "--flow", s("1v1-version", "flow.json"),
            "--report", str(rep), "--json", str(js))
    assert p.returncode == 0, p.stderr
    assert re.search(r"^PASS ", p.stdout, re.M) and "FAIL" not in p.stdout
    html = rep.read_text(encoding="utf-8")
    assert "Expectations" in html and "not affiliated with Unity" in html and "http" not in html.replace("http://x", "")
    for sec in ["Matches", "Tickets", "Timeline", "Warnings", "Interpretations applied"]:
        assert f"<h2>{sec}" in html
    doc = json.loads(js.read_text(encoding="utf-8"))
    assert {"matches", "tickets", "events", "expectations"} <= set(doc)


def test_exit_1_on_failed_expectation(tmp_path):
    p = cli("run", "--rules", s("1v1-version", "rules.json"), "--flow", s("1v1-version", "flow-fail.json"),
            "--report", str(tmp_path / "r.html"))
    assert p.returncode == 1 and "FAIL" in p.stdout and "PASS" in p.stdout


def test_exit_2_on_input_errors(tmp_path):
    assert cli("run", "--rules", "nope.json", "--flow", "nope.json").returncode == 2
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8", newline="\n")
    assert cli("run", "--rules", str(bad), "--flow", s("1v1-version", "flow.json")).returncode == 2
    assert cli("run", "--rules", s("1v1-version", "rules.json")).returncode == 2
    flow = tmp_path / "f.json"
    flow.write_text('{"tickets":[{"id":"A"}],"expect":[{"matched":["ZZ"]}]}', encoding="utf-8", newline="\n")
    assert cli("run", "--rules", s("1v1-version", "rules.json"), "--flow", str(flow)).returncode == 2


def test_unsupported_exit_2_then_allowed(tmp_path):
    rules = rules_1v1({"Name": "Q", "Type": "LessThanEqual", "Source": "Players.QoSResults.Latency", "Reference": 1})
    rp, fp, out = tmp_path / "r.json", tmp_path / "f.json", tmp_path / "o.html"
    rp.write_text(json.dumps(rules), encoding="utf-8", newline="\n")
    fp.write_text('{"tickets":[{"id":"A"},{"id":"B"}],"expect":[{"together":["A","B"]}]}', encoding="utf-8", newline="\n")
    p = cli("run", "--rules", str(rp), "--flow", str(fp), "--report", str(out))
    assert p.returncode == 2 and "unsupported" in p.stderr and not out.exists()
    p = cli("run", "--rules", str(rp), "--flow", str(fp), "--report", str(out), "--allow-unsupported")
    assert p.returncode == 0
    assert "QoS" in out.read_text(encoding="utf-8") and "Unsupported, ignored" in out.read_text(encoding="utf-8")


def test_default_report_path_and_version(tmp_path):
    fp = tmp_path / "myflow.json"
    fp.write_text('{"tickets":[{"id":"A"}]}', encoding="utf-8", newline="\n")
    p = cli("run", "--rules", s("1v1-version", "rules.json"), "--flow", str(fp))
    assert p.returncode == 0 and (tmp_path / "myflow.report.html").exists()
    v = cli("--version")
    assert v.returncode == 0 and "ugs-matchsim" in v.stdout


def test_json_is_byte_identical(tmp_path):
    outs = []
    for n in "ab":
        js = tmp_path / f"{n}.json"
        cli("run", "--rules", s("skill-relax", "rules.json"), "--flow", s("skill-relax", "flow.json"),
            "--report", str(tmp_path / f"{n}.html"), "--json", str(js))
        outs.append(js.read_bytes())
    assert outs[0] == outs[1]


def test_all_samples_pass(tmp_path):
    for name in ["1v1-version", "skill-relax", "teams"]:
        p = cli("run", "--rules", s(name, "rules.json"), "--flow", s(name, "flow.json"), "--report", str(tmp_path / "x.html"))
        assert p.returncode == 0, (name, p.stdout)
