<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { isAxiosError } from 'axios'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage } from '@/lib/http'
import { warehouseOperationsApi as api, type FabricMonthlyQuery, type FabricMonthlyReport, type FabricMonthlyView } from '@/api/warehouseOperations'

const props = defineProps<{ view: FabricMonthlyView }>()
const route = useRoute(), auth = useAuthStore()
const month = ref(new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai' }).format(new Date()).slice(0, 7))
const channel = ref<FabricMonthlyQuery['channel']>(''), party = ref(''), result = ref<FabricMonthlyReport>()
const loading = ref(false), exporting = ref(false), error = ref(''), limit = ref(50)
const direction = computed<FabricMonthlyQuery['direction']>(() => props.view === 'reconciliation' ? 'IN' : props.view === 'recipients' ? 'OUT' : '')
const title = computed(() => props.view === 'reconciliation' ? '供应商收料对账' : props.view === 'recipients' ? '领用方发料对账' : '收发数量汇总')
const query = (): FabricMonthlyQuery => ({ month: month.value, direction: direction.value, channel: channel.value, party_key: party.value })
const ready = () => route.query.factory === 'huakang-c' && !!auth.currentUser?.id
let generation = 0
async function load() {
  const epoch = ++generation
  result.value = undefined; error.value = ''; exporting.value = false; limit.value = 50
  if (!ready()) { loading.value = false; return }
  loading.value = true
  try { const report = await api.monthly(query()); if (epoch === generation) result.value = report }
  catch (e) { if (epoch === generation) error.value = getApiErrorMessage(e) }
  finally { if (epoch === generation) loading.value = false }
}
async function download() {
  if (!result.value || loading.value || exporting.value || !ready()) return
  const epoch = generation, saved = result.value
  exporting.value = true; error.value = ''
  try {
    const file = await api.exportMonthly(query(), saved.version)
    if (epoch !== generation) return
    const url = URL.createObjectURL(file), link = document.createElement('a')
    link.href = url; link.download = `${saved.month}-${title.value}.xlsx`; link.click()
    setTimeout(() => URL.revokeObjectURL(url), 30000)
  } catch (e) { if (epoch === generation) error.value = isAxiosError(e) && e.response?.status === 409 ? '收发记录已变化，请刷新汇总后再导出。' : getApiErrorMessage(e) }
  finally { if (epoch === generation) exporting.value = false }
}
watch(() => [props.view, route.query.factory, auth.currentUser?.id, auth.authorizationVersion], () => { party.value = ''; channel.value = ''; load() }, { immediate: true })
watch(() => [month.value, channel.value, party.value], load)
onBeforeUnmount(() => { generation++ })
</script>

<template>
  <section class="fabric-monthly">
    <div class="monthly-heading"><div><h2>{{ title }}</h2><p>手动与扫码共用实际库存流水，按供应商或领用方分别核对。</p></div><span class="live-label">实时数量对账</span></div>
    <div class="entry-links"><span>入库：</span><RouterLink to="/modules/pmc-warehouse/fabric-warehouse/overview?factory=huakang-c">手动入库</RouterLink><RouterLink to="/modules/pmc-warehouse/material-handover?factory=huakang-c&tab=scan">扫码入库</RouterLink><span>出库：</span><RouterLink to="/modules/pmc-warehouse/fabric-warehouse/inventory?factory=huakang-c&view=issues">手动出库</RouterLink><RouterLink to="/modules/pmc-warehouse/material-handover?factory=huakang-c&tab=scan">扫码出库</RouterLink><span class="pending">裁床接口领料 · 待接入</span></div>
    <div class="monthly-filters"><label>核对月份<input v-model="month" type="month" aria-label="月结核对月份" /></label><label>登记方式<select v-model="channel" aria-label="月结登记方式"><option value="">手动 + 扫码</option><option value="MANUAL">手动</option><option value="SCAN">扫码</option></select></label><label>{{ direction === 'IN' ? '供应商' : direction === 'OUT' ? '领用方' : '往来方' }}<select v-model="party" aria-label="月结往来方"><option value="">全部{{ direction === 'IN' ? '供应商' : direction === 'OUT' ? '领用方' : '往来方' }}</option><option v-for="item in result?.parties ?? []" :key="item.key" :value="item.key">{{ item.direction === 'IN' ? '供应商' : '领用方' }} · {{ item.name || '原单未填写' }}</option></select></label><button :disabled="loading" @click="load">刷新汇总</button><button :disabled="loading || exporting || !result" @click="download">{{ exporting ? '正在导出…' : '导出当前对账表' }}</button></div>
    <p v-if="error" role="alert">{{ error }}</p><p v-if="loading" role="status">正在汇总实际收发记录…</p>
    <template v-if="result">
      <p class="monthly-basis">{{ result.basis }}。采购实收计入手动入库；打印单据和领料申请不算实际收发，调仓不算进货或领料。</p>
      <div class="monthly-totals"><div v-for="row in result.totals" :key="row.unit"><strong>{{ row.unit }}</strong><span v-if="direction !== 'OUT'">净实收 {{ row.net_received }}（手动 {{ row.manual_received }} / 扫码 {{ row.scan_received }}）</span><span v-if="direction !== 'IN'">净发料 {{ row.net_outbound }}（手动 {{ row.manual_outbound }} / 扫码 {{ row.scan_outbound }}）</span><span v-if="!direction">本月库存增减 {{ row.stock_change }}</span></div></div>
      <h3>按往来方、物料与单位汇总</h3>
      <div class="monthly-scroll" tabindex="0"><table><thead><tr><th>方向 / 往来方</th><th>物料</th><th>单位</th><th>凭证数</th><template v-if="direction !== 'OUT'"><th>手动净实收</th><th>扫码净实收</th><th>实收 / 冲销</th><th>净实收</th></template><template v-if="direction !== 'IN'"><th>手动净发料</th><th>扫码净发料</th><th>实发 / 冲销 / 退料</th><th>净发料</th></template></tr></thead><tbody><tr v-for="row in result.summary" :key="row.direction+row.party_key+row.item_code+row.unit"><td>{{ row.direction === 'IN' ? '供应商收料' : '领用方发料' }}<strong>{{ row.party_name || '原单未填写' }}</strong></td><td>{{ row.item_code }}<small>{{ row.item_name }}</small></td><td>{{ row.unit }}</td><td>{{ row.document_count }}</td><template v-if="direction !== 'OUT'"><td>{{ row.manual_received }}</td><td>{{ row.scan_received }}</td><td>{{ row.received }} / {{ row.receipt_reversed }}</td><td>{{ row.net_received }}</td></template><template v-if="direction !== 'IN'"><td>{{ row.manual_outbound }}</td><td>{{ row.scan_outbound }}</td><td>{{ row.issued }} / {{ row.issue_reversed }} / {{ row.returned }}</td><td>{{ row.net_outbound }}</td></template></tr></tbody></table></div>
      <h3>原单与库存凭证明细 · {{ result.details.length }} 笔</h3><p>车间退料单独列出，并从领用方净发料中扣回；供应商收料保持独立。没有编号或同名无法唯一识别的供应商按原单名称单独显示，数量仍计入汇总。</p>
      <div class="monthly-scroll" tabindex="0"><table><thead><tr><th>业务日期 / 类型</th><th>登记方式</th><th>归属方 / 原单名称</th><th>原单号 / 库存凭证</th><th>物料</th><th>数量 / 单位</th><th>参考单价 / 计价单位</th><th>币种 / 依据</th><th>经办人</th></tr></thead><tbody><tr v-for="row in result.details.slice(0, limit)" :key="row.id"><td>{{ row.date }}<small>{{ row.correction ? '冲销 · ' : '' }}{{ row.kind === 'RECEIPT' ? '供应商实收' : row.kind === 'ISSUE' ? '实际发料' : '车间退料' }}</small></td><td>{{ row.channel_label }}<small v-if="row.origin === 'PROCUREMENT_RECEIVING'">采购实收</small></td><td>{{ row.party_name || '原单未填写' }}<small>{{ row.recorded_party }} · {{ row.identity_basis }}</small></td><td><RouterLink v-if="row.document_id" to="/modules/pmc-warehouse/material-handover?factory=huakang-c">{{ row.source_no }}</RouterLink><span v-else>{{ row.source_no }}</span><small>{{ row.id }}</small><small v-if="row.original_id">关联 {{ row.original_id }}</small></td><td>{{ row.item_code }}<small>{{ row.item_name }}</small></td><td>{{ row.quantity }} {{ row.unit }}</td><td>{{ row.unit_price || '未记录' }} / {{ row.price_unit || '未注明' }}<small v-if="row.amount">原入库单金额 {{ row.amount }} {{ row.currency }}</small></td><td>{{ row.currency || '未注明' }}<small>{{ row.price_note || '依据未填写' }}</small></td><td>{{ row.actor_name }}</td></tr></tbody></table></div>
      <button v-if="result.details.length > limit" @click="limit += 50">显示更多原单</button>
      <p v-if="!result.details.length" class="monthly-empty">本月当前筛选下没有已登记的实际收发记录，请核对是否仍有单据未登记。</p>
      <p class="monthly-footnote">单价保留原单依据，不计算应付金额。当前是实时数量核对，尚未确认关账；新增、补录或冲销后需刷新。期初、期末结存与正式月结确认仍待建设。</p>
    </template>
  </section>
</template>

<style scoped>
.fabric-monthly{padding:20px;color:#253d35}.monthly-heading{display:flex;align-items:start;justify-content:space-between;gap:16px}h2{font-size:21px;font-weight:650}h3{font-size:15px;font-weight:650;margin:24px 0 10px}p,small{color:#6a7c74;font-size:13px;margin:8px 0}.live-label{background:#e9f6ef;color:#26745b;padding:5px 10px;border-radius:20px;white-space:nowrap;font-size:12px}.entry-links,.monthly-filters{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:20px 0}.entry-links a,a{color:#176d59;text-decoration:underline;text-underline-offset:3px}.pending{color:#89734d;font-size:12px}.monthly-filters{align-items:end}label{display:flex;flex-direction:column;gap:6px;font-size:13px}input,select,button{border:1px solid #cedbd4;border-radius:7px;background:white;padding:8px 12px;font:inherit;color:inherit}select{max-width:300px}button{cursor:pointer;color:#176d59}button:disabled{opacity:.5;cursor:default}.monthly-basis,.monthly-footnote{background:#f5f8f6;padding:12px;border-radius:8px}.monthly-totals{display:flex;flex-wrap:wrap;gap:12px}.monthly-totals>div{display:flex;flex-direction:column;gap:5px;background:#ecf6f0;border:1px solid #d8e9df;border-radius:9px;padding:14px;font-size:13px}.monthly-scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:13px;text-align:left}th{background:#f3f7f4;font-size:12px;white-space:nowrap}th,td{padding:12px;border-bottom:1px solid #e4ece7;vertical-align:top}td strong,small{display:block}td{min-width:90px}td small{max-width:280px;overflow-wrap:anywhere}.monthly-empty{padding:30px;text-align:center}[role=alert]{color:#a23526}@media(max-width:720px){.fabric-monthly{padding:14px}.monthly-heading{flex-direction:column}.monthly-filters{gap:10px}label,select{max-width:100%}.monthly-totals>div{width:100%}}
</style>
