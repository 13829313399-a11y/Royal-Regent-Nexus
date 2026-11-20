'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM} = require('../../node_modules/jsdom');

function workbench() {
  const dom = new JSDOM('<button id="qcInspectionPrint" hidden>打印</button>', {runScripts:'outside-only'});
  const {window} = dom;
  const model = {view:'records', loaded:true, selectedId:'', drafts:new Map()};
  const rows = [
    {id:'first', dateFrom:'2026-11-09', revision:2, customer:'客户 A', productNo:'A001', poNo:'0001'},
    {id:'second', revision:1, customer:'客户 B', productNo:'B001', poNo:'0002'},
  ];
  const calls = [];
  window.__QC_NEXUS = {exportAllowed:true};
  window.QcInspectionSheet = {model, filtered:() => rows};
  window.HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  window.HTMLDialogElement.prototype.close = function () { this.open = false; this.dispatchEvent(new window.Event('close')); };
  window.URL.createObjectURL = () => 'blob:print-preview';
  window.URL.revokeObjectURL = url => calls.push({released:url});
  window.fetch = async (url, options) => {
    calls.push({url, body:JSON.parse(options.body)});
    return {ok:true, json:async () => ({
      template:JSON.parse(options.body).template, count:JSON.parse(options.body).entries.length, pdf:'UERG',
      pages:[{width:842,height:595,image:'MQ=='},{width:842,height:595,image:'Mg=='}],
    })};
  };
  for (const file of ['qc-inspection-audit.js','qc-inspection-print.js']) {
    window.eval(fs.readFileSync(path.join(__dirname,file),'utf8'));
  }
  const clickPrint = () => window.document.getElementById('qcInspectionPrint').click();
  const control = selector => window.document.querySelector(selector);
  return {dom,model,calls,clickPrint,control};
}

test('prints explicitly selected saved workbench rows, updates preview pages and releases PDF', async () => {
  const {dom,calls,clickPrint,control} = workbench();
  try {
    clickPrint();
    assert.equal(control('[data-generate]').disabled,true);
    assert.equal(control('.qip-range-heading, .qip-template'),null);
    control('[data-rows] label:nth-child(2) input').click();
    await control('[data-generate]').onclick();
    assert.deepEqual(calls,[{url:'api/inspection-sheet/print-preview',body:{
      template:'客户验货排期表',entries:[{id:'second',revision:1}],
    }}]);
    assert.equal(control('[data-preview]').hidden,false);
    assert.equal(control('[data-selected]').textContent,'客户 B · PO 0002 · 货号 B001');
    assert.equal(control('[data-page-number]').textContent,'1 / 2');
    control('[data-next]').click();
    assert.equal(control('[data-page-number]').textContent,'2 / 2');
    assert.equal(control('[data-page]').src,'data:image/png;base64,Mg==');
    control('[data-cancel]').click();
    assert.equal(control('dialog'),null);
    assert.equal(calls.at(-1).released,'blob:print-preview');
  } finally { dom.window.close(); }
});

test('preselects the highlighted row and waits for existing workbench saves without flushing them', async () => {
  const {dom,model,calls,clickPrint,control} = workbench();
  try {
    model.selectedId = 'first';
    model.drafts.set('first',{dirty:true,queue:[]});
    clickPrint();
    assert.equal(control('[data-rows] label:first-child input').checked,true);
    await control('[data-generate]').onclick();
    assert.match(control('[data-status]').textContent,/待保存/);
    assert.deepEqual(calls,[]);
  } finally { dom.window.close(); }
});

test('preloads every final PDF page and prints synchronously, including repeat after cancel', async () => {
  const {dom,model,clickPrint,control} = workbench();
  try {
    model.selectedId = 'first'; clickPrint();
    await control('[data-generate]').onclick();
    const frame = control('.qip-print-frame');
    assert.equal(dom.window.document.querySelectorAll('.qip-print-frame').length,1);
    assert.equal(control('[data-print]').disabled,true);
    const images=[...frame.contentDocument.querySelectorAll('img')];
    assert.deepEqual(images.map(image=>image.src),['data:image/png;base64,MQ==','data:image/png;base64,Mg==']);
    images[0].onload();
    assert.equal(control('[data-print]').disabled,true);
    images[1].onload();
    assert.equal(control('[data-print]').disabled,false);
    let printed=0;
    frame.contentWindow.focus=()=>{};
    frame.contentWindow.print=()=>{ printed++; frame.contentWindow.dispatchEvent(new dom.window.Event('afterprint')); };
    control('[data-print]').click(); control('[data-print]').click();
    assert.equal(printed,2);
    assert.equal(control('[data-preview]').hidden,false);
    control('[data-cancel]').click();
    assert.equal(control('.qip-print-frame'),null);
  } finally { dom.window.close(); }
});

test('range selection is explicit, and changing records invalidates print content', async () => {
  const {dom,calls,clickPrint,control} = workbench();
  try {
    clickPrint();
    assert.equal(control('[data-generate]').disabled,true);
    assert.equal(calls.length,0);
    control('[data-all]').click();
    assert.match(control('[data-selection-count]').textContent,/已选 2 \/ 2/);
    await control('[data-generate]').onclick();
    assert.equal(calls[0].body.entries.length,2);
    assert.equal(control('[data-print]').textContent,'打印');
    const {window} = dom;
    let download;
    window.HTMLAnchorElement.prototype.click = function () { download = this.download; };
    window.fetch = async (url, options) => {
      assert.equal(url, 'api/inspection-sheet/schedule-excel');
      assert.deepEqual(JSON.parse(options.body), {entries:calls[0].body.entries});
      return {ok:true,blob:async () => new window.Blob(['xlsx'])};
    };
    await control('[data-excel]').onclick();
    assert.equal(download,'客户验货排期表.xlsx');
    assert.equal(control('[data-preview]').hidden,false);
    control('[data-all]').click();
    assert.equal(control('[data-excel]').disabled,true);
    assert.equal(control('[data-generate]').disabled,true);
    assert.equal(control('[data-preview]').hidden,true);
  } finally { dom.window.close(); }
});

test('cancel aborts generation and a late response cannot reopen the preview', async () => {
  const {dom,model,clickPrint,control} = workbench();
  let complete,signal;
  dom.window.fetch = (_url,options) => { signal=options.signal; return new Promise(resolve => { complete=resolve; }); };
  try {
    model.selectedId='first'; clickPrint();
    const pending=control('[data-generate]').onclick();
    control('[data-cancel]').click();
    assert.equal(signal.aborted,true);
    complete({ok:true,json:async()=>({})}); await pending;
    assert.equal(control('dialog'),null);
    assert.equal(control('.qip-print-frame'),null);
  } finally { dom.window.close(); }
});

test('generation errors remain retryable and duplicate dialogs are prevented', async () => {
  const {dom,model,clickPrint,control} = workbench();
  try {
    model.selectedId='first'; clickPrint(); clickPrint();
    assert.equal(dom.window.document.querySelectorAll('dialog').length,1);
    dom.window.fetch=async()=>({ok:false,json:async()=>({detail:'记录版本已变化'})});
    await control('[data-generate]').onclick();
    assert.match(control('[data-status]').textContent,/记录版本已变化/);
    assert.equal(control('[data-generate]').disabled,false);
    assert.equal(control('[data-print]').disabled,true);
  } finally { dom.window.close(); }
});

test('date filter scopes cards, selection, and preview to the displayed planned date', async () => {
  const {dom,calls,clickPrint,control}=workbench();
  try {
    clickPrint();
    control('[data-all]').click();
    const date=control('[data-date]');
    date.value='2026-11-09'; date.dispatchEvent(new dom.window.Event('change'));
    assert.equal(control('[data-selection-count]').textContent,'已选 1 / 1');
    assert.equal(control('.qip-record-date').textContent,'排期 2026-11-09');
    await control('[data-generate]').onclick();
    assert.deepEqual(calls[0].body.entries,[{id:'first',revision:2}]);
    date.value='undated'; date.dispatchEvent(new dom.window.Event('change'));
    assert.equal(control('[data-preview]').hidden,true);
    assert.equal(control('[data-excel]').disabled,true);
    assert.equal(control('.qip-record-date').textContent,'未排期');
  } finally { dom.window.close(); }
});
