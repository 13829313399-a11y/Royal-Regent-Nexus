<script setup lang="ts">
import { watchCuttingWorkspace } from './workspaceRefresh'
import { computed,nextTick,onMounted,onBeforeUnmount,ref,useId } from 'vue'
import { RouterLink } from 'vue-router'
import PageHeader from '@/components/common/PageHeader.vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import { Button } from '@/components/ui/button'
import { workspaceApi,type ActivityRow,type Page } from './workspaceApi'
import { errorMessage } from './api'
import { cuttingDestination } from './location'
import { CUTTING_BASE,CUTTING_FACTORY } from './navigation'
const props=defineProps<{embedded?:boolean;initialSource?:string}>()
const source=ref(props.initialSource??''),query=ref(''),orderQuery=ref(''),month=ref(''),result=ref<Page<ActivityRow>>(),busy=ref(false),error=ref('')
const applied=ref({source:source.value,q:'',order_q:'',month:undefined as string|undefined})
type ActivityQuery=typeof applied.value & {page:number;expected_token?:string}
const failedQuery=ref<ActivityQuery>(),readingTarget=ref<ActivityQuery & {retry:boolean}>(),staleResult=ref(false),restartRequired=ref(false)
const lastSuccessAt=ref<string>()
const resultRegion=ref<HTMLElement>(),retryAlert=ref<HTMLElement>(),filterId=`cutting-activity-${useId()}`
const focusCleanups=new Set<()=>void>()
const unapplied=computed(()=>source.value!==applied.value.source||query.value!==applied.value.q||orderQuery.value!==applied.value.order_q||(month.value||undefined)!==applied.value.month)
let generation=0,alive=true
const sources:Record<string,string>={master:'基础资料',order:'接单／工程／排期',production:'每日填数与交接',warehouse:'领料／实发／签收／退仓',material:'耗用／成本／归属',period:'内部月结',settlement:'外发结算',payment:'付款核销'}
const targetLabel=(value:ActivityQuery)=>`业务来源 ${sources[value.source]||'全部授权来源'}；订单号／货号 ${value.order_q||'全部'}；业务期间 ${value.month||'全部期间'}；单据／操作人／原因 ${value.q||'未限定'}，第 ${value.page} 页`
const readTimeLabel=(value:string)=>new Date(value).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false})
const actions:Record<string,string>={revision:'版本更新',draft:'草稿',active:'启用',inactive:'停用',published:'发布',save:'保存草稿',post:'提交生效',void:'撤销',review:'主管抽查',discard:'放弃草稿',price:'确认价格',allocate:'确认完工归属',submit:'提交复核',return:'退回',lock:'锁月',reopen:'反结',confirm:'复核确认',reverse:'整笔冲销',REQUEST:'领料申请',ISSUE:'仓库实发',RETURN:'退仓',CUTTING_RECEIPT:'裁床签收',CUTTING_RECEIPT_VOID:'撤销签收',CUTTING_REQUEST_REUSE:'确认计划续用',REQUEST_CLOSE:'关闭申请',CORRECTION:'仓库更正'}
function link(row:ActivityRow){
  if(row.source==='material'&&['price','allocate'].includes(row.action)){const target=cuttingDestination(row.line_id,row.business_day?.slice(0,7)??'','costs','cost_event',row.id);return {...target,query:{...target.query,cost_view:row.action==='price'?'history':'allocation'}}}
  if(row.source==='master')return {path:`${CUTTING_BASE}/master`,query:{factory:CUTTING_FACTORY,master_id:row.document_id,master_version:String(row.version)}}
  if(['period','settlement','payment'].includes(row.source))return {path:`${CUTTING_BASE}/closing`,query:{factory:CUTTING_FACTORY,view:row.source,document_id:row.document_id,event_id:row.id,month:row.month||row.business_day?.slice(0,7)||undefined}}
  const target=cuttingDestination(row.line_id,row.business_day?.slice(0,7)??'',row.source==='production'?'reporting':row.source==='warehouse'?'materials':row.source==='material'?(row.action==='price'||row.action==='allocate'?'costs':'materials'):'planning',row.source==='production'?'report':row.source==='warehouse'?'warehouse':row.source==='material'?'usage':undefined,row.document_id)
  return {...target,query:{...target.query,...(row.business_day?{day:row.business_day}:{})}}
}
async function load(page=1,apply=false){
  if(apply){applied.value={source:source.value,q:query.value,order_q:orderQuery.value,month:month.value||undefined};page=1}
  const token=page>1?result.value?.token:undefined
  await read({...applied.value,page,expected_token:token})
}
async function read(request:ActivityQuery,retry=false,keyboardRetry=false){
  const ticket=++generation;busy.value=true;error.value='';failedQuery.value=undefined;restartRequired.value=false
  let restoreFocus=keyboardRetry,succeeded=false
  const cancelFocus=()=>{restoreFocus=false}
  const cancelOnTab=(event:KeyboardEvent)=>{if(event.key==='Tab')cancelFocus()}
  const cleanupFocus=()=>{document.removeEventListener('focusin',cancelFocus);document.removeEventListener('pointerdown',cancelFocus);document.removeEventListener('keydown',cancelOnTab);focusCleanups.delete(cleanupFocus)}
  if(keyboardRetry){document.addEventListener('focusin',cancelFocus);document.addEventListener('pointerdown',cancelFocus);document.addEventListener('keydown',cancelOnTab)}
  if(keyboardRetry)focusCleanups.add(cleanupFocus)
  readingTarget.value={...request,retry}
  if(request.page===1){result.value=undefined;lastSuccessAt.value=undefined}
  staleResult.value=Boolean(result.value)
  try{const value=await workspaceApi.activity(request);if(alive&&ticket===generation){result.value=value;lastSuccessAt.value=new Date().toISOString();staleResult.value=false;succeeded=true}}
  catch(e){if(alive&&ticket===generation){
    error.value=errorMessage(e)
    const status=(e as {response?:{status:number}}).response?.status
    if(status===401||status===403){result.value=undefined;lastSuccessAt.value=undefined;staleResult.value=false}
    else{
      restartRequired.value=status===409&&Boolean(request.expected_token)&&error.value==='操作日志已新增或查看范围已变化，请刷新第一页后继续。'
      failedQuery.value=restartRequired.value?{...request,page:1,expected_token:undefined}:{...request}
    }
  }}
  finally{
    if(alive&&ticket===generation){busy.value=false;readingTarget.value=undefined;await nextTick()}
    cleanupFocus()
    if(restoreFocus&&alive&&ticket===generation&&document.activeElement===document.body){
      const target=succeeded?resultRegion.value:failedQuery.value?retryAlert.value?.querySelector<HTMLButtonElement>('button'):undefined
      target?.focus({preventScroll:true})
    }
  }
}
function retry(event:MouseEvent){if(failedQuery.value&&!busy.value)void read({...failedQuery.value},true,event.detail===0&&event.currentTarget===document.activeElement)}
function clearFilters(){source.value=props.initialSource??'';query.value='';orderQuery.value='';month.value='';void load(1,true)}
onMounted(()=>void load());onBeforeUnmount(()=>{alive=false;generation++;for(const cleanup of focusCleanups)cleanup()})
watchCuttingWorkspace(()=>void load())
</script>
<template>
  <section :class="embedded?'cutting-overview':'cutting-page cutting-overview'">
    <PageHeader v-if="!embedded" title="操作日志" description="追溯原单、版本、操作人及更正依据；仅展示当前权限可查看的业务记录。" />
    <SectionPanel title="业务操作与关联记录" class="cutting-content-panel">
      <form class="order-toolbar" @submit.prevent="load(1,true)"><label :for="`${filterId}-source`">业务来源<select :id="`${filterId}-source`" v-model="source" name="source"><option value="">全部授权来源</option><option v-for="(label,key) in sources" :key="key" :value="key">{{label}}</option></select></label><label :for="`${filterId}-order`">订单号／货号<input :id="`${filterId}-order`" v-model="orderQuery" name="order_q" maxlength="80" /></label><label :for="`${filterId}-month`">业务期间<input :id="`${filterId}-month`" v-model="month" name="month" type="month" min="2000-01" /></label><label :for="`${filterId}-query`">单据／操作人／原因<input :id="`${filterId}-query`" v-model="query" name="q" maxlength="80" /></label><Button type="submit" :disabled="busy">查询</Button><Button type="button" variant="outline" :disabled="busy" @click="load(1)">刷新当前结果</Button><Button type="button" variant="outline" :disabled="busy" @click="clearFilters">清除筛选</Button></form>
      <p class="cutting-muted">当前查询条件：业务来源 {{sources[applied.source]||'全部授权来源'}}；订单号／货号 {{applied.order_q||'全部'}}；业务期间 {{applied.month||'全部期间'}}；单据／操作人／原因 {{applied.q||'未限定'}}。</p>
      <p class="cutting-muted">刷新从第 1 页重新核对当前已查询条件，不应用尚未查询的新输入。</p>
      <p v-if="unapplied" class="cutting-muted" role="status">筛选有未查询的修改，当前结果仍按上次查询条件展示；翻页和刷新不应用新输入，点击“查询”才应用。</p>
      <p v-if="busy" role="status">{{readingTarget?.retry?`正在按原条件重试：${targetLabel(readingTarget)}。`:'正在读取操作记录…'}}</p>
      <p v-if="error" ref="retryAlert" role="alert">{{error}} <Button v-if="failedQuery" type="button" variant="outline" :disabled="busy" @click="retry">{{restartRequired?'按原条件重读第 1 页':`按原条件重试（第 ${failedQuery.page} 页）`}}</Button></p>
      <p v-if="failedQuery" class="cutting-muted">重试目标：{{targetLabel(failedQuery)}}。{{restartRequired?'原分页依据已失效，重新从第 1 页核对，不再使用旧依据。':failedQuery.expected_token?'保留原分页依据。':'本次没有分页依据，将按原条件从第 1 页重新读取并获取新依据。'}}不应用尚未查询的新输入，不提交业务记录。</p>
      <p v-if="staleResult&&result" class="cutting-muted" role="status">以下仍为上次成功读取的第 {{result.page}} 页结果，尚未取得本次请求的新结果，请勿将其视为已刷新数据。</p>
      <p v-if="result&&lastSuccessAt" class="cutting-muted">上次成功读取时间：<time :datetime="lastSuccessAt">{{readTimeLabel(lastSuccessAt)}}</time>（页面读取时间，非业务日期）</p>
      <div ref="resultRegion" class="cutting-table-scroll" role="region" tabindex="0" aria-label="可追溯操作日志"><table><thead><tr><th>操作时间／业务日期</th><th>来源与操作</th><th>单据／版本</th><th>操作人</th><th>依据与关联</th><th>操作</th></tr></thead><tbody><tr v-for="row in result?.data" :key="`${row.source}:${row.id}:${row.version}`">
        <td>{{new Date(row.occurred_at).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'})}}<br />{{row.business_day||row.month||'未单独登记业务日期'}}</td>
        <td>{{sources[row.source]}}<br />{{actions[row.action]??row.action}}</td><td><strong>{{row.order_no||sources[row.source]}}</strong><br />{{row.document_id}}<br />V{{row.version}}</td><td>{{row.actor}}</td>
        <td>{{row.reason}}<p v-if="row.related_id">关联原单：{{row.related_id}}</p></td><td><details v-if="row.price_evidence"><summary>价格确认原记录</summary><p>事件 {{row.id}} · 任务 {{row.price_evidence.task_id}}</p><p>{{row.price_evidence.unit_price}} {{row.price_evidence.currency}}／套</p><p>{{row.price_evidence.evidence}}</p></details><Button v-else as-child variant="outline" size="sm"><RouterLink :to="link(row)">追溯原记录</RouterLink></Button></td>
      </tr></tbody></table></div>
      <p v-if="result&&!result.total" class="cutting-no-records">当前权限和筛选范围暂无操作记录，可清除筛选后重试。</p>
      <nav v-if="result" class="order-pagination" aria-label="操作日志分页"><span>第 {{result.page}} 页 · 共 {{result.total}} 条</span><Button variant="outline" :disabled="busy||restartRequired||result.page<=1" @click="load(result.page-1)">上一页</Button><Button variant="outline" :disabled="busy||restartRequired||result.page*50>=result.total" @click="load(result.page+1)">下一页</Button></nav>
      <p class="cutting-muted">业务期间按原单业务日期／所属月份筛选；未登记业务期间的资料版本不混入该期间。订单筛选包含有订单依据的结算及付款，整月内部月结请按期间查询。保留系统原始操作人标识与依据；未记录的历史岗位、字段差异或失败尝试不作推断。财务记录仅在获得对应权限后可查。</p>
    </SectionPanel>
  </section>
</template>
