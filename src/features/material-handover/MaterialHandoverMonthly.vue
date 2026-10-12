<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { getApiErrorMessage } from '@/lib/http'
import type { handoverApi, HandoverMonthly } from '@/api/materialHandover'
import type { MasterRecord } from '@/api/fabricMaster'
const props=defineProps<{ client: ReturnType<typeof handoverApi>; external?: boolean; suppliers: MasterRecord[] }>()
const month=ref(new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai'}).format(new Date()).slice(0,7))
const supplier=ref(''),result=ref<HandoverMonthly|null>(null),busy=ref(false),error=ref('')
let generation=0
async function load() {
  const epoch=++generation,client=props.client;result.value=null;busy.value=true;error.value=''
  try { const data=await client.monthly(month.value,supplier.value);if(epoch===generation)result.value=data }
  catch(e){if(epoch===generation)error.value=getApiErrorMessage(e)}
  finally{if(epoch===generation)busy.value=false}
}
async function download() {
  if(busy.value)return;const epoch=generation,client=props.client;busy.value=true
  try{const file=await client.exportMonthly(month.value,supplier.value);if(epoch!==generation)return;const link=document.createElement('a');link.href=URL.createObjectURL(file);link.download=`${month.value}-供应商数量对账.xlsx`;link.click();setTimeout(()=>URL.revokeObjectURL(link.href),30000)}
  catch(e){if(epoch===generation)error.value=getApiErrorMessage(e)}finally{if(epoch===generation)busy.value=false}
}
watch(()=>[props.client,month.value,supplier.value],load,{immediate:true})
onBeforeUnmount(()=>{generation++})
</script>
<template>
  <section class="monthly">
    <h2>{{ external ? '本供应商送货数量记录' : '供应商月度数量对账' }}</h2><p>本入口已确认送货单按实际收货和冲销的业务日期汇总，仓库统一月结在“月结对账”办理。不同单位分别计算；单价保留依据，不自动确定付款金额。</p>
    <div class="filters"><label>月份<input v-model="month" type="month" :disabled="busy" aria-label="对账月份" /></label><label v-if="!external">供应商<select v-model="supplier" :disabled="busy" aria-label="对账供应商"><option value="">全部供应商</option><option v-for="party in suppliers" :key="party.id" :value="party.id">{{ party.code }} · {{ party.name }}{{ party.status==='INACTIVE'?'（停用）':'' }}</option></select></label><button :disabled="busy" @click="load">刷新对账</button><button :disabled="busy || !result" @click="download">导出数量对账表</button></div>
    <p v-if="error" role="alert">{{ error }}</p><p v-if="busy" role="status">正在读取本月记录…</p>
    <template v-if="result">
      <p class="basis">实时核对表 · 未关账 · 导出后有新收货或冲销，需要重新核对。</p>
      <div class="totals"><p v-for="total in result.totals" :key="total.unit">{{ total.unit }}：实收 {{ total.month_received }}，冲销 {{ total.month_reversed }}，净实收 <strong>{{ total.month_net_received }}</strong></p></div>
      <h3>按供应商与物料汇总</h3><div class="table-scroll"><table><thead><tr><th>供应商</th><th>物料</th><th>单位</th><th>本月实收</th><th>本月冲销</th><th>本月净实收</th><th>相关单据月末未收</th></tr></thead><tbody><tr v-for="row in result.summary" :key="row.supplier_id+row.item_code+row.unit"><td>{{ row.supplier_name }}</td><td>{{ row.item_code }} · {{ row.item_name }}</td><td>{{ row.unit }}</td><td>{{ row.month_received }}</td><td>{{ row.month_reversed }}</td><td>{{ row.month_net_received }}</td><td>{{ row.outstanding }}</td></tr></tbody></table></div>
      <h3>送货单明细与参考单价</h3><p>相关原单包含以前月份未收完的单据。月初累计、当月净实收与月末未收分别显示，原单申报量不会每月重新累计为实收。</p>
      <div class="table-scroll"><table><thead><tr><th>供应商 / 原单</th><th>物料 / 单位</th><th>原单申报</th><th>月初累计已收</th><th>本月实收 / 冲销</th><th>月末未收</th><th>参考单价 / 计价单位</th><th>币种 / 依据</th><th>待核对</th></tr></thead><tbody><tr v-for="row in result.details" :key="row.document_id+row.line_id"><td>{{ row.supplier_name }}<small>{{ row.source_no }} · {{ row.document_date }}</small></td><td>{{ row.item_code }} · {{ row.item_name }}<small>{{ row.unit }}</small></td><td>{{ row.declared }}</td><td>{{ row.prior_received }}</td><td>{{ row.month_received }} / {{ row.month_reversed }}</td><td>{{ row.outstanding }}</td><td>{{ row.unit_price || '未记录' }} / {{ row.price_unit || '未注明' }}</td><td>{{ row.currency || '未注明' }}<small>{{ row.price_note || '依据未填写' }}</small></td><td>{{ row.notes.join('；') || '数量记录可核对' }}</td></tr></tbody></table></div>
      <p v-if="!result.details.length">本月没有相关已确认送货单记录；不代表仓库实际没有收货，请核对其他原单和线下收货。</p>
      <section v-if="!external && result.unlinked_receipts.length" class="exceptions"><h3>全仓已有收货凭证，但未关联这个入口 · {{ result.unlinked_receipts.length }} 笔</h3><p>这些数量未并入上方供应商汇总。先核对原单和供应商身份，不能再扫码入库补一遍；未来送货统一通过供应商链接办理。</p><div class="table-scroll"><table><thead><tr><th>原凭证 / 日期</th><th>往来单位</th><th>物料</th><th>数量 / 单位</th><th>说明</th></tr></thead><tbody><tr v-for="row in result.unlinked_receipts" :key="row.id"><td>{{ row.source_no }}<small>{{ row.date }}</small></td><td>{{ row.counterparty }}</td><td>{{ row.item_code }}</td><td>{{ row.quantity }} {{ row.unit }}</td><td>{{ row.reason }}</td></tr></tbody></table></div></section>
    </template>
  </section>
</template>
<style scoped>
.monthly{background:white;border:1px solid #dce5e1;border-radius:12px;padding:22px;color:#233a35}h2{font-size:21px;font-weight:650}h3{font-size:16px;font-weight:600;margin-top:24px}p,small{color:#667a73;margin:9px 0}small{display:block;font-size:12px}.filters{display:flex;gap:15px;align-items:end;flex-wrap:wrap;margin:18px 0}label{display:flex;flex-direction:column;gap:5px}input,select,button{padding:8px;border:1px solid #cfdbd6;border-radius:6px;background:white;font:inherit}button{cursor:pointer;color:#126d5b}button:disabled{opacity:.5}.table-scroll{overflow:auto}table{border-collapse:collapse;width:100%;text-align:left}th{background:#f4f8f5;white-space:nowrap}th,td{padding:11px;border-bottom:1px solid #e8eee9;vertical-align:top;font-size:13px}.basis,.totals{background:#eff7f2;border-radius:8px;padding:12px}.exceptions{background:#fff8eb;padding:16px;border-radius:8px;margin-top:24px}[role=alert]{color:#a23930}@media(max-width:720px){.monthly{padding:14px}.filters select{max-width:250px}}
</style>
