"""Self-contained HTML report writer."""

from __future__ import annotations

import html
from typing import Any

from .common import fmt

CSS = """
body{font:14px/1.45 system-ui,sans-serif;margin:2rem auto;max-width:1100px;color:#1f2933;padding:0 1rem}
h1{margin-bottom:.2rem}h2{margin-top:2rem;border-bottom:2px solid #d9e2ec;padding-bottom:.2rem}
table{border-collapse:collapse;width:100%;margin:.5rem 0}th,td{border:1px solid #d9e2ec;padding:.3rem .5rem;text-align:left;vertical-align:top}
th{background:#f0f4f8}.pass{color:#0a7a3b;font-weight:700}.fail{color:#b42318;font-weight:700}
.banner{background:#fff8e1;border:1px solid #f0d98a;padding:.5rem .8rem;border-radius:4px}
.warn{background:#fff1f0;border:1px solid #f3b8b3;padding:.4rem .8rem;border-radius:4px;margin:.3rem 0}
.muted{color:#627d98}code{background:#f0f4f8;padding:0 .25rem;border-radius:3px}ul{margin:.2rem 0;padding-left:1.2rem}
"""


def e(x: Any) -> str:
    return html.escape(fmt(x) if not isinstance(x, str) else x)


def _table(head: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return '<p class="muted">none</p>'
    h = "".join(f"<th>{e(c)}</th>" for c in head)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><tr>{h}</tr>{body}</table>"


def _event_text(ev: dict[str, Any]) -> str:
    k = ev["kind"]
    if k == "arrival":
        return f"Ticket <b>{e(ev['ticket'])}</b> arrived (players: {e(', '.join(ev['players']))})"
    if k == "timeout":
        return f"Ticket <b>{e(ev['ticket'])}</b> timed out after {e(ev['waited'])} s"
    if k == "match":
        return f"Match <b>{e(ev['match'])}</b> formed from tickets {e(', '.join(ev['tickets']))}"
    val = "" if ev["value"] is None else f" → <code>{e(ev['value'])}</code>"
    return (f"Relaxation took effect: <code>{e(ev['target'])}</code> {e(ev['type'])}{val} "
            f"(AgeType {e(ev['ageType'])}: age {e(ev['observedAge'])} s &ge; AtSeconds {e(ev['atSeconds'])}; "
            f"basis: {e(ev['basis'])})")


def render(doc: dict[str, Any]) -> str:
    t = doc["tool"]
    p: list[str] = []
    p.append(f"<h1>Matchmaking simulation report</h1><p class=\"banner\">Unofficial simulator — not affiliated with Unity.</p>")
    p.append(f"<p>Rules: <b>{e(doc['rules']['name'])}</b> (<code>{e(doc['rules']['file'])}</code>) &middot; "
             f"Flow: <code>{e(doc['flow']['file'])}</code> &middot; Tool: {e(t['name'])} {e(t['version'])}</p>")
    s = doc["summary"]
    p.append(f"<p>{s['tickets']} tickets, {s['matches']} matches, {s['ticketsMatched']} tickets matched, "
             f"{s['ticketsTimedOut']} timed out. Tick {e(doc['flow']['tickSeconds'])} s, "
             f"ticket timeout {e(doc['flow']['timeoutSeconds'])} s.</p>")

    p.append("<h2>Expectations</h2>")
    rows = [[f'<span class="{"pass" if x["passed"] else "fail"}">{"PASS" if x["passed"] else "FAIL"}</span>',
             e(x["name"]), e(x["text"])] for x in doc["expectations"]]
    p.append(_table(["Result", "Expectation", "Actual outcome"], rows))

    p.append("<h2>Matches</h2>")
    if not doc["matches"]:
        p.append('<p class="muted">no match formed</p>')
    for m in doc["matches"]:
        teams = "".join(
            f"<li><b>{e(tm['name'])}</b>: tickets {e(', '.join(tm['tickets']))} "
            f"(players {e(', '.join(tm['players']))})</li>" for tm in m["teams"])
        rel = "".join(
            f"<li><code>{e(r['target'])}</code> {e(r['type'])}"
            f"{'' if r['value'] is None else ' → ' + e(r['value'])} "
            f"(AtSeconds {e(r['atSeconds'])}, {e(r['ageType'])} age {e(r['observedAge'])} s)</li>"
            for r in m["relaxations"]) or '<li class="muted">none</li>'
        p.append(f"<h3>{e(m['id'])} — formed at t={e(m['time'])}</h3><ul>{teams}</ul>"
                 f"<p>Relaxations in effect:</p><ul>{rel}</ul>")

    p.append("<h2>Tickets</h2>")
    rows = []
    for x in doc["tickets"]:
        if x["outcome"] == "matched":
            out = f"matched in {e(x['match'])} at t={e(x['time'])} with {e(', '.join(x['with']) or '(nobody else)')} (team {e(x['team'])})"
        else:
            out = f"timed out at t={e(x['time'])}"
        why = ""
        if x["reasons"]:
            why = "<ul>" + "".join(f"<li>{e(r['text'])}</li>" for r in x["reasons"]) + "</ul>"
        elif x["outcome"] != "matched" or x["waited"] > 0:
            why = '<span class="muted">waited for the next tick; no blocking reason recorded</span>'
        rows.append([e(x["id"]), e(x["arrival"]), out, e(x["waited"]), why])
    p.append(_table(["Ticket", "Arrival", "Outcome", "Waited (s)", "Reasons while waiting"], rows))

    p.append("<h2>Timeline</h2>")
    p.append(_table(["t (s)", "Event"], [[e(ev["time"]), _event_text(ev)] for ev in doc["events"]]))

    p.append("<h2>Warnings</h2>")
    items = [f'<div class="warn">{e(w)}</div>' for w in doc["warnings"]]
    items += [f'<div class="warn"><b>Unsupported, ignored:</b> {e(u["element"])} — {e(u["effect"])}</div>'
              for u in doc["unsupported"]]
    p.append("".join(items) or '<p class="muted">none</p>')

    p.append("<h2>Interpretations applied</h2>")
    p.append("<p class=\"muted\">The public docs do not decide these points; IDs refer to the spec inventory (`ugs-matchsim docs interpretations`).</p><ul>"
             + "".join(f"<li><b>{e(i['id'])}</b>: {e(i['text'])}</li>" for i in doc["interpretations"]) + "</ul>")
    return ("<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            f"<title>ugs-matchsim report</title><style>{CSS}</style></head><body>" + "".join(p) + "</body></html>\n")
