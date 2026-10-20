<script setup lang="ts">
import { watchCuttingWorkspace } from './workspaceRefresh'
import { onMounted,onBeforeUnmount,ref } from 'vue'
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
let generation=0,alive=true
const sources:Record<string,string>={master:'基础资料',order:'接单／工程／排期',production:'每日填数与交接',warehouse:'领料／实发／签收／退仓',material:'耗用／成本／归属',period:'内部月结',settlement:'外发结算',payment:'付款核销'}
const actions:Record<string,string>={revision:'版本更新',draft:'草稿',active:'启用',inactive:'停用',published:'发布',save:'保存草稿',post:'提交生效',void:'撤销',review:'主管抽查',discard:'放弃草稿',price:'确认价格',allocate:'确认完工归属',submit:'提交复核',return:'退回',lock:'锁月',reopen:'反结',confirm:'复核确认',reverse:'整笔冲销',REQUEST:'领料申请',ISSUE:'仓库实发',RETURN:'退仓',CUTTING_RECEIPT:'裁床签收',CUTTING_RECEIPT_VOID:'撤销签收',CUTTING_REQUEST_REUSE:'确认计划续用',REQUEST_CLOSE:'关闭申请',CORRECTION:'仓库更正'}
function link(row:ActivityRow){
  if(row.source==='material'&&['price','allocate'].includes(row.action)){const target=cuttingDestination(row.line_id,row.business_day?.slice(0,7)??'','costs','cost_event',row.id);return {...target,query:{...target.query,cost_view:row.action==='price'?'history':'allocation'}}}
  if(row.source==='master')return {path:`${CUTTING_BASE}/master`,query:{factory:CUTTING_FACTORY,master_id:row.document_id}}
  if(['period','settlement','payment'].includes(row.source))return {path:`${CUTTING_BASE}/closing`,query:{factory:CUTTING_FACTORY,view:row.source,document_id:row.document_id,event_id:row.id,month:row.month||row.business_day?.slice(0,7)||undefined}}
  const target=cuttingDestination(row.line_id,row.business_day?.slice(0,7)??'',row.source==='production'?'reporting':row.source==='warehouse'?'materials':row.source==='material'?(row.action==='price'||row.action==='allocate'?'costs':'materials'):'planning',row.source==='production'?'report':row.source==='warehouse'?'warehouse':row.source==='material'?'usage':undefined,row.document_id)
  return {...target,query:{...target.query,...(row.business_day?{day:row.business_day}:{})}}
}
async function load(page=1){const ticket=++generation;busy.value=true;error.value=''
  const token=page>1?result.value?.token:undefined
  if(page===1)result.value=undefined
  try{const value=await workspaceApi.activity({source:source.value,q:query.value,order_q:orderQuery.value,month:month.value||undefined,page,expected_token:token});if(alive&&ticket===generation)result.value=value}
  catch(e){if(alive&&ticket===generation){error.value=errorMessage(e);const status=(e as {response?:{status:number}}).response?.status;if(status===401||status===403)result.value=undefined}}
  finally{if(alive&&ticket===generation)busy.value=false}}
function clearFilters(){source.value=props.initialSource??'';query.value='';orderQuery.value='';month.value='';void load()}
onMounted(()=>void load());onBeforeUnmount(()=>{alive=false;generation++})
watchCuttingWorkspace(()=>void load())
</script>
<template>
  <section :class="embedded?'cutting-overview':'cutting-page cutting-overview'">
    <PageHeader v-if="!embedded" title="操作日志" description="追溯原单、版本、操作人及更正依据；仅展示当前权限可查看的业务记录。" />
    <SectionPanel title="业务操作与关联记录" class="cutting-content-panel">
      <form class="order-toolbar" @submit.prevent="load()"><label>业务来源<select v-model="source"><option value="">全部授权来源</option><option v-for="(label,key) in sources" :key="key" :value="key">{{label}}</option></select></label><label>订单号／货号<input v-model="orderQuery" maxlength="80" /></label><label>业务期间<input v-model="month" type="month" min="2000-01" /></label><label>单据／操作人／原因<input v-model="query" maxlength="80" /></label><Button :disabled="busy">查询／刷新</Button><Button type="button" variant="outline" :disabled="busy" @click="clearFilters">清除筛选</Button></form>
      <p v-if="busy" role="status">正在读取操作记录…</p><p v-if="error" role="alert">{{error}}</p>
      <div class="cutting-table-scroll" role="region" tabindex="0" aria-label="可追溯操作日志"><table><thead><tr><th>操作时间／业务日期</th><th>来源与操作</th><th>单据／版本</th><th>操作人</th><th>依据与关联</th><th>操作</th></tr></thead><tbody><tr v-for="row in result?.data" :key="`${row.source}:${row.id}:${row.version}`">
        <td>{{new Date(row.occurred_at).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'})}}<br />{{row.business_day||row.month||'未单独登记业务日期'}}</td>
        <td>{{sources[row.source]}}<br />{{actions[row.action]??row.action}}</td><td><strong>{{row.order_no||sources[row.source]}}</strong><br />{{row.document_id}}<br />V{{row.version}}</td><td>{{row.actor}}</td>
        <td>{{row.reason}}<p v-if="row.related_id">关联原单：{{row.related_id}}</p></td><td><details v-if="row.price_evidence"><summary>价格确认原记录</summary><p>事件 {{row.id}} · 任务 {{row.price_evidence.task_id}}</p><p>{{row.price_evidence.unit_price}} {{row.price_evidence.currency}}／套</p><p>{{row.price_evidence.evidence}}</p></details><Button v-else as-child variant="outline" size="sm"><RouterLink :to="link(row)">追溯原记录</RouterLink></Button></td>
      </tr></tbody></table></div>
      <p v-if="result&&!result.total" class="cutting-no-records">当前权限和筛选范围暂无操作记录，可清除筛选后重试。</p>
      <nav v-if="result" class="order-pagination" aria-label="操作日志分页"><span>第 {{result.page}} 页 · 共 {{result.total}} 条</span><Button variant="outline" :disabled="busy||result.page<=1" @click="load(result.page-1)">上一页</Button><Button variant="outline" :disabled="busy||result.page*50>=result.total" @click="load(result.page+1)">下一页</Button></nav>
      <p class="cutting-muted">业务期间按原单业务日期／所属月份筛选；未登记业务期间的资料版本不混入该期间。订单筛选包含有订单依据的结算及付款，整月内部月结请按期间查询。保留系统原始操作人标识与依据；未记录的历史岗位、字段差异或失败尝试不作推断。财务记录仅在获得对应权限后可查。</p>
    </SectionPanel>
  </section>
</template>
