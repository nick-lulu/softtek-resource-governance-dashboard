(() => {
  'use strict';

  const months = ['2026-11', '2026-12', '2027-01'];
  const monthLabels = ['Nov 2026', 'Dec 2026', 'Jan 2027'];
  const {people, corporateIds} = JSON.parse(document.getElementById('cq-data').textContent);
  const scope = new Set(corporateIds);
  const format = new Intl.NumberFormat('en', {maximumFractionDigits: 2});
  const md = value => value === null ? '—' : format.format(value);
  const sum = values => values.every(value => value === null)
    ? null : values.reduce((total, value) => total + (value ?? 0), 0);
  const escape = value => String(value).replace(/[&<>"']/g, char =>
    ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'})[char]);
  const forecasts = months.map((_, i) => sum(people.map(person => person.forecast[i])));
  const results = people.map(() => months.map(() => null));
  const actualProjects = people.map(() => months.map(() => null));
  const body = document.getElementById('cq-people');
  const chartPeriods = document.getElementById('cq-chart-periods');
  let selectedMonth = -1;

  function pairs(forecast, actual) {
    return [...forecast, sum(forecast)].map((value, i) =>
      '<td class="cq-plan-cell">' + md(value) + '</td><td class="cq-actual-cell">' +
      md(i === months.length ? sum(actual) : actual[i]) + '</td>').join('');
  }

  function renderPeople() {
    body.innerHTML = people.map((person, i) => {
      const projects = [...person.projects];
      const refs = new Set(projects.map(project => project.ref).filter(Boolean));
      for (const snapshot of actualProjects[i]) {
        if (!snapshot) continue;
        for (const [ref, project] of snapshot.projects) {
          if (refs.has(ref)) continue;
          projects.push({ref, name: project.projectName || ref, forecast: [null, null, null], actualOnly: true});
          refs.add(ref);
        }
      }
      const count = person.projects.length;
      const summary = '<tr class="cq-person"><th scope="row" colspan="2">' + escape(person.name) +
        '<small>' + count + ' forecast project' + (count === 1 ? '' : 's') + '</small></th>' +
        pairs(person.forecast, results[i]) + '</tr>';
      const details = projects.map(project => {
        const actual = actualProjects[i].map(snapshot => {
          if (!snapshot || !scope.has(project.ref)) return null;
          return snapshot.projects.get(project.ref)?.actualMD ?? (snapshot.hasUnmapped ? null : 0);
        });
        const cscop = /^CSCOP-\d+$/.test(project.ref) ? project.ref : '';
        return '<tr class="cq-project"><td class="cq-ref">' + escape(cscop || '—') +
          '</td><th scope="row">' + escape(project.name) +
          (project.ref && !cscop ? '<small>' + escape(project.ref) + '</small>' : '') +
          (project.actualOnly ? '<small>Timesheet only</small>' : '') + '</th>' +
          pairs(project.forecast, actual) + '</tr>';
      }).join('');
      return summary + details;
    }).join('');
  }

  function chartRow(label, forecast, actual, max) {
    const series = (value, name, actualBar = false) =>
      '<div class="cq-series" aria-label="' + name + ' ' + md(value) + ' MD"><span class="cq-track">' +
      (value === null ? '' : '<i class="cq-bar' + (actualBar ? ' cq-actual' : '') +
        '" style="width:' + (value / max * 100) + '%"></i>') +
      '</span><b>' + md(value) + '</b></div>';
    return '<div class="cq-month"><strong>' + label + '</strong><div>' +
      series(forecast, 'Forecast') + series(actual, 'Actual', true) + '</div></div>';
  }

  function renderChart() {
    const plans = people.map(person => selectedMonth < 0 ? sum(person.forecast) : person.forecast[selectedMonth]);
    const actuals = results.map(row => selectedMonth < 0 ? sum(row) : row[selectedMonth]);
    const max = Math.max(1, ...plans, ...actuals);
    document.getElementById('cq-chart').innerHTML =
      '<div class="cq-legend"><span><i></i>Forecasting MD</span><span><i></i>Actual MD</span></div>' +
      people.map((person, i) => chartRow(escape(person.name), plans[i], actuals[i], max)).join('');
  }

  function renderTotals() {
    const actuals = months.map((_, i) => sum(results.map(row => row[i])));
    document.getElementById('cq-totals').innerHTML =
      '<span>Q4 Forecast MD<strong>' + md(sum(forecasts)) + '</strong></span>' +
      '<span>Q4 Actual MD<strong>' + md(sum(actuals)) + '</strong></span>';
    chartPeriods.querySelectorAll('[data-cq-month]').forEach((button, i) => {
      if (i === 0) return;
      button.querySelector('.cq-period-forecast').textContent = md(forecasts[i - 1]);
      button.querySelector('.cq-period-actual').textContent = md(actuals[i - 1]);
    });
    renderChart();
    renderPeople();
  }

  chartPeriods.innerHTML = '<button type="button" data-cq-month="-1" aria-pressed="true" aria-controls="cq-chart">Q4 total</button>' +
    monthLabels.map((label, i) => '<button type="button" data-cq-month="' + i +
      '" aria-pressed="false" aria-controls="cq-chart"><strong>' + label + '</strong>' +
      '<span>Forecast <b class="cq-period-forecast">—</b></span>' +
      '<span>Actual <b class="cq-period-actual">—</b></span></button>').join('');
  chartPeriods.addEventListener('click', event => {
    const button = event.target.closest('[data-cq-month]');
    if (!button) return;
    selectedMonth = Number(button.dataset.cqMonth);
    chartPeriods.querySelectorAll('[data-cq-month]').forEach(option =>
      option.setAttribute('aria-pressed', String(option === button)));
    renderChart();
  });

  async function refresh() {
    const status = document.getElementById('cq-status');
    if (!people.length) {
      status.textContent = 'Allocation details are available on the LCORP site.';
      return;
    }
    if (!window.TimesheetProjects) {
      status.textContent = 'Timesheet actuals are unavailable.';
      return;
    }
    let frame;
    let loaded = 0;
    let unmapped = false;
    let stale = false;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30000);
    await Promise.all(people.map(async (person, i) => {
      for (const [j, month] of months.entries()) {
        const snapshot = await window.TimesheetProjects.read(person.key, controller.signal, month);
        if (!['ready', 'stale'].includes(snapshot.status)) continue;
        stale ||= snapshot.status === 'stale';
        const known = snapshot.projects.filter(project => scope.has(project.cscop));
        const hasUnmapped = snapshot.projects.some(project => !project.cscop);
        actualProjects[i][j] = {projects: new Map(known.map(project => [project.cscop, project])), hasUnmapped};
        unmapped ||= hasUnmapped;
        results[i][j] = known.length ? sum(known.map(project => project.actualMD)) : hasUnmapped ? null : 0;
        loaded++;
        cancelAnimationFrame(frame);
        frame = requestAnimationFrame(() => {
          renderTotals();
          status.textContent = 'Loading Timesheet actuals · ' + loaded + ' of ' +
            people.length * months.length + ' person-months retrieved.';
        });
      }
    }));
    clearTimeout(timeout);
    cancelAnimationFrame(frame);
    renderTotals();
    status.textContent = !loaded ? 'Timesheet actuals are pending.' :
      (loaded < people.length * months.length || unmapped || stale
        ? 'Partial actuals · ' + loaded + ' of ' + (people.length * months.length) + ' person-months retrieved.' +
          (unmapped ? ' Unmapped projects are excluded.' : '') + (stale ? ' Includes cached Timesheet data.' : '')
        : 'Actuals include matched Corporate projects. 8 hours = 1 MD.');
  }

  const peopleButton = document.getElementById('cq-show-people');
  const detailsButton = document.getElementById('cq-show-details');
  const peopleView = document.getElementById('cq-people-view');
  const detailsView = document.getElementById('cq-details-view');
  const exportButton = document.getElementById('export');
  let hasOpenedDetails = false;

  function selectView(showDetails) {
    peopleView.hidden = showDetails;
    detailsView.hidden = !showDetails;
    exportButton.hidden = showDetails;
    peopleButton.setAttribute('aria-pressed', String(!showDetails));
    detailsButton.setAttribute('aria-pressed', String(showDetails));
    if (showDetails && !hasOpenedDetails) {
      hasOpenedDetails = true;
      renderTotals();
      refresh();
    }
  }

  peopleButton.addEventListener('click', () => selectView(false));
  detailsButton.addEventListener('click', () => selectView(true));
})();
