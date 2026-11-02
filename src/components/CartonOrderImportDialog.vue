<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import axios from 'axios'
import { DialogRoot, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogDescription } from 'reka-ui'
import { Button } from '@/components/ui/button'
import CartonOrderPaperEditor from './CartonOrderPaperEditor.vue'
import { cartonOrderImportApi, type ImportMode, type ImportFile, type ImportRow, type ImportPreview, type ImportConfirm, type ImportOptions } from '@/api/cartonOrderImport'
import { cartonBatchOrdersApi, type BatchResult, type DemandBody } from '@/api/cartonBatchOrders'
import { pendingCartonBatches } from '@/features/carton-procurement/batchOrders'
import { getApiErrorMessage } from '@/lib/http'
import { createRandomUuid } from '@/lib/randomUuid'

const props = defineProps<{ open: boolean; file: File | null; factoryId: string; viewerKey: string; identityKey: string; mode: ImportMode }>()
const emit = defineEmits<{ 'update:open': [value: boolean]; saved: [result: BatchResult]; 'close-auto-focus': [event: Event] }>()
const fileData = ref<ImportFile | null>(null), rows = ref<ImportRow[]>([]), preview = ref<ImportPreview | null>(null)
const sheet = ref(''), header = ref(1), mapping = ref<Record<string, number>>({}), step = ref<'mapping' | 'preview'>('mapping')
const selected = ref<string[]>([]), expanded = ref<number[]>([]), error = ref(''), message = ref('')
const loading = ref(false), busy = ref(false), frozen = ref(false), dirty = ref(false), defaultDate = ref(''), defaultKind = ref('样板单')
const legacyKey = computed(() => `import:${props.identityKey}:${props.factoryId}`)
const cacheKey = computed(() => props.mode === 'SPECIAL' && pendingCartonBatches.has(legacyKey.value) ? legacyKey.value : `order-import:${props.mode}:${props.identityKey}:${props.factoryId}`)
const title = computed(() => props.mode === 'REGULAR' ? '导入正单' : '导入样板／杂单需求')
const ready = computed(() => preview.value?.groups.filter(g => g.status === 'READY') || [])
const invalid = computed(() => preview.value?.groups.filter(g => g.status === 'INVALID') || [])
const requirementLabels = { required: '必填', optional: '选填', conditional: '按条件必填' }
const editableFields = computed(() => (fileData.value?.fields || []).filter(f => !['packaging_type', 'paper_quality', 'specification', 'dimension_unit', 'unit', 'item_no'].includes(f.key)))
let generation = 0, controller = new AbortController()
function activeFile() { return pendingCartonBatches.get(cacheKey.value)?.file || props.file }
function options(): ImportOptions { return { factory_id: props.factoryId, mode: props.mode, sheet: sheet.value, header_row: header.value, mapping: { ...mapping.value } } }
function body() { return { ...options(), fingerprint: fileData.value!.fingerprint, rows: rows.value.map(r => ({ source_row: r.source_row, data: { ...r.data } })) } }
function rowFor(n: number) { return rows.value.find(row => row.source_row === n)! }
function mapColumn(key: string, value: string) { if (value) mapping.value[key] = Number(value); else delete mapping.value[key] }
watch(rows, () => { dirty.value = true; selected.value = [] }, { deep: true, flush: 'sync' })
async function load() {
  const token = ++generation; controller.abort(); controller = new AbortController()
  rows.value = []; fileData.value = null; preview.value = null; selected.value = []; expanded.value = []; error.value = ''; message.value = ''; busy.value = false; loading.value = false
  frozen.value = pendingCartonBatches.has(cacheKey.value); step.value = 'mapping'; defaultDate.value = ''
  if (!props.open || !activeFile()) return
  loading.value = true
  const pending = pendingCartonBatches.get(cacheKey.value), saved = pending?.body as ImportConfirm | DemandBody | undefined
  try {
    // Re-authorize before displaying any retained uncertain-result details.
    const data = await cartonOrderImportApi.read(saved && 'mode' in saved ? { factory_id: saved.factory_id, mode: saved.mode, sheet: saved.sheet, header_row: saved.header_row, mapping: saved.mapping } : { factory_id: props.factoryId, mode: props.mode }, activeFile()!, controller.signal)
    if (token !== generation) return
    fileData.value = data; sheet.value = data.sheet; header.value = data.header_row; mapping.value = { ...data.mapping }
    if (saved) {
      if ('mode' in saved) {
        rows.value = saved.rows.map(r => ({ source_row: r.source_row, data: { ...r.data } }))
        preview.value = pending!.orderImportPreview as ImportPreview; selected.value = [...saved.selected_groups]
      } else {
        rows.value = saved.rows.map(({ source_row, ...data }) => ({ source_row, data }))
        const groups = [...new Set(saved.rows.map(r => r.group))]
        preview.value = { preview_fingerprint: '', groups: groups.map(label => ({ id: label, label, source_rows: saved.rows.filter(r => r.group === label).map(r => r.source_row), errors: [], warnings: ['核对升级前的原提交'], quantities: [], due_date: '', status: 'READY' })) }
        selected.value = groups
      }
      dirty.value = false; step.value = 'preview'
    }
  } catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation) loading.value = false }
}
watch(() => [props.open, props.file, props.factoryId, props.viewerKey, props.identityKey, props.mode], load, { immediate: true, flush: 'sync' })
onBeforeUnmount(() => { generation++; controller.abort() })
async function readSelection(remap = false) {
  if (loading.value || busy.value || frozen.value || !activeFile()) return
  const token = generation; loading.value = true; error.value = ''; message.value = ''
  try {
    const input = options(); if (remap) delete input.mapping
    const data = await cartonOrderImportApi.read(input, activeFile()!, controller.signal)
    if (token !== generation) return
    fileData.value = data; mapping.value = { ...data.mapping }; rows.value = data.rows; preview.value = null
    if (!remap) {
      if (!rows.value.length) { error.value = data.ignored_demo_rows?.length ? '已跳过演示行，没有待导入的实际数据。请在演示行下方填写实际订单后重新上传。' : '所选表头后没有数据，请核对工作表和表头行'; return }
      step.value = 'preview'
      await validate()
    }
  } catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation) loading.value = false }
}
async function validate() {
  if (!activeFile() || !fileData.value || frozen.value) return
  const token = generation; loading.value = true; error.value = ''
  try {
    const result = await cartonOrderImportApi.preview(body(), activeFile()!, controller.signal)
    if (token !== generation) return
    preview.value = result; dirty.value = false; selected.value = result.groups.filter(g => g.status === 'READY').map(g => g.id)
  } catch (cause) { if (token === generation) { error.value = getApiErrorMessage(cause); dirty.value = true } }
  finally { if (token === generation) loading.value = false }
}
function fillDefaults() {
  for (const row of rows.value) {
    const dateKey = props.mode === 'REGULAR' ? 'customer_due_date' : 'required_date'
    if (!row.data[dateKey] && defaultDate.value) row.data[dateKey] = defaultDate.value
    if (props.mode === 'SPECIAL' && !row.data.kind) row.data.kind = defaultKind.value
  }
}
function toggleRow(n: number) { expanded.value = expanded.value.includes(n) ? expanded.value.filter(v => v !== n) : [...expanded.value, n] }
async function submit() {
  if (busy.value || loading.value || !fileData.value) return
  const token = generation, key = cacheKey.value
  let attempt = pendingCartonBatches.get(key)
  if (!attempt) {
    if (dirty.value || !preview.value || !selected.value.length || !activeFile()) return
    attempt = { body: { ...body(), request_id: createRandomUuid(), selected_groups: [...selected.value], preview_fingerprint: preview.value.preview_fingerprint } satisfies ImportConfirm,
      file: activeFile()!, uncertain: false, orderImportPreview: structuredClone(JSON.parse(JSON.stringify(preview.value))) }
    pendingCartonBatches.set(key, attempt)
  }
  busy.value = true; frozen.value = true; error.value = ''; message.value = ''
  try {
    const command = attempt.body as ImportConfirm | DemandBody
    const result = 'mode' in command ? await cartonOrderImportApi.confirm(command, attempt.file!, controller.signal) : await cartonBatchOrdersApi.importDemands(command, attempt.file!, controller.signal)
    pendingCartonBatches.delete(key)
    if (token === generation) {
      frozen.value = false; selected.value = []
      message.value = `已生成 ${result.count} 张订单。其余订单仍保留在本次预览，可补齐后继续导入。`
      emit('saved', result)
      if ('mode' in command) await validate()
      else emit('update:open', false)
    }
  } catch (cause) {
    const status = axios.isAxiosError(cause) ? cause.response?.status : undefined
    if (!attempt.uncertain && status && status >= 400 && status < 500 && ![408, 429].includes(status)) pendingCartonBatches.delete(key)
    else attempt.uncertain = true
    if (token === generation) { frozen.value = pendingCartonBatches.has(key); error.value = getApiErrorMessage(cause); if (!frozen.value) dirty.value = true }
  } finally { if (token === generation) busy.value = false }
}
</script>

<template>
  <DialogRoot :open="open" @update:open="value => { if (!busy) emit('update:open', value) }"><DialogPortal>
    <DialogOverlay class="fixed inset-0 z-[80] bg-slate-950/40" />
    <DialogContent class="fixed left-1/2 top-1/2 z-[81] flex max-h-[90dvh] w-[calc(100%-2rem)] max-w-6xl -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-2xl border bg-white shadow-xl" @close-auto-focus="emit('close-auto-focus', $event)" @interact-outside.prevent @escape-key-down="event => { if (busy) event.preventDefault() }">
      <header class="shrink-0 border-b p-5"><DialogTitle class="text-base font-bold">{{ title }}</DialogTitle><DialogDescription class="mt-1 text-xs leading-5 text-slate-600">匹配列名 → 按整单核对 → 导入完整订单。{{ mode === 'REGULAR' ? '正单按客户、合同、货号及 PO 合并纸品，导入后由仓库发送供应商。' : '同一分组生成一张待确认订单，确认后沿现有流程下单。' }}</DialogDescription></header>
      <form novalidate class="flex min-h-0 flex-1 flex-col" @submit.prevent="submit">
        <div class="min-h-0 space-y-4 overflow-y-auto p-5">
          <p v-if="loading" role="status" class="text-sm">正在读取并校验订单资料…</p>
          <p v-if="error" role="alert" class="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{{ error }}</p>
          <p v-if="message" role="status" class="rounded-lg bg-teal-50 p-3 text-sm text-teal-800">{{ message }}</p>
          <p v-if="frozen" role="status" class="rounded-lg bg-amber-50 p-3 text-sm text-amber-800">原提交结果待核对，已冻结原文件、所选订单及修改内容。重试同一次提交不会重复下单。</p>
          <p v-if="fileData?.ignored_demo_rows?.length" role="status" class="rounded-lg bg-slate-50 p-3 text-xs leading-5 text-slate-600">已跳过 {{ fileData.ignored_demo_rows.length }} 行演示（原表第 {{ fileData.ignored_demo_rows.join('、') }} 行），不计入订单、纸品及数量。{{ fileData.rows.length ? '' : '当前没有待导入的实际数据，请在演示行下方填写后重新上传。' }}复制演示行作为实际订单时，请清空“模板行标记”。</p>
          <fieldset v-if="fileData" :disabled="busy || loading || frozen" class="min-w-0 space-y-4">
            <template v-if="step === 'mapping'">
              <div class="flex flex-wrap items-end gap-3 rounded-xl bg-teal-50 p-3">
                <label class="min-w-0 text-xs">工作表<select v-model="sheet" aria-label="导入工作表" class="mt-1 block h-9 max-w-full rounded-lg border bg-white px-2" @change="header = 1; readSelection(true)"><option v-for="name in fileData.sheets" :key="name">{{ name }}</option></select></label>
                <label class="text-xs">表头所在行<input v-model.number="header" aria-label="导入表头行" type="number" min="1" max="50" class="mt-1 block h-9 w-24 rounded-lg border px-2"></label>
                <Button type="button" variant="outline" size="sm" @click="readSelection(true)">重新识别列名</Button>
              </div>
              <p class="text-xs leading-5 text-slate-600">只读取所选工作表。列顺序不限；“数量”“交期”等含义不明确的列请手动指定。未匹配字段可在下一步补填。原表合并单元格不会自动向下填充。</p>
              <p class="text-xs leading-5 text-slate-600">必填：须补齐后导入；选填：可留空；按条件必填：按字段说明及当前客户规则填写。</p>
              <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <label v-for="field in fileData.fields" :key="field.key" class="min-w-0 text-xs">{{ field.label }}
                  <span v-if="field.requirement" class="ml-1 font-medium" :class="field.requirement === 'required' ? 'text-teal-700' : 'text-slate-500'">（{{ requirementLabels[field.requirement] }}）</span>
                  <select :value="mapping[field.key] || ''" :aria-label="`匹配${field.label}`" class="mt-1 h-9 w-full rounded-lg border bg-white px-2" @change="mapColumn(field.key, ($event.target as HTMLSelectElement).value)">
                    <option value="">未匹配／稍后补填</option><option v-for="col in fileData.columns" :key="col.index" :value="col.index">第 {{ col.index }} 列 · {{ col.label }}{{ col.sample ? `（${col.sample}）` : '' }}</option>
                  </select>
                  <span v-if="field.hint" class="mt-1 block leading-5 text-slate-500">{{ field.hint }}</span>
                </label>
              </div>
            </template>
            <template v-else>
              <div class="flex flex-wrap items-end gap-3 rounded-xl bg-teal-50 p-3">
                <label v-if="mode === 'SPECIAL'" class="text-xs">空白订单类型<select v-model="defaultKind" aria-label="导入缺省类型" class="mt-1 block h-9 rounded-lg border bg-white px-2"><option>样板单</option><option>杂单</option></select></label>
                <label class="text-xs">补齐空白{{ mode === 'REGULAR' ? '客户交期' : '需用日期' }}<input v-model="defaultDate" aria-label="导入统一日期" type="date" class="mt-1 block h-9 rounded-lg border bg-white px-2"></label>
                <Button type="button" variant="outline" size="sm" @click="fillDefaults">填入空白项</Button>
                <Button type="button" variant="outline" size="sm" @click="validate">重新校验</Button>
              </div>
              <p v-if="dirty" role="status" class="text-sm text-amber-800">资料已修改，请重新校验后选择完整订单。</p>
              <p class="text-xs leading-5 text-slate-600">纸品资料标 * 为必填；尺寸单位选填，留空默认 cm。{{ mode === 'REGULAR' ? '正单货号必填。' : '样板／杂单货号选填。' }}其他字段按各项标注补充，修改后重新校验。</p>
              <div v-if="preview" class="flex flex-wrap items-center gap-3 text-xs"><span>可导入 {{ ready.length }} 单 · 待补充 {{ invalid.length }} 单 · 已导入 {{ preview.groups.filter(g => g.status === 'IMPORTED').length }} 单</span><Button type="button" variant="ghost" size="sm" :disabled="dirty" @click="selected = ready.map(g => g.id)">选择全部完整订单</Button><Button type="button" variant="ghost" size="sm" @click="selected = []">清空选择</Button></div>
              <article v-for="group in preview?.groups || []" :key="group.id" class="space-y-3 rounded-xl border p-3" :class="group.status === 'INVALID' ? 'border-amber-300' : 'border-slate-200'">
                <label class="flex items-start gap-2 text-sm font-semibold"><input v-model="selected" type="checkbox" :value="group.id" :disabled="dirty || group.status !== 'READY'" :aria-label="`选择订单 ${group.label || group.id}`"><span class="min-w-0 break-words">{{ group.label || '订单信息待补充' }} <span class="font-normal text-slate-500">原表行 {{ group.source_rows.join('、') }}</span></span></label>
                <p v-for="issue in group.errors" :key="issue" class="break-words text-xs text-amber-800">{{ issue }}</p>
                <p v-for="warning in group.warnings" :key="warning" class="break-words text-xs text-slate-600">{{ warning }}</p>
                <p v-if="group.status === 'READY'" class="text-xs text-teal-700">{{ mode === 'REGULAR' ? '计划到料' : '需用日期' }}：{{ group.due_date }}</p>
                <div v-for="(n, index) in group.source_rows" :key="n" class="space-y-3 rounded-lg bg-slate-50 p-3">
                  <div class="flex flex-wrap items-center justify-between gap-2 text-xs"><span class="min-w-0 break-words">第 {{ n }} 行 · {{ [rowFor(n).data.item_no, rowFor(n).data.packaging_type, rowFor(n).data.paper_quality, rowFor(n).data.specification].filter(Boolean).join(' · ') || '纸品资料待填写' }} · {{ group.quantities[index] || rowFor(n).data.quantity || '数量待确定' }} {{ rowFor(n).data.unit }}</span><button type="button" class="shrink-0 font-semibold text-teal-700" :aria-expanded="expanded.includes(n)" @click="toggleRow(n)">{{ expanded.includes(n) ? '收起资料' : '补充／修改资料' }}</button></div>
                  <template v-if="expanded.includes(n)">
                    <CartonOrderPaperEditor :index="n - 2" :packaging="rowFor(n).data.packaging_type || ''" @update:packaging="rowFor(n).data.packaging_type = $event" :quality="rowFor(n).data.paper_quality || ''" @update:quality="rowFor(n).data.paper_quality = $event" :specification="rowFor(n).data.specification || ''" @update:specification="rowFor(n).data.specification = $event" :dimension="rowFor(n).data.dimension_unit || ''" @update:dimension="rowFor(n).data.dimension_unit = $event" :unit="rowFor(n).data.unit || ''" @update:unit="rowFor(n).data.unit = $event" :item="rowFor(n).data.item_no || ''" @update:item="rowFor(n).data.item_no = $event" item-enabled :item-required="mode === 'REGULAR'" dimension-editable :allow-millimeters="mode === 'REGULAR'" remove-disabled />
                    <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3"><label v-for="field in editableFields" :key="field.key" class="min-w-0 text-xs">{{ field.label }}<span v-if="field.requirement" class="ml-1 font-medium" :class="field.requirement === 'required' ? 'text-teal-700' : 'text-slate-500'">（{{ requirementLabels[field.requirement] }}）</span><input v-model="rowFor(n).data[field.key]" :aria-label="`第 ${n} 行${field.label}`" :type="field.key.endsWith('date') ? 'date' : 'text'" :maxlength="field.key === 'note' ? 2000 : 255" class="mt-1 h-9 w-full rounded-lg border bg-white px-2"><span v-if="field.hint" class="mt-1 block leading-5 text-slate-500">{{ field.hint }}</span></label></div>
                  </template>
                </div>
              </article>
              <p v-if="!preview && !loading" class="text-sm text-slate-600">预览尚未完成，请重新校验。</p>
            </template>
          </fieldset>
        </div>
        <footer class="flex shrink-0 flex-wrap items-center justify-between gap-3 border-t bg-slate-50 p-4 text-xs">
          <span>{{ step === 'mapping' ? '核对原表列与系统字段的对应关系' : `已选 ${selected.length} 张完整订单；同一订单全部纸品一起导入` }}</span>
          <div class="flex flex-wrap gap-2"><Button type="button" variant="outline" :disabled="busy" @click="emit('update:open', false)">关闭</Button>
            <Button v-if="!fileData" type="button" variant="outline" :disabled="loading || busy" @click="load">重新读取</Button>
            <Button v-else-if="step === 'mapping'" type="button" :disabled="loading || busy" @click="readSelection()">核对订单</Button>
            <template v-else><Button type="button" variant="outline" :disabled="busy || loading || frozen" @click="step = 'mapping'">返回列匹配</Button><Button type="submit" :disabled="busy || loading || (!frozen && (dirty || !selected.length))">{{ busy ? '正在生成…' : frozen ? '核对原提交结果' : `导入所选 ${selected.length} 张订单` }}</Button></template>
          </div>
        </footer>
      </form>
    </DialogContent>
  </DialogPortal></DialogRoot>
</template>
