# Softtek Resource Governance Dashboard

## Purpose

This is an independent Vite/React dashboard for Softtek resource planning. Do not modify the EY or parent Lululemon dashboards when changing this project.

## Data rules

- Q1 is February through April 2026; Q2 is May through July; Q3 is August through October; Q4 is November 2026 through January 2027.
- One MD equals eight hours.
- Define the cohort from the Actual workbook's 15 Softtek people.
- Exclude Yola Liang from all counts and effort because the person has only one zero-hour planning record.
- Match planning rows to the fixed 15-person cohort; do not include unrelated Softtek teams.
- Prorate task-level `planHours` by business-day overlap when tasks cross quarter boundaries.
- Treat project IDs beginning with `CSCOP-` as formal project effort.
- Keep Operation and blank IDs in Non-CSCOP.
- Keep Daisy Tang, Mengyi Zhou, Harry Shi and Jade Zhang in the Dedicated QA module.
- Define Operation Resources from the Operation space, excluding Nick Han, Ryan Xu and Jacky Zhong.
- Manual Q2 project traces are project-level confirmed values and must not be added again to portfolio Actual.
- Manual Q3 project forecasts replace source plan for the same project and must not be double-counted.
- Keep manual project demand unassigned at person level until an explicit resource allocation is provided.
- Treat the FY26 Incident, Problem and Change baseline as Non-CSCOP. Allocate the annual MD equally across all four quarters and assign it to Ryan Xu (Ops Lead), Jiarui Yang (Ops TL), Jacky Zhong (Ops BA), Ruby Yang (L1.5 Lead) and Lucy Cao (L1.5 Engineer).

## Commands

```powershell
python scripts/compute_softtek_resource_analysis.py --source-dir "D:/pm/resource/8-7"
npm install
npm run dev
npm run build
```

## Change discipline

- Keep the dashboard focused on actual vs planned, forecast readiness and actionable governance gaps.
- Do not invent resource allocations or CSCOP IDs.
- Preserve the clean visual language and responsive behavior.
- Rebuild and visually verify desktop and mobile layouts after frontend changes.
