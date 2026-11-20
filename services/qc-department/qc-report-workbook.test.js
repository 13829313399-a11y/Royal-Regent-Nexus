const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

test('monthly preview opens the filtered workbook, confirms edits before switching, and handles empty sheets', async () => {
  const dom = new JSDOM('<div id="page-monthly"><input id="monthlyMonth" value="2026-11"><select id="qmtCustomer"><option value="factory-customer">客户</option></select><section class="template-sheet"><div class="sheet-tab-bar"></div><div id="summary"></div></section></div>', { runScripts:'outside-only', url:'http://localhost/qc/' });
  const w = dom.window, doc = w.document, calls = [];
  w.__QC_NEXUS = { factory:'huadeng', factoryLabel:'华登', exportAllowed:false };
  w.HTMLDialogElement.prototype.showModal = function(){this.open = true;};
  w.HTMLElement.prototype.scrollTo = () => {};
  w.fetch = async (url, options) => {
    const q = new URL(url, 'http://localhost').searchParams;
    const body = options?.body && JSON.parse(options.body);
    calls.push({url, body});
    const cell = {customerKey:'factory-customer', field:'overviewRemark', value:'', version:2};
    const sheet = {name:'客户签核',html:'<table><tbody><tr><td data-addr="A1"></td></tr></tbody></table>'};
    let result = {sheets:[sheet],cells:{'0:A1':cell},versions:{'factory-customer':{overviewRemark:2}},sourceRevision:'r1'};
    if (body) result = {...body,version:3};
    if (q.get('kind') === 'tracking') result = {sheets:[],cells:{}};
    return {ok:true,json:async()=>result};
  };
  w.eval(fs.readFileSync(path.join(__dirname,'qc-report-workbook.js'),'utf8'));
  try {
    w.QcReportWorkbook.mount('monthly','quality',doc.getElementById('summary'),{date:'2026-11-01',tables:{quality:[]},overview:{months:[{month:1,rate:0}]}},()=>{});
    assert.match(doc.querySelector('.rate-chart').textContent,/0.0%/);
    doc.querySelector('.wb-open').click();
    await new Promise(setImmediate);
    const grid = doc.getElementById('wb-grid').shadowRoot;
    grid.querySelector('td').click();
    const input = grid.querySelector('textarea');
    input.value = '已核对';
    input.dispatchEvent(new w.Event('input'));
    doc.querySelector('#wb-templates [data-kind=tracking]').click();
    await new Promise(setImmediate);
    const saved = calls.find(x=>x.body)?.body;
    assert.equal(saved.value,'已核对');
    assert.equal(saved.baseVersion,2);
    assert.equal(saved.template,'overview');
    assert.equal(saved.customer,'factory-customer');
    assert.match(grid.textContent,/此期间没有记录/);
    assert.equal(doc.getElementById('wb-export').hidden,true);
    assert.equal(doc.querySelector('#wb-templates [data-kind=tracking]').getAttribute('aria-pressed'),'true');
  } finally {w.close();}
});
