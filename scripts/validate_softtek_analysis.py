"""Validate the generated Softtek dashboard dataset and key reconciliations."""

import json
from pathlib import Path


EXPECTED_ROSTER = {
    "Ayla Hou", "Daisy Tang", "Echo Fang", "Harry Shi", "Jacky Zhong",
    "Jade Zhang", "Jenny Qian", "Jiarui Yang", "Leah Li", "Liv Cao",
    "Lucy Cao", "Mengyi Zhou", "Nick Han", "Ruby Yang", "Ryan Xu",
}
EXPECTED_QA = {"Daisy Tang", "Mengyi Zhou", "Harry Shi", "Jade Zhang"}
EXPECTED_OPERATION = {"Echo Fang", "Jenny Qian", "Jiarui Yang", "Liv Cao", "Lucy Cao", "Ruby Yang"}
EXPECTED_ANNUAL_OPERATION_RESOURCES = {"Ryan Xu", "Jiarui Yang", "Jacky Zhong", "Ruby Yang", "Lucy Cao"}


def close(left: float, right: float, tolerance: float = 0.03) -> bool:
    return abs(left - right) <= tolerance


if __name__ == "__main__":
    data = json.loads(Path("src/data/softtek_analysis.json").read_text(encoding="utf-8"))
    assert data["resource_count"] == 15
    assert set(data["roster"]) == EXPECTED_ROSTER
    assert "Yola Liang" not in data["roster"]
    assert set(data["dedicated_qa_names"]) == EXPECTED_QA
    assert set(data["operation_resource_names"]) == EXPECTED_OPERATION
    assert len(data["resources"]) == 15

    for quarter in ("q1", "q2", "q3", "q4"):
        for measure in ("actual", "planned"):
            key = f"{quarter}_{measure}"
            assert close(data["totals"][key], data["cscop_totals"][key] + data["non_cscop_totals"][key])

    assert close(sum(row["q3_planned"] for row in data["resources"]), data["q3_forecast"]["named_resource_plan_with_annual_operations"])
    for quarter in ("Q1", "Q2", "Q3", "Q4"):
        assert close(
            sum(row["planned"] for row in data["projects"] if row["quarter"] == quarter),
            data["totals"][f"{quarter.lower()}_planned"],
            tolerance=0.08,
        )

    manual_q2 = {row["project"]: row for row in data["projects"] if row["quarter"] == "Q2" and row.get("manual_type") == "confirmed_project"}
    manual_q3 = {row["project"]: row for row in data["projects"] if row["quarter"] == "Q3" and row.get("manual_type") == "confirmed_project"}
    assert len(manual_q2) == 5 and len(manual_q3) == 5
    for project in data["manual_projects"]:
        assert close(manual_q2[project["project"]]["actual"], project["q2_actual"])
        assert close(manual_q3[project["project"]]["planned"], project["q3_planned"])

    annual_operations = data["annual_operations"]
    assert close(annual_operations["annual_total_md"], 111.09)
    assert close(sum(annual_operations["quarter_totals"].values()), 111.09)
    assert {row["name"] for row in annual_operations["resources"]} == EXPECTED_ANNUAL_OPERATION_RESOURCES
    assert close(sum(row["annual_md"] for row in annual_operations["resources"]), 111.09)
    assert {row["work_type"] for row in annual_operations["categories"]} == {"Incident", "Problem", "Change"}
    for quarter in ("Q1", "Q2", "Q3", "Q4"):
        assert close(sum(row["quarter_md"][quarter] for row in annual_operations["categories"]), annual_operations["quarter_totals"][quarter])
        assert close(sum(row["quarter_md"][quarter] for row in annual_operations["resources"]), annual_operations["quarter_totals"][quarter])
    for row in annual_operations["resources"]:
        resource = next(item for item in data["resources"] if item["name"] == row["name"])
        assert close(resource["annual_ops_fy26_planned"], row["annual_md"])

    print("Softtek analysis validation passed")
