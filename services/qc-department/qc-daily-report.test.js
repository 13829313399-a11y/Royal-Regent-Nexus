'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM} = require('jsdom');

function page() {
  const dom = new JSDOM(fs.readFileSync(path.join(__dirname,'index.html'),'utf8'), {runScripts:'outside-only'});
  const w = dom.window;
  w.__QC_NEXUS = {factory:'huaxing',exportAllowed:true};
  w.todayStr = () => '2026-11-06';
  w.getReportCompanyLabel = () => '华兴';
  w._esc = value => String(value ?? '').replace(/[&<>"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[ch]));
  const calls = [];
  w.fetch = async url => {
    calls.push(url);
    const q = new URL(url,'http://localhost').searchParams;
    return {ok:true,json:async()=>({
      date:q.get('date'),period:q.get('period'),dateFrom:'2026-11-01',dateTo:'2026-11-30',
      total:1,passed:0,failed:1,other:0,rate:0,revision:'v1',
      headers:Array.from({length:13},(_,i)=>'字段'+i),
      rows:[{values:['客户','001','英国','SKU','积木',20,'','','FAIL','压痕','','',''],improvement:'复验'}],
    })};
  };
  w.eval(fs.readFileSync(path.join(__dirname,'qc-daily-report.js'),'utf8'));
  return {dom,w,d:w.document,calls};
}
test('day week and month reuse the same dashboard with scoped details and period exports', async () => {
  const p = page();
  try {
    for (const kind of ['daily','weekly','monthly']) {
      await p.w.QcPeriodReports[kind].load();
      const body=p.d.getElementById(kind+'ReportBody');
      assert(body.querySelector('.qdr-overview'));
      assert(body.querySelector('.qdr-detail'));
      assert.equal(new URL(p.calls.at(-1),'http://localhost').searchParams.get('period'),kind);
      body.querySelector('.qdr-toggle').click();
      assert.equal(body.querySelector('.qdr-expanded').hidden,false);
      const canvas=p.w.QcPeriodReports[kind].pdfCanvas();
      assert.match(canvas.textContent, /2026-11-01 至 2026-11-30/);
      assert.equal(canvas.querySelectorAll('thead th').length,13);
    }
    assert.equal(p.d.querySelectorAll('[id="qdr-daily-record-0"]').length,1);
    assert.equal(p.d.querySelectorAll('[id="qdr-weekly-record-0"]').length,1);
    assert.equal(new URL(p.calls.at(-1),'http://localhost').searchParams.get('date'),'2026-11-01');
    p.d.getElementById('monthlyMonth').value='';
    await p.w.QcPeriodReports.monthly.load();
    assert.match(p.d.getElementById('monthlyReportBody').textContent,/请选择报告日期/);
    assert.throws(()=>p.w.QcPeriodReports.monthly.pdfCanvas());
  } finally {p.dom.window.close();}
});
test('late period response cannot overwrite the latest selected date', async () => {
  const p=page();
  try {
    const pending=[];
    p.w.fetch=()=>new Promise(resolve=>pending.push(resolve));
    const first=p.w.QcPeriodReports.weekly.load();
    p.d.getElementById('weeklyDate').value='2026-10-01';
    const second=p.w.QcPeriodReports.weekly.load();
    const response=(date)=>({ok:true,json:async()=>({date,period:'weekly',dateFrom:date,dateTo:date,total:0,rows:[],headers:[],passed:0,failed:0,other:0,rate:null})});
    pending[1](response('2026-10-01'));await second;
    pending[0](response('2026-11-06'));await first;
    assert.equal(p.d.querySelector('#page-weekly .qdr-period-range').textContent,'2026-10-01');
    assert.equal(p.d.getElementById('btnExportWeekly').disabled,true);
  } finally {p.dom.window.close();}
});
test('follow-ups preview two items, expand reversibly, reset on reload and export all items', async () => {
  const p=page();
  try {
    const originalFetch=p.w.fetch;
    let count=5;
    p.w.fetch=async url=>{
      const response=await originalFetch(url),report=await response.json();
      report.rows=Array.from({length:count},(_,i)=>({...report.rows[0],values:report.rows[0].values.map((v,j)=>j===9?'问题'+i:v)}));
      report.total=count;
      return {ok:true,json:async()=>report};
    };
    for(const kind of ['daily','weekly','monthly']) {
      const controller=p.w.QcPeriodReports[kind];
      await controller.load();
      const body=p.d.getElementById(kind+'ReportBody');
      const toggle=body.querySelector('.qdr-follow-toggle'),more=body.querySelector('.qdr-issues-more');
      assert.equal(body.querySelectorAll('.qdr-issues-preview li').length,2);
      assert.equal(more.querySelectorAll('li').length,3);
      assert.equal(toggle.getAttribute('aria-controls'),more.id);
      assert(more.hasAttribute('inert'));
      toggle.click();
      assert.equal(toggle.getAttribute('aria-expanded'),'true');
      assert.equal(more.hasAttribute('inert'),false);
      assert.equal(more.getAttribute('aria-hidden'),'false');
      p.w.HTMLElement.prototype.scrollIntoView=()=>{};
      more.querySelector('[data-qdr-follow="2"]').click();
      assert.equal(body.querySelector('#qdr-'+kind+'-record-2').hidden,false);
      toggle.click();
      assert.equal(toggle.getAttribute('aria-expanded'),'false');
      assert(more.hasAttribute('inert'));
      toggle.click();
      await controller.load();
      assert.equal(body.querySelector('.qdr-follow-toggle').getAttribute('aria-expanded'),'false');
      const pdf=controller.pdfCanvas();
      assert.equal(pdf.querySelectorAll('.qdr-issues li').length,5);
      assert.equal(pdf.querySelector('.qdr-follow-toggle'),null);
    }
    count=2;await p.w.QcPeriodReports.daily.load();
    assert.equal(p.d.querySelector('#dailyReportBody .qdr-follow-toggle'),null);
    assert.equal(p.d.querySelectorAll('#dailyReportBody .qdr-issues li').length,2);
  } finally {p.dom.window.close();}
});
