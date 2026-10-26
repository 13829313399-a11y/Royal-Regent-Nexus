<script setup lang="ts">
import { watchCuttingWorkspace } from './workspaceRefresh'
import { computed,onBeforeUnmount,ref,watch } from 'vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import { Button } from '@/components/ui/button'
import CuttingMetrics from './CuttingMetrics.vue'
import { workspaceApi,type InventoryView } from './workspaceApi'
import { errorMessage } from './api'
defineEmits<{open:[lineId:string,issueId:string]}>()
const props=defineProps<{summary?:boolean}>()
const result=ref<InventoryView>(),query=ref(''),execution=ref(''),busy=ref(false),error=ref('')
const applied=ref({q:'',execution:''})
type Query={q:string;execution:string;page:number;view:string}
const failedQuery=ref<Query>()
const unapplied=computed(()=>query.value!==applied.value.q||execution.value!==applied.value.execution)
let generation=0,alive=true
async function load(page=1,apply=false){
  if(apply){applied.value={q:query.value,execution:execution.value};page=1}
  await read({...applied.value,page,view:props.summary?'orders':'issues'})
}
async function read(request:Query){
  const ticket=++generation;busy.value=true;error.value='';result.value=undefined;failedQuery.value=undefined
  try{const value=await workspaceApi.inventory(request);if(alive&&ticket===generation)result.value=value}
  catch(e){if(alive&&ticket===generation){error.value=errorMessage(e);failedQuery.value={...request}}}finally{if(alive&&ticket===generation)busy.value=false}}
function retry(){if(failedQuery.value&&!busy.value)void read({...failedQuery.value})}
function clearFilters(){query.value='';execution.value='';void load(1,true)}
watch(()=>props.summary,()=>void load(),{immediate:true});onBeforeUnmount(()=>{alive=false;generation++})
watchCuttingWorkspace(()=>void load())
</script>
<template>
  <div class="cutting-overview">
    <CuttingMetrics :items="[{label:summary?'订单任务物料汇总':'关联实发记录',value:result?.total??'—',unit:summary?'组':'笔',hint:'已冲销实发不计入当前台账'},...Object.entries(result?.units??{}).map(([unit,v])=>({label:`账面余料（${unit}）`,value:v.remaining_quantity??'—',unit,hint:`待签收 ${v.unsigned_quantity}；已退仓 ${v.returned_quantity}`}))]" />
    <SectionPanel :title="summary?'订单领用汇总':'本厂现场与外发在外物料台账'" class="cutting-content-panel">
      <form class="order-toolbar" @submit.prevent="load(1,true)"><label>订单号／货号<input v-model="query" maxlength="80" /></label><label>保管范围<select v-model="execution"><option value="">本厂与外发</option><option value="internal">本厂现场</option><option value="outsourced">外发在外</option></select></label><Button :disabled="busy">查询／刷新</Button></form>
      <p class="cutting-muted">当前查询条件：订单号／货号 {{applied.q||'全部'}}；保管范围 {{applied.execution==='internal'?'本厂现场':applied.execution==='outsourced'?'外发在外':'本厂与外发'}}。</p>
      <p v-if="unapplied" role="status" class="cutting-muted">筛选有未查询的修改；当前仍按上次查询条件显示。点击“查询／刷新”后应用，翻页和原条件重试不会提交新输入。</p>
      <p v-if="busy" role="status">正在读取真实签收与耗用余额…</p><p v-if="error" role="alert">{{error}}</p>
      <Button v-if="failedQuery" variant="outline" :disabled="busy" @click="retry">按原条件重试（第 {{failedQuery.page}} 页）</Button>
      <p class="cutting-muted">账面余料＝签收－退仓－正常耗用－损耗。未签收实发单列，退仓以仓库生效记录为准；盘余差异不自动转为损耗。</p>
      <div class="cutting-table-scroll" tabindex="0" role="region" aria-label="裁床物料库存台账"><table><thead><tr><th>物料／规格／颜色</th><th>订单／任务</th><th>执行方</th><th>原批次／实发</th><th>单位</th><th>签收</th><th>退仓</th><th>正常耗用／损耗</th><th>账面余料</th><th>待签收</th><th>操作</th></tr></thead><tbody><tr v-for="row in result?.data" :key="row.issue_id">
        <td>{{row.context.item_name}}<br />{{row.context.item_code}}<br />{{row.context.warehouse_material.spec}} · {{row.context.warehouse_material.color}}</td><td>{{row.order_no}}<br />{{row.context.task_name}}</td>
        <td>{{row.context.resource_name}}<br />{{row.context.execution==='internal'?'本厂':'外发'}}</td><td><template v-if="summary">{{row.issue_count}} 笔实发 · 分原单追溯</template><template v-else>{{row.context.root_batch_id}}<br />{{row.issue_id}}<br />{{row.context.lot}} / {{row.context.roll_no}}</template></td><td>{{row.context.unit}}</td>
        <td>{{row.received_quantity}}</td><td>{{row.returned_quantity}}</td><td>{{row.consumed_quantity}} / {{row.loss_quantity}}</td><td>{{row.remaining_quantity}}</td><td>{{row.unsigned_quantity}}</td>
        <td><Button variant="outline" size="sm" @click="$emit('open',row.line_id,summary?'':row.issue_id)">领用与耗用详情</Button></td>
      </tr></tbody></table></div>
      <p v-if="result&&!result.total" class="cutting-no-records">{{applied.q||applied.execution?'当前筛选无匹配库存记录，请清除筛选后查看。':'暂无关联实发记录。先在“领料申请”选择已发布任务申请，由布料仓核对发料。'}}<Button v-if="applied.q||applied.execution" variant="outline" :disabled="busy" @click="clearFilters">清除筛选</Button></p>
      <nav v-if="result" class="order-pagination" aria-label="库存台账分页"><span>第 {{result.page}} 页 · 共 {{result.total}} 笔</span><Button variant="outline" :disabled="busy||result.page<=1" @click="load(result.page-1)">上一页</Button><Button variant="outline" :disabled="busy||result.page*50>=result.total" @click="load(result.page+1)">下一页</Button></nav>
    </SectionPanel>
  </div>
</template>
