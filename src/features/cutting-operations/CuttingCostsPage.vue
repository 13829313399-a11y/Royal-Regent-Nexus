<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import PageHeader from '@/components/common/PageHeader.vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import { Button } from '@/components/ui/button'
import { cuttingApi, errorMessage, type Access } from './api'
import { ordersApi, type CuttingOrder } from './ordersApi'
import CuttingMaterialUsage from './CuttingMaterialUsage.vue'
import type { CuttingWorkspace } from './navigation'
defineProps<{workspace:CuttingWorkspace}>()
const access=ref<Access>(),rows=ref<CuttingOrder[]>([]),selected=ref<CuttingOrder>(),query=ref(''),page=ref(1),total=ref(0),loading=ref(false),error=ref('')
const editor=ref<InstanceType<typeof CuttingMaterialUsage>>()
let alive=true,generation=0
function discard(){return editor.value?.discard()??true}
onBeforeRouteLeave(discard)
onBeforeUnmount(()=>{alive=false;generation++})
async function load(nextPage=page.value){
  if(!discard())return
  const ticket=++generation;selected.value=undefined;rows.value=[];loading.value=true;error.value=''
  try{const rights=await cuttingApi.access();if(!alive||ticket!==generation)return;access.value=rights
    if(!rights.enabled||!rights.usage_schema_ready||!rights.permissions.includes('cost_read')){rows.value=[];return}
    const result=await ordersApi.list(nextPage,query.value);if(alive&&ticket===generation){rows.value=result.data;page.value=result.page;total.value=result.total}
  }catch(e){if(alive&&ticket===generation){rows.value=[];error.value=errorMessage(e)}}finally{if(alive&&ticket===generation)loading.value=false}
}
function select(order:CuttingOrder){if(!loading.value&&discard())selected.value=order}
onMounted(()=>void load())
</script>
<template>
  <section class="cutting-page cutting-master">
    <PageHeader :title="workspace.title" description="按真实签收与实际耗用核对本厂、外发余料，追溯原批次成本与待计价事项。"><template #actions><StatusPill label="耗用与批次成本 · P3b 首批" /></template></PageHeader>
    <p v-if="error" role="alert" class="cutting-error">{{error}}</p><p v-if="loading" role="status">正在读取费用工作区…</p>
    <p v-if="access&&!access.enabled" class="cutting-notice">实际材料费用尚未启用，当前不能录入或计价。</p>
    <p v-else-if="access&&!access.usage_schema_ready" class="cutting-notice">P3b 需先完成 0156 显式迁移，当前未接通，不以零费用代替未知。</p>
    <p v-else-if="access&&!access.permissions.includes('cost_read')" class="cutting-notice">查看材料费用需单独授予成本查询权限；生产耗用可在物料工作区按已有耗用权限登记。</p>
    <template v-else-if="access?.enabled&&access.usage_schema_ready">
      <SectionPanel title="选择费用核对订单" class="cutting-content-panel">
        <form class="order-toolbar" @submit.prevent="load(1)"><label>订单号／货号<input v-model="query" maxlength="80" /></label><Button type="submit" variant="outline" :disabled="loading">查询／刷新</Button></form>
        <div class="cutting-table-scroll" role="region" aria-label="费用订单，可横向滚动" tabindex="0"><table><thead><tr><th>洋行名</th><th>生产／订单号</th><th>货号</th><th>操作</th></tr></thead><tbody><tr v-for="order in rows" :key="order.line_id"><td>{{order.snapshot.customer_name}}</td><td>{{order.snapshot.reference_no}}</td><td>{{order.snapshot.product_no}}</td><td><Button size="sm" variant="outline" :disabled="loading" @click="select(order)">查看耗用与费用</Button></td></tr></tbody></table></div>
        <p v-if="!rows.length&&!loading" class="cutting-no-records">暂无已下发裁床订单。</p>
        <nav class="order-pagination" aria-label="费用订单分页"><span>第 {{page}} 页 · 共 {{total}} 条</span><Button variant="outline" :disabled="loading||page<=1" @click="load(page-1)">上一页</Button><Button variant="outline" :disabled="loading||page*50>=total" @click="load(page+1)">下一页</Button></nav>
      </SectionPanel>
      <CuttingMaterialUsage v-if="selected?.current" ref="editor" :key="selected.line_id" :line-id="selected.line_id" :permissions="access.permissions" with-costs />
      <p v-else-if="selected" class="cutting-notice">请先签收订单并完成工程及领料依据。</p>
    </template>
  </section>
</template>
