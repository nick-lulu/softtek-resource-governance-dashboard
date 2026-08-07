# Softtek Resource Governance Dashboard

React dashboard for validating Softtek planned effort, actual timesheets and Q3 forecast readiness.

## Dashboard scope

- Q1: February through April 2026
- Q2: May through July 2026
- Q3: August through October 2026
- Q4: November 2026 through January 2027
- Cohort: 13 Softtek people after excluding Echo Fang and Ayla Hou from the reporting scope
- Exclusion: Yola Liang also remains excluded because the person has one zero-hour planning record
- Dedicated QA: Daisy Tang, Mengyi Zhou, Harry Shi and Jade Zhang
- Operation Resources: Operation team excluding Nick Han, Ryan Xu and Jacky Zhong
- Governance split: formal projects with a `CSCOP-` project ID vs Non-CSCOP effort
- Conversion: 1 MD = 8 hours
- Capacity benchmark: 13 people x 20 working days x 3 months = 780 gross MD per quarter

The planning workbook contains task-level `planHours`. Cross-quarter tasks are prorated by business-day overlap. Five confirmed manual project forecasts replace, rather than duplicate, source plan for the same projects. The 111.09 MD FY26 Incident, Problem and Change baseline is classified as Non-CSCOP and allocated equally across Q1-Q4 to the five named operating roles.

## Run locally

```bash
npm install
npm run dev
```

Open `http://localhost:8081/softtek-resource-governance-dashboard/`.

## Refresh workbook data

Windows:

```powershell
python scripts/compute_softtek_resource_analysis.py --source-dir "D:/pm/resource/8-7"
```

macOS:

```bash
python3 scripts/compute_softtek_resource_analysis.py --source-dir "/path/to/resource/8-7"
```

## Build

```bash
npm run build
```

GitHub Actions deploys the `dist` output to GitHub Pages after every push to `main`.
