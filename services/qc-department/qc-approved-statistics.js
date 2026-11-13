/* Approved-summary report: live read-only source, no embedded demonstration data. */
(function (root) {
  'use strict';
  const state = {sequence:0, controller:null, data:null, filters:{year:'',month:'',day:'',customer:'',result:'FAIL',page:'1'}};
  const el = name => root.document.getElementById('qstats-' + name);
  const active = () => Boolean(root.__QC_NEXUS && root.document.getElementById('page-analysis')?.classList.contains('active'));
  const percent = n => n == null ? '—' : Number(n).toFixed(1) + '%';
  const factoryName = () => root.document.querySelector('#qcFactorySelect option:checked')?.textContent || ({huaxing:'华兴',huadeng:'华登'})[root.__QC_NEXUS?.factory] || '当前厂区';
  function rateBand(rate) {
    if (rate == null) return null;
    if (rate >= 90) return {key:'green',label:'绿色 · ≥90%'};
    if (rate >= 80) return {key:'yellow-light',label:'浅黄 · 80%–<90%'};
    if (rate >= 70) return {key:'yellow-deep',label:'深黄 · 70%–<80%'};
    if (rate >= 60) return {key:'red-light',label:'淡红 · 60%–<70%'};
    return {key:'red',label:'红色 · <60%'};
  }
  function installSidebar() {
    if (!root.__QC_NEXUS) return;
    root.document.body.classList.add('qstats-shell');
  }
  function pageChanged(page) {
    root.document.body.classList.toggle('qc-approved-analysis',Boolean(root.__QC_NEXUS && page==='analysis'));
    if (page !== 'analysis') {state.sequence++; state.controller?.abort();}
  }
  function shell() {
    if (el('root')) return;
    const page = root.document.getElementById('page-analysis');
    page.querySelector('.page-inner').innerHTML = "<div id=\"qstats-root\" aria-label=\"验货年报\"><div class=\"qc-content\">\n        <div class=\"qc-heading\"><div><h1>验货年报</h1><div class=\"qc-subtitle\">验货统计与结果明细</div></div><span class=\"qc-preview\">验货汇总</span><button type=\"button\" id=\"qstats-refresh\" class=\"qc-reset\">刷新数据</button></div>\n        <section class=\"qc-filter\" aria-label=\"验货数据筛选\">\n          <div class=\"qc-filter-fields\">\n            <label>年份<select id=\"qstats-year\" class=\"\" aria-label=\"年份\"></select></label>\n            <label>月份<select id=\"qstats-month\" class=\"\" aria-label=\"月份\"></select></label>\n            <label>日期<select id=\"qstats-day\" class=\"\" aria-label=\"日期\"></select></label>\n            <label class=\"qc-client-field\">客户<select id=\"qstats-client\" class=\"\" aria-label=\"客户\"></select></label>\n            <button type=\"button\" id=\"qstats-reset\" class=\"qc-reset \">重置</button>\n          </div>\n        <p id=\"qstats-message\" class=\"qstats-status\" role=\"status\" aria-live=\"polite\"></p>\n          <div class=\"report-type-slot\" data-report-type-slot></div></section>\n        <section class=\"qc-metrics\" aria-label=\"当前筛选范围汇总\">\n          <div class=\"qc-metric\"><div class=\"qc-metric-label\">验货总数</div><div class=\"qc-metric-value\"><span id=\"qstats-total\">—</span><span class=\"qc-unit\">条</span></div></div>\n          <div class=\"qc-metric\"><div class=\"qc-metric-label\">合格率</div><div class=\"qc-metric-value\" id=\"qstats-rate\">—</div></div>\n          <div class=\"qc-metric\"><div class=\"qc-metric-label\">PASS / FAIL</div><div class=\"qc-metric-value\" id=\"qstats-decided\">—</div></div>\n          <div class=\"qc-metric\"><div class=\"qc-metric-label\">PENDING / LG</div><div class=\"qc-metric-value\" id=\"qstats-other\">—</div></div>\n        </section>\n        <section class=\"qc-report\" aria-label=\"年度验货统计表\">\n          <div class=\"qc-report-title\"><h2 id=\"qstats-report-title\">年度验货统计表</h2><span class=\"qc-caption\">统计日期 · 点击月份查看</span></div>\n          <div class=\"qc-report-grid\">\n            <div class=\"qc-table-panel qc-scroll\"><table class=\"qc-month-table\" aria-label=\"月度验货统计\"><thead><tr><th>月份</th><th>总数</th><th>PASS</th><th>FAIL</th><th>PENDING</th><th>LG</th><th>合格率</th></tr></thead><tbody id=\"qstats-month-rows\"></tbody><tfoot id=\"qstats-month-total\"></tfoot></table></div>\n            <div class=\"qc-chart-panel\">\n              <div class=\"qc-chart-title\">1—12月合格率统计对比图</div><div class=\"qc-legend\"><span id=\"qstats-chart-year\"></span><span>· 合格率（%）</span></div>\n              <div class=\"qc-color-legend\" aria-label=\"合格率自动配色规则\"><span><i class=\"qc-swatch\" aria-hidden=\"true\"></i>≥90%</span><span><i class=\"qc-swatch\" style=\"background:var(--qc-rate-yellow-light)\" aria-hidden=\"true\"></i>80%–&lt;90%</span><span><i class=\"qc-swatch\" style=\"background:var(--qc-rate-yellow-deep)\" aria-hidden=\"true\"></i>70%–&lt;80%</span><span><i class=\"qc-swatch\" style=\"background:var(--qc-rate-red-light)\" aria-hidden=\"true\"></i>60%–&lt;70%</span><span><i class=\"qc-swatch\" style=\"background:var(--qc-rate-red)\" aria-hidden=\"true\"></i>&lt;60%</span></div>\n              <div class=\"qc-chart\" role=\"group\" aria-label=\"月度合格率柱状图，点击柱子选择月份\">\n                <div class=\"qc-chart-lines\" aria-hidden=\"true\"><div class=\"qc-gridline\"><span>100%</span></div><div class=\"qc-gridline\"><span>80%</span></div><div class=\"qc-gridline\"><span>60%</span></div><div class=\"qc-gridline\"><span>40%</span></div><div class=\"qc-gridline\"><span>20%</span></div><div class=\"qc-gridline\"><span>0%</span></div></div>\n                <div class=\"qc-bars\" id=\"qstats-bars\"></div>\n              </div>\n              <div class=\"qc-chart-detail\" id=\"qstats-chart-detail\">无已判定记录的月份留空</div>\n            </div>\n          </div>\n          <div class=\"qc-footnote\">合格率 = PASS ÷（PASS + FAIL）；PENDING、LG 计入验货总数。</div>\n        </section>\n        <section class=\"qc-detail\" aria-label=\"验货结果明细\">\n          <div class=\"qc-detail-head\"><h2 id=\"qstats-detail-title\">不合格验货明细</h2><div class=\"qc-tabs\" aria-label=\"明细结果筛选\"><button type=\"button\" class=\"qc-tab \" data-result=\"ALL\" aria-pressed=\"false\">全部</button><button type=\"button\" class=\"qc-tab \" data-result=\"FAIL\" aria-pressed=\"true\">FAIL</button><button type=\"button\" class=\"qc-tab \" data-result=\"PENDING\" aria-pressed=\"false\">PENDING</button><button type=\"button\" class=\"qc-tab \" data-result=\"LG\" aria-pressed=\"false\">LG</button><button type=\"button\" class=\"qc-tab\" data-result=\"OTHER\" aria-pressed=\"false\" hidden=\"\">其他</button></div></div>\n          <div class=\"qc-scroll\"><table class=\"qc-detail-table\" aria-label=\"当前筛选的验货明细\"><thead><tr><th>统计日期</th><th>客户</th><th>产品 PO</th><th>产品名称</th><th>验货结果</th><th>不良原因 / 备注</th></tr></thead><tbody id=\"qstats-detail-rows\"></tbody></table></div>\n          <div class=\"qc-pagination\"><span id=\"qstats-detail-count\" aria-live=\"polite\"></span><div class=\"qc-page-actions\"><button type=\"button\" id=\"qstats-prev\" class=\"qc-page-btn \" aria-label=\"上一页\">上一页</button><span id=\"qstats-page\"></span><button type=\"button\" id=\"qstats-next\" class=\"qc-page-btn \" aria-label=\"下一页\">下一页</button></div></div>\n        </section>\n        \n      </div></div>";
    root.mountReportTypeSelect?.(page, 'analysis');
    for (const key of ['year','month','day','customer']) {
      const control = el(key==='customer'?'client':key);
      control.onchange = () => {
        state.filters[key]=control.value; state.filters.page='1';
        if (key==='year') {state.filters.month='';state.filters.day='';}
        if (key==='month') state.filters.day='';
        void load();
      };
    }
    el('reset').onclick=()=>{Object.assign(state.filters,{year:'',month:'',day:'',customer:'',result:'FAIL',page:'1'});void load();};
    el('refresh').onclick=()=>void load();
    if(root.__QC_NEXUS?.factory==='huaxing'){
      const button=root.document.createElement('button');button.className='qc-reset';button.textContent='年度验货问题图文记录表';button.id='qstats-issues';
      const footer=root.document.createElement('div');footer.className='qir-entry-footer';footer.append(button);el('root').querySelector('.qc-content').append(footer);button.onclick=()=>{const year=el('year').value;if(!year)return root.showToast?.('请先选择年份','error');root.QcIssueReports?.open('yearly',year+'-01-01',el('client').value);};
    }
    el('root').querySelectorAll('[data-result]').forEach(b=>b.onclick=()=>{state.filters.result=b.dataset.result;state.filters.page='1';void load();});
    el('prev').onclick=()=>{state.filters.page=String(state.data.details.page-1);void load();};
    el('next').onclick=()=>{state.filters.page=String(state.data.details.page+1);void load();};
    for (let m=1;m<=12;m++) {
      const slot=root.document.createElement('div');slot.className='qc-bar-slot';
      slot.innerHTML='<button type="button" class="qc-bar-hit"><span class="qc-bar-fill"><span class="qc-bar-label"></span></span></button><span class="qc-axis-month">'+m+'月</span>';
      slot.querySelector('button').onclick=()=>chooseMonth(String(m));el('bars').append(slot);
    }
  }
  function chooseMonth(month) {
    state.filters.month=state.filters.month===month?'':month;state.filters.day='';state.filters.page='1';void load();
  }
  function message(text,error=false) {el('message').textContent=text;el('message').classList.toggle('error',error);}
  function options(node,values,all,current,suffix='') {
    node.replaceChildren();
    if (all) {const option=root.document.createElement('option');option.value='';option.textContent=all;node.append(option);}
    values.forEach(v=>{const option=root.document.createElement('option');option.value=typeof v==='string'?v:v.key;option.textContent=typeof v==='string'?v+suffix:v.label;node.append(option);});
    node.value=current;
  }
  function clearData(text) {
    state.data=null;
    ['total','rate','decided','other'].forEach(n=>el(n).textContent='—');
    for (const name of ['month-rows','month-total','detail-rows']) el(name).replaceChildren();
    el('detail-count').textContent='';el('page').textContent='';
    el('root').querySelectorAll('.qc-bar-fill').forEach(fill=>{fill.style.height='0%';fill.style.backgroundColor='transparent';fill.dataset.band='empty';fill.querySelector('.qc-bar-label').textContent='';});
    el('root').querySelectorAll('button:not([data-report-page]),.qc-filter-fields select').forEach(c=>c.disabled=true);
    el('refresh').disabled=false;
    el('chart-detail').textContent=text;
  }
  function cell(row,text,className='') {
    const c=root.document.createElement('td');c.textContent=text;c.className=className;row.append(c);return c;
  }
  function redraw() {
    if (!active() || !state.data) return;
    const data=state.data, f=data.filters, t=data.totals;
    el('root').querySelectorAll('button:not([data-report-page]),.qc-filter-fields select').forEach(c=>c.disabled=false);
    options(el('year'),data.options.years,data.options.years.length?'':'暂无年份',f.year,'年');el('year').disabled=!data.options.years.length;
    options(el('month'),data.options.months,'全年',f.month,'月');el('month').disabled=!data.options.months.length;
    options(el('day'),data.options.days,f.month?'全部日期':'先选择月份',f.day,'日');el('day').disabled=!f.month||!data.options.days.length;
    options(el('client'),data.options.customers,'全部客户',f.customer);el('client').disabled=!data.options.customers.length;
    el('root').querySelector('.qc-subtitle').textContent=factoryName()+' · 验货统计与结果明细';
    el('report-title').textContent=factoryName()+' '+(f.year?f.year+' 年':'')+'验货统计表';
    el('chart-year').textContent=f.year?f.year+'年':'暂无年份';
    el('total').textContent=t.total;el('rate').textContent=percent(t.passRate);el('decided').textContent=t.PASS+' / '+t.FAIL;el('other').textContent=t.PENDING+' / '+t.LG;
    el('month-rows').replaceChildren();
    const monthMap=new Map(data.months.map(m=>[String(Number(m.month.slice(5,7))),m]));
    const allOther=Object.values(t.other).reduce((a,b)=>a+b,0);
    for(let m=1;m<=12;m++) {
      const month=String(m),v=monthMap.get(month),available=data.options.months.includes(month);
      const row=root.document.createElement('tr');if(f.month===month)row.className='selected';
      const td=cell(row,''),button=root.document.createElement('button');button.type='button';button.className='qc-month-link';button.textContent=m+'月';button.disabled=!available;button.setAttribute('aria-label','筛选'+f.year+'年'+m+'月');button.onclick=()=>chooseMonth(month);td.append(button);
      for(const key of ['total','PASS','FAIL','PENDING','LG','passRate']) cell(row,v?(key==='passRate'?percent(v[key]):v[key]):'—',v?'':'qc-empty');
      if(v && Object.values(v.other).some(Boolean)) row.title='其他结果：'+Object.entries(v.other).map(([k,n])=>k+' '+n).join('，');
      el('month-rows').append(row);
      const slot=el('bars').children[m-1],hit=slot.querySelector('button'),fill=slot.querySelector('.qc-bar-fill'),rate=v?.passRate??null,band=rateBand(rate);
      hit.disabled=!available;hit.setAttribute('aria-pressed',String(f.month===month));hit.setAttribute('aria-label',m+'月：'+(band?percent(rate)+'，'+band.label:'暂无已判定记录')+'；点击筛选');
      fill.style.height=rate==null?'0%':rate+'%';fill.style.backgroundColor=band?'var(--qc-rate-'+band.key+')':'transparent';fill.dataset.band=band?.key||'empty';
      // Use one decimal: rounded integer labels must not make 89.6% appear green-eligible.
      fill.querySelector('.qc-bar-label').textContent=rate==null?'':percent(rate);
      hit.onmouseenter=hit.onfocus=()=>el('chart-detail').textContent=(f.year||'')+'年'+m+'月 · 验货 '+(v?.total||0)+' 条 · 合格率 '+percent(rate)+(band?' · '+band.label:'');
      hit.onmouseleave=hit.onblur=()=>el('chart-detail').textContent='无已判定记录的月份留空';
    }
    el('chart-detail').textContent='无已判定记录的月份留空';
    const totalRow=root.document.createElement('tr');cell(totalRow,'合计');for(const k of ['total','PASS','FAIL','PENDING','LG','passRate'])cell(totalRow,k==='passRate'?percent(t[k]):t[k]);el('month-total').replaceChildren(totalRow);
    const foot=el('root').querySelector('.qc-footnote');foot.textContent='合格率 = PASS ÷（PASS + FAIL）；PENDING、LG 计入验货总数。'+(allOther?'其他结果 '+allOther+' 条也计入总数：'+Object.entries(t.other).map(([k,n])=>k+' '+n).join('、')+'。':'');
    el('root').querySelectorAll('[data-result]').forEach(b=>{b.setAttribute('aria-pressed',String(b.dataset.result===f.result));if(b.dataset.result==='OTHER')b.hidden=!allOther&&f.result!=='OTHER';});
    el('detail-title').textContent=({ALL:'全部验货明细',PASS:'合格验货明细',FAIL:'不合格验货明细',PENDING:'待定验货明细',LG:'LG 验货明细',OTHER:'其他结果验货明细'})[f.result];
    el('detail-rows').replaceChildren();
    for(const item of data.details.items) {
      const row=root.document.createElement('tr');
      for(const k of ['date','customer','poNo','productName','result','remark']) {
        const td=cell(row,k==='result'?'':item[k]||'—');
        if(k==='date'&&item.usesScheduleDate)td.textContent=item.date+'（排期）';
        if(k==='remark')td.textContent=[...new Set([item.inspectionProblem,item.remark].filter(Boolean))].join('\n')||'—';
        if(k==='result'){const badge=root.document.createElement('span');badge.className='qc-status '+(['PASS','FAIL','PENDING','LG'].includes(item.result)?item.result:'');badge.textContent=item.result;td.append(badge);}
      }
      el('detail-rows').append(row);
    }
    if(!data.details.items.length){const row=root.document.createElement('tr'),td=cell(row,'当前筛选范围内暂无此类记录');td.colSpan=6;td.className='qstats-empty-row';el('detail-rows').append(row);}
    const detail=data.details;
    el('detail-count').textContent='共 '+detail.total+' 条'+(detail.total?' · 显示 '+((detail.page-1)*detail.pageSize+1)+'—'+Math.min(detail.total,detail.page*detail.pageSize)+' 条':'');
    el('page').textContent=detail.page+' / '+detail.pages;el('prev').disabled=detail.page===1;el('next').disabled=detail.page===detail.pages;
    const excluded=Object.values(data.excluded).reduce((a,b)=>a+b,0),notes=[...data.notices];
    if(data.missingDate)notes.push('有 '+data.missingDate+' 条记录未填写最终验货日期，也无有效排期开始日，不参与年月筛选。');
    if(excluded)notes.push('有 '+excluded+' 条记录的当前状态或汇总来源异常，请核对验货汇总。');
    if(!data.ready)notes.push('验货汇总尚无可统计记录。');
    message(notes.join(' '),Boolean(excluded));
  }
  async function load() {
    if(!active())return;
    installSidebar();pageChanged('analysis');shell();
    state.controller?.abort();state.controller=new root.AbortController();const sequence=++state.sequence;
    clearData('正在读取验货汇总…');message('正在读取验货汇总…');el('root').setAttribute('aria-busy','true');
    try {
      const query=new URLSearchParams(Object.entries(state.filters).filter(([,v])=>v));
      const response=await root.fetch('api/approved-statistics/report?'+query,{cache:'no-store',signal:state.controller.signal});
      const data=await response.json();if(sequence!==state.sequence||!active())return;
      if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'统计读取失败，请重试');
      if(data.factory!==root.__QC_NEXUS.factory||data.source!=='current-inline-approved-summary-v1')throw Error('统计来源或厂区不一致，请重新进入页面');
      state.data=data;Object.assign(state.filters,data.filters,{page:String(data.details.page)});redraw();
    } catch(error) {
      if(sequence!==state.sequence||error.name==='AbortError')return;
      clearData('图表暂不可用');message(error.message,true);
    } finally {if(sequence===state.sequence)el('root').setAttribute('aria-busy','false');}
  }
  installSidebar();
  root.QcApprovedStatistics={load,redraw,pageChanged,rateBand};
})(window);
