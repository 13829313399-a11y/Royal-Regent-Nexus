const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{JSDOM}=require('jsdom');
const tick=()=>new Promise(r=>setTimeout(r,15));
function page(){
 const dom=new JSDOM('<button id="trigger">图文报表</button><section id="page-weekly"><div class="page-inner"><div id="weekly-main">周报</div></div></section><section id="page-analysis"><div class="page-inner"><div id="year-main">年报</div></div></section>',{url:'http://localhost/api/qc-department/huaxing/u-qa/',runScripts:'outside-only'}),w=dom.window,d=w.document,calls=[];
 w.__QC_NEXUS={factory:'huaxing'};w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};w.HTMLDialogElement.prototype.close=function(){this.open=false;setTimeout(()=>this.dispatchEvent(new w.Event('close')),0);};w.HTMLAnchorElement.prototype.click=function(){calls.push({download:this.download,url:this.href});};
 w.fetch=async(url,init)=>{calls.push({url,init});if(init.method==='POST')return{ok:true,json:async()=>({url:'api/monthly-templates/excel/token.xlsx',filename:'验收.xlsx',fallbackCount:0})};const customer=new URL(url,w.location).searchParams.get('customer');return{ok:true,json:async()=>({title:'验货问题图文记录表',dateFrom:'2026-11-08',dateTo:'2026-11-14',sourceRevision:'r1',canExport:true,customers:[{key:'stable-a',label:'同名 · A'},{key:'stable-b',label:'同名 · B'}],total:1,headers:Array(12).fill('字段'),tables:{issues:[{id:customer||'all',values:Array(12).fill(''),photos:[]}]}})};};
 w.eval(fs.readFileSync(path.join(__dirname,'qc-issue-reports.js'),'utf8'));return{dom,w,d,calls};
}
test('inline workbook exports the selected stable customer as preview without quality options',async()=>{const p=page();try{
 const host=p.d.createElement('section');p.d.querySelector('#weekly-main').append(host);
 await p.w.QcIssueReports.open('weekly','2026-11-09','',{host});const el=p.d.querySelector('.qir-inline'),q=s=>el.querySelector(s);
 assert.equal(p.d.querySelector('#weekly-main').hidden,false);assert.equal(q('[data-quality]'),null);assert.equal(q('[data-close]'),null);assert.equal(p.d.querySelector('dialog'),null);
 q('[data-customer]').value='stable-b';q('[data-customer]').dispatchEvent(new p.w.Event('change'));await tick();assert.match(p.calls.at(-1).url,/customer=stable-b/);
 q('[data-export]').click();await tick();const post=p.calls.find(x=>x.init?.method==='POST'),body=JSON.parse(post.init.body);assert.deepEqual(body,{period:'weekly',date:'2026-11-09',customer:'stable-b',sourceRevision:'r1',photoQuality:'preview',allowPreviewFallback:false});
 assert.equal(p.d.querySelectorAll('dialog').length,0);assert.ok(p.calls.some(x=>x.download==='验收.xlsx'));
 }finally{p.dom.window.close();}});
test('returning from page reports restores parents and cancels only its own request',async()=>{const p=page();try{
 await p.w.QcIssueReports.open('weekly','2026-11-09');let signal;
 p.w.fetch=async(_,init)=>{signal=init.signal;await tick();return{ok:true,json:async()=>({title:'新报表',dateFrom:'2026-01-01',dateTo:'2026-12-31',sourceRevision:'new',canExport:true,customers:[],total:0,headers:[],tables:{issues:[]}})};};
 await p.w.QcIssueReports.open('yearly','2026-01-01');assert.equal(signal.aborted,false);assert.equal(p.d.querySelectorAll('dialog').length,0);assert.match(p.d.querySelector('.qir-page').textContent,/新报表/);assert.equal(p.d.querySelector('#weekly-main').hidden,false);assert.equal(p.d.querySelector('#year-main').hidden,true);
 p.d.querySelector('[data-close]').click();await tick();assert.equal(signal.aborted,true);assert.equal(p.d.querySelector('.qir-page'),null);assert.equal(p.d.querySelector('#year-main').hidden,false);
 }finally{p.dom.window.close();}});
test('page view preserves parent controls, hidden state, scroll and keyboard return target',async()=>{const p=page();try{
 const parent=p.d.querySelector('#page-weekly'),main=p.d.querySelector('#weekly-main'),trigger=p.d.querySelector('#trigger');
 main.innerHTML='<input value="2026-11-09"><div hidden>原本隐藏</div>';parent.scrollTop=240;trigger.focus();
 await p.w.QcIssueReports.open('weekly','2026-11-09','stable-b');await tick();
 assert.match(p.calls.at(-1).url,/period=weekly&date=2026-11-09&customer=stable-b/);
 assert.equal(p.d.querySelector('dialog'),null);assert.equal(main.hidden,true);assert.equal(parent.scrollTop,0);
 p.w.QcIssueReports.pageChanged();assert.equal(main.hidden,false);assert.equal(main.querySelector('input').value,'2026-11-09');assert.equal(main.querySelector('div').hidden,true);assert.equal(parent.scrollTop,240);assert.equal(p.d.activeElement,trigger);
 }finally{p.dom.window.close();}});
test('page empty and failure states disable export and retry without opening a modal',async()=>{const p=page();try{
 p.w.fetch=async()=>{throw Error('隔离读取失败');};await p.w.QcIssueReports.open('yearly','2025-01-01');
 assert.match(p.d.querySelector('[data-status]').textContent,/隔离读取失败/);assert.equal(p.d.querySelector('[data-export]').disabled,true);
 p.w.fetch=async()=>({ok:true,json:async()=>({title:'年度验货问题图文记录表',dateFrom:'2025-01-01',dateTo:'2025-12-31',canExport:true,total:0,headers:[],tables:{issues:[]}})});
 p.d.querySelector('[data-refresh]').click();await tick();assert.match(p.d.querySelector('[data-status]').textContent,/没有验货问题记录/);assert.equal(p.d.querySelector('[data-export]').disabled,true);assert.equal(p.d.querySelector('dialog'),null);
 }finally{p.dom.window.close();}});
