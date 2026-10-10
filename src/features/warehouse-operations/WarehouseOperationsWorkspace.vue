<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { isAxiosError } from 'axios'
import { FocusScope } from 'reka-ui'
import WarehouseStockLedger from './WarehouseStockLedger.vue'
import WarehouseLocationPicker from './WarehouseLocationPicker.vue'
import WarehouseBulkIssueDialog from './WarehouseBulkIssueDialog.vue'
import { Button } from '@/components/ui/button'
import { getApiErrorMessage } from '@/lib/http'
import { warehouseOperationsApi as api, type WarehouseBatch, type WarehouseDocument, type WarehouseDocumentInput, type WarehouseDomain, type WarehouseOperationsWorkspace } from '@/api/warehouseOperations'
import { warehouseRequestId } from './requestIdentity'
import { documentProgress, remaining, operationLabels, operationsView, referenceKinds } from './operations'

const props = defineProps<{ warehouse: WarehouseDomain; section: string; view: string; title?: string; description?: string }>()
const data = ref<WarehouseOperationsWorkspace>(), loading = ref(false), saving = ref(false), error = ref(''), success = ref('')
const search = ref(''), offset = ref(0), from = ref(''), to = ref('')
const draft = ref<WarehouseDocumentInput>(), detail = ref<WarehouseDocument>(), frozen = ref<WarehouseDocumentInput>()
const formError = ref(''), initial = ref(''), fixedBatch = ref(false)
const bulkRows = ref<WarehouseBatch[]>()
const activeLocations = computed(() => (data.value?.locations ?? []).filter(row => row.status === 'ACTIVE'))
const formElement = ref<HTMLElement>(), detailElement = ref<HTMLElement>()
watch(() => !!draft.value, async open => { if (open) { await nextTick(); formElement.value?.querySelector<HTMLElement>('button')?.focus() } })
watch(() => !!detail.value, async open => { if (open) { await nextTick(); detailElement.value?.querySelector<HTMLElement>('button')?.focus() } })
let sequence = 0
const config = computed(() => operationsView(props.warehouse, props.section, props.view)!)
const stockMode = computed(() => config.value.stock)
const datesMatch = (value: string) => (!from.value || value >= from.value) && (!to.value || value <= to.value)
const matches = (value: unknown) => JSON.stringify(value).toLocaleLowerCase().includes(search.value.trim().toLocaleLowerCase())
const records = computed(() => {
  const movements = props.section === 'inventory' && props.view === 'movements'
  const rows = [...(data.value?.documents ?? []), ...(movements ? data.value?.original_receipts ?? [] : [])]
  return rows.filter(row => (!movements || ['RECEIPT', 'ISSUE', 'RETURN', 'TRANSFER', 'CORRECTION', 'PROCESS_SEND', 'PROCESS_RETURN', 'PACK_SEND'].includes(row.kind))
    && (!config.value.kinds.length || config.value.kinds.includes(row.kind)) && matches(row) && datesMatch(row.business_date))
    .sort((a, b) => b.business_date.localeCompare(a.business_date) || b.sequence - a.sequence)
})
const count = computed(() => records.value.length)
const visibleRecords = computed(() => records.value.slice(offset.value, offset.value + 50))
const needsBatch = computed(() => !!draft.value && ['ISSUE', 'TRANSFER', 'QUALITY', 'PROCESS_SEND', 'PACK_SEND', 'LOCATION_BIND'].includes(draft.value.kind))
const needsItem = computed(() => !!draft.value && ['RECEIPT', 'REQUEST', 'TASK'].includes(draft.value.kind))
const needsLocation = computed(() => !!draft.value && ['RECEIPT', 'RETURN', 'TRANSFER', 'PROCESS_RETURN', 'LOCATION_BIND'].includes(draft.value.kind))
const selectedBatch = computed(() => data.value?.stock.find(row => row.id === draft.value?.batch_id))
const originalOptions = computed(() => (data.value?.documents ?? []).filter(row => !row.reversed && referenceKinds(draft.value?.kind ?? 'RECEIPT').includes(row.kind)))
const tasks = computed(() => (data.value?.documents ?? []).filter(row => row.kind === 'TASK' && !row.reversed))
const selectableBatches = computed(() => (data.value?.stock ?? []).filter(row => Number(row.quantity) > 0 && (draft.value?.kind === 'LOCATION_BIND' ? !row.location_verified : row.location_verified) && (['TRANSFER', 'LOCATION_BIND'].includes(draft.value?.kind ?? '') || !['HOLD', 'REJECTED'].includes(row.quality_status))))
const dirty = computed(() => !!draft.value && JSON.stringify(draft.value) !== initial.value)
function permitted(kind: WarehouseDocumentInput['kind']) { return kind !== 'QUALITY' && !!data.value?.permissions[['CORRECTION', 'LOCATION_BIND'].includes(kind) ? 'correct' : 'operate'] }
async function load() {
  const ticket = ++sequence
  loading.value = true; error.value = ''
  try { const result = await api.workspace(props.warehouse); if (ticket === sequence) data.value = result }
  catch (e) { if (ticket === sequence) { data.value = undefined; error.value = getApiErrorMessage(e) } }
  finally { if (ticket === sequence) loading.value = false }
}
function begin(kind: WarehouseDocumentInput['kind'], batchId = '') {
  if (!permitted(kind) || !data.value) return
  const businessDate = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai' }).format(new Date())
  fixedBatch.value = !!batchId
  draft.value = { factory_id: 'huakang-c', request_id: warehouseRequestId(), expected_revision: data.value.revision, kind, business_date: businessDate,
    source_system: 'MANUAL', source_no: '', source_line: '1', source_version: '', item_code: '', item_name: '', unit: '', process_state: '', material_category: 'FABRIC',
    location: '', location_id: '', confirmed: false, lot: '', roll_no: '', quantity: '', consumed_quantity: '', counterparty: '', production_no: '', purpose: '', due_date: null,
    batch_id: batchId, original_id: '', task_id: '', quality_status: 'PENDING_INSPECTION', responsible_person: '', reason: '', allocations: [] }
  initial.value = JSON.stringify(draft.value); formError.value = ''; frozen.value = undefined
}
function issueRequest(row: WarehouseDocument) { begin('ISSUE'); if (draft.value) { draft.value.original_id = row.id; selectOriginal(); initial.value = JSON.stringify(draft.value) } }
function selectOriginal() {
  const original = data.value?.documents.find(row => row.id === draft.value?.original_id)
  if (draft.value) draft.value.counterparty = original?.data.counterparty ?? ''
}
function canLeave() {
  if (saving.value || frozen.value) { formError.value = '本次保存结果尚未确认，请使用原内容重试。'; return false }
  return !dirty.value || window.confirm('当前单据尚未保存，离开将丢失填写内容。确定离开？')
}
function close() { if (canLeave()) { draft.value = undefined; frozen.value = undefined } }
onBeforeRouteLeave(canLeave)
onBeforeRouteUpdate(canLeave)
function beforeUnload(event: BeforeUnloadEvent) { if (dirty.value || saving.value || frozen.value) { event.preventDefault(); event.returnValue = '' } }
window.addEventListener('beforeunload', beforeUnload)
onBeforeUnmount(() => { sequence++; window.removeEventListener('beforeunload', beforeUnload) })
watch(() => [props.warehouse, props.section, props.view], () => {
  draft.value = undefined; detail.value = undefined; bulkRows.value = undefined; frozen.value = undefined; success.value = ''; search.value = ''; from.value = ''; to.value = ''; offset.value = 0; void load()
}, { immediate: true })
watch([search, from, to], () => { offset.value = 0 })
async function submit() {
  if (!draft.value || saving.value) return
  if (needsLocation.value && !activeLocations.value.some(row => row.id === draft.value?.location_id)) { formError.value = '请选择基础资料中已启用的仓位'; return }
  if (draft.value.location_id) draft.value.location = activeLocations.value.find(row => row.id === draft.value?.location_id)?.label ?? ''
  const input = frozen.value ?? JSON.parse(JSON.stringify(draft.value)) as WarehouseDocumentInput
  if (input.kind !== 'ISSUE') input.allocations = []
  if (input.kind === 'PROCESS_SEND') input.counterparty = tasks.value.find(row => row.id === input.task_id)?.data.counterparty ?? ''
  saving.value = true; formError.value = ''
  try {
    await api.post(props.warehouse, input)
    draft.value = undefined; frozen.value = undefined; success.value = '单据已保存，可在记录中查看来源和经办信息。'; await load()
  } catch (e) {
    const status = isAxiosError(e) ? e.response?.status : undefined
    if (status === undefined || status === 408 || status >= 500) {
      frozen.value = input; formError.value = '保存结果尚未确认。已保留本次内容，请点击“用原内容重试”，避免重复登记。'
    } else {
      frozen.value = undefined; formError.value = getApiErrorMessage(e)
      if (status === 409) { await load(); if (draft.value && data.value) { draft.value.expected_revision = data.value.revision; draft.value.request_id = warehouseRequestId() } }
    }
  } finally { saving.value = false }
}
function rowTitle(row: WarehouseDocument) { return row.data.item_name || row.batch_snapshot?.item_name || row.data.source_no }
</script>

<template>
  <div class="warehouse-operations-live">
    <div v-if="!stockMode" class="warehouse-table-heading"><div><h2>{{ title || '收发记录' }}</h2><p>{{ description || '查看实际办理记录，点击详情追溯原单与经办信息。' }}</p></div><Button variant="outline" :disabled="loading" @click="load">刷新</Button></div>
    <p v-if="loading" role="status" class="fabric-message">正在读取仓库记录…</p>
    <p v-if="error" role="alert" class="fabric-error">{{ error }}</p>
    <p v-if="success" role="status" class="fabric-message">{{ success }}</p>
    <WarehouseStockLedger v-if="data && stockMode" :key="`${warehouse}:${view}`" :title="title" :rows="view === 'holds' ? data.stock.filter(row => ['HOLD', 'REJECTED'].includes(row.quality_status)) : data.stock" :warehouse="warehouse" :loading="loading" :can-operate="permitted('ISSUE')" :can-bind="permitted('LOCATION_BIND')" @bulk="ids => bulkRows = data?.stock.filter(row => ids.includes(row.id))" @action="begin" @refresh="load" />
    <WarehouseBulkIssueDialog v-if="bulkRows && data" :rows="bulkRows" :warehouse="warehouse" :revision="data.revision" @close="bulkRows = undefined" @saved="bulkRows = undefined; load()" />
    <template v-if="data && !stockMode">
      <div class="warehouse-operation-toolbar"><label class="grow">查找记录<input v-model="search" type="search" placeholder="物料名称 / 单号 / 领用方 / 仓位" aria-label="查找仓库收发" /></label><label>开始日期<input v-model="from" type="date" aria-label="收发开始日期" /></label><label>结束日期<input v-model="to" type="date" aria-label="收发结束日期" /></label><Button v-for="kind in config.actions" :key="kind" :disabled="loading || !permitted(kind)" @click="begin(kind)">{{ operationLabels[kind] }}</Button></div>
      <div class="warehouse-table-scroll" tabindex="0" role="region" aria-label="业务记录">
        <table class="warehouse-records-table"><thead><tr><th>业务 / 日期</th><th>物料 / 数量进度</th><th>仓位 / 去向</th><th>来源凭证</th><th>经办人</th><th>操作</th></tr></thead><tbody>
          <tr v-for="row in visibleRecords" :key="row.id">
            <td><strong>{{ operationLabels[row.kind] }}</strong><small>{{ row.business_date }}</small></td>
            <td><strong>{{ rowTitle(row) }}</strong><small>{{ row.data.item_code || row.batch_snapshot?.item_code }}<template v-if="row.data.process_state || row.batch_snapshot?.process_state"> · {{ row.data.process_state || row.batch_snapshot?.process_state }}</template></small><span v-if="row.data.quantity">{{ row.data.quantity }} {{ row.data.unit || row.batch_snapshot?.unit }}</span><small>{{ documentProgress(row) }}</small></td>
            <td><template v-if="row.kind === 'TRANSFER'">{{ row.batch_snapshot?.location }} → {{ row.data.location }}</template><template v-else>{{ row.data.location || row.batch_snapshot?.location || '—' }}<small>{{ row.data.counterparty || '—' }}</small></template></td>
            <td>{{ row.data.source_no || '未另填凭证' }}<small v-if="row.data.original_id">已关联原单</small></td>
            <td>{{ row.actor_name }}</td><td class="warehouse-record-actions"><Button v-if="row.kind === 'REQUEST' && !row.reversed && Number(remaining(row.data.quantity, row.issued_quantity)) > 0" size="sm" :disabled="!permitted('ISSUE')" @click="issueRequest(row)">办理出库</Button><Button variant="outline" size="sm" @click="detail = row">详情</Button></td>
          </tr>
        </tbody></table>
      </div>
      <div v-if="!count" class="warehouse-empty" role="status"><h3>暂无{{ title || '业务记录' }}</h3><p>{{ search || from || to ? '试试调整筛选条件。' : '办理对应业务后，记录会显示在这里。' }}</p></div>
      <footer class="warehouse-list-footer"><span>共 {{ count }} 条</span><div><Button variant="outline" size="sm" :disabled="offset === 0" @click="offset -= 50">上一页</Button><Button variant="outline" size="sm" :disabled="offset + 50 >= count" @click="offset += 50">下一页</Button></div></footer>
    </template>
    <Teleport to="body">
      <div v-if="draft" class="warehouse-operation-overlay"><FocusScope as-child loop trapped><form ref="formElement" class="warehouse-operation-dialog" role="dialog" aria-modal="true" :aria-label="operationLabels[draft.kind]" @keydown.esc.prevent="close" @submit.prevent="submit">
        <header><div><h2>{{ operationLabels[draft.kind] }}</h2><p>{{ warehouse === 'fabric' ? '布料仓' : '半成品仓' }} · 华康 C</p></div><Button type="button" variant="outline" :disabled="saving || !!frozen" @click="close">关闭</Button></header>
        <div class="warehouse-operation-form">
          <p v-if="draft.kind === 'CORRECTION'" class="fabric-message">冲销保留原单和原因。有后续质检、领用或交接的单据不能直接冲销；核对后再登记正确单据。</p>
          <p v-if="draft.kind === 'PACK_RECEIVE'" class="fabric-message">此操作为仓库代录包装接收回执，须填写实际接收人，回执备注可选填；不会再次扣库存。</p>
          <p v-if="draft.kind === 'PROCESS_RETURN'" class="fabric-message">本次产出量按加工任务的产品和单位记录；本轮核销量按原发出单位填写，不能直接用产出量相减。</p>
          <div v-if="selectedBatch" class="operation-stock-card"><strong>{{ selectedBatch.item_name }}</strong><span>{{ selectedBatch.item_code }} · {{ selectedBatch.lot || '—' }} <template v-if="selectedBatch.roll_no">· 卷 {{ selectedBatch.roll_no }}</template></span><div><span>当前仓位：{{ selectedBatch.location_label || selectedBatch.location }} <b v-if="!selectedBatch.location_verified">（待核实）</b></span><strong>结余 {{ selectedBatch.quantity }} {{ selectedBatch.unit }}</strong></div></div>
          <p v-if="needsLocation && !activeLocations.length" class="fabric-error">尚无可用仓位，请先到基础资料建立仓库与仓位。</p>
          <p v-if="draft.kind === 'LOCATION_BIND'" class="fabric-message">核实旧记录的实际存放位置，只关联正式仓位，不增加或扣减库存。实物已经移动的情况需另行登记调仓。</p>
          <fieldset :disabled="saving || !!frozen" class="warehouse-operation-fields">
            <label>业务日期<input v-model="draft.business_date" type="date" required aria-label="业务日期" /></label>
            <label>来源单号 / 手工凭证号{{ needsItem ? '' : '（选填）' }}<input v-model.trim="draft.source_no" :required="needsItem" maxlength="128" aria-label="来源单号" :placeholder="needsItem ? '保留原单编号，手工单可自行编号' : '有外部凭证时填写，已关联的批次和原单会保留'" /></label>
            <template v-if="needsItem"><label>来源明细编号<input v-model.trim="draft.source_line" required maxlength="128" aria-label="来源明细编号" /></label><label>来源版本（选填）<input v-model.trim="draft.source_version" maxlength="128" aria-label="来源版本" /></label><label>物料 / 产品编码<input v-model.trim="draft.item_code" required maxlength="128" aria-label="物料产品编码" /></label><label>名称规格<input v-model.trim="draft.item_name" required maxlength="255" aria-label="名称规格" /></label><label>原单位<input v-model.trim="draft.unit" required maxlength="32" aria-label="原单位" placeholder="码、米、件等" /></label><label v-if="warehouse === 'semi'">{{ draft.kind === 'TASK' ? '计划产出加工状态' : '加工状态' }}<input v-model.trim="draft.process_state" required maxlength="64" aria-label="加工状态" placeholder="如车缝完成、冲棉完成" /></label><label v-else>物料分类<select v-model="draft.material_category" aria-label="物料分类"><option value="FABRIC">布料</option><option value="ACCESSORY">辅料</option><option value="THREAD">线</option></select></label><label>来源单位 / 领用方 / 加工方<input v-model.trim="draft.counterparty" required maxlength="255" aria-label="往来单位" /></label><label>生产 / 放产单号（选填）<input v-model.trim="draft.production_no" maxlength="128" aria-label="生产放产单号" /></label><label v-if="draft.kind !== 'RECEIPT'">{{ draft.kind === 'TASK' ? '加工工序 / 返工说明' : '领用用途（选填）' }}<input v-model.trim="draft.purpose" :required="draft.kind === 'TASK'" maxlength="255" aria-label="用途工序" /></label><label v-if="draft.kind === 'TASK'">要求回货日期（选填）<input v-model="draft.due_date" type="date" aria-label="要求回货日期" /></label></template>
            <label v-if="referenceKinds(draft.kind).length" class="full">{{ draft.kind === 'ISSUE' ? '关联领料申请（选填）' : '关联原单' }}<select v-model="draft.original_id" :required="draft.kind !== 'ISSUE'" aria-label="关联原单" @change="selectOriginal"><option value="">{{ draft.kind === 'ISSUE' ? '不关联申请，直接出库' : '请选择原发出单' }}</option><option v-for="row in originalOptions" :key="row.id" :value="row.id">{{ row.data.source_no }} · {{ rowTitle(row) }} · {{ documentProgress(row) }} · {{ row.id }}</option></select></label>
            <label v-if="draft.kind === 'PROCESS_SEND'" class="full">本轮加工任务<select v-model="draft.task_id" required aria-label="本轮加工任务"><option value="">请选择任务</option><option v-for="row in tasks" :key="row.id" :value="row.id">{{ row.data.source_no }} · {{ row.data.item_name }} · {{ row.data.process_state }} · {{ row.data.counterparty }}</option></select></label>
            <label v-if="needsBatch" class="full">{{ draft.kind === 'TRANSFER' ? '来源批次 / 仓位' : '出入库批次' }}<select v-model="draft.batch_id" required :disabled="fixedBatch" aria-label="实际批次"><option value="">请选择批次</option><option v-for="row in selectableBatches" :key="row.id" :value="row.id">{{ row.item_code }} · {{ row.item_name }} · {{ row.process_state }} · {{ row.location_label || row.location }} · {{ row.lot }} · 结余 {{ row.quantity }} {{ row.unit }} · {{ row.received_on }} · {{ row.id.slice(-8) }}</option></select><small v-if="selectedBatch">原单位：{{ selectedBatch.unit }}，实物结余：{{ selectedBatch.quantity }}，可出库：{{ selectedBatch.available_quantity }}</small></label>
            <label v-if="!['QUALITY', 'CORRECTION', 'LOCATION_BIND'].includes(draft.kind)">{{ draft.kind === 'REQUEST' ? '申请数量' : draft.kind === 'TASK' ? '计划产出数量' : draft.kind === 'PROCESS_RETURN' ? '本次实际产出数量' : '本次实际数量' }}<input v-model.trim="draft.quantity" required inputmode="decimal" aria-label="本次数量" placeholder="请按本次实物填写" /></label>
            <label v-if="draft.kind === 'PROCESS_RETURN'">本次核销发出量（原发出单位）<input v-model.trim="draft.consumed_quantity" required inputmode="decimal" aria-label="核销发出量" /></label>
            <label v-if="draft.kind === 'ISSUE'">领用部门 / 领用方<input v-model.trim="draft.counterparty" required maxlength="255" aria-label="领用方" :readonly="!!draft.original_id" placeholder="例如裁床、车间或外发厂" /></label>
            <label v-if="draft.kind === 'ISSUE'">领用用途（选填）<input v-model.trim="draft.purpose" maxlength="255" aria-label="领用用途" /></label>
            <label v-if="draft.kind === 'PACK_SEND'">包装接收部门<input v-model.trim="draft.counterparty" required maxlength="255" aria-label="包装接收部门" /></label>
            <template v-if="needsLocation"><label>{{ draft.kind === 'LOCATION_BIND' ? '实际所在仓位' : draft.kind === 'TRANSFER' ? '调入仓位' : '入库仓位' }}<WarehouseLocationPicker v-model="draft.location_id" :locations="activeLocations" /></label><label v-if="draft.kind === 'RECEIPT' || draft.kind === 'PROCESS_RETURN'">缸号 / 批号{{ warehouse === 'fabric' && draft.material_category === 'FABRIC' ? '' : '（选填）' }}<input v-model.trim="draft.lot" :required="warehouse === 'fabric' && draft.material_category === 'FABRIC'" maxlength="128" aria-label="缸号批号" /></label><label v-if="warehouse === 'fabric' && draft.kind === 'RECEIPT'">卷号（选填）<input v-model.trim="draft.roll_no" maxlength="128" aria-label="卷号" /></label></template>
            <label v-if="draft.kind === 'PACK_RECEIVE'">实际接收人<input v-model.trim="draft.responsible_person" required maxlength="128" aria-label="实际接收人" /></label>
            <label class="full">{{ draft.kind === 'LOCATION_BIND' ? '仓位核对依据（必填）' : draft.kind === 'CORRECTION' ? '冲销原因（必填）' : '业务依据 / 差异原因 / 备注（选填）' }}<textarea v-model.trim="draft.reason" :required="['CORRECTION', 'LOCATION_BIND'].includes(draft.kind)" maxlength="1000" rows="3" aria-label="业务依据" :placeholder="draft.kind === 'LOCATION_BIND' ? '请填写实物位置的核对依据' : draft.kind === 'CORRECTION' ? '请说明录错或冲销的原因' : '有需要补充的情况再填写'" /></label>
            <label v-if="draft.kind === 'LOCATION_BIND'" class="full"><span><input v-model="draft.confirmed" type="checkbox" required aria-label="已核实实物仓位" /> 已核实实物在所选仓位，本次只补齐仓位身份</span></label>
            <p v-if="draft.kind === 'TRANSFER'" class="full fabric-message">来源仓位减少、目标仓位增加；总库存和原始入库日期保持不变。</p>
            <div v-if="draft.kind === 'ISSUE'" class="full warehouse-operation-allocations"><h3>放产单用料分配（选填）</h3><p>需要按放产单分配时再添加；填写后合计须等于本次出库数量。</p><div v-for="(allocation, index) in draft.allocations" :key="index"><label>放产单 / 用途编号<input v-model.trim="allocation.production_no" required :aria-label="`分配编号 ${index + 1}`" /></label><label>分配数量<input v-model.trim="allocation.quantity" required inputmode="decimal" :aria-label="`分配数量 ${index + 1}`" /></label><Button type="button" variant="outline" @click="draft.allocations.splice(index, 1)">移除</Button></div><Button type="button" variant="outline" :disabled="draft.allocations.length >= 100" @click="draft.allocations.push({ production_no: '', quantity: '' })">添加放产单分配</Button></div>
          </fieldset>
          <p v-if="formError" role="alert" class="fabric-error">{{ formError }}</p>
        </div>
        <footer><span>保存后保留原单与经办记录</span><Button type="submit" :disabled="saving || (needsLocation && !activeLocations.length)">{{ saving ? '正在保存…' : frozen ? '用原内容重试' : '确认保存' }}</Button></footer>
      </form></FocusScope></div>
      <div v-if="detail" class="warehouse-operation-overlay"><FocusScope as-child loop trapped><section ref="detailElement" @keydown.esc.prevent="detail = undefined" class="warehouse-operation-dialog" role="dialog" aria-modal="true" aria-label="业务单据详情"><header><div><h2>{{ operationLabels[detail.kind] }}</h2><p>{{ detail.id }}</p></div><Button variant="outline" @click="detail = undefined">关闭详情</Button></header><div class="warehouse-operation-form"><dl class="warehouse-operation-detail"><div><dt>业务日期</dt><dd>{{ detail.business_date }}</dd></div><div><dt>来源</dt><dd>{{ detail.data.source_no || '未填写外部凭证' }}<template v-if="detail.data.source_no"> / {{ detail.data.source_line }} {{ detail.data.source_version }}</template></dd></div><div><dt>物料 / 产品</dt><dd>{{ rowTitle(detail) }} {{ detail.data.item_code || detail.batch_snapshot?.item_code }}</dd></div><div><dt>数量与进度</dt><dd v-if="detail.kind === 'LOCATION_BIND'">数量未变，核实时结余 {{ detail.batch_snapshot?.quantity }} {{ detail.data.unit }}</dd><dd v-else>{{ detail.data.quantity }} {{ detail.data.unit || detail.batch_snapshot?.unit }}<br />{{ documentProgress(detail) }}</dd></div><div><dt>原单 / 加工任务</dt><dd>{{ detail.data.original_id || detail.data.task_id || '—' }}</dd></div><div v-if="detail.kind === 'LOCATION_BIND'"><dt>核实前仓位</dt><dd>{{ detail.batch_snapshot?.location || '未填写' }}</dd></div><div><dt>仓位 / 缸号</dt><dd>{{ detail.data.location || detail.batch_snapshot?.location }} / {{ detail.data.lot || detail.batch_snapshot?.lot }}</dd></div><div><dt>加工状态 / 工序</dt><dd>{{ detail.data.process_state || detail.batch_snapshot?.process_state || '—' }} / {{ detail.data.purpose || '—' }}</dd></div><div><dt>往来单位 / 确认人</dt><dd>{{ detail.data.counterparty || '—' }} / {{ detail.data.responsible_person || '—' }}</dd></div><div><dt>依据</dt><dd>{{ detail.data.reason || '—' }}</dd></div><div><dt>登记</dt><dd>{{ detail.actor_name }} · {{ detail.occurred_at }}</dd></div></dl><h3 v-if="detail.data.allocations.length">用料分配</h3><p v-for="(allocation, index) in detail.data.allocations" :key="index">{{ allocation.production_no }}：{{ allocation.quantity }}</p></div></section></FocusScope></div>
    </Teleport>
  </div>
</template>

<style scoped>
.operation-stock-card{border:1px solid var(--border);border-radius:9px;padding:16px;background:var(--muted);display:grid;gap:6px;margin-bottom:20px}.operation-stock-card>span{font-size:12px;color:var(--muted-foreground)}.operation-stock-card>div{display:flex;justify-content:space-between;gap:16px;font-size:13px}.operation-stock-card b{color:#b45309}
.warehouse-operation-toolbar{padding:0 24px}.warehouse-records-table{width:100%;border-collapse:collapse;text-align:left}.warehouse-records-table th{padding:12px 20px}.warehouse-records-table td{padding:16px 20px;border-bottom:1px solid var(--border);vertical-align:top;min-width:120px}.warehouse-records-table td strong{font-size:14px;font-weight:600}.warehouse-record-actions{white-space:nowrap}.warehouse-record-actions button+button{margin-left:8px}.warehouse-operations-live>.fabric-message,.warehouse-operations-live>.fabric-error{margin:16px 24px}

.warehouse-operation-summary{display:flex;gap:24px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px 16px;font-size:13px;margin:12px 0}.warehouse-operation-summary strong{font-size:18px;margin-left:8px;color:#0f766e}.warehouse-operation-toolbar{display:flex;align-items:end;flex-wrap:wrap;gap:12px;margin:16px 0}.grow{flex:1;min-width:200px}.warehouse-operation-toolbar label,.warehouse-operation-fields label{display:flex;flex-direction:column;gap:6px;font-size:13px;color:#334155}input,select,textarea{border:1px solid #cbd5e1;border-radius:6px;background:white;padding:8px 10px;min-width:0;color:#0f172a;font:inherit}input:focus,select:focus,textarea:focus{outline:2px solid #99f6e4;outline-offset:1px}small{display:block;font-size:12px;color:#64748b;margin-top:4px;overflow-wrap:anywhere}.warehouse-quality{background:#fff7ed;color:#9a3412;border-radius:4px;padding:3px 8px;white-space:nowrap}.warehouse-quality.qualified{background:#ecfdf5;color:#047857}.warehouse-operation-overlay{position:fixed;inset:0;background:#0f172a80;z-index:90;display:grid;place-items:center;padding:24px}.warehouse-operation-dialog{display:flex;flex-direction:column;width:min(960px,100%);max-height:92dvh;background:white;border-radius:12px;box-shadow:0 20px 60px #0003;overflow:hidden}.warehouse-operation-dialog header,.warehouse-operation-dialog footer{padding:16px 24px;display:flex;justify-content:space-between;align-items:center;gap:12px;border-bottom:1px solid #e2e8f0}.warehouse-operation-dialog h2{font-size:20px;font-weight:600}.warehouse-operation-dialog header p,.warehouse-operation-dialog footer span{font-size:12px;color:#64748b}.warehouse-operation-dialog footer{border-bottom:0;border-top:1px solid #e2e8f0}.warehouse-operation-form{padding:20px 24px;overflow:auto}.warehouse-operation-fields{display:grid;grid-template-columns:1fr 1fr;gap:16px;border:0}.full{grid-column:1/-1}.warehouse-operation-fields:disabled{opacity:.65}.warehouse-operation-allocations{background:#f8fafc;border-radius:8px;padding:16px}.warehouse-operation-allocations h3{font-weight:600}.warehouse-operation-allocations p{font-size:12px;color:#64748b;margin-bottom:12px}.warehouse-operation-allocations>div{display:flex;align-items:end;gap:12px;margin-bottom:12px}.warehouse-operation-allocations label{flex:1}.warehouse-operation-detail{display:grid;grid-template-columns:1fr 1fr;gap:20px}.warehouse-operation-detail dt{color:#64748b;font-size:12px;margin-bottom:6px}.warehouse-operation-detail dd{font-size:14px;white-space:pre-wrap;overflow-wrap:anywhere}.warehouse-operation-form>.fabric-message{margin-bottom:16px}@media(max-width:640px){.warehouse-operation-summary{flex-direction:column;gap:8px}.warehouse-operation-overlay{padding:8px}.warehouse-operation-dialog{max-height:96dvh}.warehouse-operation-fields,.warehouse-operation-detail{grid-template-columns:1fr}.warehouse-operation-dialog header,.warehouse-operation-dialog footer,.warehouse-operation-form{padding:16px}.warehouse-operation-allocations>div{flex-wrap:wrap}.warehouse-operation-allocations label{min-width:120px}.warehouse-operation-toolbar label{flex:1}.warehouse-operation-toolbar input{width:100%}}
</style>
