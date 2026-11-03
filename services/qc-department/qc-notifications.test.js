'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {JSDOM}=require('jsdom');
function clockPage(reduced=false){
 const dom=new JSDOM('<body><button id="outside">Outside</button></body>',{runScripts:'outside-only'}),w=dom.window;
 let now=0,id=0;const timers=new Map();w.setTimeout=(fn,ms)=>{timers.set(++id,{fn,at:now+ms});return id;};w.clearTimeout=id=>timers.delete(id);
 Object.defineProperty(w.performance,'now',{value:()=>now});w.matchMedia=()=>({matches:reduced});w.eval(fs.readFileSync(path.join(__dirname,'qc-inspection-audit.js'),'utf8'));
 const advance=ms=>{const end=now+ms;while(true){const next=[...timers].filter(([,t])=>t.at<=end).sort((a,b)=>a[1].at-b[1].at)[0];if(!next)break;timers.delete(next[0]);now=next[1].at;next[1].fn();}now=end;};
 const make=()=>{const panel=w.document.createElement('section');panel.innerHTML='<button>查看</button>';w.document.body.append(panel);return{panel,life:w.QcInspectionAudit.lifecycle(panel)};};
 const event=(panel,type)=>panel.dispatchEvent(new w.Event(type));
 return{w,dom,advance,make,event,timers};
}
test('complete readable hold, gradual exit, and no old timers after replacement',()=>{
 const p=clockPage();try{
  const a=p.make();assert.equal(a.panel.dataset.noticeState,'entering');p.advance(180);assert.equal(a.panel.dataset.noticeState,'visible');
  p.advance(2999);assert.equal(a.panel.dataset.noticeState,'visible');p.advance(1);assert.equal(a.panel.dataset.noticeState,'fading');
  p.advance(1999);assert.ok(a.panel.isConnected);p.advance(1);assert.ok(!a.panel.isConnected);
  const old=p.make();p.advance(1000);old.life.destroy();const newer=p.make();p.advance(1730);assert.ok(newer.panel.isConnected);assert.equal(newer.panel.dataset.noticeState,'visible');
  p.w.QcInspectionAudit.dismissNotices();assert.equal(p.timers.size,0);p.advance(9000);assert.ok(!newer.panel.isConnected);
 }finally{p.dom.window.close();}
});
test('pause resumes remaining hold and fade, including focus and repeated hover',()=>{
 const p=clockPage();try{const n=p.make();p.advance(1180);p.event(n.panel,'pointerenter');p.advance(9000);p.event(n.panel,'pointerleave');p.advance(1999);assert.equal(n.panel.dataset.noticeState,'visible');p.advance(1);assert.equal(n.panel.dataset.noticeState,'fading');
 p.advance(700);p.event(n.panel,'pointerenter');assert.equal(n.panel.dataset.noticeState,'visible');n.panel.querySelector('button').focus();p.event(n.panel,'pointerleave');p.advance(9000);assert.ok(n.panel.isConnected);p.w.document.getElementById('outside').focus();assert.equal(n.panel.dataset.noticeState,'fading');p.advance(1299);assert.ok(n.panel.isConnected);p.advance(1);assert.ok(!n.panel.isConnected);
 }finally{p.dom.window.close();}
});
test('manual close, multiple notices, reduced motion and pagehide dispose timers',()=>{
 const p=clockPage(true);try{const a=p.make();p.advance(1000);const b=p.make();p.advance(0);p.event(a.panel,'pointerenter');p.advance(3059);assert.ok(a.panel.isConnected&&b.panel.isConnected);p.advance(1);assert.ok(!b.panel.isConnected);a.life.close();p.event(a.panel,'pointerenter');p.advance(60);assert.ok(!a.panel.isConnected);p.make();p.w.dispatchEvent(new p.w.Event('pagehide'));assert.equal(p.timers.size,0);}finally{p.dom.window.close();}
});
test('audit retains event identity and actual diffs in separate collapsed accessible details',async()=>{
 const p=clockPage();try{p.w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};p.w.HTMLDialogElement.prototype.close=function(){this.dispatchEvent(new p.w.Event('close'));};
 p.w.fetch=async()=>({ok:true,json:async()=>({items:[{id:12,action:'save',actor:{name:'后台用户'},at:'2026-11-02T17:01:00Z',location:'审核中心 · 待审核',changes:{responsible:{before:'甲',after:'乙'}}},{id:11,action:'revoke',actor:{name:'复核人'},at:'2026-11-02T16:59:00Z',location:'审核中心 · 已审核',changes:{reason:'检查 <标签>',reviewState:{before:'approved',after:'pending'}}}]})});
 await p.w.QcInspectionAudit.show('a');const items=[...p.w.document.querySelectorAll('.qia-event')];assert.equal(items.length,2);assert.ok(items.every(el=>!el.open));assert.equal(items[0].dataset.eventId,'12');assert.match(items[0].querySelector('summary').textContent,/2026\/11\/03 01:01:00.*审核中心/);assert.match(items[0].textContent,/责任人.*甲 → 乙/);assert.doesNotMatch(items[0].textContent,/验货结果/);items[0].querySelector('summary').click();assert.ok(items[0].open);items[0].querySelector('summary').click();assert.ok(!items[0].open);p.w.document.querySelector('[data-close]').click();await p.w.QcInspectionAudit.show('b');assert.ok([...p.w.document.querySelectorAll('.qia-event')].every(el=>!el.open));
 }finally{p.dom.window.close();}
});
