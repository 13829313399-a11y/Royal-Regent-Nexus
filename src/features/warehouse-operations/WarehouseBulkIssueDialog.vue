<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { FocusScope } from 'reka-ui'
import { Button } from '@/components/ui/button'
import { warehouseOperationsApi as api, type WarehouseBatch, type WarehouseBulkIssue, type WarehouseDomain } from '@/api/warehouseOperations'
import { warehouseRequestId } from './requestIdentity'
import { receiptQuantity } from './receiptQuantities'
import { getApiErrorMessage } from '@/lib/http'
const props = defineProps<{ rows: WarehouseBatch[]; revision: number; warehouse: WarehouseDomain }>()
const emit = defineEmits<{ close: []; saved: [] }>()
const date = ref(new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai' }).format(new Date()))
const counterparty = ref(''), reason = ref(''), saving = ref(false), error = ref(''), frozen = ref<WarehouseBulkIssue>()
const currentRows = ref(props.rows), revision = ref(props.revision), needsRefresh = ref(false)
const lines = ref(props.rows.map(row => ({ batch_id: row.id, quantity: '', counterparty: '' })))
function canLeave() { return !saving.value && !frozen.value && (!(counterparty.value || reason.value || lines.value.some(row => row.quantity || row.counterparty)) || window.confirm('出库尚未保存，确定放弃填写？')) }
function close() { if (canLeave()) emit('close') }
onBeforeRouteLeave(canLeave); onBeforeRouteUpdate(canLeave)
function unload(event: BeforeUnloadEvent) { if (saving.value || frozen.value || counterparty.value || lines.value.some(row => row.quantity)) { event.preventDefault(); event.returnValue = '' } }
window.addEventListener('beforeunload', unload); onBeforeUnmount(() => window.removeEventListener('beforeunload', unload))
async function save() {
  if (saving.value) return
  if (needsRefresh.value) { await refreshStock(); return }
  if (!frozen.value && currentRows.value.some(row => !row.location_verified || ['HOLD', 'REJECTED'].includes(row.quality_status))) { error.value = '所选库存状态已变化，请先核实仓位或由 QC 处理后再出库。'; return }
  if (!frozen.value && lines.value.some((row, i) => { const q = receiptQuantity(row.quantity), balance = receiptQuantity(currentRows.value[i]!.quantity); return q === undefined || q <= 0n || balance === undefined || q > balance })) { error.value = '每行实发须大于零且不超过该行结余，最多六位小数。'; return }
  const body = frozen.value ?? { factory_id: 'huakang-c' as const, request_id: warehouseRequestId(), expected_revision: revision.value, business_date: date.value, counterparty: counterparty.value, reason: reason.value, items: lines.value.map(row => ({ ...row })) }
  saving.value = true; error.value = ''
  try { await api.bulkIssue(props.warehouse, body); emit('saved') }
  catch (e) { const status = (e as { response?: { status?: number } }).response?.status; if (!status || status === 408 || status >= 500) { frozen.value = body; error.value = '保存结果待确认，请用原内容重试，不能另开单重复出库。' } else { frozen.value = undefined; error.value = getApiErrorMessage(e); if (status === 409) await refreshStock() } }
  finally { saving.value = false }
}
async function refreshStock() {
  saving.value = true; needsRefresh.value = true
  try {
    const fresh = await api.workspace(props.warehouse)
    if (!fresh.permissions.operate) { error.value = '当前已无出库权限，请联系负责人。'; return }
    currentRows.value = currentRows.value.map(row => fresh.stock.find(batch => batch.id === row.id) ?? { ...row, quantity: '0', available_quantity: '0', location_verified: false })
    revision.value = fresh.revision; needsRefresh.value = false
    error.value = '库存已更新，已保留填写内容。请核对最新结余后再次确认出库。'
  } catch(e) { error.value = `未能刷新库存，填写内容已保留。${getApiErrorMessage(e)}` }
  finally { saving.value = false }
}
</script>
<template>
  <Teleport to="body"><div class="bulk-overlay"><FocusScope as-child loop trapped><form class="bulk-dialog" role="dialog" aria-modal="true" aria-label="批量出库" @submit.prevent="save" @keydown.esc.prevent="close">
    <header><div><h2>批量出库 · {{ rows.length }} 项</h2><p>按每个批次和仓位填写实发数量，全部通过校验后一起记账。</p></div><Button type="button" variant="outline" :disabled="saving || !!frozen" @click="close">关闭</Button></header>
    <fieldset :disabled="saving || !!frozen"><div class="bulk-fields"><label>业务日期<input v-model="date" type="date" required aria-label="批量出库日期" /></label><label>统一领用部门 / 领用方<input v-model.trim="counterparty" required maxlength="255" aria-label="批量领用方" /></label></div>
      <div class="bulk-table"><table><thead><tr><th>物料 / 批次</th><th>仓库 / 仓位</th><th>当前结余</th><th>本次实发</th><th>本行去向（选填）</th></tr></thead><tbody><tr v-for="(row,index) in currentRows" :key="row.id"><td><strong>{{ row.item_name }}</strong><small>{{ row.item_code }} · {{ row.lot || '—' }} <template v-if="row.roll_no">· 卷 {{ row.roll_no }}</template></small></td><td>{{ row.location_label || row.location }}</td><td>{{ row.quantity }} {{ row.unit }}</td><td><input v-model.trim="lines[index]!.quantity" required inputmode="decimal" :aria-label="`本次出库数量 ${row.id}`" :placeholder="row.unit" /></td><td><input v-model.trim="lines[index]!.counterparty" maxlength="255" :aria-label="`本行去向 ${row.id}`" placeholder="沿用统一领用方" /></td></tr></tbody></table></div>
      <label class="bulk-note">备注（选填）<textarea v-model.trim="reason" maxlength="1000" rows="2" /></label>
    </fieldset><p v-if="error" role="alert" class="fabric-error">{{ error }}</p><footer><span>按实际数量扣减，不跨单位合计。</span><Button :disabled="saving" type="submit">{{ saving ? '正在处理…' : frozen ? '用原内容重试' : needsRefresh ? '刷新库存后重试' : '确认批量出库' }}</Button></footer>
  </form></FocusScope></div></Teleport>
</template>
<style scoped>
.bulk-overlay{position:fixed;inset:0;z-index:90;background:#0f172a80;display:grid;place-items:center;padding:20px}.bulk-dialog{width:min(1050px,100%);max-height:92dvh;overflow:auto;border-radius:12px;background:var(--card);color:var(--foreground)}header,footer{padding:20px 24px;display:flex;justify-content:space-between;align-items:center;gap:20px;border-bottom:1px solid var(--border)}h2{font-size:20px;font-weight:600}p,small,footer span{font-size:12px;color:var(--muted-foreground)}fieldset{padding:24px;border:0}.bulk-fields{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px}label{display:flex;flex-direction:column;gap:8px;font-size:13px}input,textarea{min-width:0;max-width:100%;border:1px solid var(--border);border-radius:6px;padding:9px;background:var(--card);font:inherit}.bulk-table{overflow:auto}table{width:100%;text-align:left;border-collapse:collapse;font-size:13px}th,td{padding:12px;border-bottom:1px solid var(--border)}th{background:var(--muted);white-space:nowrap}td input{width:140px}small{display:block;margin-top:4px}.bulk-note{margin-top:20px}.fabric-error{margin:0 24px}footer{border-top:1px solid var(--border)}@media(max-width:640px){.bulk-fields{grid-template-columns:1fr}header,footer,fieldset{padding:16px}.bulk-overlay{padding:8px}}
</style>
