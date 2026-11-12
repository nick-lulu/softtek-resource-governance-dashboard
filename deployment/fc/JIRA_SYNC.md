# Portfolio Jira sync

The FC backend exposes `GET /api/v1/portfolio/jira`. The page first renders its
published snapshot, then checks this same-origin endpoint every 60 seconds while
visible. A backend worker reads the fixed Jira filter with complete pagination.
The page renders the published cache immediately. Its independent API request
waits for an in-flight refresh (up to 50 seconds), keeping FC active until the
upstream read finishes. Fresh backend cache hits return immediately; errors never replace it.
One Page matching uses the published Confluence snapshot, not a live Confluence pull.

Set the following **FC environment variables**, without committing their values:

- `ATLASSIAN_EMAIL`: authorized Jira API account
- `ATLASSIAN_API_TOKEN`: Jira read token for that account

The upstream hostname and JQL are fixed in `portfolio_jira.py`. Only calendar-year
2026 issues are included: created >= 2026-01-01 AND created < 2027-01-01,
excluding Cancelled, Closed and Done. Assignee-domain rules
and explicit exclusions (CSCOP-1067) come from `jira-master-data.json`.
Only issue key, Summary, assignee name, status, issue type and creation/update dates
are returned. Tokens, emails, descriptions and comments are not included.

The cache is per FC process; cold starts use the bundled snapshot until refreshed.
GitHub Pages remains a static snapshot because it has no Python backend.
