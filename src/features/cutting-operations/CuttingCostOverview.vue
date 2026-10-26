<script setup lang="ts">
import { watchCuttingWorkspace } from './workspaceRefresh'
import { computed,onMounted,onBeforeUnmount,ref } from 'vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import { Button } from '@/components/ui/button'
import CuttingMetrics from './CuttingMetrics.vue'
import { workspaceApi,type CostView } from './workspaceApi'
import { errorMessage } from './api'
defineEmits<{open:[lineId:string]}>()
const result=ref<CostView>(),query=ref(''),busy=ref(false),error=ref('')
const applied=ref({q:''})
type Query={q:string;page:number}
const failedQuery=ref<Query>()
const unapplied=computed(()=>query.value!==applied.value.q)
let generation=0,alive=true
async function load(page=1,apply=false){
  if(apply){applied.value={q:query.value};page=1}
  await read({...applied.value,page})
}
async function read(request:Query){
  const ticket=++generation;busy.value=true;error.value='';result.value=undefined;failedQuery.value=undefined
  try{const value=await workspaceApi.costs(request);if(alive&&ticket===generation)result.value=value}
  catch(e){if(alive&&ticket===generation){error.value=errorMessage(e);failedQuery.value={...request}}}finally{if(alive&&ticket===generation)busy.value=false}}
function retry(){if(failedQuery.value&&!busy.value)void read({...failedQuery.value})}
onMounted(()=>void load());onBeforeUnmount(()=>{alive=false;generation++})
watchCuttingWorkspace(()=>void load())
</script>
<template>
  <div class="cutting-overview">
    <CuttingMetrics :items="[{label:'待计价实发',value:result?.pending_pricing??'—',unit:'笔',hint:'缺价不以零元代替'},...Object.entries(result?.currencies??{}).map(([currency,v])=>({label:`已计价正常耗用（${currency}）`,value:v.normal,unit:currency,hint:`完工 ${v.completed??'待归属'} / 在制 ${v.wip??'待归属'}；损耗 ${v.loss} ${currency}`}))]" />
    <SectionPanel title="订单实际材料费用" class="cutting-content-panel">
      <form class="order-toolbar" @submit.prevent="load(1,true)"><label>订单号／货号<input v-model="query" maxlength="80" /></label><Button :disabled="busy">查询／刷新</Button></form>
      <p class="cutting-muted">当前查询条件：订单号／货号 {{applied.q||'全部'}}。</p>
      <p v-if="unapplied" role="status" class="cutting-muted">筛选有未查询的修改；当前仍按上次查询条件显示。点击“查询／刷新”后应用，翻页和原条件重试不会提交新输入。</p>
      <p class="cutting-notice">当前累计核对，已计价部分按币种汇总。完工及在制归属进入订单确认；已锁月份以内部月结冻结快照为准。</p>
      <p v-if="busy" role="status">正在核对原批次价格与实际耗用…</p><p v-if="error" role="alert">{{error}}</p>
      <Button v-if="failedQuery" variant="outline" :disabled="busy" @click="retry">按原条件重试（第 {{failedQuery.page}} 页）</Button>
      <div class="cutting-table-scroll" tabindex="0" role="region" aria-label="订单材料费用汇总"><table><thead><tr><th>客户／订单</th><th>货号</th><th>正常材料费用</th><th>损耗费用</th><th>完工／在制费用</th><th>待计价实发</th><th>完工与在制</th><th>操作</th></tr></thead><tbody><tr v-for="row in result?.data" :key="row.line_id">
        <td>{{row.customer}}<br />{{row.order_no}}</td><td>{{row.item_no}}</td><td><p v-for="(value,currency) in row.normal" :key="currency">{{value}} {{currency}}</p><span v-if="!Object.keys(row.normal).length">待计价／暂无耗用</span></td><td><p v-for="(value,currency) in row.loss" :key="currency">{{value}} {{currency}}</p></td><td><p v-for="(value,currency) in row.normal" :key="currency">{{row.completed[currency]??'待归属'}} / {{row.wip[currency]??'待归属'}} {{currency}}</p></td><td>{{row.pending_pricing}} 笔</td><td>{{row.allocation_pending?`${row.allocation_pending} 组待核对`:'已核对／无待归属记录'}}</td><td><Button variant="outline" size="sm" @click="$emit('open',row.line_id)">核对明细与归属</Button></td>
      </tr></tbody></table></div>
      <p v-if="result&&!result.total" class="cutting-no-records">{{applied.q?'当前筛选无匹配费用记录，请清除筛选后查看。':'暂无关联实发与耗用费用记录。'}}<Button v-if="applied.q" variant="outline" :disabled="busy" @click="query='';load(1,true)">清除筛选</Button></p>
      <nav v-if="result" class="order-pagination" aria-label="费用汇总分页"><span>第 {{result.page}} 页 · 共 {{result.total}} 笔订单</span><Button variant="outline" :disabled="busy||result.page<=1" @click="load(result.page-1)">上一页</Button><Button variant="outline" :disabled="busy||result.page*50>=result.total" @click="load(result.page+1)">下一页</Button></nav>
    </SectionPanel>
  </div>
</template>
