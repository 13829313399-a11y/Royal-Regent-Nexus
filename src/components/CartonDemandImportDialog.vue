<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import axios from 'axios'
import { DialogRoot, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogDescription } from 'reka-ui'
import { Button } from '@/components/ui/button'
import CartonOrderPaperEditor from './CartonOrderPaperEditor.vue'
import { cartonBatchOrdersApi, type DemandRow, type DemandBody, type BatchResult } from '@/api/cartonBatchOrders'
import { pendingCartonBatches, scaledQuantity } from '@/features/carton-procurement/batchOrders'
import { getApiErrorMessage } from '@/lib/http'
import { createRandomUuid } from '@/lib/randomUuid'

const props = defineProps<{ open: boolean; file: File | null; factoryId: string; viewerKey: string; identityKey: string }>()
const emit = defineEmits<{ 'update:open': [value: boolean]; saved: [result: BatchResult] }>()
const rows = ref<(DemandRow & { selected: boolean; expanded: boolean })[]>([]), fingerprint = ref(''), error = ref(''), loading = ref(false), busy = ref(false), frozen = ref(false)
const defaultDate = ref(''), defaultKind = ref('样板单')
const cacheKey = computed(() => `import:${props.identityKey}:${props.factoryId}`)
const selected = computed(() => rows.value.filter(row => row.selected))
const groupCount = computed(() => new Set(selected.value.map(row => row.group)).size)
let generation = 0, controller = new AbortController()
function issue(row: DemandRow) {
  if (!row.group.trim()) return '缺少分组编号'
  if (!['样板单', '样板', '杂单', 'SAMPLE', 'WORKSHOP_MISC'].includes(row.kind)) return '请选择订单类型'
  if (!/^\d{4}-\d{2}-\d{2}$/.test(row.required_date)) return '缺少需用日期'
  if (!row.packaging_type.trim() || !row.paper_quality.trim() || !row.specification.trim() || !row.unit.trim()) return '请展开补齐纸品资料'
  if ((scaledQuantity(row.quantity) ?? 0n) <= 0n) return '数量须为正数，最多四位小数'
  if (!['cm', 'in', 'inch', '厘米', '英寸'].includes(row.dimension_unit.toLowerCase())) return '请核对尺寸单位'
  return ''
}
const invalid = computed(() => selected.value.some(row => issue(row)))
function fillDefaults() {
  for (const row of selected.value) { if (!row.kind) row.kind = defaultKind.value; if (!row.required_date && defaultDate.value) row.required_date = defaultDate.value }
}
async function load() {
  const token = ++generation; controller.abort(); controller = new AbortController(); rows.value = []; error.value = ''; busy.value = false; loading.value = false; fingerprint.value = ''
  frozen.value = pendingCartonBatches.has(cacheKey.value)
  if (!props.open) return
  const pending = pendingCartonBatches.get(cacheKey.value)
  if (pending) {
    const body = pending.body as DemandBody
    rows.value = body.rows.map(row => ({ ...row, selected: true, expanded: false })); fingerprint.value = body.fingerprint
    return
  }
  if (!props.file) return
  loading.value = true
  try {
    const data = await cartonBatchOrdersApi.preview(props.factoryId, props.file, controller.signal)
    if (token !== generation) return
    fingerprint.value = data.fingerprint
    rows.value = data.rows.map(row => ({ ...row, dimension_unit: ({ inch: 'in', 英寸: 'in', 厘米: 'cm' } as Record<string, string>)[row.dimension_unit] || row.dimension_unit, selected: true, expanded: false }))
  } catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation) loading.value = false }
}
watch(() => [props.open, props.file, props.factoryId, props.viewerKey, props.identityKey], load, { immediate: true, flush: 'sync' })
onBeforeUnmount(() => { generation++; controller.abort() })
async function submit() {
  if (busy.value || loading.value || !selected.value.length) return
  const token = generation, key = cacheKey.value
  let attempt = pendingCartonBatches.get(key)
  if (!attempt) {
    if (invalid.value || !props.file) return
    const input = selected.value.map(({ selected: _selected, expanded: _expanded, ...row }) => row)
    attempt = { body: { factory_id: props.factoryId, request_id: createRandomUuid(), fingerprint: fingerprint.value, rows: input } satisfies DemandBody, file: props.file, uncertain: false }
    pendingCartonBatches.set(key, attempt)
  }
  busy.value = true; frozen.value = true; error.value = ''
  try {
    const result = await cartonBatchOrdersApi.import(attempt.body as DemandBody, attempt.file!, controller.signal)
    pendingCartonBatches.delete(key)
    if (token === generation) { emit('saved', result); emit('update:open', false) }
  } catch (cause) {
    const status = axios.isAxiosError(cause) ? cause.response?.status : undefined
    if (!attempt.uncertain && status && status >= 400 && status < 500 && ![408, 429].includes(status)) pendingCartonBatches.delete(key)
    else attempt.uncertain = true
    if (token === generation) { frozen.value = pendingCartonBatches.has(key); error.value = getApiErrorMessage(cause) }
  } finally { if (token === generation) busy.value = false }
}
</script>

<template>
  <DialogRoot :open="open" @update:open="value => { if (!busy) emit('update:open', value) }"><DialogPortal>
    <DialogOverlay class="fixed inset-0 z-[80] bg-slate-950/40" />
    <DialogContent class="fixed left-1/2 top-1/2 z-[81] flex max-h-[90dvh] w-[calc(100%-2rem)] max-w-6xl -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-2xl border bg-white shadow-xl" @interact-outside.prevent @escape-key-down="event => { if (busy) event.preventDefault() }">
      <header class="shrink-0 border-b p-5"><DialogTitle class="text-base font-bold">导入新建需求 · 样板／杂单</DialogTitle><DialogDescription class="mt-1 text-xs leading-5 text-slate-600">同一分组生成一张订单。选择本次需求、补齐资料后生成待确认草稿；不会直接发送供应商或登记入库。</DialogDescription></header>
      <form class="flex min-h-0 flex-1 flex-col" @submit.prevent="submit">
        <div class="min-h-0 space-y-4 overflow-y-auto p-5">
          <p v-if="loading" role="status">正在读取新建需求文件…</p>
          <p v-if="error" role="alert" class="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{{ error }}</p>
          <p v-if="frozen" role="status" class="rounded-lg bg-amber-50 p-3 text-sm text-amber-800">原提交结果待确认，已冻结原文件和需求。核对原提交结果不会重复建单。</p>
          <fieldset :disabled="busy || loading || frozen" class="space-y-3">
            <div class="flex flex-wrap items-end gap-3 rounded-xl bg-teal-50 p-3"><label class="text-xs">缺省订单类型<select v-model="defaultKind" aria-label="导入缺省类型" class="mt-1 block h-9 rounded-lg border bg-white px-2"><option>样板单</option><option>杂单</option></select></label><label class="text-xs">统一补齐缺失需用日期<input v-model="defaultDate" aria-label="导入统一需用日期" type="date" class="mt-1 block h-9 rounded-lg border bg-white px-2"></label><Button type="button" variant="outline" size="sm" @click="fillDefaults">填入所选空白项</Button><Button type="button" variant="ghost" size="sm" @click="rows.forEach(row => row.selected = true)">全选</Button><Button type="button" variant="ghost" size="sm" @click="rows.forEach(row => row.selected = false)">清空选择</Button></div>
            <article v-for="row in rows" :key="row.source_row" class="space-y-3 rounded-xl border p-3" :class="row.selected && issue(row) ? 'border-amber-300' : 'border-slate-200'">
              <div class="flex flex-wrap items-center justify-between gap-2"><label class="flex items-center gap-2 text-xs"><input v-model="row.selected" type="checkbox" :aria-label="`选择需求第 ${row.source_row} 行`">原表第 {{ row.source_row }} 行</label><button type="button" class="text-xs font-semibold text-teal-700" :aria-expanded="row.expanded" @click="row.expanded = !row.expanded">{{ row.expanded ? '收起纸品资料' : '修改纸品资料' }}</button></div>
              <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><label class="text-xs">分组编号<input v-model="row.group" :aria-label="`第 ${row.source_row} 行分组`" maxlength="64" class="mt-1 h-9 w-full rounded-lg border px-2"></label><label class="text-xs">订单类型<select v-model="row.kind" :aria-label="`第 ${row.source_row} 行类型`" class="mt-1 h-9 w-full rounded-lg border bg-white px-2"><option value="">请选择</option><option value="样板单">样板单</option><option value="杂单">杂单</option><option v-if="['SAMPLE', '样板'].includes(row.kind)" :value="row.kind">样板单</option><option v-if="row.kind === 'WORKSHOP_MISC'" :value="row.kind">杂单</option></select></label><label class="text-xs">需用日期<input v-model="row.required_date" :aria-label="`第 ${row.source_row} 行需用日期`" type="date" class="mt-1 h-9 w-full rounded-lg border px-2"></label><label class="text-xs">需求数量（{{ row.unit || '单位待填写' }}）<input v-model="row.quantity" :aria-label="`第 ${row.source_row} 行数量`" inputmode="decimal" maxlength="19" class="mt-1 h-9 w-full rounded-lg border px-2 text-right"></label></div>
              <p class="break-words text-xs text-slate-600">{{ [row.item_no, row.packaging_type, row.paper_quality, row.specification, row.dimension_unit].filter(Boolean).join(' · ') || '纸品资料待填写' }}</p>
              <p v-if="row.selected && issue(row)" class="text-xs text-amber-800">{{ issue(row) }}</p>
              <template v-if="row.expanded"><CartonOrderPaperEditor :index="row.source_row - 2" v-model:packaging="row.packaging_type" v-model:quality="row.paper_quality" v-model:specification="row.specification" v-model:dimension="row.dimension_unit" v-model:unit="row.unit" v-model:item="row.item_no" item-enabled dimension-editable remove-disabled /><label class="block text-xs">备注<textarea v-model="row.note" maxlength="2000" rows="2" :aria-label="`第 ${row.source_row} 行备注`" class="mt-1 w-full rounded-lg border p-2" /></label></template>
            </article>
          </fieldset>
        </div>
        <footer class="flex shrink-0 flex-wrap items-center justify-between gap-3 border-t bg-slate-50 p-4 text-xs"><span>已选 {{ selected.length }} 项纸品 · {{ groupCount }} 个订单分组</span><div class="flex gap-2"><Button type="button" variant="outline" :disabled="busy" @click="emit('update:open', false)">返回</Button><Button type="button" variant="outline" :disabled="busy || loading || frozen" @click="load">重新读取</Button><Button type="submit" :disabled="busy || loading || !selected.length || (!frozen && invalid)">{{ busy ? '正在创建…' : frozen ? '核对原提交结果' : '确认生成订单草稿' }}</Button></div></footer>
      </form>
    </DialogContent>
  </DialogPortal></DialogRoot>
</template>
