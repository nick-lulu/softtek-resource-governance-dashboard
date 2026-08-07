import React, { useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { AlertTriangle, BarChart3, CheckCircle2, Download, Gauge, Target, Users } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import data from "./data/softtek_analysis.json";
import "./styles.css";

const formatMd = (value, digits = 1) =>
  Number(value || 0).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });

const signedMd = (value) => `${Number(value) >= 0 ? "+" : ""}${formatMd(value)} MD`;
const pct = (value) => `${(Number(value || 0) * 100).toFixed(0)}%`;

function projectRead(row, quarter) {
  if (row.manual_type === "annual_operation") return "FY26 baseline allocated evenly across quarters";
  if (row.confirmed_manual) return quarter === "Q3" ? "Confirmed Q3 forecast" : "Confirmed Q2 trace";
  if (quarter === "Q3") return "Source forecast baseline";
  if (row.planned === 0 && row.actual > 0) return "Actual recorded without plan";
  if (row.actual === 0 && row.planned > 0) return "Plan not reflected in Actual";
  if (row.planned === 0) return "No effort recorded";
  const varianceRate = (row.actual - row.planned) / row.planned;
  if (varianceRate > 0.2) return "Actual materially above plan";
  if (varianceRate < -0.2) return "Actual materially below plan";
  return "Plan broadly aligned";
}

function Kpi({ icon: Icon, label, value, note, tone = "" }) {
  return (
    <section className={`kpi ${tone}`}>
      <div className="kpi-heading"><p>{label}</p><Icon size={19} /></div>
      <strong>{value}</strong>
      <span>{note}</span>
    </section>
  );
}

function StatusBadge({ value }) {
  return <span className={`status ${value.toLowerCase()}`}>{value}</span>;
}

function downloadDetail() {
  const columns = [
    "Resource", "Group", "Space", "Status", "Q1 Actual", "Q1 Planned", "Q2 Actual", "Q2 Planned", "Q3 Named Forecast",
    "Q1 CSCOP Actual", "Q1 CSCOP Planned", "Q2 CSCOP Actual", "Q2 CSCOP Planned", "Q3 CSCOP Forecast",
    "Q1 Non-CSCOP Actual", "Q1 Non-CSCOP Planned", "Q2 Non-CSCOP Actual", "Q2 Non-CSCOP Planned", "Q3 Non-CSCOP Forecast",
    "FY26 Incident Problem Change", "Q1 Annual Ops", "Q2 Annual Ops", "Q3 Annual Ops", "Q4 Annual Ops", "Current Read",
  ];
  const rows = data.resources.map((row) => [
    row.name, row.group, row.space, row.status, row.q1_actual, row.q1_planned, row.q2_actual, row.q2_planned, row.q3_planned,
    row.q1_cscop_actual, row.q1_cscop_planned, row.q2_cscop_actual, row.q2_cscop_planned, row.q3_cscop_planned,
    row.q1_non_cscop_actual, row.q1_non_cscop_planned, row.q2_non_cscop_actual, row.q2_non_cscop_planned, row.q3_non_cscop_planned,
    row.annual_ops_fy26_planned, row.annual_ops_q1_planned, row.annual_ops_q2_planned, row.annual_ops_q3_planned, row.annual_ops_q4_planned, row.current_read,
  ]);
  const csv = [columns, ...rows]
    .map((row) => row.map((value) => `"${String(value).replaceAll('"', '""')}"`).join(","))
    .join("\n");
  const url = URL.createObjectURL(new Blob([`\ufeff${csv}`], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "Softtek_Resource_Governance_Detail.csv";
  link.click();
  URL.revokeObjectURL(url);
}

function GroupSection({ title, names, subtitle, description }) {
  const [scope, setScope] = useState("cscop");
  const rows = names.map((name) => data.resources.find((row) => row.name === name)).filter(Boolean);
  const value = (row, quarter, type) => row[`${quarter}_${scope}_${type}`] || 0;
  const total = (quarter, type) => rows.reduce((sum, row) => sum + value(row, quarter, type), 0);
  const scopeLabel = scope === "cscop" ? "CSCOP" : "Non-CSCOP";

  return (
    <section className="panel dedicated-panel">
      <div className="panel-title">
        <h2>{title}</h2>
        <div className="panel-controls">
          <span className="unit">{subtitle}</span>
          <div className="tabs scope-tabs" role="tablist" aria-label={`${title} scope`}>
            <button className={scope === "cscop" ? "active" : ""} type="button" onClick={() => setScope("cscop")}>CSCOP Projects</button>
            <button className={scope === "non_cscop" ? "active" : ""} type="button" onClick={() => setScope("non_cscop")}>Non-CSCOP</button>
          </div>
        </div>
      </div>
      <div className="dedicated-summary">
        <div><span>Q1 {scopeLabel} Actual / Planned</span><strong>{formatMd(total("q1", "actual"))} / {formatMd(total("q1", "planned"))} MD</strong></div>
        <div><span>Q2 {scopeLabel} Actual / Planned</span><strong>{formatMd(total("q2", "actual"))} / {formatMd(total("q2", "planned"))} MD</strong></div>
        <div><span>Q3 {scopeLabel} Named Forecast</span><strong>{formatMd(total("q3", "planned"))} MD</strong></div>
        <p>{description(scope, rows)}</p>
      </div>
      <div className="table-wrap compact-table">
        <table>
          <thead><tr><th>Status</th><th>Resource</th><th>Q1 Actual / Planned</th><th>Q2 Actual / Planned</th><th>Q3 Named Forecast</th><th>Current Read</th></tr></thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.name}>
                <td><StatusBadge value={row.status} /></td>
                <td><strong>{row.name}</strong><small>Softtek · {row.space}</small></td>
                <td>{formatMd(value(row, "q1", "actual"))} / {formatMd(value(row, "q1", "planned"))} MD</td>
                <td>{formatMd(value(row, "q2", "actual"))} / {formatMd(value(row, "q2", "planned"))} MD</td>
                <td>{formatMd(value(row, "q3", "planned"))} MD</td>
                <td>{scope === "cscop"
                  ? value(row, "q3", "planned") > 0 ? "Named CSCOP allocation exists" : "Historical CSCOP effort; no Q3 allocation"
                  : value(row, "q1", "actual") + value(row, "q2", "actual") > 5 ? "Material Non-CSCOP effort; validate classification" : "Limited Non-CSCOP effort"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function App() {
  const [projectQuarter, setProjectQuarter] = useState("Q3");
  const [projectScope, setProjectScope] = useState("cscop");
  const [resourceScope, setResourceScope] = useState("cscop");
  const [summaryScope, setSummaryScope] = useState("all");
  const { totals, cscop_totals: cscopTotals, non_cscop_totals: nonCscopTotals } = data;
  const capacity = data.methodology.quarterly_capacity_md;
  const q1Gap = totals.q1_actual - totals.q1_planned;
  const q2Gap = totals.q2_actual - totals.q2_planned;
  const q1Realization = totals.q1_actual / totals.q1_planned;
  const q2Realization = totals.q2_actual / totals.q2_planned;
  const q3Coverage = totals.q3_planned / capacity;
  const q3VsQ2Actual = totals.q3_planned / totals.q2_actual;
  const manualShare = data.q3_forecast.manual_projects_confirmed / totals.q3_planned;
  const manualTrace = data.manual_projects.reduce((sum, row) => sum + row.q2_actual, 0);
  const annualOperations = data.annual_operations;
  const confirmedCscopProjects = data.manual_projects
    .filter((row) => row.project_id.startsWith("CSCOP-"))
    .reduce((sum, row) => sum + row.q3_planned, 0);
  const confirmedNonCscopProjects = data.manual_projects
    .filter((row) => !row.project_id.startsWith("CSCOP-"))
    .reduce((sum, row) => sum + row.q3_planned, 0);
  const q3SourceBaseline = data.q3_forecast.source_named_resource_plan - data.q3_forecast.manual_projects_source_plan;
  const q3CscopSourceBaseline = cscopTotals.q3_planned - confirmedCscopProjects;
  const q3NonCscopSourceBaseline = nonCscopTotals.q3_planned - confirmedNonCscopProjects - annualOperations.quarter_totals.Q3;
  const unassignedConfirmedUplift = totals.q3_planned - data.q3_forecast.named_resource_plan_with_annual_operations;
  const summaryTotals = summaryScope === "all" ? totals : summaryScope === "cscop" ? cscopTotals : nonCscopTotals;
  const summaryLabel = summaryScope === "all" ? "Overall" : summaryScope === "cscop" ? "CSCOP" : "Non-CSCOP";
  const summaryQ1Gap = summaryTotals.q1_actual - summaryTotals.q1_planned;
  const summaryQ2Gap = summaryTotals.q2_actual - summaryTotals.q2_planned;
  const summaryQ3Note = summaryScope === "all"
    ? `${formatMd(q3SourceBaseline)} MD source baseline + ${formatMd(data.q3_forecast.manual_projects_confirmed)} MD confirmed projects + ${formatMd(annualOperations.quarter_totals.Q3)} MD annual operations`
    : summaryScope === "cscop"
      ? `${formatMd(q3CscopSourceBaseline)} MD source baseline + ${formatMd(confirmedCscopProjects)} MD confirmed projects`
      : `${formatMd(q3NonCscopSourceBaseline)} MD source BAU + ${formatMd(confirmedNonCscopProjects)} MD CVE (CSCOP pending) + ${formatMd(annualOperations.quarter_totals.Q3)} MD annual operations`;
  const q1CscopCoverage = cscopTotals.q1_actual / totals.q1_actual;
  const q2CscopCoverage = cscopTotals.q2_actual / totals.q2_actual;
  const q3CscopCoverage = cscopTotals.q3_planned / totals.q3_planned;

  const chartData = [
    { quarter: "Q1", actual: totals.q1_actual, planned: totals.q1_planned },
    { quarter: "Q2", actual: totals.q2_actual, planned: totals.q2_planned },
    { quarter: "Q3", actual: 0, planned: totals.q3_planned },
  ];
  const detailRows = useMemo(
    () => [...data.resources].sort((a, b) => (b.q1_actual + b.q2_actual) - (a.q1_actual + a.q2_actual)),
    [],
  );
  const projectRows = useMemo(
    () => data.projects
      .filter((row) => row.quarter === projectQuarter && row.cscop === (projectScope === "cscop"))
      .slice(0, 12),
    [projectQuarter, projectScope],
  );
  const scopedResourceValue = (row, quarter, type) => row[`${quarter}_${resourceScope}_${type}`] || 0;

  return (
    <main>
      <header className="hero">
        <div>
          <p className="eyebrow">Lululemon Portfolio Resource Planning</p>
          <h1>Softtek Resource Reality</h1>
          <p className="subtitle">Q1 and Q2 validate actual effort against planned MD. Q3 combines the source forecast, five confirmed project forecasts and the quarterly share of the FY26 operating baseline.</p>
        </div>
        <div className="hero-actions">
          <div className="tabs summary-tabs" role="tablist" aria-label="Portfolio summary scope">
            <button className={summaryScope === "all" ? "active" : ""} type="button" onClick={() => setSummaryScope("all")}>Overall</button>
            <button className={summaryScope === "cscop" ? "active" : ""} type="button" onClick={() => setSummaryScope("cscop")}>CSCOP</button>
            <button className={summaryScope === "non_cscop" ? "active" : ""} type="button" onClick={() => setSummaryScope("non_cscop")}>Non-CSCOP</button>
          </div>
          <button className="download" type="button" onClick={downloadDetail}><Download size={17} />Data detail</button>
        </div>
      </header>

      <section className="kpis">
        <Kpi icon={Users} label="Quarterly Capacity Benchmark" value={`${data.resource_count} people / ${formatMd(capacity, 0)} MD`} note="20 days x 3 months; Yola Liang excluded" />
        <Kpi icon={BarChart3} label={`Q1 ${summaryLabel} Actual vs Planned`} value={`${formatMd(summaryTotals.q1_actual)} / ${formatMd(summaryTotals.q1_planned)} MD`} note={`${signedMd(summaryQ1Gap)} variance`} tone="blue" />
        <Kpi icon={Target} label={`Q2 ${summaryLabel} Actual vs Planned`} value={`${formatMd(summaryTotals.q2_actual)} / ${formatMd(summaryTotals.q2_planned)} MD`} note={`${signedMd(summaryQ2Gap)} variance`} tone="amber" />
        <Kpi icon={Gauge} label={`Q3 ${summaryLabel} Forecast`} value={`${formatMd(summaryTotals.q3_planned)} MD`} note={summaryQ3Note} tone="green" />
      </section>

      <section className="summary-grid">
        <article className="panel narrative">
          <div className="panel-title"><h2>Takeaway</h2><StatusBadge value="High" /></div>
          <ul>
            <li><strong>Planning accuracy improved materially in Q2.</strong><span>Q1 actual reached {pct(q1Realization)} of plan ({signedMd(q1Gap)}), while Q2 reached {pct(q2Realization)} ({signedMd(q2Gap)}). Q2 is a much stronger planning baseline.</span></li>
            <li><strong>Q2 used most of the theoretical capacity visible in this model.</strong><span>Actual was {formatMd(totals.q2_actual)} MD, or {pct(totals.q2_actual / capacity)} of the {formatMd(capacity, 0)} MD gross benchmark; plan coverage was {pct(totals.q2_planned / capacity)}.</span></li>
            <li><strong>Q3 demand is lower, but not empty.</strong><span>{formatMd(totals.q3_planned)} MD covers {pct(q3Coverage)} of gross capacity and {pct(q3VsQ2Actual)} of Q2 actual. The five confirmed projects contribute {formatMd(data.q3_forecast.manual_projects_confirmed)} MD ({pct(manualShare)} of Q3), with another {formatMd(annualOperations.quarter_totals.Q3)} MD from the annual operating baseline.</span></li>
          </ul>
        </article>

        <article className="panel narrative">
          <div className="panel-title"><h2>Insight</h2><span className="unit">Decision view</span></div>
          <ul>
            <li><strong>Use Q2 as the operating baseline, not Q1.</strong><span>The Q2 plan-to-actual gap is only {formatMd(Math.abs(q2Gap))} MD ({pct(Math.abs(q2Gap) / totals.q2_planned)} of plan), while Q1 was under-planned by {formatMd(q1Gap)} MD.</span></li>
            <li><strong>Convert the Q3 project forecast into named person-month allocation.</strong><span>The annual Incident / Problem / Change baseline is already assigned to five named roles. The remaining {formatMd(unassignedConfirmedUplift)} MD confirmed project uplift still needs person and month allocation before vendor decisions.</span></li>
            <li><strong>Close the CSCOP governance gap before execution.</strong><span>The five Q2 traces total {formatMd(manualTrace)} MD. CVE has {formatMd(7.5)} MD Q3 demand but no confirmed CSCOP ID; assign the ID and owner before work starts.</span></li>
          </ul>
        </article>
      </section>

      <section className="panel governance-panel">
        <div className="panel-title"><h2>CSCOP Governance Split</h2><span className="unit">Formal project ID vs Non-CSCOP</span></div>
        <div className="dedicated-summary governance-summary">
          <div><span>Q1 CSCOP Actual / Planned</span><strong>{formatMd(cscopTotals.q1_actual)} / {formatMd(cscopTotals.q1_planned)} MD</strong><small>{pct(q1CscopCoverage)} of Q1 actual has CSCOP ID</small></div>
          <div><span>Q2 CSCOP Actual / Planned</span><strong>{formatMd(cscopTotals.q2_actual)} / {formatMd(cscopTotals.q2_planned)} MD</strong><small>{pct(q2CscopCoverage)} of Q2 actual has CSCOP ID</small></div>
          <div><span>Q3 CSCOP Forecast</span><strong>{formatMd(cscopTotals.q3_planned)} MD</strong><small>{pct(q3CscopCoverage)} of Q3 plan has CSCOP ID</small></div>
          <p>About half of Q2 actual is Non-CSCOP. Confirm whether this is valid Operation / BAU effort or project work that still needs a CSCOP ID.</p>
        </div>
        <div className="governance-band"><strong>Non-CSCOP:</strong><span>Q1 {formatMd(nonCscopTotals.q1_actual)} / {formatMd(nonCscopTotals.q1_planned)} MD</span><span>Q2 {formatMd(nonCscopTotals.q2_actual)} / {formatMd(nonCscopTotals.q2_planned)} MD</span><span>Q3 forecast {formatMd(nonCscopTotals.q3_planned)} MD</span></div>
      </section>

      <section className="panel annual-operations-panel">
        <div className="panel-title">
          <h2>FY26 Incident / Problem / Change Baseline</h2>
          <span className="unit">Named roles · Non-CSCOP</span>
        </div>
        <div className="annual-summary">
          <div><span>FY26 Annual Demand</span><strong>{formatMd(annualOperations.annual_total_md, 2)} MD</strong></div>
          {["Q1", "Q2", "Q3", "Q4"].map((quarter) => (
            <div key={quarter}><span>{quarter} Allocated Plan</span><strong>{formatMd(annualOperations.quarter_totals[quarter], 2)} MD</strong></div>
          ))}
        </div>
        <p className="allocation-note">Annual demand is distributed evenly across Lulu FY26 quarters because no monthly seasonality was provided. A 0.01 MD rounding balance keeps every quarterly and annual total reconciled. These amounts are included in each quarter's Non-CSCOP planned MD.</p>
        <div className="annual-detail-grid">
          <div className="table-wrap compact-table">
            <table>
              <thead><tr><th>Work Type</th><th>FY26</th><th>Q1</th><th>Q2</th><th>Q3</th><th>Q4</th></tr></thead>
              <tbody>
                {annualOperations.categories.map((row) => (
                  <tr key={row.work_type}>
                    <td><strong>{row.work_type}</strong></td>
                    <td>{formatMd(row.annual_md, 2)} MD</td>
                    {["Q1", "Q2", "Q3", "Q4"].map((quarter) => <td key={quarter}>{formatMd(row.quarter_md[quarter], 2)} MD</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="table-wrap compact-table">
            <table>
              <thead><tr><th>Role</th><th>Resource</th><th>FY26</th><th>Q1</th><th>Q2</th><th>Q3</th><th>Q4</th></tr></thead>
              <tbody>
                {annualOperations.resources.map((row) => (
                  <tr key={row.name}>
                    <td>{row.role}</td>
                    <td><strong>{row.name}</strong></td>
                    <td>{formatMd(row.annual_md, 2)} MD</td>
                    {["Q1", "Q2", "Q3", "Q4"].map((quarter) => <td key={quarter}>{formatMd(row.quarter_md[quarter], 2)} MD</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section className="summary-grid">
        <article className="panel chart-panel">
          <div className="panel-title"><h2>Quarter View</h2><span className="unit">MD</span></div>
          <ResponsiveContainer width="100%" height={286}>
            <BarChart data={chartData} margin={{ top: 12, right: 12, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="#e5e7eb" strokeDasharray="3 3" /><XAxis dataKey="quarter" tick={{ fontSize: 12 }} /><YAxis tick={{ fontSize: 12 }} />
              <Tooltip formatter={(value) => `${formatMd(value)} MD`} /><Legend />
              <Bar dataKey="planned" name="Planned / Forecast" fill="#668078" radius={[2, 2, 0, 0]} /><Bar dataKey="actual" name="Actual" fill="#46586b" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </article>
        <article className="panel action-panel">
          <div className="panel-title"><h2>Management Actions</h2><span className="unit">Next review</span></div>
          <div className="action-list">
            <div><AlertTriangle size={18} /><span><strong>PM / Project owner</strong>Reconcile the 82.88 MD confirmed projects; assign the {formatMd(unassignedConfirmedUplift)} MD uplift to names and months.</span></div>
            <div><AlertTriangle size={18} /><span><strong>Governance owner</strong>Create or confirm the CSCOP ID for cve-2026-4-973 fix.</span></div>
            <div><CheckCircle2 size={18} /><span><strong>Resource owner</strong>Review the 27.77 MD quarterly Incident / Problem / Change baseline against actual workload and adjust the next-quarter split when a seasonal pattern becomes visible.</span></div>
          </div>
        </article>
      </section>

      <GroupSection
        title="Dedicated QA Reality"
        names={data.dedicated_qa_names}
        subtitle="Daisy · Mengyi · Harry · Jade"
        description={(scope) => scope === "cscop"
          ? `Dedicated QA delivered ${formatMd(data.dedicated_qa_totals.q2_cscop_actual)} MD CSCOP actual in Q2, but only ${formatMd(data.dedicated_qa_totals.q3_cscop_planned)} MD is currently assigned for Q3. Confirm QA allocation against the five project forecasts.`
          : "Dedicated QA Non-CSCOP effort is limited. Any material increase should be checked for missing CSCOP classification."}
      />

      <GroupSection
        title="Operation Resource Reality"
        names={data.operation_resource_names}
        subtitle="Echo · Jenny · Jiarui · Liv · Lucy · Ruby"
        description={(scope) => scope === "cscop"
          ? `The six Operation resources recorded ${formatMd(data.operation_resource_totals.q2_cscop_actual)} MD CSCOP actual in Q2 versus ${formatMd(data.operation_resource_totals.q2_cscop_planned)} MD planned. Validate which Q3 projects require named allocation.`
          : `Non-CSCOP is the main workload for this group: ${formatMd(data.operation_resource_totals.q2_non_cscop_actual)} MD actual in Q2. Confirm that this is genuine Operation / BAU demand.`}
      />

      <section className="panel project-panel">
        <div className="panel-title">
          <h2>Project Effort Detail</h2>
          <div className="panel-controls">
            <div className="tabs scope-tabs" role="tablist" aria-label="Project ID scope">
              <button className={projectScope === "cscop" ? "active" : ""} type="button" onClick={() => setProjectScope("cscop")}>CSCOP Projects</button>
              <button className={projectScope === "non_cscop" ? "active" : ""} type="button" onClick={() => setProjectScope("non_cscop")}>Non-CSCOP</button>
            </div>
            <div className="tabs" role="tablist" aria-label="Project quarter">
              {["Q1", "Q2", "Q3"].map((quarter) => <button key={quarter} className={projectQuarter === quarter ? "active" : ""} type="button" onClick={() => setProjectQuarter(quarter)}>{quarter}</button>)}
            </div>
          </div>
        </div>
        <div className="table-wrap project-table">
          <table>
            <thead><tr><th>Project ID</th><th>Project</th><th>Actual MD</th><th>Planned / Forecast MD</th><th>Variance</th><th>Read</th></tr></thead>
            <tbody>
              {projectRows.map((row) => {
                const variance = row.actual - row.planned;
                return (
                  <tr key={`${row.quarter}-${row.project_id}-${row.project}`}>
                    <td><span className={row.cscop ? "project-id" : "operation-id"}>{row.project_id}</span></td>
                    <td><strong>{row.project}</strong>{row.confirmed_manual && <small>{row.manual_type === "annual_operation" ? "FY26 annual baseline" : "Confirmed manual input"}</small>}</td>
                    <td>{projectQuarter === "Q3" ? "Not started" : `${formatMd(row.actual)} MD`}</td>
                    <td>{formatMd(row.planned)} MD</td>
                    <td className={variance > 0 ? "negative" : "positive"}>{projectQuarter === "Q3" ? "-" : signedMd(variance)}</td>
                    <td>{projectRead(row, projectQuarter)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel resource-panel">
        <div className="panel-title">
          <h2>All Softtek Resource Detail</h2>
          <div className="tabs scope-tabs" role="tablist" aria-label="Resource ID scope">
            <button className={resourceScope === "cscop" ? "active" : ""} type="button" onClick={() => setResourceScope("cscop")}>CSCOP Projects</button>
            <button className={resourceScope === "non_cscop" ? "active" : ""} type="button" onClick={() => setResourceScope("non_cscop")}>Non-CSCOP</button>
          </div>
        </div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Status</th><th>Resource</th><th>Q1 Actual / Planned</th><th>Q2 Actual / Planned</th><th>Q3 Named Forecast</th><th>Current Read</th></tr></thead>
            <tbody>
              {detailRows.map((row) => (
                <tr key={row.name}>
                  <td><StatusBadge value={row.status} /></td>
                  <td><strong>{row.name}</strong><small>{row.group} · {row.space}</small></td>
                  <td>{formatMd(scopedResourceValue(row, "q1", "actual"))} / {formatMd(scopedResourceValue(row, "q1", "planned"))} MD</td>
                  <td>{formatMd(scopedResourceValue(row, "q2", "actual"))} / {formatMd(scopedResourceValue(row, "q2", "planned"))} MD</td>
                  <td>{formatMd(scopedResourceValue(row, "q3", "planned"))} MD</td>
                  <td>{resourceScope === "cscop"
                    ? scopedResourceValue(row, "q3", "planned") > 0 ? "Named CSCOP allocation exists" : "Historical CSCOP effort; no Q3 allocation"
                    : "Non-CSCOP effort; validate Operation / BAU classification"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <footer><CheckCircle2 size={16} />Source cut-off: {data.as_of}. Q1 = Feb-Apr, Q2 = May-Jul, Q3 = Aug-Oct, Q4 = Nov-Jan. 1 MD = 8 hours. Source plan is prorated by business-day overlap; the FY26 operating baseline is split evenly by quarter.</footer>
    </main>
  );
}

const rootElement = document.getElementById("root");
const root = import.meta.hot?.data.root ?? createRoot(rootElement);
root.render(<App />);

if (import.meta.hot) import.meta.hot.data.root = root;
