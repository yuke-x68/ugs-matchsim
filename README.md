# ugs-matchsim

**Unofficial** local simulator of rule-based matchmaking in the shape of the Unity Gaming Services (UGS) Matchmaker pool rules — not affiliated with, endorsed by, or supported by Unity.

You give it one pool's rules JSON and a *flow* (tickets arriving over time plus expectations). It replays the flow on a simulated clock, forms matches, and tells you which expectations hold and, for every ticket that waited, which rule or count constraint blocked it.

It is built only from the public documentation (see [`src/ugs_matchsim/docs/spec-inventory.md`](src/ugs_matchsim/docs/spec-inventory.md)). Where the docs are silent, it picks a simple deterministic behaviour and lists it as an interpretation (`N1`, `N2`, …). Treat results as a design aid, not as a prediction of the real service.

## Install

Python 3.11+ and [uv](https://docs.astral.sh/uv/). No runtime dependencies.

```bash
uv tool install git+https://github.com/yuke-x68/ugs-matchsim            # latest
uv tool install git+https://github.com/yuke-x68/ugs-matchsim@v0.2.0     # pin a release (@v<version>)
```

Or keep a copy of this repository inside your project and run it from there; the working directory is
preserved, so relative paths to your rules and flows work:

```bash
uv run --project <path-to-copy> ugs-matchsim run --rules rules.json --flow flow.json
```

## Run

From a checkout of this repository:

```bash
uv sync
uv run pytest -q
uv run ugs-matchsim run --rules samples/1v1-version/rules.json --flow samples/1v1-version/flow.json \
    --report out.html --json out.json
uv run ugs-matchsim --version
```

Exit codes: `0` ran, all expectations passed (or none); `1` ran, at least one expectation failed; `2` usage/input error, or the inputs use a documented element that is not implemented (unless `--allow-unsupported`, which ignores it and lists it under Warnings in the report).

Default report path: `<flow file name without extension>.report.html` next to the flow file. Output is deterministic: same inputs, byte-identical JSON.

## Inputs

**Rules file**: one pool's rules in the documented shape (`Name`, `MatchDefinition.Teams`, `MatchDefinition.MatchRules`, `BackfillEnabled`). Keys are case-insensitive; unknown keys produce a warning.
A UGS CLI queue file (`.mmq`, e.g. `samples/1v1-version/queue.mmq`) is accepted too: its `defaultPool.matchLogic` is the pool rules, and its `defaultPool.timeoutSeconds` and `maxPlayersPerTicket` are used when the flow's `queue` omits them (a value in the flow wins, with a warning if it differs). Filtered pools, pool variants and `enabled: false` are unsupported.

**Flow file**: JSON, `//` and `/* */` comments and trailing commas allowed, camelCase keys.

```jsonc
{
  "queue": { "timeoutSeconds": 60, "maxPlayersPerTicket": 4 },
  "tickSeconds": 1,
  "tickets": [
    { "id": "A", "at": 0, "players": [ { "id": "a1", "customData": { "GameVersion": "1.2.0" } } ] },
    { "id": "B", "at": 1.5, "customData": { "GameVersion": "1.2.0" } }   // shorthand: one player, id = ticket id
  ],
  "expect": [
    { "together": ["A", "B"], "by": 5 },
    { "apart": ["A", "C"] },
    { "matched": ["B"] },
    { "unmatched": ["E"] },
    { "sameTeam": ["A", "B"] },
    { "opposingTeams": ["A", "C"] }
  ]
}
```

Each expectation may carry a `"name"`. Unknown expectation kinds or ticket ids are input errors.

## What is implemented

- Teams: `TeamCount` / `PlayerCount` Min/Max, several team definitions, multi-player tickets kept together.
- Match rules and team rules of type Equality, Difference, LessThan, LessThanEqual, GreaterThan, GreaterThanEqual, InList, Intersection on `Players.CustomData.*` (nested paths, `Count/Median/Avg/Sum/Min/Max` suffixes), with `Reference`, `Overlap`, `Not`, `EnableRule`.
- Relaxations: `RuleControl.Enable/Disable`, `ReferenceControl.Replace`, `RangeControl.ReplaceMin`, with `AtSeconds` and `AgeType` Oldest/Average/Youngest.
- Queue ticket timeout.

Not implemented (reported as unsupported): QoS and ExternalData sources, backfill (`BackfillEnabled: true`), pools and filters / ticket `attributes`, regions, other rule types.

See [`src/ugs_matchsim/docs/spec-inventory.md`](src/ugs_matchsim/docs/spec-inventory.md) for the per-element status table, the interpretations, and the limits.

## Report

A single offline HTML file: expectations, matches (with relaxations in effect), tickets (outcome and blocking reasons), timeline, warnings and applied interpretations. `--json <path>` (or `--json -` for stdout, with the summary then on stderr) writes the same data in machine-readable form (`schemaVersion` 1).

The flow format is strict: unknown keys, unknown expectation kinds or unknown ticket ids are input errors (exit 2), reported as `<file>: <json path>: <what is wrong>; expected <form>`.

## For AI agents

The installed CLI documents itself; start there instead of this README:

```bash
ugs-matchsim --version          # tool version, flow-format, json-schema
ugs-matchsim docs               # list topics: flow, output, rules, interpretations
ugs-matchsim docs flow          # complete flow-file reference
ugs-matchsim run --rules rules.json --flow flow.json --json -   # JSON on stdout, summary on stderr
```

A Claude Code plugin with a skill for this workflow is included. In Claude Code:

```
/plugin marketplace add yuke-x68/ugs-matchsim
/plugin install ugs-matchsim@ugs-matchsim
```

The skill needs the `ugs-matchsim` command (see Install). Once installed, `ugs-matchsim docs …` prints the bundled reference (`docs flow`, `docs output`, `docs rules`, `docs interpretations`).

## License

Apache-2.0. See `LICENSE` and `NOTICE`.

Unity and Unity Gaming Services are trademarks of Unity Technologies. This project is not affiliated with, endorsed by, or sponsored by Unity Technologies.
