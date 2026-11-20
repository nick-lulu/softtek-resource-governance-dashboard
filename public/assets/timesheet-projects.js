((root) => {
  'use strict';

  const cscopPattern = /^CSCOP-\d+$/;
  const amount = value => typeof value === 'number' && Number.isFinite(value) && value >= 0;
  const sourceReady = snapshot => ['ready', 'stale'].includes(snapshot?.status);
  const numberedFirst = rows => [...rows.values()].sort((a, b) => Number(!a.ref) - Number(!b.ref));

  function references(value) {
    const ids = String(value ?? '').trim().toUpperCase();
    if (!/^CSCOP-\d+(?:\/(?:CSCOP-)?\d+)*$/.test(ids)) return [];
    return [...new Set(ids.split('/').map(id => id.startsWith('CSCOP-') ? id : 'CSCOP-' + id))];
  }

  function rowsFor(person, snapshot, includeUnplanned = true) {
    const rows = new Map();
    const sharedRefs = new Set();
    for (const contribution of person.contributions) {
      for (const project of contribution.resource.projects) {
        const ids = references(project.id);
        const sourceRef = ids.sort().join(' / ') || String(project.id ?? '').trim();
        const ref = ids.length === 1 ? ids[0] : '';
        const key = ref || (sourceRef ? 'ref:' + sourceRef : 'name:' + project.name);
        const row = rows.get(key) ?? {
          ref: ids.length ? sourceRef : '', name: project.name, roles: new Set(), forecast: null, actual: null,
          note: ids.length > 1 ? 'Shared forecast' : (!ref && sourceRef ? 'Source ref · ' + sourceRef : '')
        };
        if (project.role) row.roles.add(project.role);
        if (contribution.resource.planReady && amount(project.md)) {
          row.forecast = (row.forecast ?? 0) + project.md;
        }
        rows.set(key, row);
        if (ids.length > 1) ids.forEach(id => sharedRefs.add(id));
      }
    }
    if (!sourceReady(snapshot)) return numberedFirst(rows);

    for (const project of snapshot.projects) {
      const key = project.cscop || (project.projectNo ? 'timesheet:' + project.projectNo
        : 'timesheet-name:' + project.projectName.toLowerCase());
      const existing = rows.get(key);
      if (existing) {
        existing.actual = project.actualMD;
        continue;
      }
      const shared = sharedRefs.has(project.cscop);
      if (!includeUnplanned && !shared) continue;
      rows.set(key, {
        ref: project.cscop || '',
        name: project.projectName || project.projectNo,
        roles: new Set(),
        forecast: project.cscop && !shared ? 0 : null,
        actual: project.actualMD,
        note: !project.cscop ? (project.projectNo ? 'CSCOP mapping pending · ' + project.projectNo : 'No CSCOP supplied by Timesheet')
          : shared ? 'Forecast shared across CSCOPs' : 'Outside Q4 project forecast'
      });
    }
    // An unmatched internal project number could belong to a forecasted CSCOP.
    if (snapshot.projects.every(project => project.cscop)) {
      for (const [key, row] of rows) {
        if (cscopPattern.test(key) && row.actual === null) row.actual = 0;
      }
    }
    return numberedFirst(rows);
  }

  const dialogRequests = new WeakMap();
  function showDetails(dialog, section, person, format, {includeUnplanned = true} = {}) {
    const escape = value => String(value ?? '').replace(/[&<>"']/g, char =>
      ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'})[char]);
    section.innerHTML = '<h3>Project Review Details</h3><p role="status">Loading Timesheet actuals…</p>' +
      (includeUnplanned ? '' : '<p>Actual MD is the person’s total for each listed CSCOP across Timesheet.</p>') +
      '<div class="project-review-scroll" role="region" aria-label="Project Review Details" tabindex="0"><table>' +
      '<thead><tr><th scope="col">CSCOP No.</th><th scope="col">Project Name</th><th scope="col">Role</th>' +
      '<th scope="col">Forecasting MD</th><th scope="col">Actual MD</th></tr></thead><tbody></tbody></table></div>';
    const body = section.querySelector('tbody');
    const status = section.querySelector('[role="status"]');
    const request = new AbortController();
    dialogRequests.get(dialog)?.abort();
    dialogRequests.set(dialog, request);
    const close = () => { if (!dialog.open) request.abort(); };
    dialog.addEventListener('close', close);
    function render(snapshot) {
      const rows = rowsFor(person, snapshot, includeUnplanned);
      body.innerHTML = rows.map(row => '<tr><th scope="row">' + escape(row.ref || '—') +
        '</th><td><strong>' + escape(row.name) + '</strong>' + (row.note ? '<small>' + escape(row.note) + '</small>' : '') +
        '</td><td>' + escape([...row.roles].join(' / ') || '—') + '</td><td>' + escape(format(row.forecast)) +
        '</td><td>' + escape(format(row.actual)) + '</td></tr>').join('') ||
        '<tr><td colspan="5">No Q4 project records available.</td></tr>';
    }
    render();
    const timer = setTimeout(() => request.abort(), 15000);
    read(person.key, request.signal).then(snapshot => {
      if (dialogRequests.get(dialog) !== request || !dialog.open || !section.isConnected) return;
      render(snapshot);
      status.textContent = snapshot.status === 'ready' ? '' : snapshot.status === 'stale'
        ? 'Showing the last available Timesheet actuals.' : 'Timesheet project actuals are unavailable.';
    }).finally(() => {
      clearTimeout(timer);
      dialog.removeEventListener('close', close);
    });
  }

  async function read(resourceKey, signal, month) {
    if (location.protocol === 'file:' || location.hostname.endsWith('.github.io')) return {status: 'not_configured'};
    const start = month ? month + '-01' : '2026-11-01';
    const end = month ? month + (month === '2026-11' ? '-30' : '-31') : '2027-01-31';
    const query = new URLSearchParams({resourceKey});
    if (month) query.set('month', month);
    try {
      const response = await fetch('/api/v1/timesheet/projects?' + query,
        {cache: 'no-store', signal});
      if (!response.ok) return {status: 'unavailable'};
      const data = await response.json();
      if (data.schemaVersion !== 1 || data.resourceKey !== resourceKey || data.hoursPerMD !== 8 ||
          data.period?.startDate !== start || data.period?.endDate !== end ||
          !Array.isArray(data.projects) || !data.projects.every(project =>
            project && (project.cscop === null || cscopPattern.test(project.cscop)) &&
            typeof project.projectNo === 'string' && typeof project.projectName === 'string' &&
            amount(project.actualHours) && amount(project.actualMD) &&
            Math.abs(project.actualHours / 8 - project.actualMD) < 1e-8)) {
        return {status: 'unavailable'};
      }
      return data;
    } catch {
      return {status: 'unavailable'};
    }
  }

  const api = {rowsFor, read, showDetails};
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.TimesheetProjects = api;
})(typeof window === 'undefined' ? globalThis : window);
