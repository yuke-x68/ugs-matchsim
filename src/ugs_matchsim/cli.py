"""Command line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import FLOW_FORMAT, JSON_SCHEMA, __version__
from .common import Diagnostics, InputError
from .flow import load_flow
from .report import render
from .docs import TOPICS, topic_text
from .rules import load_rules
from .runner import dumps, run


def _read(path: str, what: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as ex:
        raise InputError(f"{path}: cannot read {what} file: {ex.strerror}; expected a readable file") from None


def _run(args: argparse.Namespace) -> int:
    diag = Diagnostics()
    try:
        rules = load_rules(_read(args.rules, "rules"), diag, args.rules)
        flow = load_flow(_read(args.flow, "flow"), diag, args.flow, rules.queue)
        for w in diag.warnings:
            print(f"warning: {w}", file=sys.stderr)
        if diag.unsupported:
            for u in diag.unsupported:
                print(f"unsupported: {u['element']} — {u['effect']}", file=sys.stderr)
            if not args.allow_unsupported:
                print("error: unsupported elements found; rerun with --allow-unsupported to proceed "
                      "(they will be ignored and listed in the report)", file=sys.stderr)
                return 2
        doc = run(rules, flow, diag, args.rules, args.flow)
        report_path = Path(args.report) if args.report else Path(args.flow).with_name(
            Path(args.flow).stem + ".report.html")
        report_path.write_text(render(doc), encoding="utf-8", newline="\n")
        if args.json == "-":
            sys.stdout.write(dumps(doc))
        elif args.json:
            Path(args.json).write_text(dumps(doc), encoding="utf-8", newline="\n")
    except InputError as ex:
        print(ex, file=sys.stderr)
        return 2
    except OSError as ex:
        print(f"error: cannot write output: {ex}", file=sys.stderr)
        return 2
    s = doc["summary"]
    out = sys.stderr if args.json == "-" else sys.stdout
    print(f"{s['tickets']} tickets, {s['matches']} matches ({s['ticketsMatched']} matched, "
          f"{s['ticketsTimedOut']} timed out); expectations: {s['expectationsPassed']} passed, "
          f"{s['expectationsFailed']} failed; report: {report_path}", file=out)
    for x in doc["expectations"]:
        print(f"{'PASS' if x['passed'] else 'FAIL'} {x['name']}", file=out)
    return 1 if s["expectationsFailed"] else 0


def _docs(args: argparse.Namespace) -> int:
    if args.topic is None:
        print("Topics (ugs-matchsim docs <topic>):")
        for name, summary in TOPICS.items():
            print(f"  {name:<16} {summary}")
        return 0
    sys.stdout.write(topic_text(args.topic))
    return 0


class _Version(argparse.Action):
    def __init__(self, option_strings, dest, **kw):
        super().__init__(option_strings, dest, nargs=0, **kw)

    def __call__(self, parser, namespace, values, option_string=None):
        print(f"ugs-matchsim {__version__}\nflow-format: {FLOW_FORMAT}\njson-schema: {JSON_SCHEMA}")
        parser.exit()


def _utf8_stdio() -> None:
    # Output contains non-ASCII text; do not depend on the console code page (Windows).
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _utf8_stdio()
    ap = argparse.ArgumentParser(prog="ugs-matchsim",
                                 description="Unofficial local simulator of rule-based matchmaking (not affiliated with Unity).")
    ap.add_argument("--version", action=_Version, help="print tool version, flow-format and json-schema")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("docs", help="print the bundled reference (flow, output, rules, interpretations)")
    d.add_argument("topic", nargs="?", choices=list(TOPICS), help="topic; omit to list topics")
    d.set_defaults(func=_docs)
    r = sub.add_parser("run", help="simulate a flow against a rules file",
                       description="Simulate a flow against a rules file. Flow format and result schema: "
                                   "run `ugs-matchsim docs flow` and `ugs-matchsim docs output`. "
                                   "Exit 0 all expectations passed, 1 some failed, 2 input error.")
    r.add_argument("--rules", required=True, help="pool rules JSON, or a UGS CLI queue file (.mmq)")
    r.add_argument("--flow", required=True, help="flow JSON (tickets + expectations)")
    r.add_argument("--report", help="HTML report path (default: <flow name>.report.html next to the flow file)")
    r.add_argument("--json", help="also write machine-readable JSON to this path; use - for stdout (summary then goes to stderr)")
    r.add_argument("--allow-unsupported", action="store_true",
                   help="proceed although unsupported elements exist (they are ignored and reported)")
    r.set_defaults(func=_run)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
