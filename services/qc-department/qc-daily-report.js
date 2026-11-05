/* Huaxing daily report. The actor-scoped gateway owns the data and workbook. */
(function (root) {
  'use strict';
  const doc = root.document;
  const enabled = () => root.__QC_NEXUS?.factory === 'huaxing';
  const exportAllowed = () => root.__QC_NEXUS?.exportAllowed === true;
  const area = () => doc.getElementById('dailyReportBody');
  const dateInput = () => doc.getElementById('dailyDate');
  const pdfButton = () => doc.getElementById('btnExportDaily');
  const esc = value => root._esc(value);
  const display = value => value === '' || value == null ? '—' : esc(value);
  const quantity = value => typeof value === 'number' ? value.toLocaleString('zh-CN', {maximumFractionDigits:4}) : display(value);
  const kind = result => result === 'PASS' ? 'pass' : ['FAIL','REJ'].includes(result) ? 'fail' : 'other';
  const badge = result => '<span class="qdr-result ' + kind(result) + '">' + display(result) + '</span>';
  const path = 'api/daily-report';
  let sequence = 0;
  let snapshot = null;
  let mode = 'compact';

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
      const key = 'qdr-record-' + index;
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
    }).join('');
    return '<div class="qdr-overview"><section class="qdr-panel" aria-label="当日验货概览"><h3>当日验货概览</h3>' +
      '<p class="qdr-score"><strong>' + (report.rate == null ? '—' : report.rate.toFixed(1) + '%') +
      '</strong><span>PASS 率 · ' + report.total + ' 批验货</span></p><div class="qdr-bar" aria-hidden="true">' + segments + '</div>' +
      '<div class="qdr-counts"><span>PASS <b>' + report.passed + '</b></span><span>FAIL <b>' + report.failed +
      '</b></span><span>其他 <b>' + report.other + '</b></span></div></section>' +
      '<section class="qdr-panel" aria-label="待跟进"><div class="qdr-heading"><h3>待跟进</h3><small>' + follow.length +
      ' 项</small></div>' + (follow.length ? '<ul class="qdr-issues">' + followRows + '</ul>' : '<p class="qdr-muted">暂无跟进事项</p>') + '</section></div>';
  }

  function setMode() {
    const host = area();
    host.querySelector('[data-qdr-compact]').hidden = mode !== 'compact';
    host.querySelector('[data-qdr-full]').hidden = mode !== 'full';
    host.querySelectorAll('[data-qdr-view]').forEach(button =>
      button.setAttribute('aria-pressed', String(button.dataset.qdrView === mode)));
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
    area().innerHTML = '<div class="qdr"><header><div><h2>验货日报</h2><p>' + root.getReportCompanyLabel() +
      '</p></div></header>' + overview(report, true) +
      (report.scheduleCount ? '<p class="qdr-muted">' + report.scheduleCount + ' 条记录按排期开始日统计。</p>' : '') +
      '<section class="qdr-panel qdr-detail" aria-label="验货明细"><div class="qdr-heading"><div><h3>验货明细</h3><small>' +
      report.total + ' 条记录</small></div>' + (report.total ? '<div class="qdr-views" role="group" aria-label="明细视图">' +
      '<button type="button" data-qdr-view="compact">精简</button><button type="button" data-qdr-view="full">完整 13 列</button></div>' : '') + '</div>' +
      (report.total ? '<div data-qdr-compact>' + compactTable(report) + '</div><div class="qdr-scroll" data-qdr-full hidden role="region" aria-label="完整 13 列" tabindex="0">' + fullTable(report, true) + '</div>'
        : '<p class="qdr-empty">该日期暂无可列入日报的已审核验货记录</p>') + '</section>' +
      (exportAllowed() ? '<div class="qdr-footer"><button type="button" class="qdr-export" data-qdr-export' +
        (report.total ? '' : ' disabled') + '>导出 Excel</button><span class="qdr-muted" role="status" data-qdr-export-status></span></div>' : '') + '</div>';
    if (!report.total) return;
    setMode();
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
    const button = area().querySelector('[data-qdr-export]');
    if (button) button.onclick = () => download(report, button);
  }

  async function load() {
    const id = ++sequence;
    const input = dateInput();
    input.closest('#page-daily').classList.add('qdr-active');
    const day = input.value;
    snapshot = null;
    pdfButton().disabled = true;
    area().innerHTML = '<p class="qdr-message" role="status">' + (day ? '正在读取已审核验货记录…' : '请选择报告日期') + '</p>';
    if (!day) return;
    try {
      const response = await read(path + '?' + new URLSearchParams({date:day}));
      const report = await response.json();
      if (id !== sequence || input.value !== day) return;
      if (report.date !== day) throw Error('返回的日报日期不一致，请重试');
      paint(report);
      snapshot = report;
      pdfButton().disabled = !exportAllowed() || !report.total;
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
      const params = new URLSearchParams({date:report.date,revision:report.revision});
      const response = await read(path + '/export?' + params);
      const data = await response.blob();
      if (snapshot !== report || dateInput().value !== report.date) return;
      const url = root.URL.createObjectURL(data);
      const link = doc.createElement('a');
      link.href = url;
      link.download = '每日验货情况统计表_' + report.date + '.xlsx';
      doc.body.append(link);
      link.click();
      link.remove();
      root.setTimeout(() => root.URL.revokeObjectURL(url), 30000);
      status.textContent = '已发起下载';
    } catch (error) {
      status.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  }

  function pdfCanvas() {
    const report = snapshot;
    if (!report?.total || report.date !== dateInput().value) throw Error('请先读取当日日报');
    const canvas = doc.createElement('div');
    canvas.id = 'rpt-canvas';
    canvas.className = 'qdr-pdf';
    canvas.innerHTML = '<div class="rpt-header"><div><div class="rpt-co-name">' + root.getReportCompanyLabel() +
      '</div><div class="rpt-doc-type">验货日报</div></div><div class="rpt-doc-no">' + esc(report.date) +
      '</div></div><div class="qdr">' + overview(report) + fullTable(report) + '</div>';
    return canvas;
  }

  root.QcDailyReport = {enabled, load, pdfCanvas};
})(window);
