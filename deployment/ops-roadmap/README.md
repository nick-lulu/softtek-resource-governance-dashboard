# SCM Ops delivery & operations

Independent dashboard: `public/ops-roadmap/`. Intended custom domain: `ops.lcorp.msofttek.com`.
This package does not replace the Q4 Resource Planning / Timesheet service.

## Source and interpretation

Snapshot: Tech SCM Ops FY26, Confluence page 6178078750, version 400, captured 2026-11-11.
27 named delivery cases: 24 PDCA and 3 CR. Wuhan has 13 named rows and one explicitly pending row,
excluded from confirmed status counts. Transferred is separate from Complete.
Operation Highlight defaults to 3 active cases; 57 historical cases are opt-in.
Month/quarter targets are estimates, not development durations or committed deployment dates.
Yearless month/day values use the FY26 source context (2026). FY26 Q4 is Nov-Jan;
FY27 Q1 is Feb-Apr 2027. No API credentials or raw Confluence export are included.
This is a read-only snapshot, not a live Confluence integration.

## Local preview

`python -m http.server 8096 --directory public/ops-roadmap`

## Package

`python deployment/ops-roadmap/package.py --output Ops-Roadmap-FC.zip`

## Alibaba FC

Use a separate function with Python 3.10+ custom runtime, command `python3 app.py`, port 9000.
Upload the generated ZIP and map `ops.lcorp.msofttek.com/*` to that function.
Keep the existing `lcorp.msofttek.com` routes and Q4 function unchanged.
No third-party Python packages or environment secrets are needed.
Check `/healthz`, `/data.json`, both dashboard modules, filtering, details and mobile layout.
