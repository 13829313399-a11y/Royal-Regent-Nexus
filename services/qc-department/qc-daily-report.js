/* QC daily report. The actor-scoped gateway owns the data and workbook. */
(function (root) {
  'use strict';
  const doc = root.document;
  const enabled = () => !!root.__QC_NEXUS?.factory;
  const exportAllowed = () => root.__QC_NEXUS?.exportAllowed === true;
  function syncCustomerOptions(select, customers) {
    if (!Array.isArray(customers)) return;
    const previous = select.selectedOptions[0];
    const value = select.value;
    const options = customers.map(item => new Option(item.label,item.key));
    if (value && !customers.some(item => item.key === value)) options.push(previous);
    select.replaceChildren(new Option('全部客户',''),...options);
    select.value = value;
  }
  function createReport(period, inputId, customerId, label, overviewLabel) {
    const area = () => doc.getElementById(period + 'ReportBody');
    const dateInput = () => doc.getElementById(inputId);
    const esc = value => root._esc(value);
    const display = value => value === '' || value == null ? '—' : esc(value);
    const quantity = value => typeof value === 'number' ? value.toLocaleString('zh-CN', {maximumFractionDigits:4}) : display(value);
    const kind = result => result === 'PASS' ? 'pass' : ['FAIL','REJ'].includes(result) ? 'fail' : 'other';
    const badge = result => '<span class="qdr-result ' + kind(result) + '">' + display(result) + '</span>';
    const path = 'api/daily-report';
    let sequence = 0;
    let snapshot = null;
    let mode = 'compact';
    let initialized = false;
    const selectedDate = () => period === 'monthly' && dateInput().value ? dateInput().value + '-01' : dateInput().value;
    const periodLabel = report => report.dateFrom === report.dateTo ? report.dateFrom : report.dateFrom + ' 至 ' + report.dateTo;

    async function read(url) {
      const response = await root.fetch(url, {cache:'no-store'});
      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw Error(typeof error.detail === 'string' ? error.detail : '请求未完成，请稍后重试');
      }
      return response;
    }

    function fullTable(report, interactive = false) {
      const head = report.headers.map(label => '<th scope="col">' + esc(label) + '</th>').join('');
      const rows = report.rows.map(({values}, index) => (interactive ? detailRow(index) : '<tr>') + values.map((value, index) =>
        '<td>' + (index === 8 ? badge(value) : index === 5 ? quantity(value) : display(value)) + '</td>').join('') + '</tr>').join('');
      return '<table class="qdr-full-table"><thead><tr>' + head + '</tr></thead><tbody>' + rows + '</tbody></table>';
    }

    function detailRow(index) {
      return '<tr data-qdr-row="' + index + '" tabindex="-1">';
    }

    function compactTable(report) {
      const fields = [0,1,5,2,6,7,10,11,12];
      const rows = report.rows.map(({values:v}, index) => {
        const key = 'qdr-' + period + '-record-' + index;
        const details = fields.map(i => '<div><dt>' + esc(report.headers[i]) + '</dt><dd>' +
          (i === 5 ? quantity(v[i]) : display(v[i])) + '</dd></div>').join('');
        return detailRow(index) + '<td><strong>' + display(v[4]) + '</strong><small>' + display(v[3]) + '</small></td>' +
          '<td class="qdr-wide">' + display(v[0]) + '<small>' + display(v[1]) + '</small></td>' +
          '<td class="qdr-number qdr-wide">' + quantity(v[5]) + '</td><td>' + badge(v[8]) + '</td>' +
          '<td>' + display(v[9]) + '</td><td><button type="button" class="qdr-toggle" aria-expanded="false" aria-controls="' +
          key + '" aria-label="展开第 ' + (index+1) + ' 条验货详情">展开</button></td></tr>' +
          '<tr class="qdr-expanded" id="' + key + '" hidden><td colspan="6"><dl>' + details + '</dl></td></tr>';
      }).join('');
      return '<table aria-label="精简验货明细"><thead><tr><th scope="col">产品 / 货号</th>' +
        '<th scope="col" class="qdr-wide">洋行 / 合同</th><th scope="col" class="qdr-number qdr-wide">PO数量</th>' +
        '<th scope="col">结果</th><th scope="col">验货问题</th><th scope="col">详情</th></tr></thead><tbody>' + rows + '</tbody></table>';
    }

    function issues(report) {
      return report.rows.map((row, index) => ({...row, index}))
        .filter(({values:v,improvement}) => (v[8] && v[8] !== 'PASS') || v[9] || improvement);
    }

    function overview(report, interactive = false) {
      const follow = issues(report);
      const segments = [['pass',report.passed],['fail',report.failed],['other',report.other]]
        .filter(([,count]) => count).map(([type,count]) => '<span class="' + type + '" style="flex-grow:' + count + '"></span>').join('');
      const followRows = follow.map(({values:v,improvement,index}) => {
        const content = '<span><strong>' + display(v[9] || v[4]) + '</strong><small>' +
          [v[3],improvement,v[10]].filter(Boolean).map(esc).join(' · ') + '</small></span>';
        const status = badge(v[8]);
        return '<li>' + (interactive
          ? '<button type="button" class="qdr-follow" data-qdr-follow="' + index + '">' + content +
            '<span class="qdr-follow-end">' + status + '<span class="qdr-follow-label">定位</span></span></button>'
          : '<div class="qdr-follow">' + content + status + '</div>') + '</li>';
      });
      const collapsible = interactive && follow.length > 2;
      const followList = collapsible
        ? '<div class="qdr-follow-disclosure"><div class="qdr-issues-preview"><ul class="qdr-issues">' + followRows.slice(0,2).join('') +
          '</ul></div><div class="qdr-issues-more" id="qdr-' + period + '-more-issues" inert aria-hidden="true"><div><ul class="qdr-issues">' +
          followRows.slice(2).join('') + '</ul></div></div><div class="qdr-follow-toggle-zone"><button type="button" class="qdr-follow-toggle" aria-expanded="false" aria-controls="qdr-' +
          period + '-more-issues" aria-label="展开全部 ' + follow.length + ' 条待跟进事项"><svg viewBox="0 0 28 16" aria-hidden="true" focusable="false"><path d="M3 3 L14 13 L25 3" /></svg></button></div></div>'
        : '<ul class="qdr-issues">' + followRows.join('') + '</ul>';
      return '<div class="qdr-overview"><section class="qdr-panel" aria-label="' + overviewLabel + '"><h3>' + overviewLabel + '</h3>' +
        '<p class="qdr-score"><strong>' + (report.rate == null ? '—' : report.rate.toFixed(1) + '%') +
        '</strong><span>PASS 率 · ' + report.total + ' 批验货</span></p><div class="qdr-bar" aria-hidden="true">' + segments + '</div>' +
        '<div class="qdr-counts"><span>PASS <b>' + report.passed + '</b></span><span>FAIL <b>' + report.failed +
        '</b></span><span>其他 <b>' + report.other + '</b></span></div></section>' +
        '<section class="qdr-panel" aria-label="待跟进"><div class="qdr-heading"><h3>待跟进</h3><small>' + follow.length +
        ' 项</small></div>' + (follow.length ? followList : '<p class="qdr-muted">暂无跟进事项</p>') + '</section></div>';
    }

    function setMode() {
      const host = area();
      host.querySelector('[data-qdr-compact]').hidden = mode !== 'compact';
      host.querySelector('[data-qdr-full]').hidden = mode !== 'full';
      host.querySelectorAll('[data-qdr-view]').forEach(button => {
        const active = button.dataset.qdrView === mode;
        button.setAttribute('aria-pressed', String(active));
      });
    }

    function locateDetail(index) {
      const host = area();
      const targets = [...host.querySelectorAll('[data-qdr-row]')];
      targets.forEach(row => row.classList.toggle('qdr-target', row.dataset.qdrRow === index));
      const table = host.querySelector('[data-qdr-' + mode + ']');
      const target = targets.find(row => row.dataset.qdrRow === index && table.contains(row));
      if (!target) return;
      const expand = target.querySelector('.qdr-toggle[aria-expanded="false"]');
      if (expand) expand.click();
      target.focus({preventScroll:true});
      target.scrollIntoView({block:'center', inline:'nearest'});
    }

    function paint(report) {
      const footer = exportAllowed() ? '<div class="qdr-footer"><button type="button" class="qdr-export" data-qdr-export' +
        (report.total ? '' : ' disabled') + '>导出 Excel</button><span class="qdr-muted" role="status" data-qdr-export-status></span></div>' : '';
      if (period === 'daily') {
        const empty = '<p class="qdr-empty">该日期暂无可列入报表的已审核验货记录</p>';
        area().innerHTML = '<section class="qdr template-sheet" aria-label="日报验货明细">' +
          '<div class="daily-sheet-body"><div class="daily-table-scroll" role="region" aria-label="完整验货明细" tabindex="0" data-qdr-full>' +
          (report.total ? fullTable(report) : empty) + '</div>' +
          footer + '</div></section>';
      } else {
        area().innerHTML = '<div class="qdr">' + overview(report, true) +
        '<section class="qdr-panel qdr-detail" aria-label="验货明细"><div class="qdr-heading"><div><h3>验货明细</h3><small>' +
        report.total + ' 条记录</small></div>' + (report.total ? '<div class="qdr-views" role="group" aria-label="明细视图">' +
        '<button type="button" data-qdr-view="compact">精简</button><button type="button" data-qdr-view="full">完整 13 列</button></div>' : '') + '</div>' +
        (report.total ? '<div data-qdr-compact>' + compactTable(report) + '</div><div class="qdr-scroll" data-qdr-full hidden role="region" aria-label="完整 13 列" tabindex="0">' + fullTable(report, true) + '</div>'
          : '<p class="qdr-empty">该日期暂无可列入报表的已审核验货记录</p>') + '</section>' +
        footer + '</div>';
      }
      const button = area().querySelector('[data-qdr-export]');
      root.QcExportColumns.mount(button,'daily');
      if (button && report.total) button.onclick = () => download(report, button);
      if(period==='daily')root.QcReportWorkbook?.mount('daily','daily',area().querySelector('[data-qdr-full]'),report,load);
      if (period === 'daily' || !report.total) return;
      setMode();
      const followToggle = area().querySelector('.qdr-follow-toggle');
      if (followToggle) followToggle.onclick = () => {
        const open = followToggle.getAttribute('aria-expanded') !== 'true';
        const disclosure = followToggle.closest('.qdr-follow-disclosure');
        const more = disclosure.querySelector('.qdr-issues-more');
        disclosure.classList.toggle('is-expanded', open);
        more.toggleAttribute('inert', !open);
        more.setAttribute('aria-hidden', String(!open));
        followToggle.setAttribute('aria-expanded', String(open));
        followToggle.setAttribute('aria-label', open ? '收起待跟进事项' : '展开全部 ' + issues(report).length + ' 条待跟进事项');
      };
      area().querySelectorAll('[data-qdr-view]').forEach(button => {
        button.onclick = () => { mode = button.dataset.qdrView; setMode(); };
      });
      area().querySelectorAll('[data-qdr-follow]').forEach(button => {
        button.onclick = () => locateDetail(button.dataset.qdrFollow);
      });
      area().querySelectorAll('.qdr-toggle').forEach((button, index) => {
        button.onclick = () => {
          const row = doc.getElementById(button.getAttribute('aria-controls'));
          const open = row.hidden;
          row.hidden = !open;
          button.textContent = open ? '收起' : '展开';
          button.setAttribute('aria-expanded', String(open));
          button.setAttribute('aria-label', button.textContent + '第 ' + (index+1) + ' 条验货详情');
        };
      });
    }

    async function load() {
      const id = ++sequence;
      const input = dateInput();
      const customerSelect = doc.getElementById(customerId);
      customerSelect.hidden = false;
      if (period === 'daily') customerSelect.onchange = load;
      input.closest('.page').classList.add('qdr-active');
      if (!initialized && !input.value) input.value = period === 'monthly' ? root.todayStr().slice(0,7) : root.todayStr();
      initialized = true;
      root.QcReportDates?.sync(input);
      const day = selectedDate();
      snapshot = null;
      const rangeLabel = input.closest('.report-toolbar').querySelector('.qdr-period-range');
      if (rangeLabel) rangeLabel.textContent = '';

      area().innerHTML = '<p class="qdr-message" role="status">' + (day ? '正在读取已审核验货记录…' : '请选择报告日期') + '</p>';
      if (!day) return;
      try {
        const params = new URLSearchParams({date:day,period});
        const customer = customerSelect.value;
        if (customer) params.set('customer',customer);
        const response = await read(path + '?' + params);
        const report = await response.json();
        if (id !== sequence || selectedDate() !== day) return;
        if (report.date !== day || report.period !== period) throw Error('返回的报表日期不一致，请重试');
        if ((report.customer || '') !== customer) throw Error('报告客户与当前筛选不一致，请重试');
        if (period === 'weekly' && root.QcWeeklyTemplates) root.QcWeeklyTemplates.syncCustomers(report.customers);
        else syncCustomerOptions(customerSelect,report.customers);
        paint(report);
        let range = input.closest('.report-toolbar').querySelector('.qdr-period-range');
        if (!range) {
          range = doc.createElement('span'); range.className = 'qdr-period-range qdr-muted';
          input.closest('.report-date-field').after(range);
        }
        range.textContent = period === 'daily' ? '' : periodLabel(report);
        snapshot = report;

      } catch (error) {
        if (id !== sequence) return;
        area().innerHTML = '<div class="qdr-message" role="alert"><span>' + esc(error.message) +
          '</span> <button type="button" class="btn-secondary">重试</button></div>';
        area().querySelector('button').onclick = load;
      }
    }

    async function download(report, button) {
      const status = area().querySelector('[data-qdr-export-status]');
      button.disabled = true;
      status.textContent = '正在生成…';
      try {
        const params = new URLSearchParams({date:report.date,period,revision:report.revision});
        const on=root.QcExportColumns.enabled('daily');
        params.set('hideEmptyCols',on?'1':'0');
        if (report.customer) params.set('customer',report.customer);
        const response = await read(path + '/export?' + params);
        const data = await response.blob();
        if (snapshot !== report || selectedDate() !== report.date) return;
        const url = root.URL.createObjectURL(data);
        const link = doc.createElement('a');
        link.href = url;
        link.download = label + '_' + periodLabel(report) + '.xlsx';
        doc.body.append(link);
        link.click();
        link.remove();
        root.setTimeout(() => root.URL.revokeObjectURL(url), 30000);
        status.textContent = root.QcExportColumns.message(on,root.QcExportColumns.fromHeader(response));
      } catch (error) {
        status.textContent = error.message;
      } finally {
        button.disabled = false;
      }
    }

    return {enabled, load, syncCustomers: customers => syncCustomerOptions(doc.getElementById(customerId),customers)};
  }
  root.QcPeriodReports = {
    daily: createReport('daily', 'dailyDate', 'qdrCustomer', '验货日报', '当日验货概览'),
    weekly: createReport('weekly', 'weeklyDate', 'qwtCustomer', '验货周报', '本周验货概览'),
    monthly: createReport('monthly', 'monthlyMonth', 'qmtCustomer', '验货月报', '本月验货概览'),
  };
  root.QcDailyReport = root.QcPeriodReports.daily;
})(window);

/* Report pickers write through the original control and its existing change handlers. */
(function (root) {
  'use strict';
  const doc = root.document;
  const pad = value => String(value).padStart(2, '0');
  const yearText = year => String(year).padStart(4, '0');
  const monthKey = (year, month) => yearText(year) + '-' + pad(month);
  const today = () => root.todayStr();
  const buttons = new WeakMap();
  let open = null;

  function close(restoreFocus = false) {
    if (!open) return;
    const {trigger, panel} = open;
    open = null;
    panel.remove();
    trigger.setAttribute('aria-expanded', 'false');
    trigger.removeAttribute('aria-controls');
    if (restoreFocus) trigger.focus();
  }

  function commit(value) {
    const input = open.input;
    close(true);
    if (input.disabled || input.value === value) return;
    input.value = value;
    input.dispatchEvent(new root.Event('change', {bubbles:true}));
    sync(input); // A template with an unsaved edit may have restored the previous value.
  }

  function place() {
    if (!open) return;
    const {panel, trigger} = open;
    const rect = trigger.getBoundingClientRect();
    if (!rect.width) { close(); return; }
    const left = Math.max(8, Math.min(rect.left, root.innerWidth - panel.offsetWidth - 8));
    const below = root.innerHeight - rect.bottom - 12;
    const above = rect.top - 12;
    const up = panel.scrollHeight > below && above > below;
    panel.style.maxHeight = Math.max(80, up ? above : below) + 'px';
    panel.style.left = left + 'px';
    panel.style.top = (up ? Math.max(6, rect.top - panel.offsetHeight - 5) : rect.bottom + 5) + 'px';
  }

  function makeButton(text, action, label = text) {
    const button = doc.createElement('button');
    button.type = 'button';
    button.textContent = text;
    button.setAttribute('aria-label', label);
    button.onclick = action;
    return button;
  }

  function draw(focusGrid = true) {
    const {input, panel, kind, view, year, month} = open;
    const selected = input.value;
    const prefix = monthKey(year, month);
    const startYear = year - (year - 1) % 12;
    panel.replaceChildren();
    const header = doc.createElement('div');
    header.className = 'qdr-picker-head';
    const title = view === 'days' ? year + '年' + month + '月' : view === 'months' ? year + '年' :
      kind === 'year' ? '选择年份' : startYear + ' — ' + Math.min(9999, startYear + 11);
    if (kind !== 'year') {
      const step = view === 'days' ? 1 : view === 'months' ? 12 : 144;
      const navigate = delta => {
        const offset = (year - 1) * 12 + month - 1 + delta * step;
        open.year = Math.floor(offset / 12) + 1;
        open.month = offset % 12 + 1;
        draw(false);
        open.panel.querySelector(delta < 0 ? '.qdr-prev' : '.qdr-next')?.focus();
      };
      const unit = view === 'days' ? '个月' : view === 'months' ? '一年' : '一组年份';
      const prev = makeButton('‹', () => navigate(-1), '上' + unit);
      const next = makeButton('›', () => navigate(1), '下' + unit);
      prev.className = 'qdr-prev'; next.className = 'qdr-next';
      prev.disabled = (year - 1) * 12 + month - 1 < step;
      next.disabled = (year - 1) * 12 + month - 1 + step >= 9999 * 12;
      const heading = view === 'years' ? doc.createElement('strong') :
        makeButton(title, () => { open.view = view === 'days' ? 'months' : 'years'; draw(); });
      heading.textContent = title;
      header.append(prev, heading, next);
      panel.append(header);
    }
    const grid = doc.createElement('div');
    grid.className = 'qdr-picker-grid ' + (view === 'days' ? 'qdr-days' : 'qdr-periods');
    grid.setAttribute('role', 'group');
    grid.setAttribute('aria-label', title);
    function choice(text, label, current, action, isToday = false) {
      const b = makeButton(text, action, label);
      b.setAttribute('aria-pressed', String(current));
      if (isToday) b.setAttribute('aria-current', 'date');
      grid.append(b);
    }
    if (view === 'days') {
      for (const name of '一二三四五六日') {
        const weekday = doc.createElement('span');
        weekday.textContent = name; grid.append(weekday);
      }
      const first = new Date(prefix + '-01T00:00:00Z');
      grid.style.setProperty('--first-column', String((first.getUTCDay() + 6) % 7 + 1));
      first.setUTCMonth(first.getUTCMonth() + 1, 0);
      const currentDate = today();
      for (let day = 1; day <= first.getUTCDate(); day++) {
        const value = prefix + '-' + pad(day);
        choice(day, value, selected === value, () => commit(value), currentDate === value);
      }
    } else if (view === 'months') {
      for (let m = 1; m <= 12; m++) {
        const value = monthKey(year, m);
        choice(m + '月', year + '年' + m + '月', selected.slice(0,7) === value, () => {
          if (kind === 'month') commit(value);
          else { open.month = m; open.view = 'days'; draw(); }
        });
      }
    } else {
      const years = kind === 'year' ? [...input.options].filter(o=>o.value && !o.disabled).map(o=>o.value) :
        Array.from({length:Math.min(12, 10000 - startYear)}, (_, i) => yearText(startYear + i));
      if (kind === 'year') panel.style.setProperty('--qdr-year-columns',String(Math.max(1, Math.min(3, years.length))));
      for (const y of years) choice(Number(y) + '年', Number(y) + '年', selected.slice(0,4) === y, () => {
        if (kind === 'year') commit(y);
        else { open.year = Number(y); open.view = 'months'; draw(); }
      });
    }
    panel.append(grid);
    const choices = [...grid.querySelectorAll('button')];
    if (choices.length) {
      const cursor = grid.querySelector('[aria-pressed="true"]') || grid.querySelector('[aria-current="date"]') || choices[0];
      choices.forEach(b=>{ b.tabIndex = b === cursor ? 0 : -1; });
      grid.onkeydown = event => {
        const i = choices.indexOf(event.target);
        if (i < 0) return;
        const columns = view === 'days' ? 7 : 3;
        const moves = {ArrowLeft:i-1,ArrowRight:i+1,ArrowUp:i-columns,ArrowDown:i+columns,Home:0,End:choices.length-1};
        if (!Object.hasOwn(moves,event.key)) return;
        event.preventDefault();
        const next = choices[Math.max(0,Math.min(choices.length-1,moves[event.key]))];
        event.target.tabIndex = -1; next.tabIndex = 0; next.focus();
      };
      if (focusGrid) cursor.focus({preventScroll:true});
    }
    if (kind !== 'year') {
      const footer = doc.createElement('div');
      footer.className = 'qdr-picker-footer';
      footer.append(makeButton('清除', () => commit('')), makeButton(kind === 'month' ? '本月' : '今天',
        () => commit(kind === 'month' ? today().slice(0,7) : today())));
      panel.append(footer);
    }
    place();
  }

  function toggle(input, trigger) {
    if (open?.trigger === trigger) { close(true); return; }
    close();
    if (input.disabled) return;
    const kind = input.tagName === 'SELECT' ? 'year' : input.getAttribute('type') === 'month' ? 'month' : 'day';
    const [year, month] = (input.value || today()).split('-').map(Number);
    const panel = doc.createElement('div');
    panel.className = 'qdr-date-panel';
    panel.dataset.kind = kind;
    panel.id = input.id + '-panel';
    panel.setAttribute('role','dialog');
    panel.setAttribute('aria-label',trigger.getAttribute('aria-label'));
    doc.body.append(panel);
    open = {input, trigger, panel, year, month:month || 1, kind, view:{year:'years',month:'months',day:'days'}[kind]};
    trigger.setAttribute('aria-controls',panel.id);
    trigger.setAttribute('aria-expanded','true');
    draw();
  }

  // The weekly report always covers Monday through Sunday for the chosen day.
  function weekCaption(value) {
    const monday = new Date(value + 'T00:00:00Z');
    monday.setUTCDate(monday.getUTCDate() - (monday.getUTCDay() + 6) % 7);
    const sunday = new Date(monday);
    sunday.setUTCDate(monday.getUTCDate() + 6);
    const short = date => (date.getUTCMonth() + 1) + '月' + date.getUTCDate() + '日';
    if (monday.getUTCMonth() === sunday.getUTCMonth()) {
      return (monday.getUTCMonth() + 1) + '月' + monday.getUTCDate() + '–' + sunday.getUTCDate() + '日';
    }
    return short(monday) + '–' + short(sunday);
  }

  function sync(input) {
    const field = input.closest('.report-date-field');
    if (!field) return;
    let trigger = buttons.get(input);
    if (!trigger) {
      trigger = makeButton('', () => toggle(input,trigger));
      buttons.set(input,trigger);
      trigger.className = 'qdr-date-trigger';
      trigger.setAttribute('aria-haspopup','dialog');
      trigger.setAttribute('aria-expanded','false');
      field.append(trigger);
      field.classList.add('qdr-date-ready');
      if (input.tagName === 'SELECT') {
        input.hidden = true;
        field.querySelector('label').htmlFor = trigger.id = input.id + '-trigger';
      }
      input.addEventListener('keydown', event => {
        if (event.key === 'F4' || (event.altKey && event.key === 'ArrowDown')) {
          event.preventDefault(); toggle(input,trigger);
        }
      });
      input.addEventListener('change', () => sync(input));
    }
    const [y,m,d] = input.value.split('-').map(Number);
    const label = field.querySelector('label').textContent;
    let display = y ? y+'年'+(m ? m+'月' : '')+(d ? d+'日' : '') : '选择'+label;
    if (y && root.__QC_NEXUS?.factory) {
      if (input.id === 'weeklyDate') display = weekCaption(input.value);
      if (input.id === 'dailyDate') display = m+'月'+d+'日';
      if (input.id === 'monthlyMonth') display = m+'月';
    }
    trigger.textContent = input.tagName === 'SELECT' ? (input.selectedOptions[0]?.textContent || display) : display;
    trigger.setAttribute('aria-label', label+'，'+trigger.textContent);
    trigger.disabled = input.disabled;
    if (input.disabled && open?.input === input) close();
  }

  doc.addEventListener('pointerdown', event => {
    if (open && !open.panel.contains(event.target) && !open.trigger.contains(event.target)) close();
  });
  doc.addEventListener('focusin', event => {
    if (open && !open.panel.contains(event.target) && open.trigger !== event.target) close();
  });
  doc.addEventListener('keydown', event => {
    if (!open) return;
    if (event.key === 'Escape') { event.preventDefault(); close(true); }
    if (event.key === 'Tab' && open.panel.contains(event.target)) {
      const stops = [...open.panel.querySelectorAll('button:not(:disabled)')].filter(b=>b.tabIndex >= 0);
      if (event.target === (event.shiftKey ? stops[0] : stops.at(-1))) {
        // Resume the toolbar's tab order when leaving the portaled panel.
        close(true);
      }
    }
  });
  root.addEventListener('resize',place);
  doc.addEventListener('scroll',event=>{if(open && !open.panel.contains(event.target))place();},true);
  root.QcReportDates = {sync, close};
})(window);

/* Direct report views. The template controllers own edits, data and export permissions. */
(function (root) {
  const doc = root.document;
  const catalog = {
    weekly: {detail:'各客户验货明细及汇总', issues:'验货问题与整改跟踪表'},
    monthly: {orders:'订单对账明细', tracking:'问题整改跟踪', quality:'客户质量签核'},
  };
  const remembered = {};
  const templateKey = period => 'qc.' + root.__QC_NEXUS.factory + '.template.' + period;
  for (const period of Object.keys(catalog)) {
    try {
      const key = root.localStorage.getItem(templateKey(period));
      if (Object.hasOwn(catalog[period],key)) remembered[period] = key;
    } catch { /* Selection remains available within this session. */ }
  }
  const id = name => doc.getElementById(name);
  function mountRefresh(period) {
    const page = id('page-' + period);
    const toolbar = page.querySelector('.report-toolbar');
    if (toolbar.querySelector('.report-toolbar-refresh')) return;
    const content = id({daily:'dailyReportBody', weekly:'qwtView', monthly:'qmtView'}[period]);
    const refresh = doc.createElement('button');
    refresh.type = 'button';
    refresh.className = 'qc-refresh-icon report-toolbar-refresh';
    refresh.title = '刷新数据';
    refresh.setAttribute('aria-label', refresh.title);
    toolbar.append(refresh);
    const source = () => content.querySelector('[data-refresh],#qmtRefresh,#qwtRefresh,#qmtLoadRetry,#qwtLoadRetry');
    function sync() {
      refresh.disabled = period === 'daily' ? !!content.querySelector('.qdr-message[role=status]') : !source() || source().disabled;
    }
    refresh.onclick = () => period === 'daily' ? root.QcDailyReport.load() : source()?.click();
    new MutationObserver(sync).observe(content, {childList:true, subtree:true, attributes:true, attributeFilter:['disabled']});
    sync();
  }
  function createTabs(period, panel, choice, controller) {
    const sheet = doc.createElement('div');
    sheet.className = 'template-sheet';
    panel.before(sheet);
    const bar = doc.createElement('div');
    bar.className = 'sheet-tab-bar';
    const nav = doc.createElement('div');
    nav.className = 'sheet-tabs';
    nav.setAttribute('role','tablist');
    nav.setAttribute('aria-label',period === 'weekly' ? '周报模板' : '月报模板');
    bar.append(nav);
    sheet.append(bar,panel);
    panel.setAttribute('role','tabpanel');
    panel.tabIndex = 0;
    for (const [key,label] of Object.entries(catalog[period])) {
      const button = doc.createElement('button');
      button.type = 'button';
      button.textContent = label;
      button.title = Array.from(choice.options).find(option => option.value === key)?.textContent || label;
      button.id = 'template-' + period + '-' + key;
      button.dataset.key = key;
      button.setAttribute('role','tab');
      button.setAttribute('aria-controls',panel.id);
      button.onclick = () => {
        if (choice.value !== key) controller.open(key);
        // open() accepts or rejects the selection synchronously before loading.
        updateTabs(period,nav,panel,choice.value);
      };
      nav.append(button);
    }
    nav.onkeydown = event => {
      const buttons = Array.from(nav.children);
      const index = buttons.indexOf(event.target);
      const next = {ArrowRight:(index+1)%buttons.length, ArrowLeft:(index+buttons.length-1)%buttons.length, Home:0, End:buttons.length-1}[event.key];
      if (index < 0 || next === undefined) return;
      event.preventDefault();
      buttons[next].focus();
      buttons[next].click();
    };
    return nav;
  }
  function updateTabs(period,nav,panel,key) {
    for (const button of nav.children) {
      const active = button.dataset.key === key;
      button.setAttribute('aria-selected',String(active));
      button.tabIndex = active ? 0 : -1;
      if (active) {
        panel.setAttribute('aria-labelledby',button.id);
        if (remembered[period] !== key) {
          remembered[period] = key;
          try { root.localStorage.setItem(templateKey(period),key); } catch {}
        }
      }
    }
  }
  function enter(period) {
    const weekly = period === 'weekly';
    const prefix = weekly ? 'qwt' : 'qmt';
    const controller = weekly ? root.QcWeeklyTemplates : root.QcMonthlyTemplates;
    const input = id(weekly ? 'weeklyDate' : 'monthlyMonth');
    if (!input.value) input.value = weekly ? root.todayStr() : root.todayStr().slice(0,7);
    root.QcReportDates.sync(input);
    id('page-' + period).classList.add('qdr-active');
    mountRefresh(period);
    const panel = id(prefix+'View'), choice = id(prefix+'Choice');
    const nav = panel.parentElement.querySelector('.sheet-tabs') || createTabs(period,panel,choice,controller);
    const key = remembered[period] || (weekly ? 'detail' : 'quality');
    const loading = choice.value ? undefined : controller.open(key);
    updateTabs(period,nav,panel,choice.value);
    return loading;
  }
  root.QcReportSheets = {enter,mountRefresh};
})(window);
