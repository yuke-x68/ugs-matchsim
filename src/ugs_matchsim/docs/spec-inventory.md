# UGS Matchmaker (rule-based) — public-docs spec inventory

Unofficial. Facts below come only from the pages listed under Sources. Anything the pages do not decide is under "Not specified by the docs".

## Sources

Pages fetched and read in full (markdown rendition):

- https://docs.unity.com/en-us/mps-sdk/matchmaking/mm-rules — "Matchmaking rules"
- https://docs.unity.com/en-us/mps-sdk/matchmaking/rule-relaxations — "Rule relaxations"
- https://docs.unity.com/en-us/mps-sdk/matchmaking/queues-pools — "Queues and pools"
- https://docs.unity.com/en-us/mps-sdk/matchmaking/get-started-mm — "Get started with matchmaking"
- https://docs.unity.com/en-us/mps-sdk/matchmaking/mm-backfill — "Backfill"
- https://docs.unity.com/en-us/mps-sdk/matchmaking/mm-qos — "Quality of Service"
- https://docs.unity.com/en-us/mps-sdk/matchmaking/mm-rate-limits — "Matchmaker rate limits"

Read, but not on docs.unity.com (public sample of the config-as-code file; used only for key names/shape):

- https://github.com/Unity-Technologies/unity-gaming-services-cli/blob/main/Samples/Deploy/Matchmaker/queue.mmq — UGS CLI sample queue file (camelCase keys, `$schema` = `https://ugs-config-schemas.unity3d.com/v1/matchmaker/matchmaker-queue.schema.json`)

Seen only as web-search result snippets (page body not read; treated as weak evidence):

- https://docs.unity.com/en-us/matchmaker-unreal/sdk-api/matchmaker-client/models/status-enum — ticket status enum (Unreal SDK)
- https://docs.unity.com/en-us/mps-sdk/matchmaking/mm-backfill and the `advanced-topics-backfill` / `advanced-topics-parties` pages were also surfaced by search; the `advanced-topics-*` pages could not be fetched here.

Note: the Matchmaker pages exist under several URL families (`/matchmaker/...`, `/ugs/manual/matchmaker/...`, `/mps-sdk/matchmaking/...`) with the same content. Unity's docs also state the sample rule JSON in PascalCase (dashboard / REST style) while the CLI `.mmq` sample uses camelCase.

## Inventory

| ID | Area | Element | What the docs say | Source | Status | Simulator behaviour / interpretation |
|---|---|---|---|---|---|---|
| S01 | Queue | Name | A queue has a name; a ticket names its queue (`queueName`). Name is a free string chosen at creation. | queues-pools; get-started-mm | N/A | One run = one queue/pool; the rules file `Name` is shown in the report. The queue `name` of a `.mmq` file is accepted and not used. |
| S02 | Queue | Default queue | Fallback queue used "if the ticket created doesn't specify the name of the queue". | queues-pools | N/A | No queue selection. |
| S03 | Queue | Queue isolation | "A queue contains a mutually exclusive set of tickets that you can match together. Tickets in a queue are not matched with tickets found in another queue." | queues-pools | N/A | Only one pool exists per run, so isolation is trivial. |
| S04 | Queue | Enabled | `enabled` (bool) exists on queue (and pool) in the CLI sample file (`true`). Semantics not described in the pages read. | queue.mmq sample | Partial | Not part of the pool rules JSON. In a `.mmq` file (S73), `true` on the queue and the default pool is accepted (the simulated pool is enabled); `false` is reported as unsupported (N25). |
| S05 | Queue | MaxPlayersPerTicket | Set when creating a queue ("maximum number of players on a matchmaking ticket"); CLI key `maxPlayersPerTicket` (sample: 2). Ticket limit: number of players "150 or the maximum number of players in a team". | get-started-mm; mm-rate-limits; queue.mmq | Implemented | Flow `queue.maxPlayersPerTicket`; if the flow omits it, `maxPlayersPerTicket` of a `.mmq` rules file (S73); else 150 (N31). A ticket above it is an input error (exit 2, N27). |
| S06 | Queue | Limits | Max 10 queues; max 10 pools per queue. | mm-rate-limits | Not implemented | Queue/pool count limits are not enforced. |
| S07 | Pool | Timeout | "Set the timeout value for a ticket" when creating a pool. CLI key `timeoutSeconds` lives on the pool (sample: 90). No default or min/max stated in the pages read. | get-started-mm; queue.mmq | Implemented | Flow `queue.timeoutSeconds`; if the flow omits it, `defaultPool.timeoutSeconds` of a `.mmq` rules file (S73); else 60 (N31). Terminal status `timeout` (N23). |
| S08 | Pool | DefaultPool | Fallback pool of a queue: processes tickets "that aren't compatible with any other pool". Example: regional pools with a default pool as fallback region. CLI: `defaultPool` object. | queues-pools; queue.mmq | Partial | One pool described by the rules file. In a `.mmq` file (S73) that pool is `defaultPool` (its `matchLogic` and `timeoutSeconds`); there is no fallback logic because filtered pools are not simulated (S09). |
| S09 | Pool | FilteredPools | Other pools in the queue, each with filters. CLI: `filteredPools` array (empty in sample). "The matchmaker assigns tickets that don't match the filters of a pool to a subsequent pool. If the ticket isn't compatible with any of the pools, it uses the default pool." Implies ordered evaluation of pools. | queues-pools; queue.mmq | Not implemented | No filtered pools; ticket `attributes` in a flow and a non-empty `filteredPools` in a `.mmq` file are reported as unsupported (exit 2 without `--allow-unsupported`; with it, every ticket joins the default pool). |
| S10 | Pool | Filters | Decide which tickets a pool processes, based on ticket `Attributes` (key/value; values `text` or `number`). All filters case sensitive. Multiple filters on one pool: all must pass (AND). | queues-pools | Not implemented | Pool filters are not simulated (see S09). |
| S11 | Pool | Filter type Comparator | Operators `=`, `!=`, `<`, `>`. Value type (text) inferred. | queues-pools | Not implemented | Comparator filters are not simulated. |
| S12 | Pool | Filter type CEL | Free boolean expression in Google CEL; string literals need quotes; attributes are flat key→text/number. Example: `platform == "windows" \|\| platform == "ps5"`. | queues-pools | Not implemented | CEL filters are not simulated. |
| S13 | Pool | Pool variants | CLI sample has `variants: []` on the default pool. Not described in the docs pages read. | queue.mmq | Not implemented | A non-empty `variants` in a `.mmq` file is reported as unsupported (exit 2 without `--allow-unsupported`; with it, every ticket uses the default pool's `matchLogic`). |
| S14 | Pool | Hosting | Each pool can specify hosting info (Cloud Code module / Client Hosting; sample: Multiplay). Out of simulator scope. | queues-pools; get-started-mm | N/A | Hosting is out of scope; `matchHosting` in a `.mmq` file is accepted and not read. |
| S15 | Pool rules JSON | Name | Top-level `Name` (string), e.g. "Test". CLI nests it as `matchLogic.name`. | get-started-mm; queue.mmq | Implemented | `Name` (in a `.mmq` file, `defaultPool.matchLogic.name`) shown in report/JSON. |
| S16 | Pool rules JSON | MatchDefinition | Object with `Teams` (array) and `MatchRules` (array of rules). | get-started-mm | Implemented | `Teams` and `MatchRules` parsed (keys case-insensitive; unknown keys warn). |
| S17 | Pool rules JSON | BackfillEnabled | Bool. When true, Matchmaker itself starts backfill ("start a match faster, without all the required players"). When false, backfill still works if the game server creates a backfill ticket. | get-started-mm; mm-backfill | Partial | `false` implemented. `true` is reported as unsupported (exit 2 unless `--allow-unsupported`, then behaves as `false`, N28). |
| S18 | Teams | Team Name | Each team definition has `Name` (e.g. "Main team", "Team"). | get-started-mm; mm-backfill | Implemented | Used as team name in matches and expectations (`Name #i` if TeamCount.Max > 1). |
| S19 | Teams | TeamCount | `{Min, Max, Relaxations}` — number of teams of this definition in a match. Example: `Min 1, Max 1`. CLI sample: `Min 2, Max 2`. `Relaxations` optional. | get-started-mm; mm-backfill; queue.mmq | Implemented | Min/Max and `RangeControl.ReplaceMin` relaxation (N20, N21). |
| S20 | Teams | PlayerCount | `{Min, Max, Relaxations}` — players per team. Example `Min 1, Max 5`; `Min 60, Max 60` with relaxation. | get-started-mm; mm-backfill | Implemented | Min/Max and `RangeControl.ReplaceMin` relaxation; Max fills greedily (N1). |
| S21 | Teams | TeamRules | Array of rules evaluated at team level ("team-level rules ensure the validity of the team they are defined in"). | mm-rules; get-started-mm | Implemented | Evaluated over the players of one team (the match-wide ticket age drives relaxations, N6). |
| S22 | Teams | MatchRules | Array of rules evaluated at match level. Limits: 25 match rules; 25 team rules (per config). | mm-rules; mm-rate-limits | Implemented | Evaluated over all players of the candidate match. The 25-rule limit is not enforced. |
| S23 | Teams | Multiple team definitions | `Teams` is an array; limit "Teams: 100". Docs pages read give no multi-definition example or statement about how TeamCount applies per definition. | mm-rate-limits | Implemented | Several definitions: each contributes its TeamCount.Min..Max teams (N20). |
| S24 | Rule | Name | Optional label in examples (`"Name": "QoS"`). Not in the base rule field table. | mm-qos; mm-rules | Implemented | Used in reasons/reports; defaults to `matchRuleN`/`teamRuleN`. |
| S25 | Rule | Type | Required string; one of the supported rule types (S33–S40). | mm-rules | Partial | Equality, Difference, LessThan(Equal), GreaterThan(Equal), InList, Intersection. Any other type (e.g. `DoubleDifference`, not in this inventory) is unsupported (N35). |
| S26 | Rule | Source | Required string: data source path (S41+), optionally with an operation suffix (S47). | mm-rules | Partial | `Players.CustomData.<nested path>[.<operation>]` only; this covers `Players.CustomData.ExternalData.CloudSave.<key>[.<path>]` (S44). QoS sources and ExternalData sources other than CloudSave (Leaderboard, S43) are unsupported. |
| S27 | Rule | Reference | Optional string/number/array. "Not used by all rules. Valid reference types depend on rule type." | mm-rules | Implemented | Type-checked per rule type at parse time (input error if wrong). |
| S28 | Rule | Overlap | Number; used by Intersection ("minimum intersection"). | mm-rules | Implemented | Intersection `Overlap` (N15); required for Intersection. |
| S29 | Rule | Not | Optional bool; "Inverses the rule if set as true. Is false, if not provided." | mm-rules | Implemented | Negates the whole rule result (N12). |
| S30 | Rule | EnableRule | Optional bool; "Disables the rule if set to false. Is true if not provided. This is usually used to disable or enable a rule by a relaxation." A disabled rule is not applied (docs call rules "hard" vs "soft" nowhere; EnableRule is only an on/off switch). | mm-rules; rule-relaxations | Implemented | `false` = rule not applied until a `RuleControl.Enable` relaxation triggers. |
| S31 | Rule | Level | Match-level rules validate the match; team-level rules validate the team they are defined in. Same rule definition means different scope depending on placement (e.g. Difference "within a match or team"). | mm-rules | Implemented | MatchRules over the match, TeamRules over each team. |
| S32 | Rule | Relaxations | Optional list of relaxations on the rule; max 25 per rule. | mm-rules; mm-rate-limits | Implemented | List kept in AtSeconds order (N8). The 25-per-rule limit is not enforced. |
| S33 | Rule type | Difference | Source: List\<number>; Reference: number. "Ensures that the difference between all values in a list is within a certain distance." Example: all players within 200 skill points of each other (max − min ≤ 200 is the natural reading). Inclusive/exclusive bound not stated. | mm-rules | Implemented | max - min <= Reference (N10). Single-valued source is trivially true (N13). |
| S34 | Rule type | Equality | Source: List\<string or number>; Reference: string or number (same type as source), optional. "Ensures that all values in the list are equal." With Reference: all values equal that reference (team-selection example). Without Reference: all values equal each other (same password / same bracket). | mm-rules | Implemented | All values equal; with Reference all equal Reference (N14). Numbers, strings and booleans compare by type. |
| S35 | Rule type | LessThan | Source: number; Reference: number. Source < Reference. Source is typically a single number or an operation result (e.g. `.Count`, `.Avg`); behaviour with a per-player list source is not stated (QoS examples apply it per player: "latency of all the players in the match must be under 100"). | mm-rules; mm-qos | Implemented | Every player's value must satisfy it, or the operation result (N11). |
| S36 | Rule type | LessThanEqual | Source ≤ Reference. Examples: `Players.CustomData.PreferMedic.Count ≤ 2` at team level; QoS latency ≤ 100 at match level. | mm-rules; mm-qos | Implemented | As S35. |
| S37 | Rule type | GreaterThan | Source > Reference. | mm-rules | Implemented | As S35. |
| S38 | Rule type | GreaterThanEqual | Source ≥ Reference. Example: all players have skill ≥ 500 at match level. | mm-rules | Implemented | As S35. |
| S39 | Rule type | InList | Source: string or number; Reference: List\<string or number>. "Ensures that the source value is in the reference list." Example: ChosenCharacter in monster list at team level. | mm-rules | Implemented | Every player's value must be in the Reference list. |
| S40 | Rule type | Intersection | Source: List\<List\<string or number>>; `Overlap`: number; optional Reference list (List\<string>/List\<number>). Ensures the given lists have "a minimum intersection of the provided overlap number". Example: all players share ≥3 preferred maps. With Reference list + Overlap 1: all players have at least one of the reference items. | mm-rules | Implemented | Common items across all players (and Reference) >= Overlap (N15). Scalar values count as one-item lists. |
| S41 | Source | Players.CustomData.{field} | Per-player custom data set by client at ticket creation. "Data in all players" — i.e. rule sees the value of every player in the match/team. | mm-rules; get-started-mm | Implemented | Nested object paths (`A.B.C`) resolved exactly (case-sensitive); missing field = rule unsatisfied (N16). |
| S42 | Source | Players.QoSResults.Latency / .PacketLoss | QoS per player on the ticket (results are by region, with latency and packet-loss ratio). Docs spell it `QoSResults` in the source table and `QosResults` in the example JSON. | mm-rules; mm-qos | Not implemented | QoS sources are unsupported (rule ignored under `--allow-unsupported`). |
| S43 | Source | ExternalData: Leaderboard | `Players.CustomData.ExternalData.Leaderboard.Score` / `.Tier`; rule must carry `ExternalData.Leaderboard.Id`. Data auto-appended to incoming tickets. Player without data: added to the leaderboard with score 0. Leaderboard without tiers + tier rule: "All tickets that end up in this pool will fail to match." | mm-rules | Not implemented | Leaderboard sources and a rule-level `ExternalData.Leaderboard` are unsupported (N29). |
| S44 | Source | ExternalData: CloudSave | `Players.CustomData.ExternalData.CloudSave.{path}`; period-delimited path: first segment = Cloud Save key, remaining segments traverse the item (e.g. `Inventory.Apples` → 10). Optional `ExternalData.CloudSave.AccessClass` (default `Protected`) and `Default` (type must be compatible with the rule). No data and no Default → "the ticket will be incompatible with the rule definition". | mm-rules | Implemented | Values come from each player's `externalData.cloudSave` in the flow, never from `customData` (N29). The segment after `CloudSave` is the key and the rest is the path inside the item (both case-sensitive; `ExternalData`/`CloudSave` themselves are case-insensitive); an operation suffix (S47) needs at least the key before it (N32). A player without the key uses `Default` as the whole item (N37). No key and no `Default`, or nothing at the path, leaves the rule unsatisfied (as N16); the ticket's reasons say why. A `Default` with nothing at the path warns when the rules are read. `AccessClass` must be a string and is not used (N38). A Source that names no key is an input error; an `ExternalData.CloudSave` block on a rule with another Source warns and is ignored. |
| S45 | Source | Ticket attributes | `Attributes` on the ticket are used by pool filters (S10), not documented as rule sources. | queues-pools | Not implemented | Ticket attributes are unsupported in flows (see S09). |
| S46 | Source | Aggregation (implicit) | Sources named `Players.…` resolve to a list with one entry per player in the evaluated scope (match or team); Difference/Equality operate over that list. Docs describe this only through examples ("all players in the match"). | mm-rules | Implemented | One list entry per player in scope. |
| S47 | Source | Data operations | Suffix on a source path: `Count` (List\<*>→number), `Median`, `Avg`, `Sum`, `Min`, `Max` (List\<number>→number). Examples: `Players.CustomData.Skill.Avg` "averaging the skill of all the players in a match/team"; `Players.CustomData.PreferMedic.Count`. "Some of the input provided on players custom data … support operations." | mm-rules | Implemented | Count/Median/Avg/Sum/Min/Max over all players' (flattened) values (N17, N32, N33). |
| S48 | Relaxation | Fields | `Type` (req), `Value` (req, any type per docs table), `AtSeconds` (req, number, "seconds (inclusive) after which the relaxation is triggered"), `AgeType` (req per table). Examples omit Value (Enable/Disable) and AgeType (Replace). | rule-relaxations | Implemented | `Type`, `AtSeconds` required; `AgeType` defaults to Oldest; `Value` required for Replace types (N9). |
| S49 | Relaxation | AgeType | `Oldest` (default), `Average`, `Youngest`. Triggered when: oldest ticket in the match is X s old / average age of tickets in the match reaches X / youngest ticket in the match reaches X. | rule-relaxations | Implemented | Oldest/Average/Youngest over the tickets of the candidate match (N5). |
| S50 | Relaxation | Type RuleControl.Enable | When triggered, the rule is applied (pairs with `EnableRule: false`). | rule-relaxations | Implemented | Rule applied from the trigger on. |
| S51 | Relaxation | Type RuleControl.Disable | When triggered, the rule stops being applied. | rule-relaxations | Implemented | Rule skipped from the trigger on. |
| S52 | Relaxation | Type ReferenceControl.Replace | When triggered, the rule's Reference is replaced by `Value` (examples: 200→300 Difference; latency 100→150 at 30 s). | rule-relaxations; mm-qos | Implemented | Reference replaced (validated against the rule type). |
| S53 | Relaxation | Type RangeControl.ReplaceMin | Only for TeamCount / PlayerCount: Min replaced by `Value` (example: PlayerCount Min 60→1 at 5 s, AgeType Oldest). | rule-relaxations; mm-backfill | Implemented | Min of TeamCount/PlayerCount replaced; the new Min is not checked against Max. |
| S54 | Relaxation | Age of ticket | "Relaxation is triggered based on the age of tickets in a match." Ticket age = time since ticket creation is implied; the pages do not define the clock precisely. | rule-relaxations | Implemented | Age = simulated seconds since arrival (N7). |
| S55 | Relaxation | Multiple relaxations | A rule/range holds a list; up to 25 per rule. Interaction of several triggered entries on one field is not described (later AtSeconds naturally overrides). | mm-rules; mm-rate-limits | Implemented | Applied in AtSeconds order, last wins (N8). |
| S56 | Relaxation | Backfill | "Team count and player count are automatically relaxed to their maximum relaxation when backfilling a match." | rule-relaxations | Not implemented | No backfill. |
| S57 | Ticket | Creation | `POST /v2/tickets` with `queueName`, `attributes`, `players[{id, customData, (QoS results)}]`. "Player IDs must be different to be matched together." | get-started-mm | Partial | Flow tickets: `id`, `at`, `players[{id, customData, externalData}]` or one-player shorthand; `externalData` stands in for the data the service appends (S44). Tickets sharing a player id are never matched together (N36). No `queueName`. |
| S58 | Ticket | Size limits | Request ≤25 KB; player ID ≤64 chars; players per ticket ≤150 or max team size; ≤128 custom-data properties; name ≤64 chars; string value ≤200 chars; array ≤100 items. | mm-rate-limits | Partial | Only players-per-ticket is checked (S05); other size limits are not enforced. |
| S59 | Ticket | Polling / status | Clients poll ticket status (about 1 per second; rate limit 1 req/s per player). Status enum (Unreal SDK page, snippet only): `InProgress` (default), `Found`, `Timeout`, `Failed`, `Forbidden`. | get-started-mm; mm-rate-limits; status-enum (snippet) | Partial | Outcomes `matched` / `timeout` only (N24). |
| S60 | Ticket | Timeout | Pool-level ticket timeout (S07). Ticket that exceeds it ends as `Timeout` (per status enum). | get-started-mm | Implemented | See S07. |
| S61 | Ticket | Deletion | Players can delete a ticket (cancel); rate limited to 1/s per player. | mm-rate-limits; get-started-mm | Not implemented | No ticket cancellation in flows. |
| S62 | Ticket | Multi-player tickets | A ticket may contain several players (party), up to MaxPlayersPerTicket. Party QoS strategies: per-player results, averaged, or leader's. That a ticket's players stay together in one match is implied by "ticket" being the matching unit but is not stated verbatim in pages read. | mm-qos; mm-rate-limits | Implemented | Ticket is atomic: its players stay on one team of one match (N18). |
| S63 | Timing | Cycle / latency | No evaluation interval is documented. Only hints: backfill ticket auto-update by `backfillingLoopInterval`; backfill approvals every second; "at least four seconds" recommended for a min-player relaxation in backfill setups. | mm-backfill | Implemented | Simulated tick, default 1 s, flow `tickSeconds` (N2). |
| S64 | Match search | Choosing among matches | Not documented. Docs describe only validity ("rules ensure the validity of the match") and relaxations making matches easier over time. | mm-rules; rule-relaxations | Implemented | First valid match in deterministic order (N3, N4). |
| S65 | Match search | Min vs Max | Example: PlayerCount Min=Max=60, relaxed to Min 1 after 5 s, so "first match is created if there are 60 players… after five seconds, the subsequent match is created if at least one player is in the match". Also: "When the minimum player count is one, the matchmaker considers a match found as soon as a single player enters the queue." Suggests a match can form as soon as Min is satisfied (as opposed to waiting for Max). | mm-backfill | Implemented | Form once all Min are met, fill to Max, never wait for more (N1). |
| S66 | Backfill | Initiation | Matchmaker-initiated (config `BackfillEnabled: true`) to start with fewer players, or server-initiated by creating a backfill ticket. | mm-backfill | Not implemented | No backfill (S17). |
| S67 | Backfill | Flow | Server approves backfill ticket every second (proves liveness); un-approved ticket is deleted by service; new compatible tickets are added to an existing backfill ticket and assigned on next approval; unassigned tickets are released to the pool if the backfill ticket is updated/deleted/timed out. | mm-backfill | Not implemented | No backfill. |
| S68 | Backfill | Rate limits | Create/update backfill ticket: 1 req/s (service account). | mm-rate-limits | N/A | Rate limits are not simulated. |
| S69 | QoS | Rules & regions | QoS results are per region (latency + packet-loss ratio). Rules read `Players.QoSResults.Latency/PacketLoss`; example match rule LessThanEqual 100 relaxed to 150 at 30 s. Docs advise always relaxing QoS rules. How the region of a match is chosen: not documented in pages read. | mm-qos | Not implemented | No QoS or regions (N26). |
| S70 | Output | MatchProperties | Backfill code shows match properties: `teams[{teamName, teamId, playerIDs[]}]`, `players[{id, customData}]`, `region`, `backfillTicketId`. | mm-backfill | Partial | JSON/report list teams, tickets and player ids per match; no region/backfill ticket id. |
| S71 | Output | Team assignment | Output assigns each player to a named team; names come from the Team `Name` in MatchDefinition (implied). How players are distributed to teams is not specified. | mm-backfill; get-started-mm | Implemented | Deterministic slot assignment (N19). |
| S72 | Config limits | Config | Teams 100; team rules 25; match rules 25; relaxations per rule 25. | mm-rate-limits | Not implemented | Limits are not enforced. |
| S73 | Config-as-code | File shape | UGS CLI `.mmq` queue file: `$schema`, `name`, `enabled`, `maxPlayersPerTicket`, `defaultPool{variants, name, enabled, timeoutSeconds, matchLogic{matchDefinition{teams[{name, teamCount{min,max,relaxations}, playerCount{min,max,relaxations}, teamRules}], matchRules}, name, backfillEnabled}, matchHosting{…}}`, `filteredPools`. Same model as dashboard JSON with camelCase. | queue.mmq | Partial | `--rules` accepts a `.mmq` file (detected by the `.mmq` extension or a top-level `defaultPool` key; keys case-insensitive, unknown keys warn). `defaultPool.matchLogic` is read like the pool rules JSON. `maxPlayersPerTicket` and `defaultPool.timeoutSeconds` are used when the flow's `queue` omits them; a value in the flow wins, with a warning when the two differ (S05, S07). `$schema`, the queue and pool `name` and `matchHosting` are accepted and not used. A non-empty `filteredPools` (S09) or `variants` (S13), and `enabled: false` (S04), are unsupported. |

## Not specified by the docs

1. **N1 · Formation threshold: Max or Min?** Docs show only that Min=1 forms a match as soon as one player is present (S65). Not stated whether the matcher waits for Max when Min is already met. *Proposed in survey:* at each evaluation, build the largest valid match possible per team up to Max from the candidate tickets (greedy fill to Max), and emit it if every count ≥ Min; never hold tickets back to wait for more players.
   *Chosen:* Greedy fill up to Max once all Min are satisfied; a match is emitted at once, never held back.
2. **N2 · Evaluation cycle interval / latency.** No cycle documented (S63). *Proposed in survey:* a fixed simulated tick (default 1 s of sim time, configurable); matches are formed only on ticks; relaxations are evaluated at tick time.
   *Chosen:* Fixed tick, default 1 s of simulated time (flow `tickSeconds`); matches form only on ticks (t = 0, tick, 2*tick, ...). Timeouts are stamped at their exact time.
3. **N3 · Order tickets are considered.** *Proposed in survey:* oldest ticket first (creation time, then ticket id as tie-break); each match is anchored on the oldest unmatched ticket, then candidates are added in age order.
   *Chosen:* Oldest first (arrival, then ticket id). Each ticket in that order is tried as anchor; candidates are added in the same order. An anchor that cannot form a match is skipped and later anchors are still tried.
4. **N4 · Choosing among valid matches / soft-rule optimisation.** Docs give no scoring (S64). *Proposed in survey:* purely feasibility-based: first valid match found by the deterministic greedy order in (3); no scoring.
   *Chosen:* Feasibility only, no scoring: the first valid match in the order of N3 wins.
5. **N5 · How AgeType=Average is computed across a candidate match.** Docs: "average age of tickets in a match". *Proposed in survey:* arithmetic mean of the ages of tickets (one entry per ticket, not per player) in the candidate match at the evaluation instant; Oldest = max, Youngest = min.
   *Chosen:* Arithmetic mean of ticket ages in the candidate match; Oldest = max, Youngest = min.
6. **N6 · When AgeType is evaluated for a relaxation on a rule shared across candidates.** *Proposed in survey:* re-evaluate against each candidate match; a relaxation is active if its trigger holds for that candidate (age ≥ AtSeconds, inclusive).
   *Chosen:* Re-evaluated per candidate: while tickets are added (on the partial match) and on the finished candidate. The timeline additionally logs when a relaxation first holds for the waiting queue as a whole.
7. **N7 · Ticket age clock origin.** *Proposed in survey:* simulated time since the ticket's creation (enqueue) event, in seconds; not reset by re-queue or pool reassignment.
   *Chosen:* Simulated seconds since the ticket's arrival; never reset.
8. **N8 · Several triggered relaxations on the same field.** *Proposed in survey:* apply all triggered entries in ascending AtSeconds order (ties: list order); for Replace/ReplaceMin the last applied wins; Enable/Disable likewise last wins.
   *Chosen:* Ascending AtSeconds, ties by list order, last applied wins.
9. **N9 · Relaxation `Value` with RuleControl, and omitted `AgeType`.** Docs table marks AgeType required but also says Oldest is default and examples omit it. *Proposed in survey:* default `Oldest`; ignore `Value` for Enable/Disable.
   *Chosen:* AgeType defaults to Oldest; `Value` ignored for Enable/Disable.
10. **N10 · Difference bound inclusiveness and semantics.** Docs: "within a certain distance". *Proposed in survey:* max(values) − min(values) ≤ Reference (inclusive).
   *Chosen:* max - min <= Reference (inclusive).
11. **N11 · Numeric comparators on list sources.** LessThan etc. take a single number, yet QoS examples apply them to per-player values. *Proposed in survey:* if the source resolves to a list, the comparator must hold for every element; if it has an operation suffix, it is a single number.
   *Chosen:* A list source must satisfy the comparator for every player; with an operation suffix the single result is compared.
12. **N12 · `Not` semantics for list-wide rules.** *Proposed in survey:* logical negation of the whole rule result (e.g. Not+Equality = "not all equal"), not per-element negation.
   *Chosen:* Negation of the whole rule result. Example: `Not` + `InList` is violated only when every player's value is in the list.
13. **N13 · Equality / Difference with a single player in scope.** *Proposed in survey:* trivially true.
   *Chosen:* Trivially true.
14. **N14 · Equality with Reference on a list source.** *Proposed in survey:* every element equals Reference.
   *Chosen:* Every element equals the Reference.
15. **N15 · Intersection details.** Whether `Overlap` counts items common to *all* players or pairwise; behaviour when a Reference is also given. *Proposed in survey:* size of the set-intersection across all players' lists (and with Reference if given) ≥ Overlap.
   *Chosen:* Items common to all players' lists (and to the Reference list if given) counted by type-aware equality; need >= Overlap.
16. **N16 · Missing custom-data field on a player.** Only ExternalData cases are covered (S43/S44). *Proposed in survey:* the rule cannot be satisfied (ticket incompatible), unless the rule is disabled; reported loudly in the simulator output.
   *Chosen:* The rule is unsatisfied (also with `Not`) and the ticket's reasons say which player lacks the field. Disabled rules are not evaluated.
17. **N17 · Source with array custom data across multi-player tickets.** Sources aggregate "per player" (S46), but how a ticket-level array (e.g. `PreferredMaps`) flattens for Count/Sum. *Proposed in survey:* per-player value is the array; operations apply per player, then rules apply across players.
   *Chosen:* Changed from the proposal: values of all players are flattened (arrays expand) and the operation aggregates across every player in scope; the rule then sees one number.
18. **N18 · Do a ticket's players stay together?** Not stated verbatim (S62). *Proposed in survey:* yes, a ticket is atomic; its players always land on the same team and in the same match.
   *Chosen:* A ticket is atomic.
19. **N19 · Team assignment of tickets.** Docs do not describe how tickets are distributed over multiple teams/definitions. *Proposed in survey:* deterministic first-fit in ticket-age order over teams in definition order, honouring team rules and Max, then balance by adding to the team with fewest players on ties.
   *Chosen:* Changed from the proposal: slots for the effective TeamCount.Min of each definition are filled balanced (fewest players first; ties by definition order, then slot index); slots beyond Min up to Max are used only when no required slot fits or accepts the ticket.
20. **N20 · Multiple team definitions with TeamCount.** Meaning of TeamCount per definition, and whether definitions with different names can have different counts. *Proposed in survey:* each definition contributes between Min and Max teams; total match must satisfy each definition's TeamCount and PlayerCount.
   *Chosen:* Every definition contributes TeamCount.Min..Max teams; each non-empty team needs PlayerCount.Min..Max players; all definitions must reach their TeamCount.Min.
21. **N21 · TeamCount.Min < Max semantics.** *Proposed in survey:* a match needs ≥ Min full-enough teams (each with PlayerCount ≥ Min); fill extra teams up to Max if tickets remain.
   *Chosen:* A match needs >= effective TeamCount.Min non-empty teams per definition, each with >= effective PlayerCount.Min players; extra teams are filled up to Max.
22. **N22 · Pool-filter assignment time and ordering.** Docs: "subsequent pool", default pool fallback (S09). *Proposed in survey:* at enqueue, test filtered pools in listed order, first match wins, else default pool; tickets never move between pools afterwards; pools match independently.
   *Chosen:* Not implemented: no pools or filters; flow ticket `attributes` are reported as unsupported.
23. **N23 · Ticket timeout boundary.** Default/limits not stated (S07). *Proposed in survey:* ticket times out when age ≥ `TimeoutSeconds` before it is matched; a timeout is a terminal status; a match formed in the same tick wins.
   *Chosen:* A ticket times out when age >= `timeoutSeconds`; a match formed on the same tick wins; the timeout time is arrival + timeout (may fall between ticks).
24. **N24 · Ticket statuses beyond the enum.** Transitions of `Failed`/`Forbidden` undefined. *Proposed in survey:* simulator emits only InProgress, Found, Timeout (and Deleted for cancel), plus a hard error for invalid config.
   *Chosen:* Only `matched` and `timeout` are produced.
25. **N25 · Queue `Enabled=false` / pool `enabled=false`.** *Proposed in survey:* ticket creation to a disabled queue is rejected; disabled pools are skipped in assignment.
   *Chosen:* Not implemented: `enabled: false` on the queue or the default pool of a `.mmq` file is reported as unsupported; if allowed, the run behaves as if it were enabled. The pool rules JSON has no `enabled`.
26. **N26 · QoS region selection.** Docs do not say how a match region is chosen or which region's latency a rule reads when a ticket has several. *Proposed in survey:* ticket QoS is a single latency/packet-loss pair per player (best region); regions are out of scope for v1.
   *Chosen:* Not implemented: QoS sources are unsupported; no regions.
27. **N27 · MaxPlayersPerTicket enforcement vs team Max.** *Proposed in survey:* reject tickets with more players than MaxPlayersPerTicket at creation; a ticket larger than the team Max can never match.
   *Chosen:* Changed from the proposal: a ticket above `queue.maxPlayersPerTicket` is an input error (exit 2). A ticket larger than every team's PlayerCount.Max stays unmatched and the reason says so.
28. **N28 · Backfill simulation.** Server-side flow is documented, matching of backfill tickets to new tickets is not. *Proposed in survey:* v1 out of scope except honouring `BackfillEnabled` as a marker and the "auto-relax to max when backfilling" note.
   *Chosen:* `BackfillEnabled: true` is reported as unsupported and, if allowed, treated as `false`.
29. **N29 · Leaderboard/CloudSave external data in a local simulator.** *Proposed in survey:* treated as ordinary per-player custom data supplied in the ticket stream under the same source path, with the documented defaults (score 0, CloudSave `Default`).
   *Chosen:* Changed from the proposal: CloudSave values are supplied per player in the flow under `externalData.cloudSave` (Cloud Save key → item), separately from `customData`, and `Default` applies as in N37. A key named `ExternalData` in a flow's `customData` is not read by any rule and produces a warning: a user's measurement on the real service found that ticket custom data does not change the values these rules read. Leaderboard sources (S43) stay unsupported and the score-0 default is not applied.
30. **N30 · Docs typos to resolve.** `Players.Custom.SkillBracket` (S34 example) and `QoSResults` vs `QosResults` spelling. *Proposed in survey:* accept both `QoSResults` and `QosResults` case-insensitively; treat `Players.Custom.*` as unknown source → error.
   *Chosen:* Changed from the proposal: any source other than `Players.CustomData.*` (including `Players.Custom.*` and either QoS spelling) is reported as unsupported rather than an error.
31. **N31 · Flow defaults.** The inventory gives no defaults. *Chosen:* `queue.timeoutSeconds` 60, `queue.maxPlayersPerTicket` 150 (the documented limit), `tickSeconds` 1. With a `.mmq` rules file, its `defaultPool.timeoutSeconds` and `maxPlayersPerTicket` are used instead when the flow omits them (S73); these defaults apply only when neither file gives a value.
32. **N32 · Operation suffix vs. nested field.** A custom-data field may be named like an operation. *Chosen:* a last source segment named Count/Median/Avg/Sum/Min/Max (case-insensitive, after at least one field segment) is always the operation.
33. **N33 · What `Count` counts.** *Chosen:* the number of values (after flattening) that are neither `null` nor `false`.
34. **N34 · Non-monotone rules during greedy fill.** Rules with `Not` or an operation suffix can fail on a subset and pass on a superset. *Chosen:* such rules are checked only on the finished candidate; if it fails, tickets are removed from the end (never the anchor) until it passes or only the anchor is left. All other rules are checked on every addition.
35. **N35 · Rule types outside this inventory** (e.g. `DoubleDifference`). *Chosen:* unsupported: exit 2, or ignored (rule treated as always satisfied) with `--allow-unsupported`.
36. **N36 · Same player id on two tickets.** Docs: "Player IDs must be different to be matched together". *Chosen:* such tickets are never placed into the same match.
37. **N37 · What the CloudSave `Default` stands in for.** Docs: `Default` is used when the player has no data and its "type must be compatible with the rule" (S44); they do not say whether it replaces the item of the Cloud Save key or the value at the end of the path. *Chosen:* `Default` replaces the whole item of the key (the first segment after `CloudSave`) and the rest of the Source path is read from it, so `Default: {"rating": 1000}` fits `CloudSave.progress.rating`. A `Default` with nothing at that path leaves the rule unsatisfied for a player without the key (as N16) and warns when the rules are read. The real service was observed to fail such a ticket before its timeout; the simulator has no such outcome (N24), so the ticket waits and times out. Basis: not the public docs but a user's measurement on the real service (2026-10): with `Default` set to a whole item, a player without the key matched a player whose value equalled the `Default`'s and did not match one outside the allowed difference, and two players without the key matched; a bare-number `Default` under a nested path made the ticket fail.
38. **N38 · CloudSave `AccessClass`.** Docs: optional, default `Protected`. A flow has no access classes. *Chosen:* `AccessClass` must be a string when given but changes nothing: a player's `externalData.cloudSave` is the data the rule reads, whatever the access class.

## Limits

What this simulator cannot tell you:

- It is an unofficial approximation built from public docs only; the real service may behave differently wherever the docs are silent (all `N*` items) and in unknown internals (matching algorithm, scheduling, scoring).
- Timing is simulated (ticks, ticket arrival times you supply). Real cycle times, latency, rate limits and polling are not modelled.
- Match quality is not optimised or scored; the first feasible match in a fixed order wins, so the real service may group tickets differently.
- Not simulated: pools and filters, ticket attributes, QoS and regions, Leaderboard ExternalData, backfill, hosting, ticket deletion, configuration limits.
- CloudSave values are whatever the flow supplies (N29); access classes are not modelled (N38), and a ticket the real service would fail because of its `Default` times out instead (N37).
- Rules with `Not` or operation suffixes are checked after the greedy fill (N34), which can miss a valid match that a different selection would give.

## Minimal examples

Written for this document in the documented PascalCase shape.

1. 1v1, same game version (Equality without Reference):

```json
{
  "Name": "duel",
  "MatchDefinition": {
    "Teams": [
      { "Name": "Player", "TeamCount": { "Min": 2, "Max": 2 }, "PlayerCount": { "Min": 1, "Max": 1 } }
    ],
    "MatchRules": [
      { "Name": "SameVersion", "Type": "Equality", "Source": "Players.CustomData.GameVersion" }
    ]
  },
  "BackfillEnabled": false
}
```

2. Skill window widening over time (Difference + ReferenceControl.Replace):

```json
{
  "Name": "skill",
  "MatchDefinition": {
    "Teams": [
      { "Name": "Side", "TeamCount": { "Min": 2, "Max": 2 }, "PlayerCount": { "Min": 2, "Max": 2 } }
    ],
    "MatchRules": [
      {
        "Name": "SkillSpread", "Type": "Difference",
        "Source": "Players.CustomData.Skill", "Reference": 100,
        "Relaxations": [
          { "Type": "ReferenceControl.Replace", "Value": 250, "AtSeconds": 10, "AgeType": "Oldest" },
          { "Type": "ReferenceControl.Replace", "Value": 500, "AtSeconds": 20, "AgeType": "Oldest" }
        ]
      }
    ]
  },
  "BackfillEnabled": false
}
```

3. Ranges with RangeControl relaxation (4–8 players, drop minimum, fall back to a single team):

```json
{
  "Name": "ffa",
  "MatchDefinition": {
    "Teams": [
      {
        "Name": "Everyone",
        "TeamCount": { "Min": 1, "Max": 1 },
        "PlayerCount": {
          "Min": 8, "Max": 8,
          "Relaxations": [
            { "Type": "RangeControl.ReplaceMin", "Value": 4, "AtSeconds": 15, "AgeType": "Average" },
            { "Type": "RangeControl.ReplaceMin", "Value": 2, "AtSeconds": 30, "AgeType": "Youngest" }
          ]
        }
      }
    ],
    "MatchRules": []
  },
  "BackfillEnabled": true
}
```

4. InList (team rule) plus Intersection (match rule), with a rule enabled by a relaxation:

```json
{
  "Name": "roles",
  "MatchDefinition": {
    "Teams": [
      {
        "Name": "Heroes",
        "TeamCount": { "Min": 1, "Max": 1 },
        "PlayerCount": { "Min": 2, "Max": 4 },
        "TeamRules": [
          { "Name": "HeroClass", "Type": "InList", "Source": "Players.CustomData.Class",
            "Reference": ["Tank", "Healer", "Mage"] }
        ]
      }
    ],
    "MatchRules": [
      { "Name": "CommonMaps", "Type": "Intersection", "Source": "Players.CustomData.Maps", "Overlap": 2,
        "Relaxations": [ { "Type": "RuleControl.Disable", "AtSeconds": 25, "AgeType": "Oldest" } ] },
      { "Name": "StrictRegion", "Type": "Equality", "Source": "Players.CustomData.Region",
        "EnableRule": false,
        "Relaxations": [ { "Type": "RuleControl.Enable", "AtSeconds": 5, "AgeType": "Youngest" } ] }
    ]
  },
  "BackfillEnabled": false
}
```

5. Numeric operation source and QoS with Not:

```json
{
  "Name": "coop",
  "MatchDefinition": {
    "Teams": [
      {
        "Name": "Squad", "TeamCount": { "Min": 1, "Max": 1 }, "PlayerCount": { "Min": 3, "Max": 4 },
        "TeamRules": [
          { "Name": "AvgLevel", "Type": "GreaterThanEqual", "Source": "Players.CustomData.Level.Avg", "Reference": 10 },
          { "Name": "MaxTwoMedics", "Type": "LessThanEqual", "Source": "Players.CustomData.Medic.Count", "Reference": 2 }
        ]
      }
    ],
    "MatchRules": [
      { "Name": "Latency", "Type": "LessThanEqual", "Source": "Players.QoSResults.Latency", "Reference": 80,
        "Relaxations": [ { "Type": "ReferenceControl.Replace", "Value": 150, "AtSeconds": 30, "AgeType": "Oldest" } ] },
      { "Name": "NoBannedTag", "Type": "InList", "Not": true, "Source": "Players.CustomData.Tag", "Reference": ["banned"] }
    ]
  },
  "BackfillEnabled": false
}
```
