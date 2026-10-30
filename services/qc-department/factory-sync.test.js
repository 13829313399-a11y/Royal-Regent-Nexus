'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {JSDOM}=require(path.resolve(__dirname,'../../node_modules/jsdom'));
const script=fs.readFileSync(path.join(__dirname,'nexus-integration.js'),'utf8');
function page(){
 const dom=new JSDOM('<div id="userBadge"><span class="user-badge-company">河源华兴</span></div><div id="page-sales-schedule"></div>',{runScripts:'outside-only',url:'http://localhost/api/qc-department/huaxing/u-test/'});
 const w=dom.window;w.__QC_NEXUS={factory:'huaxing',company:'hy-huaxing'};w.eval(script);
 return {dom,w};
}
test('QC selector delegates to Nexus without mutating local factory or issuing data requests',async()=>{
 const {dom,w}=page();const requested=[];w.showPage=name=>requested.push('page:'+name);
 w.fetch=()=>{throw Error('a selector must not fetch another factory directly');};
 w.__QC_SET_FACTORY_BRIDGE({factory:'huaxing',options:[{id:'group',label:'集团'},{id:'huaxing',label:'华兴'},{id:'huakang-a',label:'华康A'}],page:'sales-schedule',select:async id=>requested.push(id)});
 const select=w.document.getElementById('qcFactorySelect');
 assert.equal(select.value,'huaxing');assert.equal(select.getAttribute('aria-label'),'QC 厂区');
 select.value='huakang-a';await select.onchange();
 assert.equal(w.__QC_NEXUS.factory,'huaxing');assert.equal(w.__QC_NEXUS.company,'hy-huaxing');
 assert.equal(select.value,'huaxing');assert.deepEqual(requested,['page:sales-schedule','huakang-a']);
 dom.window.close();
});
test('wrong factory bridge is ignored and options are rendered as text',()=>{
 const {dom,w}=page();w.__QC_SET_FACTORY_BRIDGE({factory:'huakang-a',options:[]});
 assert.equal(w.document.getElementById('qcFactorySelect'),null);
 w.__QC_SET_FACTORY_BRIDGE({factory:'huaxing',options:[{id:'huaxing',label:'<script>bad</script>'}],select:async()=>{}});
 assert.equal(w.document.querySelector('option').textContent,'<script>bad</script>');assert.equal(w.document.querySelector('script'),null);dom.window.close();
});
test('unsaved content prompts without clearing drafts; busy uploads and queued writes cannot be abandoned',()=>{
 const {dom,w}=page();let dirty=true,busy=false,confirms=0,alerts=0;
 w.QcWorkflow={navigationState:()=>({dirty,busy})};w.confirm=()=>{confirms++;return false;};w.alert=()=>alerts++;
 assert.equal(w.__QC_CONFIRM_FACTORY_LEAVE(),false);assert.equal(dirty,true);assert.equal(confirms,1);
 w.confirm=()=>true;assert.equal(w.__QC_CONFIRM_FACTORY_LEAVE(),true);assert.equal(dirty,true);
 busy=true;assert.equal(w.__QC_CONFIRM_FACTORY_LEAVE(),false);assert.equal(alerts,1);
 busy=false;dirty=false;w.__QC_PENDING_WRITES=1;assert.equal(w.__QC_CONFIRM_FACTORY_LEAVE(),false);
 w.__QC_PENDING_WRITES=0;w.QcSchedule={navigationState:()=>({dirty:true,busy:false})};w.confirm=()=>false;
 assert.equal(w.__QC_CONFIRM_FACTORY_LEAVE(),false);w.QcSchedule={navigationState:()=>({dirty:false,busy:false})};
 assert.equal(w.__QC_CONFIRM_FACTORY_LEAVE(),true);dom.window.close();
});

test('factory page survives app initialization RAF after the iframe load bridge',()=>{
 const {dom,w}=page(); const frames=[],pages=[];
 w.document.body.insertAdjacentHTML('beforeend','<div id="loginScreen"></div><div id="appWrapper"></div>');
 w._initSidebar=()=>{};w._renderUserBadge=()=>{};w.applyPermissions=()=>{};
 w.requestAnimationFrame=cb=>frames.push(cb);w.showPage=name=>pages.push(name);
 const app=fs.readFileSync(path.join(__dirname,'app.js'),'utf8');
 const start=app.indexOf('function _showApp()'); const end=app.indexOf('\n}',start)+2;
 w.eval(app.slice(start,end));w._showApp();
 frames.shift()();
 w.__QC_SET_FACTORY_BRIDGE({factory:'huaxing',options:[],page:'sales-schedule',select:async()=>{}});
 frames.shift()();assert.deepEqual(pages,['sales-schedule','sales-schedule']);
 const second=page(),later=second.w,after=[];later.showPage=name=>after.push(name);
 assert.equal(later.__QC_INITIAL_PAGE(),'dashboard');
 later.showPage(later.__QC_INITIAL_PAGE());
 later.__QC_SET_FACTORY_BRIDGE({factory:'huaxing',options:[],page:'sales-schedule',select:async()=>{}});
 assert.deepEqual(after,['dashboard','sales-schedule']);second.dom.window.close();
 dom.window.close();
});
