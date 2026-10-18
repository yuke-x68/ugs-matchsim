# Output reference (json-schema 1)

## Exit codes

| Code | Meaning |
|---|---|
| 0 | The run completed; every expectation passed (or there were none). |
| 1 | The run completed; at least one expectation failed. Read `expectations[].actual` and `tickets[].reasons`. |
| 2 | Input/usage error (bad JSON, invalid flow, invalid rules, unreadable file), or an unsupported element was found and `--allow-unsupported` was not given. Nothing is simulated. Fix the input from stderr. |

## Streams

- `--json -` writes the JSON result to **stdout** and the human summary (counts, PASS/FAIL lines) to **stderr**.
- `--json <path>` writes the file; the summary goes to stdout.
- Warnings (`warning: ...`), unsupported elements and errors always go to stderr. Warnings and unsupported
  elements are also in the JSON (`warnings`, `unsupported`).
- The HTML report is written next to the flow file (or `--report <path>`).

## Input errors (exit 2)

One line per error on stderr, each of the form

    <file>: <json path>: <what is wrong>; expected <form>

for example `flow-a.json: tickets[2].players[0].customData: array; expected an object, e.g. {"GameVersion": "1.2.0"}`.
JSON syntax errors read `<file>: line <L>, column <C>: <message>` (position in the original file).
All flow validation errors found are reported in one pass. In the flow file unknown keys are errors
(with "did you mean"); in the rules file they are warnings.

## JSON result

Key order is stable and the output is deterministic (same inputs -> identical bytes).

```
{
  "schemaVersion": 1,                       int
  "tool":   { "name", "version", "flowFormat": int, "unofficial": true },
  "rules":  { "name": str, "file": str },   file = base name
  "flow":   { "file": str, "tickSeconds": num, "timeoutSeconds": num },
  "summary": { "tickets", "matches", "ticketsMatched", "ticketsTimedOut",
               "expectationsPassed", "expectationsFailed" },          all int
  "expectations": [ Expectation ],
  "matches": [ { "id": "M1", "time": num, "anchor": ticket id,
                 "teams": [ { "name", "definition", "tickets": [id], "players": [id] } ],
                 "relaxations": [ { "target", "type", "value", "atSeconds", "ageType", "observedAge" } ] } ],
  "tickets": [ Ticket ],                    ordered by (arrival, id)
  "events":  [ { "time": num, "kind": "arrival"|"relaxation"|"match"|"timeout", ... } ],
  "warnings": [ str ],
  "unsupported": [ { "element": str, "effect": str } ],
  "interpretations": [ { "id": "N1", "text": str } ]   simulator choices that applied to this run
}
```

### Expectation

```
{ "index": int,            0-based position in the flow's expect array
  "name": str,             the flow's name, else "<kind> <ids> [by N]"
  "kind": "together"|"apart"|"matched"|"unmatched"|"sameTeam"|"opposingTeams",
  "tickets": [id], "by": num|null,
  "passed": bool,
  "actual": {              what really happened (never empty)
     "tickets": { "<id>": { "status": "matched", "match": "M1", "time": num, "team": str, "partners": [id] }
                        | { "status": "timeout", "time": num } },
     "sameMatch": bool,         together / sameTeam / opposingTeams
     "matchTime": num|null,     together (time the shared match formed)
     "teams": [str|null],       sameTeam / opposingTeams (team of each listed ticket, in order)
     "sharedMatchPairs": [[id,id]]   apart (pairs that ended in the same match; empty = none) },
  "text": str              one human sentence }
```

How to read a FAIL: look at `actual.tickets` (did each listed ticket match? with whom? when?) and the
kind-specific field (`sameMatch: false`, `matchTime` later than `by`, `sharedMatchPairs` non-empty,
`teams` equal). Then read those tickets' `reasons` to see why they did not match.

### Ticket

```
{ "id": str, "arrival": num, "players": [id],
  "outcome": "matched"|"timeout", "time": num,     time of match or timeout
  "waited": num,                                   time - arrival
  "match": str, "team": str, "with": [id],         only when matched
  "reasons": [ Reason ] }                          why it was not matched earlier (empty if it matched at once)
```

### Reason

```
{ "kind": "rule" | "count" | "player" | "size" | "timeout",
  "rule": str | null,        rule name for kind "rule"
  "scope": "match" | "team:<name>",
  "with": [ticket id],       other tickets involved in the conflict
  "values": { "<ticket id>": value },   each involved ticket's own value of the rule's source (plain rules only)
  "text": str }              one human sentence
```

Kinds: `rule` - a match/team rule was violated by combining this ticket with those in `with`;
`count` - TeamCount/PlayerCount minimum could not be reached; `player` - duplicate player id;
`size` - the ticket is larger than any team can hold; `timeout` - the ticket timed out
(always the last reason of a timed-out ticket).
A ticket has at most one reason per `(kind, rule, scope)`; `with` and `values` accumulate all counterparts,
so e.g. a version mismatch with B and D is one reason with `with: ["B","D"]`.
