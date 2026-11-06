# Live Timesheet integration — FY26 Q4

The Python service uses the Softtek API v1 contract confirmed on 6 November 2026.
Keep the existing Alibaba FC function, `python3 app.py`, and port 9000.

## Authoritative calculations

- Work dates: 2026-11-01 through 2027-01-31, inclusive (FY26 Q4).
- Actual MD = totalHours / 8. For example, 32 hours = 4 MD.
- Unspent MD = the person's total Q4 Planned MD across domains minus Actual MD.
- Keep negative balances and calculation precision. Round only for display.
- Each successful response replaces prior cumulative totals, including corrections.
- Each person is matched once by a verified email mapping, even across domains.
- Unmapped people stay pending. Never guess emails or assign missing people zero.
- The vendor API includes valid, non-deleted filled entries by work_date
  (`status=1`, `deleted=0`), across all projects. It is not an approval-only feed.
- The API cannot attribute Actual MD to domain, role or CSCOP. Do not infer this.
- A returned zero may mean no hours or an unmatched vendor email; verify identities.

## Server-only configuration

Use `timesheet.env.example` as the schema. Configure these privately in FC:
`TIMESHEET_PROVIDER=softtek`, `TIMESHEET_API_URL`, `TIMESHEET_AK`, `TIMESHEET_SK`,
`TIMESHEET_TIMEOUT_SECONDS=8`, and `TIMESHEET_RESOURCE_MAP`.

Mapping shape: `{"verified-timesheet-email@example.com":"nick_han"}`.
The verified Nick email is supplied separately by the owner, not shipped publicly.
Only add other people once their Timesheet email is confirmed. Never add secrets
or private maps to GitHub, public assets, deployment ZIPs, or browser requests.

Authentication uses POST `/open-api/v1/token` with `{ak,sk}`. Token is cached in
server memory using expires_in with a 60-second renewal margin. Queries use POST
`/open-api/v1/hours/summary` with Bearer authentication and `{emails,startDate,endDate}`.
Dates are yyyy-MM-dd, inclusive. Batches are at most 100 emails. HTTP 200 alone
is insufficient: JSON code must be 200. Business 401 renews the token and retries
once. Redirects are refused, and source errors never expose response bodies.

## Page entry and refresh

Planning renders first using the existing embedded snapshot. The Actual request
runs asynchronously after the first paint; it never gates planning rendering.
Every GET `/api/v1/timesheet/actuals` queries the source afresh; concurrent requests
waiting for one refresh share its result. Resource List refreshes every 60 seconds
while visible, when returning to the tab, and on Refresh sources. This is live
on request, not a webhook or a guarantee that a Timesheet entry appears instantly.

Failures retain the last successful values with a stale label and timestamp;
retry backs off 30 seconds. A failed cold start remains unavailable. An FC restart
clears in-memory values. No fake zero or hardcoded Actual enters the page.

GET `/api/v1/timesheet/status` returns status without querying upstream.
Both endpoints use no-store. Responses include only existing resource keys/names,
hours, MD, period and sync metadata, never emails, keys or tokens. GitHub Pages
has no Python service and does not fetch or embed real employee Actual values.

## Release checks

1. Run `python -m unittest discover -s deployment/fc/tests -v`.
2. Verify the browser client, missing records, repeated snapshots, token renewal,
   stale fallback, and 32 hours -> 4 MD. Check mobile layout when browser is available.
3. Commit reviewed code to GitHub, then build a matching FC package.
4. Back up the current function, upload that package, retain runtime/domain settings.
5. Set secret environment values in FC and deploy. Verify live Actual and Unspent.

The owner authorized connecting Nick first to the existing public dashboard.
Private API credentials remain on the server. Future access restrictions must be
implemented on the server; a frontend-only login would not protect API responses.
