# Portfolio Jira sync

The FC backend exposes `GET /api/v1/portfolio/jira`. The page first renders its
published snapshot, then checks this same-origin endpoint every 60 seconds while
visible. A backend worker reads the fixed Jira filter with complete pagination.
Requests return immediately from the last good cache; errors never replace it.
One Page matching uses the published Confluence snapshot, not a live Confluence pull.

Set the following **FC environment variables**, without committing their values:

- `ATLASSIAN_EMAIL`: authorized Jira API account
- `ATLASSIAN_API_TOKEN`: Jira read token for that account

The upstream hostname and JQL are fixed in `portfolio_jira.py`. The cutoff remains
2026-10-22, so later-created issues are outside this filter. Assignee-domain rules
and explicit exclusions (CSCOP-1067) come from `jira-master-data.json`.
Only issue key, Summary, assignee name, status, issue type and creation/update dates
are returned. Tokens, emails, descriptions and comments are not included.

The cache is per FC process; cold starts use the bundled snapshot until refreshed.
GitHub Pages remains a static snapshot because it has no Python backend.
