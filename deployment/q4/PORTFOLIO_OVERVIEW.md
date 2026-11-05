# Portfolio Overview and One Page reconciliation

`/portfolio/` replaces Project Labels in all primary navigation. Existing `/project-labels/` bookmarks redirect; its embedded label registry remains the build input to preserve labels/exports. Root continues to open Total Summary.

The generated `assets/portfolio-overview-data.json` combines current domain project rows with the existing label register. It does not change any planning totals or connect to Confluence itself. Plan rows include unnamed/zero-effort projects and projects retained in the current domain planning source (including the approved FY27Q1 Upstream item). Plan B is excluded.

## CSCOP control view

The menu remains last. The main register now has one card per CSCOP across domains, with every related source project name retained in details. Records without a CSCOP are available in a separate view and excluded from the CSCOP count. The four visible dimensions are:

1. Type = confirmed demand source (HMT / Mainland / HMT + Mainland); unknown sources are not assigned Mainland.
2. Intake = a real recorded intake number. Empty values and N/A/TBD placeholders do not count.
3. Five Gateway timelines with planned and actual dates shown separately and explicit evidence criteria.
4. Q4 itemised resource allocations by domain, project, person, role, category and MD. Shared-reference source effort is deduplicated within a card, but cannot be summed across its linked CSCOP cards. No portfolio MD total is derived from the CSCOP cards.

Gateway criteria follow the latest confirmed user definition: GW1 BRD sign-off; GW2 SOW signed; GW3 Coding AND TUAT complete; GW4 Release complete; GW5 Handover sign-off. A stage label or an actual date alone never establishes completion. Completion evidence is not assembled across different project records. If one CSCOP covers several named projects, all relevant project records need completion evidence. Conflicting dates/booleans require review. A missing actual date is still displayed when completion evidence is supplied. Only explicit planned dates can drive a past-target flag, which indicates that confirmation is needed, not a proven delay. Existing goLive fields populate GW4 planned date only. Optional SIT/BUAT and feasibility artefacts can be retained as source evidence later; they are not silently introduced as mandatory gates by this implementation.

Example of additional fields on a future One Page project (example only; not published into production data):

```json
{
  "intakeNumber": "RITM1234567",
  "demandSource": "HMT",
  "gateways": {
    "intake": {"plannedDate":"2026-11-02","actualDate":"2026-11-03","evidence":{"brdSignOff":true}},
    "feasibility": {"plannedDate":"2026-11-06","actualDate":null,"evidence":{"sowSigned":false}},
    "dev": {"plannedDate":"2026-12-01","actualDate":null,"evidence":{"codingComplete":false,"tuatComplete":false}},
    "deploy": {"plannedDate":"2026-12-10","actualDate":null,"evidence":{"releaseComplete":false}},
    "handover": {"plannedDate":"2026-12-15","actualDate":null,"evidence":{"handoverSignOff":false}}
  }
}
```

Use source booleans only when explicitly evidenced; omitted/null is unknown. Resolve business-approved non-applicability for SOW/other artefacts in the source contract before enabling gate exemptions; do not fake sign-off as true. Core tests verify the combined Coding + TUAT condition and prevent stage-only completion.

The Confluence inventory check compares its source rows to the pre-existing Dashboard register (plans AND labels), not just named allocations. A project can be present in the Dashboard and still be Pending planning. A source ID found only in a different domain requires domain review. No matching is attempted through credentials in browser JavaScript.

Matching is constrained to the owning domain. Unique CSCOP matches are accepted. Shared references require project name disambiguation. Missing IDs, name-only matches and conflicting IDs require review. No cross-domain handover record establishes plan coverage in the source domain. Pending planning does not mean Not Started. Person-level Actual MD is never allocated to projects.

## Future server-side source contract

`assets/confluence-onepage-data.json` is currently an explicit disconnected placeholder. A later authenticated backend job can replace this with a reviewed snapshot and rebuild the package. Never put API tokens, AK/SK, private API response dumps or credentials into public assets. This release does not fetch private Confluence pages or publish their contents.

Schema version 1:

```json
{
  "schemaVersion": 1,
  "domains": [
    {"name":"Corporate","status":"ready","complete":true,"asOf":"2026-11-05T10:00:00+08:00","sourceUrl":"https://lululemon.atlassian.net/wiki/spaces/CNT/pages/6107498041"}
  ],
  "projects": [
    {"key":"stable-source-row-key","domain":"Corporate","id":"CSCOP-1234","name":"Example only - not production data","status":"Ongoing","stage":"Feasibility","sourceUrl":"https://lululemon.atlassian.net/wiki/spaces/CNT/pages/6107498041"}
  ]
}
```

Allowed domains: Corporate, MP&A, Fulfillment, Upstream SCM & MDM, SCM Ops. The Omni/Fulfillment source must cover the agreed scope; OF is not silently treated as an extra fifth domain. Confirm whether the separate OF One Page must be included in the Fulfillment domain before connecting. No automatic deletion is inferred from a project absent in a source. Source stage is not proof of approval. Gateway documents/sign-offs need an explicit future field contract.

Only `ready` + `complete:true` + timestamp makes a domain complete for absence checks. Stale/partial/failed domains remain visibly unchecked. A newly seen source project without an exact plan match is shown as Pending planning; a source identity conflict is Needs review. Missing effort is never zero. Re-run reconciliation against the same snapshot must not append duplicates or change resource totals.

Export project register follows active filters; existing Export by CSCOP retains the current planning register until the later Confluence ingestion/export contract is confirmed.

Tests: `node deployment/q4/test-portfolio-overview.cjs`.