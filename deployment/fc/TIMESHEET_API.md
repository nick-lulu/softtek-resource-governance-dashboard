# Timesheet integration — FY26 Q4 person totals

Python backend for the existing `lulu-test` FC Web function. No new ECS instance
or Python package installation is required. The existing `python3 app.py`
command and port 9000 are retained. Softtek supplies a read-only API; this backend
pulls from it. It does not receive or trust employee totals submitted by browsers.

## Calculation and scope

- FY26 Q4: **2026-11-01 through 2027-01-31**, inclusive, by work date.
- Source totals must cover precisely this whole period, not just a daily delta.
- Source hours are authoritative cumulative totals. Each successful snapshot
  **replaces** the previous one; repeated pulls never add totals together.
- Actual MD = totalHours / 8. Keep precision through calculation; round for display.
- Resource List Unspent MD = that person's total Q4 planned MD − Actual MD.
  Keep negative balances. Missing source records remain unavailable, not zero.
- Timesheet must confirm what “filled” means. Set `TIMESHEET_STATUS_BASIS` to
  `filled`, `submitted`, or `approved`; the adapter rejects a different source basis.
- Per-person actual includes all returned work for the person and period. This
  contract cannot attribute Actual to Domain, role or CSCOP. Those drill-downs
  require an extended Timesheet API. Off-plan work cannot be separated yet.
- Corporate/Shared/QA classifications affect planning; one person's total Actual
  must be counted only once across all Domain assignments.

## Contract to agree with Softtek

This is a **proposed adapter contract**, not a claim that Softtek already has these
field names. When their API document arrives, adapt `fetch_page` to normalize its
response into this contract. Credentials belong only in FC environment variables.

Request (server to server):

```http
GET <TIMESHEET_API_URL>?startDate=2026-11-01&endDate=2027-01-31&statusBasis=submitted&page=1&pageSize=500
Authorization: Bearer <server-side credential>
Accept: application/json
```

`TIMESHEET_AUTH_MODE=api-key` uses `X-API-Key` instead. `none` is only for an
explicitly agreed source authentication setup. OAuth client-credential token
exchange is not implemented until Softtek confirms its authentication protocol.
Use an HTTPS endpoint without query parameters or embedded credentials.

Response:

```json
{
  "period": {"startDate": "2026-11-01", "endDate": "2027-01-31"},
  "unit": "hours",
  "statusBasis": "submitted",
  "snapshotId": "stable-source-export-version",
  "complete": true,
  "resources": [
    {
      "employeeId": "stable-employee-id",
      "name": "name matching the planning roster",
      "totalHours": 0
    }
  ],
  "nextPage": null
}
```

`0` here illustrates an explicitly recorded zero, not an actual employee's effort.
`complete=true` confirms the query includes all matching work/statuses for the
requested period, not just a partial report. Every employee appears once. Paginated
results must use one stable `snapshotId` across all pages; `nextPage` is the next
integer or null. Any failed page rejects the entire refresh. Repeated employees,
ambiguous identity, negative/non-numeric hours, wrong period/basis/unit, or snapshot
changes reject the refresh. Adjustments/retractions reduce the next cumulative
total and are therefore reflected without needing individual entry IDs.

Prefer explicit stable employee-ID mappings in `TIMESHEET_RESOURCE_MAP`:
`{"employee-id-from-softtek":"nick_han"}`. Keys can also be lowercase email.
Existing exact Resource List keys/names and known aliases can be matched; there
is no fuzzy name matching. Unknown people are excluded and counted as unmatched.
Duplicate employees mapping to one resource reject the refresh.

## Dashboard endpoints

- `GET /api/v1/timesheet/status`: configuration/cache status; no upstream call.
- `GET /api/v1/timesheet/actuals`: whole-period normalized totals for roster members.

Both return `schemaVersion`, `status`, `period`, `hoursPerMD`, `statusBasis`,
`lastSuccessfulSyncAt`, and `resources`. Resource entries contain `resourceKey`,
`name`, `actualHours`, `actualMD`. Vendor employee IDs, emails, URLs and credentials
are not returned. Responses use `Cache-Control: no-store`, with no cross-origin
API access enabled.

States: `not_configured` / `status_basis_required` keep the UI pending. `ready`
means the most recent source query passed validation. A failure after success is
`stale`, carrying the last successful values and its time; it must never be shown
as a fresh sync. A failure before any success is `unavailable`. Errors are generic
codes; raw source responses/tokens are not exposed. Missing person totals stay blank.

## Refresh behavior and persistence

This initial integration is **read-through**, not a background scheduler: the first
Actuals request pulls a complete source snapshot; requests within 300 seconds reuse
the in-memory snapshot. Resource List polls while open. After expiry, its next
request refreshes the source. Failures back off 30 seconds. FC instances each have
their own cache; cold starts fetch again. This is near-real-time under active use,
not a guaranteed continuous or instantaneous sync.

Supabase is not configured yet. This version stores neither history nor durable
checkpoints. Add scheduled FC sync plus a transactional Supabase snapshot store
when database access is available; do not rely on a sleeping FC process as a timer.
Webhook ingestion is not needed for this cumulative-total contract.

## Deployment and activation

1. Run `python -m unittest discover -s deployment/fc/tests -v`.
2. Commit source and deployment configuration to GitHub first.
3. GitHub Actions builds the FC ZIP; only deploy a validated matching revision.
4. Upload it to the existing function, keeping `python3 app.py` / port 9000.
5. Leave Timesheet variables empty until Softtek's contract/auth and reporting
   basis are confirmed. No mock or demonstration Actual is used in production.
6. Set API variables privately in FC. Restart/redeploy after configuration changes.
7. Verify zero, missing people, revised totals, outages, and cross-Domain identity
   with the source team before declaring the integration connected.

The site is currently public by the owner's previous decision. Enabling real
employee Actual data requires confirming the intended audience. Supabase/Auth and
the backend must enforce access when login is added; a frontend login screen alone
does not protect this endpoint or copies embedded in public HTML/GitHub Pages.