<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import axios from 'axios'
import { DialogRoot, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogDescription } from 'reka-ui'
import { Button } from '@/components/ui/button'
import CartonOrderPaperEditor from './CartonOrderPaperEditor.vue'
import { cartonSpecialRequestsApi, type UnifiedOrderRef } from '@/api/cartonSpecialRequests'
import { cartonBatchOrdersApi, type AppendBody, type BatchResult } from '@/api/cartonBatchOrders'
import { appendDraft, appendItems, sumQuantity, pendingCartonBatches, type AppendDraft } from '@/features/carton-procurement/batchOrders'
import { getApiErrorMessage } from '@/lib/http'
import { createRandomUuid } from '@/lib/randomUuid'

const props = defineProps<{ open: boolean; factoryId: string; viewerKey: string; identityKey: string; selection: UnifiedOrderRef[] }>()
const emit = defineEmits<{ 'update:open': [value: boolean]; saved: [result: BatchResult] }>()
const drafts = ref<AppendDraft[]>([]), reason = ref(''), error = ref(''), busy = ref(false), loading = ref(false), frozen = ref(false)
const cacheKey = computed(() => `append:${props.identityKey}:${props.factoryId}`)
let generation = 0, controller = new AbortController()
const editedCount = computed(() => drafts.value.filter(row => !row.removed && (row.new_lines.length || row.lines.some(line => !!line.addition && Number(line.addition) !== 0))).length)
async function load() {
  const token = ++generation; controller.abort(); controller = new AbortController(); drafts.value = []; error.value = ''; reason.value = ''; busy.value = false
  frozen.value = pendingCartonBatches.has(cacheKey.value)
  if (!props.open) return
  loading.value = true
  try {
    const pending = pendingCartonBatches.get(cacheKey.value)?.body as AppendBody | undefined
    const refs = (pending?.items || props.selection).map(({ kind, id, expected_revision }) => ({ kind, id, expected_revision }))
    const entries = await cartonSpecialRequestsApi.selected(props.factoryId, refs, controller.signal)
    if (token !== generation) return
    if (entries.length !== refs.length) throw new Error('部分订单不可访问或已删除，请关闭后重新选择')
    const cached = pendingCartonBatches.get(cacheKey.value)
    drafts.value = cached?.appendPreview ? JSON.parse(JSON.stringify(cached.appendPreview)) : entries.map(appendDraft)
    reason.value = cached?.commonReason || ''
  } catch (cause) { if (token === generation) error.value = getApiErrorMessage(cause) }
  finally { if (token === generation) loading.value = false }
}
watch(() => [props.open, props.factoryId, props.viewerKey, props.identityKey], load, { immediate: true, flush: 'sync' })
onBeforeUnmount(() => { generation++; controller.abort() })
function addPaper(row: AppendDraft) {
  row.new_lines.push({ item_no: row.item, packaging_type: '', paper_quality: '', specification: '', dimension_unit: 'cm', quantity: '', unit: '个', mark_mode: 'PENDING' })
}
async function submit() {
  if (busy.value || loading.value || !drafts.value.length) return
  const key = cacheKey.value, token = generation
  let attempt = pendingCartonBatches.get(key)
  try {
    if (!attempt) {
      const items = appendItems(drafts.value, reason.value)
      if (!items.length) throw new Error('请至少填写一项追加数量')
      attempt = { body: { factory_id: props.factoryId, request_id: createRandomUuid(), items } satisfies AppendBody, uncertain: false,
        appendPreview: JSON.parse(JSON.stringify(drafts.value.filter(row => items.some(item => item.kind === row.entry.kind && item.id === (row.entry.order?.order_no || row.entry.special?.id))))), commonReason: reason.value }
      pendingCartonBatches.set(key, attempt)
    }
    frozen.value = true; busy.value = true; error.value = ''
    const result = await cartonBatchOrdersApi.append(attempt.body as AppendBody, controller.signal)
    pendingCartonBatches.delete(key)
    if (token === generation) { emit('saved', result); emit('update:open', false) }
  } catch (cause) {
    if (attempt) {
      const status = axios.isAxiosError(cause) ? cause.response?.status : undefined
      if (!attempt.uncertain && status && status >= 400 && status < 500 && ![408, 429].includes(status)) pendingCartonBatches.delete(key)
      else attempt.uncertain = true
    }
    if (token === generation) { frozen.value = pendingCartonBatches.has(key); error.value = getApiErrorMessage(cause) }
  } finally { if (token === generation) busy.value = false }
}
</script>

<template>
  <DialogRoot :open="open" @update:open="value => { if (!busy) emit('update:open', value) }"><DialogPortal>
    <DialogOverlay class="fixed inset-0 z-[80] bg-slate-950/40" />
    <DialogContent class="fixed left-1/2 top-1/2 z-[81] flex max-h-[90dvh] w-[calc(100%-2rem)] max-w-6xl -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-2xl border bg-white shadow-xl" @interact-outside.prevent @escape-key-down="event => { if (busy) event.preventDefault() }">
      <header class="shrink-0 border-b p-5"><DialogTitle class="text-base font-bold">批量追加订单</DialogTitle><DialogDescription class="mt-1 text-xs leading-5 text-slate-600">按原订单分别追加；已收数量保持不变。留空或填 0 不追加，全部校验通过后一次提交。已发送订单同步供应商，待发送订单仍需确认下单。</DialogDescription></header>
      <form class="flex min-h-0 flex-1 flex-col" @submit.prevent="submit">
        <div class="min-h-0 space-y-4 overflow-y-auto p-5">
          <p v-if="loading" role="status">正在核对所选订单…</p>
          <p v-if="error" role="alert" class="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{{ error }}</p>
          <p v-if="frozen" role="status" class="rounded-lg bg-amber-50 p-3 text-sm text-amber-800">上次提交结果待确认，已保留原追加内容。请使用“核对原提交结果”，不会再次追加；原提交未确认前不能修改内容。</p>
          <fieldset :disabled="busy || frozen || loading" class="space-y-4">
            <label class="block text-xs font-semibold">统一追加原因（可逐单覆盖）<textarea v-model="reason" aria-label="批量追加原因" minlength="4" maxlength="500" rows="2" class="mt-2 w-full rounded-lg border p-3" placeholder="例如：客户增加需求" /></label>
            <article v-for="row in drafts.filter(item => !item.removed)" :key="row.key" class="min-w-0 rounded-xl border">
              <div class="flex flex-wrap items-start justify-between gap-2 border-b bg-slate-50 p-3"><div class="min-w-0 break-words text-sm"><b>{{ row.contract || row.number }}</b><p v-if="row.contract" class="mt-1 text-xs text-slate-500">{{ row.number }} · {{ row.item }}</p></div><Button type="button" variant="ghost" size="sm" @click="row.removed = true">移出本次</Button></div>
              <div class="space-y-3 p-3">
                <table class="w-full table-fixed text-left text-xs"><thead class="bg-teal-50"><tr><th class="w-[46%]">货号／纸品／纸质／规格</th><th>当前需求</th><th>本次追加</th><th>追加后总需求</th></tr></thead><tbody><tr v-for="line in row.lines" :key="line.id" class="border-t"><td data-label="纸品资料">{{ line.label }}</td><td data-label="当前需求">{{ line.current }} {{ line.unit }}</td><td data-label="本次追加"><input v-model="line.addition" :aria-label="`${row.number} ${line.id} 本次追加数量`" type="text" inputmode="decimal" maxlength="19" placeholder="0" class="h-9 w-full rounded-lg border px-2 text-right"></td><td data-label="追加后总需求" class="font-bold text-teal-700">{{ sumQuantity(line.current, line.addition) }} {{ line.unit }}</td></tr></tbody></table>
                <div class="grid gap-3 sm:grid-cols-2"><label class="text-xs">{{ row.dateLabel }}（原 {{ row.date }}，留空沿用）<input v-model="row.due_date" type="date" :aria-label="`${row.number} 追加后交期`" class="mt-1 h-9 w-full rounded-lg border px-2"></label><label class="text-xs">本单追加原因（留空使用统一原因）<input v-model="row.reason" maxlength="500" :aria-label="`${row.number} 追加原因`" class="mt-1 h-9 w-full rounded-lg border px-2"></label></div>
                <CartonOrderPaperEditor v-for="(paper, index) in row.new_lines" :key="index" :index="index" v-model:packaging="paper.packaging_type" v-model:quality="paper.paper_quality" v-model:specification="paper.specification" v-model:dimension="paper.dimension_unit" v-model:unit="paper.unit" v-model:item="paper.item_no" :item-enabled="!row.entry.order" dimension-editable @remove="row.new_lines.splice(index, 1)"><template #quantity><label class="text-xs">新增纸品数量 *<input v-model="paper.quantity" required inputmode="decimal" :aria-label="`${row.number} 新增纸品数量 ${index + 1}`" class="mt-1 h-9 w-full rounded-lg border px-2"></label></template></CartonOrderPaperEditor>
                <Button type="button" variant="outline" size="sm" :disabled="row.lines.length + row.new_lines.length >= 50" @click="addPaper(row)">新增纸品</Button>
              </div>
            </article>
          </fieldset>
        </div>
        <footer class="flex shrink-0 flex-wrap items-center justify-between gap-3 border-t bg-slate-50 p-4 text-xs"><span>{{ frozen ? '按原提交内容核对' : `本次追加 ${editedCount} 张订单` }}</span><div class="flex gap-2"><Button type="button" variant="outline" :disabled="busy" @click="emit('update:open', false)">返回</Button><Button type="submit" :disabled="busy || loading || !drafts.length || (!frozen && !editedCount)">{{ busy ? '正在提交…' : frozen ? '核对原提交结果' : '确认批量追加' }}</Button></div></footer>
      </form>
    </DialogContent>
  </DialogPortal></DialogRoot>
</template>

<style scoped>
th, td { padding: 10px 8px; overflow-wrap: anywhere; font-variant-numeric: tabular-nums; }
@media (max-width: 639px) { table, tbody, tr, td { display: block; } thead { display: none; } tr { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); } td:first-child { grid-column: 1 / -1; } td::before { display:block; content:attr(data-label); color:var(--muted-foreground); margin-bottom:4px; } }
</style>
