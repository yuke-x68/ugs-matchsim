# Flow file reference (flow-format 2)

A **flow** is a test definition: tickets arriving over simulated time, plus expectations about
the outcome. The file is JSON; `//` and `/* */` comments and trailing commas are allowed.
Keys are camelCase (matched case-insensitively). The format is **strict**: an unknown key
anywhere is an input error (exit 2) with a "did you mean" hint when a valid key is close.

Run: `ugs-matchsim run --rules <rules.json> --flow <flow.json> --json -`

## Top level

| Key | Type | Required | Default | Meaning |
|---|---|---|---|---|
| `queue` | object | no | `{}` | Queue settings (below). |
| `tickSeconds` | number > 0 | no | `1` | Simulated seconds between matching passes. Matches form only on ticks (t = 0, tick, 2*tick, ...). |
| `tickets` | array of ticket | **yes**, non-empty | – | Tickets that enter the queue. |
| `expect` | array of expectation | no | `[]` | Checks on the outcome. Without any, the run exits 0. |

### `queue`

| Key | Type | Default | Meaning |
|---|---|---|---|
| `timeoutSeconds` | number > 0 | `60` | A ticket unmatched after this many seconds since its arrival times out. Set it to the real queue's timeout. |
| `maxPlayersPerTicket` | integer >= 1 | `150` | A ticket with more players is an input error. |

If the rules file is a UGS CLI queue file (`.mmq`), its `defaultPool.timeoutSeconds` and
`maxPlayersPerTicket` replace these defaults. A value written in the flow always wins; when it differs
from the queue file's value, a warning names both values and says the flow value is used.

## Ticket

All times are **seconds from the start of the run (t = 0)**.

| Key | Type | Required | Default | Meaning |
|---|---|---|---|---|
| `id` | string | **yes** | – | Unique ticket id; expectations refer to it. |
| `at` | number >= 0 | no | `0` | Arrival time in seconds. (Not `time`.) |
| `customData` | object | no | `{}` | **Shorthand** for a one-player ticket whose player id is the ticket id. |
| `externalData` | object | no | `{}` | **Shorthand**: the external data of that one player (below). |
| `players` | array of player | no | – | Explicit players (a party). Use *either* `players` *or* the `customData`/`externalData` shorthand, never both. |
| `attributes` | object | no | – | Pool-filter attributes: not simulated; reported as unsupported (exit 2 unless `--allow-unsupported`). |

Player: `{ "id": <string, required>, "customData": <object, default {}>, "externalData": <object, default {}> }`.
`customData` values are what the rules read via `Players.CustomData.<path>` (nested objects ok,
e.g. `{"Skill": {"Rating": 1500}}` is `Players.CustomData.Skill.Rating`).
A ticket is atomic: its players always end up on the same team of the same match.
Two tickets that share a player id are never put into the same match.

### `externalData`

Data the real service appends to a ticket itself; in a flow you supply it per player.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `cloudSave` | object | `{}` | The player's Cloud Save items: `{ "<key>": <item>, ... }`, any JSON item. |

A rule with Source `Players.CustomData.ExternalData.CloudSave.<key>.<path>` reads item `<key>` of each
player's `externalData.cloudSave` and follows `<path>` inside it (keys and path are case-sensitive).
A player without `<key>` uses the rule's `ExternalData.CloudSave.Default` as the whole item and follows
`<path>` inside it (interpretation N37). If there is no Default, or the item/Default has nothing at `<path>`,
the rule is not satisfied for any match with that player while it is enabled, and the ticket's reasons say why.
There is no `failed` outcome, so such a ticket waits and times out where the real service may fail it earlier.
`customData` never feeds these rules: a key named `ExternalData` in `customData` only produces a warning.
`AccessClass` is not used (N38). Leaderboard data is not supported, so `externalData` has no `leaderboard` key.

```jsonc
// rules: "Source": "Players.CustomData.ExternalData.CloudSave.progress.rating",
//        "ExternalData": { "CloudSave": { "Default": { "rating": 1000 } } }
{ "id": "A", "at": 0, "externalData": { "cloudSave": { "progress": { "rating": 1200 } } } },
{ "id": "B", "at": 0 },                                   // no "progress" key: rating 1000 from the Default
{ "id": "P", "at": 1, "players": [
    { "id": "p1", "externalData": { "cloudSave": { "progress": { "rating": 1100 } } } },
    { "id": "p2" } ] }                                    // p2 uses the Default
```

## Expectations

Each element of `expect` has **exactly one kind key** (whose value is a list of ticket ids), and
optionally `by` (only with `together`) and `name` (string, shown in results). Ids must exist in `tickets`.
Expectations are independent; each is `passed` true/false. Index = position in `expect` (0-based).

| Kind | Needs | PASS when | FAIL when |
|---|---|---|---|
| `together` | >= 2 ids | all listed tickets are matched **in the same match** | any is unmatched (timed out) or they are in different matches |
| `together` + `by` | >= 2 ids, `by` = seconds | as `together`, and the match formed at time <= `by` (inclusive) | as `together`, or the match formed later than `by` |
| `apart` | >= 2 ids | no two listed tickets share a match (unmatched tickets are fine) | any two listed tickets are in the same match |
| `matched` | >= 1 id | every listed ticket ends up in some match | any listed ticket timed out |
| `unmatched` | >= 1 id | every listed ticket **times out** (never matched) | any listed ticket is matched |
| `sameTeam` | >= 2 ids | all in one match **and** on the same team | any unmatched, in different matches, or on different teams |
| `opposingTeams` | >= 2 ids | all in one match **and** every listed ticket on a different team | any unmatched, in different matches, or two share a team |

`by` is a time in seconds from t = 0 (same clock as `at`), not a duration since arrival.

## How the run ends

The clock advances tick by tick. Every ticket ends as `matched` (with a match id, time, team) or
`timeout` (at `at + queue.timeoutSeconds`). The run is over when no ticket is waiting.
Consequence: **`unmatched` can only pass after the ticket's timeout has elapsed**, which the simulator
always plays out; if `timeoutSeconds` is larger than the real queue's, results will differ from reality.

## Complete annotated example

```jsonc
{
  "queue": { "timeoutSeconds": 10, "maxPlayersPerTicket": 2 },   // seconds; ticket timeout
  "tickSeconds": 1,
  "tickets": [
    // shorthand: one player, player id = ticket id
    { "id": "A", "at": 0,   "customData": { "GameVersion": "1.2.0" } },
    { "id": "B", "at": 0.5, "customData": { "GameVersion": "1.1.0" } },
    // explicit players (a two-player party)
    { "id": "P", "at": 1, "players": [
        { "id": "p1", "customData": { "GameVersion": "1.2.0" } },
        { "id": "p2", "customData": { "GameVersion": "1.2.0" } } ] },
    { "id": "C", "at": 2,   "customData": { "GameVersion": "1.2.0" } }
  ],
  "expect": [
    { "name": "A and the party meet quickly", "together": ["A", "P"], "by": 3 },
    { "apart": ["A", "B"] },          // different versions must never share a match
    { "matched": ["A", "P"] },
    { "unmatched": ["B"] },           // B has no partner and times out at t = 10.5
    { "opposingTeams": ["A", "P"] }   // 1v1-style rules: they are on different teams
  ]
}
```

(Which of these hold depends on the rules file; the example shows the syntax.)

## Common mistakes

- `time`/`arrival` instead of `at` -> error `tickets[i].time: unknown key ... did you mean 'at'?`.
- Using `players` **and** `customData` or `externalData` on one ticket -> error; choose one.
- `customData` on the ticket for a party: shorthand creates only *one* player. Use `players`.
- Cloud Save values written into `customData` (as `ExternalData...`): not read; a warning says so.
  Put them under `externalData.cloudSave`.
- Treating `by` as "seconds after arrival": it is absolute time from t = 0.
- Expecting `unmatched` with a huge `timeoutSeconds`: the run still plays it out, but a short real
  timeout would behave differently - set `queue.timeoutSeconds` to the real value.
- Forgetting that a match needs the rules' `TeamCount.Min`/`PlayerCount.Min` to be reachable: a lone
  ticket never matches under 1v1 rules.
- Duplicate ticket ids, ids in `expect` that are not in `tickets`, or an expectation with two kind keys.
- Ticket `attributes` (pool filters), QoS and Leaderboard sources, backfill: unsupported, see `ugs-matchsim docs rules`.
- Times are plain numbers of seconds, not strings like `"5s"`.
