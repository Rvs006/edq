# EDQ Gap Analysis v3 — Current / Missing / Required

**For:** Claude Code, run inside the EDQ (Electracom Device Qualifier) repository.
**From:** Raj Kadam, Smart Building Solutions Manager, Electracom Projects UK (SAUTER AG).
**Paired reference files (keep open alongside this prompt):**
- `ip_device_qualification_methodology.json` — the 43-test methodology plus operational and edge-resilience contracts as structured data.
- `golden_vector_bms_sauter_ey6as80.json` — first entry in the golden-vector corpus (Sauter EY6AS80 BMS controller, manually qualified 17/04/2026, overall PASS).
- The origin workbook: `Sauter_-_680-AS_-_IP_Device_Qualification_Template_C00.xlsx`.

---

## 1. Mission

The EDQ app exists to reproduce, in software, the IP Device Qualification report that a skilled manual tester produces from the 43-test methodology. **The report EDQ emits must be equivalent to the manual workbook for any IP device, under any reasonable operating conditions, with full evidence preservation and auditable scoring.** Finding that EDQ handles one device cleanly is necessary but not sufficient. Finding that it silently falls over on a different archetype, loses evidence, or produces non-deterministic verdicts is the more important class of finding.

You are performing a gap analysis on the **current EDQ codebase** against that standard. You are not writing fixes in this pass — only identifying where the app currently does the right thing, where it doesn't, and what it should be doing instead.

---

## 2. The primary framing — Current / Missing / Required

Every finding in this analysis must be expressed as a three-way answer:

| Dimension | Question | How to answer |
|---|---|---|
| **Current** | What does EDQ actually do today? | Cite file:line. Paste the relevant code. Describe the observed behaviour. |
| **Missing** | What is the gap between Current and Required? | Be specific. "Missing" includes: feature absent, feature partial, feature wrong, feature correct but only for one archetype, feature correct but not tested. |
| **Required** | What should EDQ do to achieve equivalence with the manual workbook? | Draw from the methodology JSON (`expected_evidence`, `applicability`, `device_agnosticism_pitfalls`, `operational_contract`, `edge_resilience_contract`) and the golden vector (`overall_result_rationale`). |

This trichotomy is the spine of the mapping matrix and every report section. If you ever find yourself writing a finding that says only "this is wrong" without stating both what EDQ does now and what it should do — that finding is not done.

---

## 3. Six levels of equivalence (Tier 1 — MUST)

Every test is evaluated against all six. A test is fully aligned only when all six pass.

| # | Level | Question |
|---|---|---|
| 1 | **Coverage** | Does EDQ have a test at all that corresponds to this reference test number? |
| 2 | **Logic** | Does the EDQ test probe the same property of the device (same protocol, port, trigger)? Or does it superficially share a name but test something different? |
| 3 | **Evidence** | Does the EDQ test capture at minimum the same evidence the methodology declares in `expected_evidence` — and also attach the raw artefacts declared in `evidence_artefacts_required`? |
| 4 | **Verdict vocabulary** | Does the EDQ test emit a result from exactly `{PASS, FAIL, ADVISORY, INFO, N/A}`, with a `na_reason` whenever the result is N/A? |
| 5 | **Essential-flag semantics** | Does EDQ respect the `essential_flag` field? Tests flagged `YES (IoT GATEWAYS ONLY)` must be marked N/A (with reason) on non-gateway devices. |
| 6 | **Device-agnosticism** | Would the EDQ implementation of this test produce a correct, meaningful result if pointed at any of the six non-Sauter archetypes (IoT gateway, IP camera, ACS panel, managed switch, utility meter, simple sensor)? See each test's `device_agnosticism_pitfalls` in the methodology JSON. |

---

## 4. Tiers of audit scope

The full audit covers 20 concerns grouped into three tiers. Claude Code must address every concern. Tiering controls depth — Tier 1 gets exhaustive per-test analysis, Tier 2 gets a dedicated report section each, Tier 3 gets one consolidated "edge-resilience" section.

### Tier 1 — MUST (blocks the equivalence claim)

1. **Coverage** — does the test exist in EDQ?
2. **Logic** — does it probe the right property?
3. **Evidence** — does it capture the right evidence + raw artefacts?
4. **Verdict vocabulary** — correct result values?
5. **Essential-flag semantics** — correctly applied?
6. **Device-agnosticism** — works across archetypes?
7. **Scoring transparency** — is the per-test verdict rule and the overall-result rollup rule explicit, inspectable, and documented? The manual workbook leaves the overall verdict to tester judgement; EDQ must make it a deterministic rule. The golden vector's `overall_result_rationale` is the reference.
8. **Report-template parity** — does EDQ's output map 1:1 to the Sauter C00 workbook's sheet structure, header fields, and per-test row layout? A SAUTER acceptance reviewer must be able to use the EDQ output interchangeably with a manual workbook.
9. **Determinism** — for deterministic-class tests, does running EDQ twice against an unchanged device produce identical verdicts and substantially identical evidence?

### Tier 2 — SHOULD (operational readiness)

10. **Destructiveness and safety gates** — every test has a `destructive_level` in the methodology. EDQ must respect it: refuse destructive tests without `--allow-destructive`, block destructive/disruptive tests on production VLANs, enforce `preceding_tests` ordering. Tests 36 (credentials) and 38 (brute-force lockout) are the critical destructive cases.
11. **Evidence preservation** — raw tool output, command line, tool version, timestamp, tester input verbatim must all be attached to every result. See `operational_contract.evidence_preservation`.
12. **Idempotency and re-run behaviour** — what does EDQ do on a second run? Overwrite, append, merge? Does it resume from an interrupted point? What are the per-test timeouts and retry policies?
13. **SOAK orchestration (test 43)** — seven-day test. State must survive EDQ container restart, tester host reboot, network interruption. Must emit partial-PASS labelling when asked before day 7. Reachability probe must fall back from ICMP to TCP-connect when ICMP is blocked.
14. **Concurrency and test dependency graph** — EDQ must respect `preceding_tests` and avoid collisions (test 4 changes DHCP range → must not collide with test 3; test 38 triggers lockout → must run after all other authenticated tests).
15. **Auth state management** — credential storage never logged, never in report; per-service iteration for tests 36–39 (web + SSH + SNMPv3 + ONVIF + RTSP + proprietary); session hygiene (explicit logout at end of run).
16. **Auditability** — report SHA-256 hash, tester signature, manual override log (original verdict, override, identity, timestamp, justification), EDQ version stamp.
17. **Agent-swarm accountability** — EDQ uses claude-flow / ruflo multi-agent workflows. If any LLM agent makes verdict decisions, the agent prompt, inputs, and decision must be logged with the result. Prompt versioning. Deterministic scoring rules preferred over LLM judgement for PASS/FAIL — LLMs acceptable for narrative comments only.

### Tier 3 — NICE (edge resilience)

18. **Misbehaving-device handling** — device drops packets, closes connections mid-scan, rate-limits, returns garbage on one port but valid on the next. EDQ must handle gracefully with timeouts, retries with backoff, per-probe error reporting.
19. **Manual-test UX and dead code** — the seven manual-inspection tests (14, 20, 23, 31, 33, 40 and others) must show consistent, archetype-appropriate prompts; validate tester input; accept photo/screenshot attachments. Separately, no orphan test definitions (in registry but not invoked, or invoked but not registered).
20. **Internal test harness, IPv6-only, resource constraints, localisation** — EDQ's own scanners should have unit/integration tests against known-good/known-bad fixtures; full test suite runnable against a v6-only device; behaves predictably on modest tester hosts; non-ASCII device hostnames/SSIDs/certificate subjects round-trip without corruption; tester-host timezone does not corrupt SOAK timestamps.

---

## 5. The device classifier is a first-class concern

Before any of the 43 tests runs meaningfully, EDQ must classify the device into one of the nine archetypes in `ip_device_qualification_methodology.json` → `device_archetypes.classes`. The classifier drives which tests run, skip, or emit N/A — especially 6, 12, 25–31 (gateway-only), 32–34 (Wi-Fi), 35 (PoE). If no classifier exists, that is itself a P0 finding and most downstream per-test findings cascade from it.

Classifier audit questions:
- Where in the codebase is device classification performed?
- What signals does it use? (Open-port fingerprint, BACnet vendor-id, MQTT presence, mDNS/SSDP/LLDP, HTTP banners, MAC OUI, explicit tester input.)
- What archetypes does it emit? Do they match the canonical list?
- How is the classifier's output wired into test gating?
- What is the default behaviour on low confidence or `unknown`? Must be fail-safe: run everything, emit N/A only where evidence is unambiguous.

---

## 6. Phased workflow

Do not skip phases. Each one feeds the next. Checkpoint at the end of each phase — this is a big audit and context discipline matters.

### Phase 0 — Orient *(≈ 10–15 tool calls)*

Read `README.md`, `CLAUDE.md` (if present), `docker-compose.yml` / `Dockerfile`. Enumerate the directory tree to ~3 levels. Identify:

- Test **definitions** (`tests/`, `checks/`, `probes/`, `scanners/`, `modules/`).
- **Agent** definitions for the claude-flow / ruflo swarm.
- **Device classifier** — search `classifier`, `archetype`, `device_type`, `profiler`, `fingerprint`.
- **Manual-test** input schema (UI forms, JSON schemas for tester input).
- **Report generation** (`report/`, `templates/`, `renderer/`, `outputs/`).
- **Result model / schema** (`schemas/`, `models/`, `types/`, pydantic models, TS interfaces).
- **Safety / run controls** (CLI flags, VLAN allowlists, destructive-test gating).
- **Persistence layer** (for SOAK state and re-run history).
- **Internal test harness** (`tests/` pytest/jest directory, fixtures).

Locate the canonical list of tests EDQ believes it runs.

Write a ≤ 300-word orientation note summarising: where tests live, how results flow to the report, whether automated and manual paths are separated, whether a classifier exists, whether there is any safety-gate infrastructure, whether there is any internal test coverage.

**Stop after Phase 0 and present the orientation note for review before continuing.** If the repo shape is unexpected, catch it here.

### Phase 1 — Mapping matrix *(≈ 43 × 3 tool calls)*

Load `ip_device_qualification_methodology.json`. For each of the 43 reference tests, produce one row with these columns:

| Column | Content |
|---|---|
| `ref_test_number` | 1–43 |
| `ref_brief` | From methodology JSON |
| `ref_essential_flag` | From methodology JSON |
| `ref_applies_to` | From `applicability.applies_to` |
| `ref_na_conditions` | From `applicability.na_conditions` |
| `ref_destructive_level` | From methodology JSON |
| `ref_evidence_artefacts_required` | From methodology JSON |
| `edq_test_id` | Identifier used inside EDQ. Blank if none. |
| `edq_file_path` | Path(s) where the test is defined |
| `edq_automation_mode` | `automated` / `manual` / `hybrid` / `missing` |
| `edq_scanner_or_tool` | Underlying tool used |
| `edq_current_behaviour` | **1–2 sentence description of what EDQ does today.** |
| `gap_identified` | **Specific gap — what is missing or wrong.** |
| `required_behaviour` | **1–2 sentence description of what EDQ should do.** |
| `coverage_verdict` | `PRESENT` / `PARTIAL` / `MISSING` |
| `logic_verdict` | `MATCHES` / `DRIFTS` / `UNKNOWN` |
| `evidence_verdict` | `MATCHES` / `THINNER` / `MISSING` / `RICHER` |
| `raw_artefacts_attached` | `YES` / `NO` / `PARTIAL` |
| `verdict_vocab_ok` | `YES` / `NO` |
| `essential_flag_ok` | `YES` / `NO` / `N/A_not_applicable` |
| `destructive_gate_ok` | `YES` / `NO` / `N/A_test_is_read_only` |
| `determinism_ok` | `YES` / `NO` / `UNKNOWN` |
| `archetype_risk` | Comma-separated list of archetypes where this EDQ test would fail |
| `na_handling_ok` | `YES` / `NO` — N/A emitted with reason when inapplicable? |
| `overall_alignment` | `FULLY_ALIGNED` / `PARTIALLY_ALIGNED` / `MISALIGNED` / `MISSING` |
| `priority` | `P0` / `P1` / `P2` |
| `notes` | Free text |

Save as `edq_gap_analysis/mapping_matrix.csv` **and** `edq_gap_analysis/mapping_matrix.json`. The three `edq_current_behaviour` / `gap_identified` / `required_behaviour` columns are non-negotiable — every row must have all three populated.

### Phase 2 — Classifier audit *(~10 tool calls)*

Dedicated deep-dive on the device classifier or its absence. Output: `edq_gap_analysis/classifier_audit.md`.

- Locate the classifier. If it does not exist, mark P0 and write a design proposal (inputs, outputs, archetype list, confidence scoring, fail-safe behaviour).
- If it exists, paste 20–50 lines of key code. Answer: what signals? what archetypes emitted? how is confidence expressed/consumed? where is its output read? default on unknown?
- Compare emitted archetypes against `device_archetypes.classes`. Note missing archetypes.
- For each archetype, trace which of the 43 tests would run vs skip vs emit N/A. Does that match the `applicability` rules?

### Phase 3 — Tier 1 deep-dives *(3 sub-phases)*

**Phase 3a — The ten critical-path tests.** Deep-dive on tests where device-agnostic misbehaviour would be most damaging: 8 (MAC OUI coverage), 13 (protocol classifier breadth), 15 (port scan profile), 16 (archetype-aware ruleset), 17/18 (TLS port iteration), 22 (BACnet absence → N/A not FAIL), 25-31 (MQTT archetype gating), 36 (per-service credential iteration), 38 (per-service brute-force), 42 (product-driven CVE match). For each: paste 10–30 lines of code; describe probe invocation; describe verdict decision logic; predict behaviour on each non-Sauter archetype. Answer in current/missing/required form.

**Phase 3b — Scoring transparency audit.** For every test: is the per-test verdict rule expressible as a human-readable rule? Is it inspectable outside the code? Where is the overall-result rollup rule implemented? Does it match `overall_result_rationale` in the golden vector? Are N/A results correctly excluded from the rollup? If any verdict decision is made inside an LLM agent call, is the decision logic auditable? Output: `edq_gap_analysis/scoring_audit.md`.

**Phase 3c — Template-parity and determinism audit.** Obtain the Sauter C00 template structure (sheets, header cell positions, per-test row layout). Diff EDQ's report output structure against it. For determinism: identify tests in `determinism_class=deterministic` and check whether EDQ's implementation is actually deterministic (fixed scan ports? sorted output? stable hash of evidence blob?). Output: `edq_gap_analysis/template_and_determinism_audit.md`.

### Phase 4 — Tier 2 operational audit *(~15 tool calls)*

One consolidated deep-dive covering concerns 10–17 from Section 4. Output: `edq_gap_analysis/operational_audit.md`, with subsections:

1. **Safety gates** — is there a `--allow-destructive` flag? A VLAN allowlist? Test ordering enforcement for `preceding_tests`? What happens today if you run EDQ against a production device?
2. **Evidence preservation** — are raw artefacts attached? Where are they stored? Are command line / tool version / timestamp logged?
3. **Idempotency** — second-run behaviour: overwrite / append / merge? Resume from interruption? Per-test timeout + retry policies?
4. **SOAK orchestration** — how is test 43 implemented? State persistence across restart? Partial-PASS labelling? Reachability fallback?
5. **Concurrency / dependency graph** — is there a dependency graph? Does it enforce `preceding_tests`?
6. **Auth state** — credential storage, per-service iteration for 36–39, session hygiene?
7. **Auditability** — report hash, tester signature, override log, EDQ version stamp?
8. **Agent accountability** — if claude-flow / ruflo agents are in the verdict path, are their prompts versioned and their decisions logged?

### Phase 5 — Tier 3 edge-resilience audit *(~5 tool calls)*

One brief, consolidated section. Output section: append to the final report. Cover concerns 18–20 from Section 4. No need to deep-dive individually; identify the specific risks and flag.

### Phase 6 — Golden-vector simulation *(no network calls)*

Load `golden_vector_bms_sauter_ey6as80.json`. For each expected result, write a one-sentence assertion: "If EDQ is pointed at the Sauter EY6AS80, it should classify as `bms_controller` with `is_iot_gateway=false`, and produce test N result=`X` with `na_reason=Y` if applicable." Then check, against the code read in Phases 2–3, whether EDQ would actually produce that. Pay specific attention to `deviations_from_manual_source` — those are the places where the manual workbook was ambiguous and EDQ must do better.

Then project forward: for each of the six target archetypes in `corpus_coverage_recommendation.target_archetypes_to_add_next`, write a 3–5 sentence prediction of what EDQ would get right and wrong today. This is the device-agnosticism red-team exercise.

### Phase 7 — Final report

Write `edq_gap_analysis/REPORT.md` with the structure below. Every finding uses the current / missing / required framing explicitly.

---

## 7. Report structure

1. **Executive summary** — 8–12 bullets, severity-ranked (`CRITICAL / HIGH / MEDIUM / LOW / INFO`). Classifier and safety-gate findings lead. Each bullet states Current / Missing / Required in compressed form.
2. **Architecture observations** — how EDQ is structured and how that affects equivalence.
3. **Device classifier audit** (Tier 1 / concern 6 foundation) — current / missing / required.
4. **Per-test findings table** — compressed mapping matrix, rows where `overall_alignment != FULLY_ALIGNED`, with the three framing columns prominent.
5. **Tier 1 deep-dives** — the ten critical-path tests, plus scoring transparency, template parity, determinism.
6. **Tier 2 operational readiness audit** — the eight subsections from Phase 4.
7. **Tier 3 edge-resilience audit** — single consolidated section from Phase 5.
8. **Verdict-vocabulary audit** — every EDQ result value not in `{PASS, FAIL, ADVISORY, INFO, N/A}`, file:line refs. Every N/A without a `na_reason`.
9. **Metadata contract audit** — does EDQ capture all 14 required header fields including `device_archetype_classification` and `device_classifier_confidence`?
10. **Device-agnosticism audit** — per reference test, which archetypes does the EDQ implementation handle correctly, which would it break on? Cross-reference `archetype_risk` column.
11. **Essential-flag audit** — every `YES (IoT GATEWAYS ONLY)` test and how EDQ currently decides to run / skip.
12. **Output-format parity** — specific gaps in the workbook/PDF output against the C00 template.
13. **Strengths** — places where EDQ is actively better than the manual workbook (no blank verdicts, explicit N/A reasons, deterministic rollup, raw evidence attachment, archetype-aware rulesets). Important for commercial positioning.
14. **Remediation backlog** — ordered actionable fixes. Per item: file(s), one-line description, effort (S/M/L), priority (P0/P1/P2), tier (T1/T2/T3). No code — just the backlog.
15. **Corpus expansion plan** — directory structure and next 5–6 golden vectors to add (IoT gateway, camera, switch, ACS panel, meter, simple sensor). For each: device properties to capture, which of the 43 tests exercised in PASS path vs N/A path.

---

## 8. Rules of engagement

- **Read-only in this pass.** The only files created are the mapping matrix, the five audit sub-reports, and the final report — all under `edq_gap_analysis/`.
- **Every finding uses the current / missing / required framing.** If a finding is not three-way, it is not done.
- **Cite file:line for every claim about EDQ's current behaviour.**
- **When evidence is ambiguous, mark `UNKNOWN` and state what would resolve it.** Do not guess.
- **Absent classifier = P0.** Absent safety gates for destructive tests = P0. Absent evidence preservation = P1 minimum. LLM-driven verdict decisions without logging = P1.
- **Flag where EDQ is better than the manual workbook.** The manual workbook has known weaknesses (blank verdicts on T12/T16, implicit rollup rule, no raw evidence, over-lenient PASS on T42). If EDQ addresses these, that is commercial differentiation and belongs in the Strengths section.
- **Do not over-format.** Markdown with sensible hierarchy. No emojis. No preamble. No motivational bullets at the top of sections.

---

## 9. Success criteria

Done when all of the following hold:

1. `edq_gap_analysis/mapping_matrix.csv` and `.json` exist, 43 rows each, with `edq_current_behaviour`, `gap_identified`, `required_behaviour`, and `archetype_risk` populated for every row.
2. `edq_gap_analysis/classifier_audit.md`, `scoring_audit.md`, `template_and_determinism_audit.md`, `operational_audit.md` all exist.
3. `edq_gap_analysis/REPORT.md` exists and addresses all 15 sections.
4. Every finding in the report states Current, Missing, and Required.
5. Every claim is traceable to a reference-test number, an archetype, an operational-contract clause, or a specific EDQ file:line.
6. The ten Tier 1 critical-path tests each have a per-archetype behaviour prediction (right/wrong on IoT gateway, camera, switch, ACS panel, meter, sensor).
7. The corpus expansion plan names at least five additional archetypes with per-archetype test-applicability summaries.
8. Tier 2 and Tier 3 each have at least one concrete finding per concern. If a concern genuinely does not apply ("EDQ has no agents"), that is itself a finding — state it.

---

## 10. Kickoff

Begin with Phase 0. Pause at the end of Phase 0 and present the orientation note before moving to Phase 1. Do not attempt all phases in a single uninterrupted run — the mapping matrix alone will take dozens of tool calls; checkpoint progress so the work can be course-corrected.

If at any point the codebase contradicts this prompt (EDQ uses a sixth result value, stores tests in an unexpected format, has a classifier that doesn't match this document's archetype list, uses an LLM for verdict decisions), **stop and surface the contradiction** rather than silently reinterpreting the prompt.
