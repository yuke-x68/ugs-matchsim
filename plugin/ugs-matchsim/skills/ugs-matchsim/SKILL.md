---
name: ugs-matchsim
description: Use when writing or running matchmaking tests for a UGS (Unity Gaming Services) Matchmaker rules JSON, checking which tickets would match (or not, and why) under given rules, or reading ugs-matchsim results (expectations, ticket reasons, exit codes).
---

# ugs-matchsim

`ugs-matchsim` is an **unofficial** local simulator of rule-based UGS Matchmaker pools. You write a
*flow* (timed tickets + expectations), run it against a rules JSON, and read a JSON result.
The installed CLI is the canonical reference; this skill is only the workflow.

## 0. Make sure the tool is there and current

```bash
ugs-matchsim --version
```

- Missing? Install it: `uv tool install git+https://github.com/yuke-x68/ugs-matchsim`. If the project
  keeps a copy of the repository, use `uv run --project <path-to-copy> ugs-matchsim ...` instead
  (cwd is preserved, so relative paths to rules/flows work).
- This skill was written for `flow-format: 1` and `json-schema: 1`. If the printed numbers differ,
  trust `ugs-matchsim docs flow` / `ugs-matchsim docs output` over this skill.

Reference topics: `ugs-matchsim docs` lists them: `flow` (flow file), `output` (JSON/exit codes),
`rules` (what of the rules JSON is supported), `interpretations` (simulator choices + limits).
Read `docs flow` before writing your first flow; do not guess field names.

## 1. The loop

1. Write `flow-<what>.json` (one scenario per file). Minimal example (1v1 rules, same game version):

```json
{
  "queue": { "timeoutSeconds": 30 },
  "tickets": [
    { "id": "A", "at": 0, "customData": { "GameVersion": "1.2.0" } },
    { "id": "B", "at": 1, "customData": { "GameVersion": "1.2.0" } },
    { "id": "C", "at": 2, "customData": { "GameVersion": "1.1.0" } }
  ],
  "expect": [
    { "together": ["A", "B"], "by": 2 },
    { "unmatched": ["C"] }
  ]
}
```

   Expectation kinds: `together` (optionally `by`), `apart`, `matched`, `unmatched`, `sameTeam`,
   `opposingTeams`. Ticket shorthand `customData` = one player; use `players: [{id, customData}]` for parties.

2. Run it and read the JSON from stdout (the human summary goes to stderr):

```bash
ugs-matchsim run --rules <rules.json> --flow <flow.json> --json -
```

3. Act on the exit code:
   - **0** - all expectations passed. Done.
   - **1** - some failed. For each `expectations[]` with `"passed": false` read `actual` (what really
     happened to the listed tickets: match, time, team, partners) and `text`; then read the involved
     `tickets[].reasons[]` (`kind`, `rule`, `scope`, `with`, `values`, `text`) to see which rule or count
     blocked them. Decide whether the rules or the expectation is wrong.
   - **2** - input error. stderr has one line per problem: `<file>: <json path>: <what>; expected <form>`
     (JSON syntax errors give line and column). Fix the file and rerun; do not retry unchanged.

An HTML report is also written next to the flow file; it is for humans, you do not need it.

## 2. Pitfalls

- Times are plain numbers of **seconds from 0**; `at` is the arrival time, `by` is absolute time (not
  "after arrival").
- Set `queue.timeoutSeconds` to the real queue's timeout (default 60). `unmatched` only passes once the
  ticket times out, and relaxations (`AtSeconds`) depend on waiting time.
- `--rules` also takes a UGS CLI queue file (`.mmq`). Its `defaultPool.timeoutSeconds` and
  `maxPlayersPerTicket` then fill in for a flow that omits `queue`; do not copy them into the flow
  (a flow value wins and a differing one only warns).
- Unknown keys in the flow are errors (typos do not silently pass); in the rules file they are warnings
  (see `warnings` in the JSON and on stderr).
- The simulator is an interpretation of the public docs, not real UGS. Where the docs are silent it makes
  documented choices: see `ugs-matchsim docs interpretations`. Treat results as a design aid.
- Unsupported elements (QoS, ExternalData, backfill, pools/filters, ticket `attributes`, other rule
  types) make the run exit 2. `--allow-unsupported` ignores them, which **can change results**; check
  the `unsupported` list in the JSON before trusting a pass.
- Keep scenarios small: a few tickets, one behaviour per flow file, so a failure is easy to read.
