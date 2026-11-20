(() => {
  'use strict';

  const dialog = document.getElementById('cq-hmt');
  const status = dialog.querySelector('[role="status"]');
  const list = dialog.querySelector('.cq-hmt-results');
  const md = value => Number.isFinite(value) ? value.toFixed(2) : '—';
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char =>
    ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'})[char]);
  let pending;
  let ready = false;
  const actuals = new Map();

  function actualFor(person, refs) {
    if (!refs.size) return Promise.resolve(null);
    const key = person.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
    if (!actuals.has(key)) {
      actuals.set(key, window.TimesheetProjects.read(key, AbortSignal.timeout(15000)));
    }
    return actuals.get(key).then(snapshot => {
      if (!['ready', 'stale'].includes(snapshot.status)) return null;
      const matches = snapshot.projects.filter(project => refs.has(project.cscop));
      if (!matches.length && snapshot.projects.some(project => !project.cscop)) return null;
      return {md: matches.reduce((total, project) => total + project.actualMD, 0),
        stale: snapshot.status === 'stale'};
    });
  }

  async function load() {
    status.textContent = 'Loading HMT projects…';
    try {
      const data = await Promise.all(['project-label-data', 'cscop-export-data'].map(async name => {
        const response = await fetch('../assets/' + name + '.json');
        if (!response.ok) throw new Error('HMT data unavailable');
        return response.json();
      }));
      const [labels, allocations] = data;
      const hmt = labels.projects.filter(project => project.market === 'HMT');
      const cells = [];
      list.innerHTML = hmt.map(project => {
        const refs = new Set(project.references || []);
        if (project.id) refs.add(project.id);
        const rows = allocations.details.filter(row =>
          (project.recordKey && row.recordKey === project.recordKey && row.domain === project.domain) ||
          (refs.size && row.references.some(ref => refs.has(ref))));
        const named = rows.filter(row => row.person);
        const numeric = named.filter(row => Number.isFinite(row.md));
        const total = numeric.length ? numeric.reduce((sum, row) => sum + row.md, 0) : null;
        const people = new Map();
        for (const row of named) {
          const person = people.get(row.person) || {roles: new Set(), planned: null};
          if (row.role) person.roles.add(row.role);
          if (Number.isFinite(row.md)) person.planned = (person.planned ?? 0) + row.md;
          people.set(row.person, person);
        }
        const body = [...people].map(([name, person]) => {
          cells.push({name, refs});
          return '<tr><td>' + escape(name) + '</td><td>' + escape([...person.roles].join(' / ')) +
            '</td><td>' + md(person.planned) + '</td><td data-hmt-actual>—</td></tr>';
        }).join('');
        return '<section class="cq-hmt-project"><h3>' + escape(project.name) + '</h3><p>' +
          escape(project.id || 'CSCOP pending') + ' · ' + escape(project.domain) + ' · ' +
          escape(project.status) + '</p>' + (named.length
            ? '<div class="tablewrap" role="region" tabindex="0" aria-label="' + escape(project.name) +
              ' resource MD"><table><thead><tr><th>Resource</th><th>Role</th><th>Q4 Planned MD</th><th>Actual MD</th></tr></thead><tbody>' +
              body + '</tbody><tfoot><tr><th colspan="2" scope="row">Named planned MD' +
              (numeric.length < named.length ? ' · partial' : '') + '</th><td>' + md(total) +
              '</td><td></td></tr></tfoot></table></div>'
            : '<p class="cq-hmt-empty">Named resource MD has not been supplied.</p>') + '</section>';
      }).join('');
      ready = true;
      const description = hmt.length + ' HMT projects across all domains. Actual MD is matched by person and CSCOP.';
      status.textContent = description + ' Loading Timesheet…';
      const targets = list.querySelectorAll('[data-hmt-actual]');
      const values = await Promise.all(cells.map(({name, refs}) => actualFor(name, refs)));
      values.forEach((value, i) => {
        if (value) targets[i].textContent = md(value.md) + (value.stale ? ' (cached)' : '');
      });
      status.textContent = description + (values.some(value => value === null)
        ? ' A dash means Actual MD is unavailable.' : '');
    } catch {
      status.textContent = 'HMT project data is unavailable. Reopen to retry.';
    }
  }

  document.addEventListener('click', async event => {
    const trigger = event.target.closest('.cscop-tag-guide .hmt-project-count');
    if (!trigger) return;
    if (!dialog.open) dialog.showModal();
    if (ready || pending) return;
    pending = load();
    await pending;
    pending = null;
  });
  dialog.querySelector('button').addEventListener('click', () => dialog.close());
})();
