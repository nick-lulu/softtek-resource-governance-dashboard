"""Build the Softtek resource governance dataset from planning and timesheet workbooks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


QUARTERS = {
    "Q1": (pd.Timestamp("2026-02-01"), pd.Timestamp("2026-04-30")),
    "Q2": (pd.Timestamp("2026-05-01"), pd.Timestamp("2026-07-31")),
    "Q3": (pd.Timestamp("2026-08-01"), pd.Timestamp("2026-10-31")),
    "Q4": (pd.Timestamp("2026-11-01"), pd.Timestamp("2027-01-31")),
}
DEDICATED_QA = ["Daisy Tang", "Mengyi Zhou", "Harry Shi", "Jade Zhang"]
OPERATION_EXCLUSIONS = {"Nick Han", "Ryan Xu", "Jacky Zhong"}
EXCLUDED_RESOURCES = {"Yola Liang"}
MANUAL_PROJECTS = [
    {"project": "Legacy to New Pipeline Migration", "project_id": "CSCOP-1037", "q2_actual": 5.91, "q3_planned": 16.00},
    {"project": "IP Protection - Baison Omni", "project_id": "CSCOP-990", "q2_actual": 2.91, "q3_planned": 35.50},
    {"project": "IP Protection - Samplehub-WMS", "project_id": "CSCOP-991", "q2_actual": 3.81, "q3_planned": 15.00},
    {"project": "Helios embedded XXL JOB update", "project_id": "CSCOP-953", "q2_actual": 5.75, "q3_planned": 8.88},
    {"project": "cve-2026-4-973 fix", "project_id": "CSCOP pending", "q2_actual": 0.00, "q3_planned": 7.50},
]
ANNUAL_OPERATION_WORK = [
    {
        "work_type": "Incident",
        "annual_md": 71.50,
        "resource_md": {"Ryan Xu": 5.00, "Jiarui Yang": 12.00, "Jacky Zhong": 20.00, "Ruby Yang": 15.00, "Lucy Cao": 19.50},
        "quarter_md": {"Q1": 17.87, "Q2": 17.87, "Q3": 17.88, "Q4": 17.88},
    },
    {
        "work_type": "Problem",
        "annual_md": 9.00,
        "resource_md": {"Ryan Xu": 1.00, "Jiarui Yang": 1.00, "Jacky Zhong": 1.00, "Ruby Yang": 2.00, "Lucy Cao": 4.00},
        "quarter_md": {"Q1": 2.25, "Q2": 2.25, "Q3": 2.25, "Q4": 2.25},
    },
    {
        "work_type": "Change",
        "annual_md": 30.59,
        "resource_md": {"Ryan Xu": 1.00, "Jiarui Yang": 8.00, "Jacky Zhong": 0.00, "Ruby Yang": 6.00, "Lucy Cao": 15.59},
        "quarter_md": {"Q1": 7.65, "Q2": 7.65, "Q3": 7.64, "Q4": 7.65},
    },
]
OPERATION_ROLES = {
    "Ryan Xu": "Ops Lead",
    "Jiarui Yang": "Ops TL",
    "Jacky Zhong": "Ops BA",
    "Ruby Yang": "L1.5 Lead",
    "Lucy Cao": "L1.5 Engineer",
}
ANNUAL_OPERATION_RESOURCE_QUARTERS = {
    "Ryan Xu": {"Q1": 1.75, "Q2": 1.75, "Q3": 1.75, "Q4": 1.75},
    "Jiarui Yang": {"Q1": 5.25, "Q2": 5.25, "Q3": 5.25, "Q4": 5.25},
    "Jacky Zhong": {"Q1": 5.25, "Q2": 5.25, "Q3": 5.25, "Q4": 5.25},
    "Ruby Yang": {"Q1": 5.75, "Q2": 5.75, "Q3": 5.75, "Q4": 5.75},
    "Lucy Cao": {"Q1": 9.77, "Q2": 9.77, "Q3": 9.77, "Q4": 9.78},
}


def normalize(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip()


def md(hours: float) -> float:
    return round(float(hours) / 8, 2)


def actual_hours(dates: pd.Series, hours: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> float:
    return float(hours[dates.between(start, end)].sum())


def business_days(start: pd.Timestamp, end: pd.Timestamp) -> int:
    if pd.isna(start) or pd.isna(end) or end < start:
        return 0
    return int(np.busday_count(start.date(), (end + pd.Timedelta(days=1)).date()))


def allocated_plan_hours(frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> float:
    total = 0.0
    for row in frame.itertuples(index=False):
        overlap_start = max(row.start, start) if not pd.isna(row.start) else pd.NaT
        overlap_end = min(row.end, end) if not pd.isna(row.end) else pd.NaT
        overlap_days = business_days(overlap_start, overlap_end)
        if overlap_days == 0:
            continue
        total_days = business_days(row.start, row.end)
        if total_days:
            total += row.hours * overlap_days / total_days
    return total


def resource_status(row: dict) -> str:
    historical_gap = max(abs(row["q1_actual"] - row["q1_planned"]), abs(row["q2_actual"] - row["q2_planned"]))
    if row["q3_planned"] == 0 and row["q1_actual"] + row["q2_actual"] >= 10:
        return "High"
    if historical_gap >= 10:
        return "High"
    if historical_gap >= 3 or row["q3_planned"] == 0:
        return "Medium"
    return "Low"


def current_read(row: dict) -> str:
    historical = row["q1_actual"] + row["q2_actual"]
    if row["q3_planned"] == 0 and historical >= 10:
        return "Historical effort exists; no named Q3 allocation"
    if row["q3_planned"] < row["q2_actual"] * 0.5 and row["q2_actual"] >= 3:
        return "Q3 named allocation is light vs Q2 actual"
    if row["q3_planned"] == 0:
        return "No Q3 demand currently assigned"
    return "Named Q3 allocation exists"


def summarize_resources(resources: list[dict], names: set[str]) -> dict:
    keys = [
        "q1_actual", "q1_planned", "q2_actual", "q2_planned", "q3_actual", "q3_planned",
        "q1_cscop_actual", "q1_cscop_planned", "q2_cscop_actual", "q2_cscop_planned", "q3_cscop_actual", "q3_cscop_planned",
        "q1_non_cscop_actual", "q1_non_cscop_planned", "q2_non_cscop_actual", "q2_non_cscop_planned", "q3_non_cscop_actual", "q3_non_cscop_planned",
    ]
    return {key: round(sum(row[key] for row in resources if row["name"] in names), 2) for key in keys}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", default=r"D:/pm/resource/8-7")
    parser.add_argument("--output", default="src/data/softtek_analysis.json")
    args = parser.parse_args()

    source = Path(args.source_dir)
    actual_path = source / "Ops team填报工时(1.1-7.31).xlsx"
    plan_path = source / "计划工时数据2026-08-06.xlsx"
    actual = pd.read_excel(actual_path)
    plan = pd.read_excel(plan_path)

    actual = actual[normalize(actual["公司"]).str.casefold().eq("softtek")].copy()
    roster = sorted(set(normalize(actual["姓名"]).unique()) - EXCLUDED_RESOURCES)
    actual = actual[normalize(actual["姓名"]).isin(roster)].copy()
    plan = plan[
        normalize(plan["companyName"]).str.casefold().eq("softtek")
        & normalize(plan["nickName"]).isin(roster)
    ].copy()

    actual_frame = pd.DataFrame({
        "name": normalize(actual["姓名"]),
        "space": normalize(actual["所属Space"]),
        "date": pd.to_datetime(actual["填写日期"], errors="coerce"),
        "hours": pd.to_numeric(actual["填报工时"], errors="coerce").fillna(0),
        "project_id": normalize(actual["项目编号"]),
        "project": normalize(actual["项目名称"]).replace("", "Unassigned"),
    })
    actual_frame["cscop"] = actual_frame["project_id"].str.upper().str.startswith("CSCOP-")

    plan_frame = pd.DataFrame({
        "name": normalize(plan["nickName"]),
        "space": normalize(plan["spaceNames"]),
        "start": pd.to_datetime(plan["taskStartTime"], errors="coerce"),
        "end": pd.to_datetime(plan["taskEndTime"], errors="coerce"),
        "hours": pd.to_numeric(plan["planHours"], errors="coerce").fillna(0),
        "project_id": normalize(plan["projectNo"]),
        "project": normalize(plan["projectName"]).replace("", "Unassigned"),
    })
    plan_frame["cscop"] = plan_frame["project_id"].str.upper().str.startswith("CSCOP-")

    spaces = actual_frame.groupby("name")["space"].agg(lambda values: values.mode().iloc[0] if not values.mode().empty else "")
    operation_names = sorted(
        name for name in roster if spaces.get(name, "").casefold() == "operation" and name not in OPERATION_EXCLUSIONS
    )

    resources = []
    for name in roster:
        row = {
            "name": name,
            "space": spaces.get(name, ""),
            "group": "Dedicated QA" if name in DEDICATED_QA else "Operation Resource" if name in operation_names else "Other Softtek",
        }
        for quarter, (start, end) in QUARTERS.items():
            q = quarter.lower()
            person_actual = actual_frame[actual_frame["name"].eq(name)]
            person_plan = plan_frame[plan_frame["name"].eq(name)]
            row[f"{q}_actual"] = md(actual_hours(person_actual["date"], person_actual["hours"], start, end))
            row[f"{q}_planned"] = md(allocated_plan_hours(person_plan, start, end))
            for scope, scope_value in (("cscop", True), ("non_cscop", False)):
                scoped_actual = person_actual[person_actual["cscop"].eq(scope_value)]
                scoped_plan = person_plan[person_plan["cscop"].eq(scope_value)]
                row[f"{q}_{scope}_actual"] = md(actual_hours(scoped_actual["date"], scoped_actual["hours"], start, end))
                row[f"{q}_{scope}_planned"] = md(allocated_plan_hours(scoped_plan, start, end))
        resources.append(row)

    source_named_q3 = round(sum(row["q3_planned"] for row in resources), 2)

    totals = {}
    cscop_totals = {}
    non_cscop_totals = {}
    for quarter, (start, end) in QUARTERS.items():
        q = quarter.lower()
        totals[f"{q}_actual"] = md(actual_hours(actual_frame["date"], actual_frame["hours"], start, end))
        totals[f"{q}_planned"] = md(allocated_plan_hours(plan_frame, start, end))
        for scope_name, scope_value, target in (
            ("cscop", True, cscop_totals),
            ("non_cscop", False, non_cscop_totals),
        ):
            actual_scope = actual_frame[actual_frame["cscop"].eq(scope_value)]
            plan_scope = plan_frame[plan_frame["cscop"].eq(scope_value)]
            target[f"{q}_actual"] = md(actual_hours(actual_scope["date"], actual_scope["hours"], start, end))
            target[f"{q}_planned"] = md(allocated_plan_hours(plan_scope, start, end))

    annual_operation_total = round(sum(item["annual_md"] for item in ANNUAL_OPERATION_WORK), 2)
    annual_resource_totals = {
        name: round(sum(item["resource_md"].get(name, 0) for item in ANNUAL_OPERATION_WORK), 2)
        for name in OPERATION_ROLES
    }
    quarter_operation_totals = {
        quarter: round(sum(item["quarter_md"][quarter] for item in ANNUAL_OPERATION_WORK), 2)
        for quarter in QUARTERS
    }
    resource_by_name = {row["name"]: row for row in resources}
    for quarter in QUARTERS:
        q = quarter.lower()
        totals[f"{q}_planned"] = round(totals[f"{q}_planned"] + quarter_operation_totals[quarter], 2)
        non_cscop_totals[f"{q}_planned"] = round(non_cscop_totals[f"{q}_planned"] + quarter_operation_totals[quarter], 2)
        for name in annual_resource_totals:
            allocation = ANNUAL_OPERATION_RESOURCE_QUARTERS[name][quarter]
            row = resource_by_name[name]
            row[f"annual_ops_{q}_planned"] = round(allocation, 4)
            row[f"{q}_planned"] = round(row[f"{q}_planned"] + allocation, 2)
            row[f"{q}_non_cscop_planned"] = round(row[f"{q}_non_cscop_planned"] + allocation, 2)

    for row in resources:
        row["annual_ops_fy26_planned"] = annual_resource_totals.get(row["name"], 0)
        for quarter in QUARTERS:
            row.setdefault(f"annual_ops_{quarter.lower()}_planned", 0)
        row["status"] = resource_status(row)
        row["current_read"] = current_read(row)

    project_rows = []
    for quarter, (start, end) in QUARTERS.items():
        q_actual = actual_frame[actual_frame["date"].between(start, end)]
        actual_projects = q_actual.groupby(["project_id", "project", "cscop"], as_index=False)["hours"].sum()
        project_keys = plan_frame[["project_id", "project", "cscop"]].drop_duplicates()
        plan_projects = []
        for item in project_keys.itertuples(index=False):
            match = plan_frame[
                plan_frame["project_id"].eq(item.project_id)
                & plan_frame["project"].eq(item.project)
                & plan_frame["cscop"].eq(item.cscop)
            ]
            plan_projects.append({
                "project_id": item.project_id,
                "project": item.project,
                "cscop": bool(item.cscop),
                "hours": allocated_plan_hours(match, start, end),
            })
        planned_projects = pd.DataFrame(plan_projects)
        merged = planned_projects.merge(actual_projects, on=["project_id", "project", "cscop"], how="outer", suffixes=("_planned", "_actual")).fillna(0)
        for item in merged.itertuples(index=False):
            project_rows.append({
                "quarter": quarter,
                "project_id": item.project_id or "No CSCOP",
                "project": item.project,
                "cscop": bool(item.cscop),
                "actual": md(item.hours_actual),
                "planned": md(item.hours_planned),
                "confirmed_manual": False,
                "manual_type": None,
            })

    for item in ANNUAL_OPERATION_WORK:
        for quarter in QUARTERS:
            project_rows.append({
                "quarter": quarter,
                "project_id": "Annual operating baseline",
                "project": item["work_type"],
                "cscop": False,
                "actual": 0.0,
                "planned": item["quarter_md"][quarter],
                "confirmed_manual": True,
                "manual_type": "annual_operation",
            })

    manual_deltas = []
    for manual in MANUAL_PROJECTS:
        normalized_name = manual["project"].casefold()
        for quarter, field, confirmed_value in (("Q2", "actual", manual["q2_actual"]), ("Q3", "planned", manual["q3_planned"])):
            matches = [row for row in project_rows if row["quarter"] == quarter and row["project"].casefold() == normalized_name]
            source_value = round(sum(row[field] for row in matches), 2)
            source_actual = round(sum(row["actual"] for row in matches), 2)
            source_planned = round(sum(row["planned"] for row in matches), 2)
            project_rows = [row for row in project_rows if not (row["quarter"] == quarter and row["project"].casefold() == normalized_name)]
            project_rows.append({
                "quarter": quarter,
                "project_id": manual["project_id"],
                "project": manual["project"],
                "cscop": manual["project_id"].startswith("CSCOP-"),
                "actual": confirmed_value if field == "actual" else source_actual,
                "planned": confirmed_value if field == "planned" else source_planned,
                "confirmed_manual": True,
                "manual_type": "confirmed_project",
            })
            manual_deltas.append({
                "quarter": quarter,
                "field": field,
                "project": manual["project"],
                "source_value": source_value,
                "confirmed_value": confirmed_value,
                "delta": round(confirmed_value - source_value, 2),
            })

    q3_plan_delta = round(sum(item["delta"] for item in manual_deltas if item["quarter"] == "Q3"), 2)
    totals["q3_planned"] = round(totals["q3_planned"] + q3_plan_delta, 2)
    cscop_delta = round(sum(
        item["delta"] for item in manual_deltas
        if item["quarter"] == "Q3" and next(project for project in MANUAL_PROJECTS if project["project"] == item["project"])["project_id"].startswith("CSCOP-")
    ), 2)
    cscop_totals["q3_planned"] = round(cscop_totals["q3_planned"] + cscop_delta, 2)
    non_cscop_totals["q3_planned"] = round(totals["q3_planned"] - cscop_totals["q3_planned"], 2)

    named_q3_with_annual_operations = round(sum(row["q3_planned"] for row in resources), 2)
    confirmed_manual_q3 = round(sum(item["q3_planned"] for item in MANUAL_PROJECTS), 2)
    manual_source_q3 = round(sum(item["source_value"] for item in manual_deltas if item["quarter"] == "Q3"), 2)

    monthly = []
    monthly_operation_md = annual_operation_total / 12
    for month in pd.period_range("2026-02", "2027-01", freq="M"):
        start = month.start_time
        end = month.end_time
        monthly.append({
            "month": month.strftime("%b"),
            "actual": md(actual_hours(actual_frame["date"], actual_frame["hours"], start, end)),
            "planned": round(md(allocated_plan_hours(plan_frame, start, end)) + monthly_operation_md, 2),
        })

    annual_operation_resources = [
        {
            "name": name,
            "role": OPERATION_ROLES[name],
            "annual_md": annual_md,
            "quarter_md": ANNUAL_OPERATION_RESOURCE_QUARTERS[name],
        }
        for name, annual_md in annual_resource_totals.items()
    ]
    annual_operation_categories = [
        {
            **item,
        }
        for item in ANNUAL_OPERATION_WORK
    ]

    output = {
        "as_of": actual_frame["date"].max().strftime("%Y-%m-%d"),
        "source": {"plan": plan_path.name, "actual": actual_path.name},
        "resource_count": len(roster),
        "roster": roster,
        "excluded_resources": sorted(EXCLUDED_RESOURCES),
        "dedicated_qa_names": DEDICATED_QA,
        "operation_resource_names": operation_names,
        "totals": totals,
        "cscop_totals": cscop_totals,
        "non_cscop_totals": non_cscop_totals,
        "dedicated_qa_totals": summarize_resources(resources, set(DEDICATED_QA)),
        "operation_resource_totals": summarize_resources(resources, set(operation_names)),
        "resources": resources,
        "projects": sorted(project_rows, key=lambda row: (row["quarter"], -(row["actual"] + row["planned"]))),
        "manual_projects": MANUAL_PROJECTS,
        "manual_reconciliation": manual_deltas,
        "annual_operations": {
            "annual_total_md": annual_operation_total,
            "quarter_totals": quarter_operation_totals,
            "allocation_method": "FY26 annual demand allocated evenly across Q1-Q4, with 0.01 MD rounding balanced across quarters",
            "classification": "Non-CSCOP",
            "categories": annual_operation_categories,
            "resources": annual_operation_resources,
        },
        "q3_forecast": {
            "source_named_resource_plan": source_named_q3,
            "annual_operations_named_plan": quarter_operation_totals["Q3"],
            "named_resource_plan_with_annual_operations": named_q3_with_annual_operations,
            "manual_projects_confirmed": confirmed_manual_q3,
            "manual_projects_source_plan": manual_source_q3,
            "confirmed_portfolio_plan": totals["q3_planned"],
        },
        "monthly": monthly,
        "methodology": {
            "md_hours": 8,
            "quarterly_capacity_md": len(roster) * 20 * 3,
            "plan_allocation": "Task planHours prorated across business days in each quarter",
            "annual_operation_allocation": "FY26 Incident, Problem and Change demand allocated equally across four fiscal quarters and assigned to named roles",
            "manual_actual_treatment": "Project trace only; not added again to portfolio actual",
            "manual_forecast_treatment": "Confirmed project total replaces source plan for the same project",
        },
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {output_path} with {len(roster)} Softtek resources")


if __name__ == "__main__":
    main()
