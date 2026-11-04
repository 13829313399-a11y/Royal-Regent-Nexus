<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import axios from 'axios'
import { DialogRoot, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogDescription } from 'reka-ui'
import CartonOrderEditorForm from './CartonOrderEditorForm.vue'
import CartonOrderPaperEditor from './CartonOrderPaperEditor.vue'
import CartonOrderPaperSection from './CartonOrderPaperSection.vue'
import CartonOrderQuantityField from './CartonOrderQuantityField.vue'
import CartonQuantityRuleInput from './CartonQuantityRuleInput.vue'
import CartonPaperWeightFields from './CartonPaperWeightFields.vue'
import CartonOrderNoteField from './CartonOrderNoteField.vue'
import { cartonMasterApi, masterPaperOptions, masterDueRules, type MasterRecord } from '@/api/cartonMaster'
import { cartonProcurementApi, type CartonOrderResponse } from '@/api/cartonProcurement'
import { cartonCustomerResponsibilitiesApi } from '@/api/cartonCustomerResponsibilities'
import { cartonScheduleBatchApi, type ScheduleBatchBody, type ScheduleBatchLineOverride } from '@/api/cartonScheduleBatch'
import { batchPaperPreview, batchPaperError, batchSourceError, batchWeightError, effectiveBatchWeights, emptyBatchPapers, isScheduleBox, pendingScheduleBatches, sameScheduleItem, scheduleBatchConfigurations, scheduleSourceKey, readScheduleBatchDraft, writeScheduleBatchDraft, clearScheduleBatchDraft, scheduleBatchDraftKey, type BatchPaper, type BatchOverrides, type ScheduleBatchPreview, type ScheduleBatchDraft } from '@/features/carton-procurement/scheduleBatch'
import { referencesAfterRemoval, reusableQuantityRule } from '@/features/carton-procurement/paperQuantity'
import { isCardPaper, showPaperWeightInputs } from '@/features/carton-procurement/paperCatalog'
import { formatBusinessDate } from '@/lib/dateTime'
import { getApiErrorMessage } from '@/lib/http'
import { createRandomUuid } from '@/lib/randomUuid'
import '@/features/carton-procurement/layout.css'

const props = defineProps<{ open: boolean; factoryId: string; viewerKey: string; identityKey: string; selection: ScheduleBatchPreview[]; defaultDimension?: 'cm' | 'inch' | 'mm' }>()
const emit = defineEmits<{ 'update:open': [value: boolean]; saved: [orders: CartonOrderResponse[]]; 'draft-change': [] }>()
const rows = ref<ScheduleBatchPreview[]>([]), records = ref<MasterRecord[]>([]), papers = ref<BatchPaper[]>([])
const planned = ref(''), configId = ref(''), configRevision = ref(0), error = ref(''), busy = ref(false), loading = ref(false), frozen = ref(false)
const note = ref(''), rush = ref(false), rushReason = ref(''), overrides = ref<BatchOverrides>({}), expanded = ref<string[]>([])
const storageError = ref(''), restored = ref(false), changedSource = ref(false), discardConfirm = ref(false)
const storedExists = ref(false)
const cacheKey = computed(() => `schedule:${props.identityKey}:${props.factoryId}`)
const configurations = computed(() => rows.value[0] ? scheduleBatchConfigurations(records.value, rows.value[0].source) : [])
const configuration = computed(() => configurations.value.find(row => row.id === configId.value))
const configChanged = computed(() => !!configId.value && (!configuration.value || configuration.value.revision !== configRevision.value))
let generation = 0, controller = new AbortController(), ready = false
let activeScope: { identity: string; factory: string } | null = null
const qualityOptions = computed(() => masterPaperOptions(records.value, 'paper_quality'))
const packagingOptions = computed(() => masterPaperOptions(records.value, 'packaging_type'))
const specificationOptions = computed(() => masterPaperOptions(records.value, 'specification'))
const unitOptions = computed(() => [...new Set(['个', '张', '套', ...records.value.filter(row => row.kind === 'CONFIG' && row.status === 'ACTIVE').flatMap(row => (row.data.lines || []).map(line => line.unit).filter(Boolean))])])
const dimension = () => props.defaultDimension === 'inch' ? 'in' : props.defaultDimension || 'cm'
const businessTodayIso = () => formatBusinessDate(new Date().toISOString())
const packingDiffers = computed(() => new Set(rows.value.map(row => row.source.carton_rule)).size > 1)
function snapshot(): ScheduleBatchDraft {
  return JSON.parse(JSON.stringify({ preview: rows.value, papers: papers.value, planned: planned.value, configId: configId.value, configRevision: configRevision.value,
    note: note.value, rush: rush.value, rushReason: rushReason.value, overrides: overrides.value, attempt: pendingScheduleBatches.get(cacheKey.value) }))
}
function persist(strict = false) {
  if (!ready || !activeScope || !rows.value.length) return
  try { writeScheduleBatchDraft(window.localStorage, activeScope.identity, activeScope.factory, snapshot()); storageError.value = ''; emit('draft-change') }
  catch { storageError.value = '浏览器未能保存草稿。请恢复浏览器存储后再提交，避免刷新后无法核对原提交。'; if (strict) throw new Error(storageError.value) }
}
function chooseConfiguration() {
  const current = configuration.value
  if (!current) configId.value = ''
  configRevision.value = current?.revision || 0
  papers.value = current ? (current.data.lines || []).map(line => ({ ...line, usage_quantity: isScheduleBox(line.packaging_type) ? null : line.usage_quantity == null ? null : Number(line.usage_quantity), dimension_unit: line.dimension_unit || '', quantity_rule: reusableQuantityRule(line.quantity_rule), net_weight_kg: line.net_weight_kg == null ? null : Number(line.net_weight_kg), gross_weight_kg: line.gross_weight_kg == null ? null : Number(line.gross_weight_kg) })) : emptyBatchPapers(rows.value, dimension())
  overrides.value = {}
}
function addPaper() {
  if (papers.value.length >= 50) return
  papers.value.push({ packaging_type: '', paper_quality: '', specification: '', dimension_unit: dimension(), unit: '个', usage_quantity: null,
    quantity_rule: { mode: 'PER_CARTON', carton_line_no: papers.value.findIndex(line => line.quantity_rule?.mode !== 'PER_CARTON') + 1 || null, per_carton_quantity: 1 } })
}
function removePaper(index: number) {
  if (papers.value.length <= 1) return
  papers.value.splice(index, 1)
  papers.value.forEach(line => { line.quantity_rule = referencesAfterRemoval(line.quantity_rule, index) })
  Object.keys(overrides.value).forEach(key => { overrides.value[key] = overrides.value[key]!.filter(line => line.line_no !== index + 1).map(line => ({ ...line, line_no: line.line_no > index + 1 ? line.line_no - 1 : line.line_no })) })
}
function suggestRule(index: number) {
  const paper = papers.value[index]!
  if (isCardPaper(paper.packaging_type) && paper.quantity_rule?.mode !== 'PER_CARTON') paper.quantity_rule = { mode: 'PER_CARTON', carton_line_no: papers.value.findIndex((line, i) => i !== index && line.quantity_rule?.mode !== 'PER_CARTON') + 1 || null, per_carton_quantity: 1 }
}
const sourceLines = (row: ScheduleBatchPreview) => overrides.value[scheduleSourceKey(row)] || []
const lineOverride = (row: ScheduleBatchPreview, index: number) => sourceLines(row).find(line => line.line_no === index + 1)
function patchOverride(row: ScheduleBatchPreview, index: number, patch: Partial<ScheduleBatchLineOverride>) {
  const key = scheduleSourceKey(row), lines = overrides.value[key] ||= []
  let entry = lines.find(line => line.line_no === index + 1)
  if (!entry) { entry = { line_no: index + 1 }; lines.push(entry) }
  Object.assign(entry, patch)
}
function toggleWeights(row: ScheduleBatchPreview, index: number, enabled: boolean) {
  if (enabled) patchOverride(row, index, { net_weight_kg: papers.value[index]!.net_weight_kg ?? null, gross_weight_kg: papers.value[index]!.gross_weight_kg ?? null })
  else { const line = lineOverride(row, index); if (line) { delete line.net_weight_kg; delete line.gross_weight_kg } }
}
const ownWeights = (row: ScheduleBatchPreview, index: number) => lineOverride(row, index)?.net_weight_kg !== undefined || lineOverride(row, index)?.gross_weight_kg !== undefined
const demands = (row: ScheduleBatchPreview) => batchPaperPreview(row.source, papers.value, sourceLines(row))
function toggleExpanded(row: ScheduleBatchPreview) { const key = scheduleSourceKey(row); expanded.value = expanded.value.includes(key) ? expanded.value.filter(value => value !== key) : [...expanded.value, key] }
function dateWarning(row: ScheduleBatchPreview) {
  if (!planned.value || !row.source.customer_due_date) return ''
  const lead = masterDueRules(records.value, row.source.customer_code || '').lead_days
  const available = Math.round((Date.parse(`${row.source.customer_due_date}T00:00:00Z`) - Date.parse(`${planned.value}T00:00:00Z`)) / 86400000)
  return available < 0 ? '计划交期晚于客户交期，请重点核对交付安排。' : available < lead ? `距客户交期仅 ${available} 天，少于安全提前 ${lead} 天，请重点跟进。` : ''
}
async function load() {
  const token = ++generation; ready = false; activeScope = null; controller.abort(); controller = new AbortController()
  rows.value = []; records.value = []; papers.value = []; error.value = ''; planned.value = ''; configId.value = ''; configRevision.value = 0; busy.value = false; loading.value = false
  note.value = ''; rush.value = false; rushReason.value = ''; overrides.value = {}; expanded.value = []; restored.value = false; changedSource.value = false; discardConfirm.value = false
  frozen.value = false; storageError.value = ''
  storedExists.value = false
  if (!props.open) return
  const scope = { identity: props.identityKey, factory: props.factoryId }, key = cacheKey.value
  loading.value = true
  try {
    const saved = readScheduleBatchDraft(window.localStorage, scope.identity, scope.factory)
    const cached = saved?.attempt || pendingScheduleBatches.get(key)
    // A reload/context interruption can happen after dispatch but before catch persisted
    // its flag. Any retained request must stay frozen until its exact replay succeeds.
    if (cached) cached.uncertain = true
    storedExists.value = !!saved || !!cached; frozen.value = !!cached
    const preview = cached?.preview || saved?.preview || props.selection
    if (!preview.length || preview.length > 100) throw new Error('请勾选 1 至 100 条同客户同货号排期')
    const [workspace, responsibility] = await Promise.all([cartonMasterApi.get(scope.factory), cartonCustomerResponsibilitiesApi.get(scope.factory, controller.signal, true)])
    if (token !== generation) return
    const canUseCustomer = (code?: string) => !!code && (responsibility.unrestricted || responsibility.own_customer_codes.includes(code)
      || Array.isArray(responsibility.blocked_customer_codes) && !responsibility.blocked_customer_codes.includes(code))
    if (preview.some(row => !canUseCustomer(row.source.customer_code))) throw new Error('当前账号无权办理这份草稿的客户，请联系主管核对客户责任')
    const batches = await Promise.all([...new Set(preview.map(row => row.batchId))].map(id => cartonProcurementApi.importDetail(scope.factory, id)))
    if (token !== generation) return
    const refreshed: ScheduleBatchPreview[] = []
    for (const entry of preview) {
      const batch = batches.find(batch => batch.id === entry.batchId)
      const current = batch?.parse_summary.rows?.find(row => row.source_sheet === entry.source.source_sheet && row.source_row === entry.source.source_row)
      if (!current || current.can_operate_source === false) throw new Error('部分来源不可访问，请刷新排期或联系主管核对')
      const source = { ...current, customer_code: current.customer_code || batch?.parse_summary.schedule_customer?.customer_code, customer_name: current.customer_name || batch?.parse_summary.schedule_customer?.customer_name }
      if (!canUseCustomer(source.customer_code)) throw new Error('当前账号无权办理此客户，请联系主管核对客户责任')
      if (!cached && batchSourceError(source)) throw new Error(batchSourceError(source))
      if (!sameScheduleItem(preview[0]!.source, source)) throw new Error('只能批量创建同客户、同货号的订单')
      if (source.quantity !== entry.source.quantity || source.carton_rule !== entry.source.carton_rule || source.customer_due_date !== entry.source.customer_due_date
        || source.contract_no !== entry.source.contract_no || source.source_reference !== entry.source.source_reference
        || source.customer_po !== entry.source.customer_po) changedSource.value = true
      refreshed.push({ batchId: entry.batchId, source })
    }
    records.value = workspace.records; rows.value = JSON.parse(JSON.stringify(cached ? preview : refreshed))
    if (cached) {
      pendingScheduleBatches.set(key, cached); frozen.value = true
      papers.value = JSON.parse(JSON.stringify(cached.body.lines)); planned.value = cached.body.planned_due_date; configId.value = cached.body.master_config_id; configRevision.value = cached.body.master_config_revision
      note.value = cached.body.note || ''; rush.value = !!cached.body.rush; rushReason.value = cached.body.rush_reason || ''
      for (const item of cached.body.order_overrides || []) overrides.value[JSON.stringify([item.batch_id, item.source_sheet, item.source_row])] = JSON.parse(JSON.stringify(item.lines))
    } else if (saved) {
      papers.value = saved.papers; planned.value = saved.planned; configId.value = saved.configId; configRevision.value = saved.configRevision
      note.value = saved.note; rush.value = saved.rush; rushReason.value = saved.rushReason; overrides.value = saved.overrides; restored.value = true
    } else { configId.value = configurations.value.length === 1 ? configurations.value[0]!.id : ''; chooseConfiguration() }
    activeScope = scope; ready = true; persist()
  } catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation) loading.value = false }
}
watch(() => [props.open, props.factoryId, props.viewerKey, props.identityKey, props.selection], load, { immediate: true, flush: 'sync' })
watch([papers, planned, configId, configRevision, note, rush, rushReason, overrides], () => { if (!frozen.value) { error.value = ''; persist() } }, { deep: true, flush: 'sync' })
onBeforeUnmount(() => { generation++; controller.abort() })
const validation = computed(() => {
  if (!rows.value.length) return '没有可下单的排期'
  if (configChanged.value) return '基础资料版本已变化，请重新带入当前资料并核对'
  if (configurations.value.length > 1 && !configuration.value) return '此货号有多套纸箱资料，请选择本次使用的一套'
  if (!papers.value.length || papers.value.some(paper => !paper.packaging_type.trim() || !paper.paper_quality.trim() || !paper.specification.trim() || !paper.dimension_unit || !paper.unit.trim())) return '请统一补齐纸品类型、纸质、规格和尺寸单位'
  for (let index = 0; index < papers.value.length; index++) { const issue = batchWeightError(papers.value[index]!); if (issue) return `公共纸品第 ${index + 1} 项：${issue}` }
  if (rows.value.some(row => batchPaperError(row.source, papers.value))) return '纸品配置与排期装箱数不一致，请核对必需内外箱及配套关系'
  for (const row of rows.value) {
    if (demands(row).some(line => line.error || !(line.actual > 0))) return `${row.source.contract_no}：请核对每项纸品数量，数量必须大于 0`
    for (let i = 0; i < papers.value.length; i++) { const issue = batchWeightError(effectiveBatchWeights(papers.value[i]!, lineOverride(row, i))); if (issue) return `${row.source.contract_no} 第 ${i + 1} 项：${issue}` }
  }
  if (!planned.value) return '请填写统一计划交期'
  if (planned.value < businessTodayIso()) return '计划交期不能早于今天的下单日期'
  return ''
})
async function submit() {
  if (busy.value || loading.value || !rows.value.length) return
  const key = cacheKey.value, token = generation, identity = props.identityKey, factory = props.factoryId
  let attempt = pendingScheduleBatches.get(key), dispatched = false
  try {
    if (!attempt) {
      if (validation.value) throw new Error(validation.value)
      const body: ScheduleBatchBody = { factory_id: factory, request_id: createRandomUuid(), planned_due_date: planned.value,
        sources: rows.value.map(row => ({ batch_id: row.batchId, source_sheet: row.source.source_sheet!, source_row: row.source.source_row! })),
        lines: JSON.parse(JSON.stringify(papers.value.map(paper => !isScheduleBox(paper.packaging_type) && !paper.quantity_rule && Number(paper.usage_quantity) > 0
          ? { ...paper, quantity_rule: { mode: 'PACKING' } } : paper))), master_config_id: configId.value, master_config_revision: configRevision.value,
        note: note.value.trim(), rush: rush.value, rush_reason: rush.value ? rushReason.value.trim() : '',
        order_overrides: rows.value.map(row => ({ batch_id: row.batchId, source_sheet: row.source.source_sheet!, source_row: row.source.source_row!, lines: sourceLines(row).filter(line => Object.keys(line).some(key => key !== 'line_no')) })).filter(row => row.lines.length) }
      attempt = { body: JSON.parse(JSON.stringify(body)), preview: JSON.parse(JSON.stringify(rows.value)), uncertain: false }; pendingScheduleBatches.set(key, attempt)
    }
    frozen.value = true; busy.value = true; error.value = ''; persist(true)
    const submittedRaw = window.localStorage.getItem(scheduleBatchDraftKey(identity, factory))
    dispatched = true
    const result = await cartonScheduleBatchApi.create(attempt.body, controller.signal)
    pendingScheduleBatches.delete(key)
    try { if (window.localStorage.getItem(scheduleBatchDraftKey(identity, factory)) === submittedRaw) clearScheduleBatchDraft(window.localStorage, identity, factory) }
    catch { /* The committed command remains safely replayable in the retained draft. */ }
    if (token === generation) { ready = false; emit('draft-change'); emit('saved', result); emit('update:open', false) }
  } catch (cause) {
    if (attempt) {
      const status = axios.isAxiosError(cause) ? cause.response?.status : undefined
      if (!dispatched || !attempt.uncertain && status && status >= 400 && status < 500 && ![408, 429].includes(status)) pendingScheduleBatches.delete(key)
      else attempt.uncertain = true
    }
    if (token === generation) { frozen.value = pendingScheduleBatches.has(key); error.value = getApiErrorMessage(cause); persist() }
  } finally { if (token === generation) busy.value = false }
}
function discard() {
  if (busy.value || frozen.value) return
  try { ready = false; clearScheduleBatchDraft(window.localStorage, props.identityKey, props.factoryId); pendingScheduleBatches.delete(cacheKey.value); emit('draft-change'); emit('update:open', false) }
  catch { ready = true; storageError.value = '未能清空浏览器草稿，请稍后重试。' }
}
function close() { if (!busy.value) { persist(); emit('update:open', false) } }
</script>

<template>
  <DialogRoot :open="open" @update:open="value => { if (!value) close() }"><DialogPortal>
    <DialogOverlay class="fixed inset-0 z-[80] bg-slate-950/40" />
    <DialogContent class="fixed left-1/2 top-1/2 z-[81] w-[calc(100%-2rem)] max-w-5xl -translate-x-1/2 -translate-y-1/2" @interact-outside.prevent @escape-key-down="event => { if (busy) event.preventDefault() }">
      <DialogTitle class="sr-only">同货号批量下单</DialogTitle><DialogDescription class="sr-only">共用普通订单的纸品、数量和重量字段，各条排期分别生成独立订单。</DialogDescription>
      <CartonOrderEditorForm title="同货号批量下单" description="每条排期分别生成待发送订单；供应商接单、上传资料和仓库入库继续逐单办理。" :busy="busy" :disabled="frozen || loading" :submit-disabled="loading || !rows.length" :submit-label="frozen ? '核对原提交结果' : `创建 ${rows.length} 张独立订单`" close-label="关闭批量下单" back-label="保存并退出" @submit="submit" @close="close">
        <p v-if="loading" role="status" class="text-sm text-slate-600">正在读取纸箱资料并核对来源…</p>
        <div v-if="!loading && !rows.length && storedExists && !frozen" class="rounded-lg border border-amber-200 p-3 text-xs"><p>这份本机草稿的来源目前不能继续下单。可以只清空本机未提交草稿后重新选择，不会修改正式订单。</p><button type="button" class="mt-2 text-teal-700 underline" @click="discardConfirm = true">清空不可用草稿</button><button v-if="discardConfirm" type="button" class="ml-3 rounded border px-3 py-2" @click="discard">确认清空草稿</button></div>
        <p v-if="frozen" role="status" class="rounded-lg bg-amber-50 p-3 text-xs text-amber-900">上次提交结果待确认，已保存原内容和提交记录，关闭或刷新后仍可恢复。只能点击“核对原提交结果”，不会重复下单。</p>
        <template v-if="rows.length">
          <div class="flex flex-wrap items-start justify-between gap-3 rounded-lg bg-teal-50 p-3 text-sm text-teal-900"><div><strong>{{ rows[0]!.source.customer_name || rows[0]!.source.customer_code }} · {{ rows[0]!.source.item_no }}</strong><p class="mt-1 text-xs">供应商：沿用本厂固定供应商，无需重复选择。</p><p class="mt-1 text-xs">{{ restored ? '已恢复本机未完成草稿。' : '填写内容自动保存在本机当前账号和厂区。' }}</p></div><button v-if="!frozen" type="button" class="text-xs underline" @click="discardConfirm = !discardConfirm">清空批量草稿</button></div>
          <div v-if="discardConfirm && !frozen" class="rounded-lg border border-amber-200 p-3 text-xs"><p>清空仅移除本机未提交的草稿，不会修改任何正式订单。确定清空？</p><button type="button" class="mt-2 rounded border px-3 py-2" @click="discard">确认清空草稿</button></div>
          <p v-if="changedSource && !frozen" class="rounded-lg bg-amber-50 p-3 text-xs text-amber-900">来源的合同、SO、客户 PO、数量、装箱或交期已有变化，已刷新来源数据；请重新核对订单资料、手动数量和每箱重量。</p>
          <div class="grid gap-3 sm:grid-cols-2"><label class="block text-xs font-semibold">统一计划交期 *<input v-model="planned" type="date" :min="businessTodayIso()" aria-label="批量下单计划交期" required class="mt-2 block h-9 w-full rounded-lg border bg-white px-3"></label><div class="space-y-2 text-xs"><label class="flex items-center gap-2"><input v-model="rush" type="checkbox" aria-label="批量下单加急" class="accent-teal-700">加急订单</label><input v-if="rush" v-model="rushReason" aria-label="批量下单加急原因" maxlength="80" placeholder="原因（选填）" class="h-9 w-full rounded-lg border px-3"></div></div>
          <section class="space-y-3" aria-label="批量下单公共纸箱资料">
            <label v-if="configurations.length > 1" class="block text-xs">此货号有多套资料，请核对后选择<select v-model="configId" aria-label="批量下单纸箱配置" class="mt-2 h-9 w-full rounded-lg border bg-white px-2" @change="chooseConfiguration"><option value="">请选择纸箱配置</option><option v-for="config in configurations" :key="config.id" :value="config.id">{{ (config.data.lines || []).map(line => `${line.packaging_type} ${line.paper_quality} ${line.specification} ${line.dimension_unit}`).join('；') }}</option></select></label>
            <p v-if="configChanged" class="rounded-lg bg-amber-50 p-3 text-xs">基础资料版本已变化。<button type="button" class="underline" @click="chooseConfiguration">重新带入当前基础资料</button>（会清除本次逐单覆盖，请重新核对）</p>
            <p class="text-xs text-slate-500">{{ configuration ? '已带入基础资料，请核对本次纸箱要求。' : configurations.length > 1 ? '确认配置后再继续，不会自动选用不同规格。' : '没有现成资料，纸质和规格在这里填写一次即可。' }} 装箱数分别沿用每条排期。</p>
            <p v-if="packingDiffers" class="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">所选排期装箱数不同：每箱净重、毛重可能不同，请在下面逐单核对；可按订单覆盖重量，不会按数量自动换算重量。</p>
            <CartonOrderPaperSection :disabled="papers.length >= 50" guidance="与普通下单相同，可新增卡纸等配套纸品。必需内外箱不能缺；数量在下面各订单分别核对或手动修改。" @add="addPaper">
              <CartonOrderPaperEditor v-for="(paper, index) in papers" :key="index" :index="index" v-model:packaging="paper.packaging_type" v-model:quality="paper.paper_quality" v-model:specification="paper.specification" v-model:dimension="paper.dimension_unit" v-model:unit="paper.unit" :packaging-options="packagingOptions" :quality-options="qualityOptions" :specification-options="specificationOptions" :unit-options="unitOptions" :remove-disabled="papers.length <= 1" dimension-editable allow-millimeters @remove="removePaper(index)" @update:packaging="suggestRule(index)">
                <template #basis><p class="text-xs leading-5 text-slate-500">{{ paper.quantity_rule?.mode === 'PER_CARTON' ? '按对应纸箱和每箱用量计算' : '装箱数：按各条排期' }}</p></template>
                <CartonQuantityRuleInput v-model="paper.quantity_rule" :lines="papers" :index="index" />
                <label v-if="paper.quantity_rule?.mode !== 'PER_CARTON' && !isScheduleBox(paper.packaging_type)" class="block text-xs">每份纸品对应产品数<input :value="paper.usage_quantity" :aria-label="`每份对应产品数 ${index + 1}`" type="number" min="0.0001" step="0.0001" class="mt-1 h-9 w-full rounded-lg border px-2" @input="paper.usage_quantity = ($event.target as HTMLInputElement).value === '' ? null : Number(($event.target as HTMLInputElement).value)"></label>
                <CartonPaperWeightFields v-if="showPaperWeightInputs(paper.packaging_type, paper.quantity_rule?.mode)" :net="paper.net_weight_kg" :gross="paper.gross_weight_kg" :index="index" @update:net="paper.net_weight_kg = $event" @update:gross="paper.gross_weight_kg = $event" />
              </CartonOrderPaperEditor>
              <p class="text-xs text-slate-500">纸箱净重为每箱货物不含包装的重量，毛重为含包装的整箱重量，单位 kg；两项选填，毛重不能小于净重。卡类及按箱配套纸品无需填写重量。</p>
            </CartonOrderPaperSection>
          </section>
          <section class="space-y-3" aria-label="批量下单来源核对"><h3 class="text-sm font-bold">逐单核对 · 各自生成独立订单</h3>
            <article v-for="row in rows" :key="scheduleSourceKey(row)" class="rounded-xl border border-slate-200 p-3">
              <div class="grid gap-3 text-xs sm:grid-cols-3"><div><strong>{{ row.source.contract_no }}</strong><p class="mt-1 text-slate-500">客户 PO：{{ row.source.customer_po || '未填' }}</p><p v-if="row.source.source_reference" class="mt-1 text-slate-500">业务 SO：{{ row.source.source_reference }}</p></div><div>产品数量：{{ row.source.quantity }}<p class="mt-1">内 / 外箱装箱：{{ row.source.carton_rule }}</p></div><div>客户交期：{{ row.source.customer_due_date }}<p v-if="dateWarning(row)" class="mt-1 text-amber-800">{{ dateWarning(row) }}</p></div></div>
              <div class="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs"><p v-for="(paper, index) in demands(row)" :key="index" :class="paper.error ? 'text-amber-700' : 'text-teal-800'">{{ paper.type || `纸品 ${index + 1}` }}：{{ paper.error ? '待核对装箱' : `${paper.actual} ${paper.unit}` }}{{ lineOverride(row, index)?.manual_quantity != null ? '（手动）' : '' }}</p></div>
              <button type="button" :aria-expanded="expanded.includes(scheduleSourceKey(row))" :aria-label="`调整本单数量重量 ${row.source.contract_no}`" class="mt-3 text-xs font-semibold text-teal-700 underline" @click="toggleExpanded(row)">调整本单数量 / 重量</button>
              <fieldset v-if="expanded.includes(scheduleSourceKey(row))" :aria-label="`本单纸品 ${row.source.contract_no}`" class="mt-3 space-y-3 border-t pt-3"><div v-for="(paper, index) in papers" :key="index" class="space-y-3 rounded-lg bg-slate-50 p-3"><strong class="text-xs">第 {{ index + 1 }} 项 · {{ paper.packaging_type || '未命名纸品' }}</strong><div class="grid items-start gap-3 sm:grid-cols-2"><CartonOrderQuantityField :index="index" :model-value="demands(row)[index]?.actual" calculated :manual="lineOverride(row, index)?.manual_quantity != null" @update:model-value="patchOverride(row, index, { manual_quantity: $event === '' ? 0 : Number($event) })" @restore="patchOverride(row, index, { manual_quantity: null })" /><div class="pt-5 text-xs text-slate-500">自动参考：{{ demands(row)[index]?.automatic }} {{ paper.unit }}<p class="mt-1">{{ demands(row)[index]?.error }}</p></div></div><template v-if="showPaperWeightInputs(paper.packaging_type, paper.quantity_rule?.mode)"><label class="flex gap-2 text-xs"><input type="checkbox" :aria-label="`单独填写重量 ${row.source.contract_no} ${index + 1}`" :checked="ownWeights(row, index)" @change="toggleWeights(row, index, ($event.target as HTMLInputElement).checked)">本单单独填写重量（留空代表未知；取消勾选沿用公共重量）</label><CartonPaperWeightFields v-if="ownWeights(row, index)" :index="index" :prefix="row.source.contract_no" :net="lineOverride(row, index)?.net_weight_kg" :gross="lineOverride(row, index)?.gross_weight_kg" @update:net="patchOverride(row, index, { net_weight_kg: $event })" @update:gross="patchOverride(row, index, { gross_weight_kg: $event })" /><p v-else class="text-xs text-slate-500">沿用每箱净重 {{ paper.net_weight_kg ?? '未填' }} kg / 毛重 {{ paper.gross_weight_kg ?? '未填' }} kg</p></template></div></fieldset>
            </article>
          </section>
          <CartonOrderNoteField v-model="note" />
        </template>
        <template #feedback><p v-if="error" role="alert" class="text-xs text-red-700">{{ error }}</p><p v-if="storageError" role="alert" class="text-xs text-red-700">{{ storageError }}</p><p v-else-if="!error && !frozen && !loading && validation" class="text-xs text-slate-600">{{ validation }}</p></template>
      </CartonOrderEditorForm>
    </DialogContent>
  </DialogPortal></DialogRoot>
</template>
