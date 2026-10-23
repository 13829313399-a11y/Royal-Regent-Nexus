<script setup lang="ts">
import '@/features/carton-procurement/layout.css'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { isAxiosError } from 'axios'
import { cartonProcurementApi as api, type OpeningInventoryBatch, type OpeningBatchReversalPreview } from '@/api/cartonProcurement'
import { getApiErrorMessage } from '@/lib/http'
import { formatCartonSpecification } from '@/lib/cartonDimensions'

const props = defineProps<{ factoryId: string; viewerKey: string; connected: boolean; canManage: boolean; refreshKey?: number }>()
const emit = defineEmits<{ reversed: [] }>()
type Pending = { payload: { factory_id: string; request_id: string; expected_fingerprint: string; reason: string }; preview: OpeningBatchReversalPreview }
const batches = ref<OpeningInventoryBatch[]>([]), total = ref(0), offset = ref(0)
const loading = ref(false), previewing = ref(false), saving = ref(false)
const error = ref(''), listError = ref(''), message = ref(''), storageWarning = ref('')
const preview = ref<OpeningBatchReversalPreview | null>(null), pending = ref<Pending | null>(null)
const reason = ref('期初库存导入有误，整批撤销后更正重导'), reviewed = ref(false)
const enabled = computed(() => props.connected && props.canManage && Boolean(props.viewerKey))
const busy = computed(() => loading.value || previewing.value || saving.value)
let generation = 0, listGeneration = 0, previewGeneration = 0
const statuses = { ACTIVE: '已入账', PARTIAL: '已有逐笔冲销，须核实', REVERSED: '已整批撤销' }
const dateText = (value: string) => value ? value.replace('T', ' ').slice(0, 19) : '未记录'
const quantityText = (value: string) => Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 4 })
const requestKey = (batch: string) => `rr:opening-reversal:v1:${JSON.stringify([props.viewerKey, props.factoryId, batch])}`
function stored(batch: string): Pending | null {
  try {
    const raw = sessionStorage.getItem(requestKey(batch))
    if (!raw) return null
    const value = JSON.parse(raw) as Pending
    return value.preview?.batch_id === batch && value.preview.factory_id === props.factoryId
      && Array.isArray(value.preview.rows) && Array.isArray(value.preview.errors) && Array.isArray(value.preview.totals)
      && value.payload?.factory_id === props.factoryId && typeof value.payload.request_id === 'string'
      && typeof value.payload.reason === 'string' && value.payload.expected_fingerprint === value.preview.source_fingerprint
      ? value : null
  } catch { return null }
}
async function load() {
  const scope = generation, call = ++listGeneration
  batches.value = []; total.value = 0; listError.value = ''
  if (!enabled.value) return
  loading.value = true
  try {
    const result = await api.listOpeningInventoryBatches(props.factoryId, offset.value)
    if (scope === generation && call === listGeneration) { batches.value = result.items; total.value = result.total }
  } catch (failure) { if (scope === generation && call === listGeneration) listError.value = getApiErrorMessage(failure) }
  finally { if (scope === generation && call === listGeneration) loading.value = false }
}
function closePreview() { previewGeneration++; preview.value = null; pending.value = null; reviewed.value = false; error.value = ''; storageWarning.value = '' }
async function begin(batch: OpeningInventoryBatch) {
  if (!enabled.value || busy.value) return
  closePreview(); message.value = ''; reason.value = '期初库存导入有误，整批撤销后更正重导'
  const retained = stored(batch.batch_id)
  if (retained) {
    pending.value = retained; preview.value = retained.preview; reason.value = retained.payload.reason; reviewed.value = true
    return
  }
  const scope = generation, call = ++previewGeneration
  previewing.value = true
  try {
    const result = await api.previewOpeningBatchReversal(props.factoryId, batch.batch_id)
    if (scope === generation && call === previewGeneration) preview.value = result
  } catch (failure) { if (scope === generation && call === previewGeneration) error.value = getApiErrorMessage(failure) }
  finally { if (scope === generation && call === previewGeneration) previewing.value = false }
}
async function confirmReversal() {
  if (!enabled.value || busy.value || !preview.value || preview.value.errors.length || !reviewed.value || !reason.value.trim()) return
  const scope = generation, batch = preview.value.batch_id, key = requestKey(batch)
  const request = pending.value ?? { preview: preview.value, payload: { factory_id: props.factoryId,
    request_id: crypto.randomUUID(), expected_fingerprint: preview.value.source_fingerprint, reason: reason.value.trim() } }
  pending.value = request
  try { sessionStorage.setItem(key, JSON.stringify(request)) }
  catch { storageWarning.value = '本机无法保存重试信息；若结果未确认，请先刷新批次状态核对。' }
  saving.value = true; error.value = ''
  try {
    const result = await api.reverseOpeningBatch(batch, request.payload)
    try { sessionStorage.removeItem(key) } catch { /* The result is already confirmed by the server. */ }
    if (scope !== generation) return
    closePreview()
    message.value = `${result.duplicate ? '已核实原撤销结果' : '期初库存已整批撤销'}，共 ${result.reversed_count} 笔。原记录保留，修正文件后可重新预览导入。`
    emit('reversed')
    await load()
  } catch (failure) {
    if (scope !== generation) return
    error.value = getApiErrorMessage(failure)
    if (isAxiosError(failure) && failure.response && [400, 409, 422].includes(failure.response.status)) {
      try { sessionStorage.removeItem(key) } catch { /* The server rejected this request before writing. */ }
      preview.value = null; pending.value = null; reviewed.value = false
      error.value += ' 请重新预览撤销；本次整批操作未完成。'
    } else error.value += ' 请沿当前请求核对或重试，勿重复新建撤销。'
  } finally { if (scope === generation) saving.value = false }
}
watch(() => [props.factoryId, props.viewerKey, props.connected, props.canManage], () => {
  generation++; listGeneration++; previewGeneration++
  loading.value = false; previewing.value = false; saving.value = false
  closePreview(); message.value = ''; offset.value = 0; void load()
}, { immediate: true })
watch(() => props.refreshKey, () => { closePreview(); void load() })
onBeforeUnmount(() => { generation++; listGeneration++; previewGeneration++ })
</script>

<template>
  <section aria-label="期初库存导入批次" class="min-w-0 space-y-3 rounded-xl border border-slate-200 bg-white p-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div><h3 class="text-sm font-bold text-slate-900">已导入批次 · 整批撤销</h3><p class="mt-1 text-xs leading-6 text-slate-500">按原文件的导入批次撤销。先核对全部明细，确认后一次处理；原记录和撤销原因保留。</p></div>
      <button type="button" :disabled="!enabled || busy" class="h-9 rounded-lg border px-3 text-xs disabled:opacity-40" @click="closePreview(); load()">刷新导入批次</button>
    </div>
    <p v-if="!canManage" class="text-xs text-amber-700">查看及撤销导入批次需要本厂库存操作权限。</p>
    <p v-else-if="!connected" class="text-xs text-amber-700">后端未连接，恢复后再核对批次。</p>
    <p v-if="loading" role="status" class="text-xs text-slate-500">正在读取导入批次…</p>
    <p v-if="listError" role="alert" class="rounded-lg bg-red-50 p-3 text-xs text-red-700">批次读取失败：{{ listError }}</p>
    <p v-if="error" role="alert" class="rounded-lg bg-red-50 p-3 text-xs text-red-700">{{ error }}</p>
    <p v-if="message" role="status" class="rounded-lg bg-teal-50 p-3 text-xs text-teal-800">{{ message }}</p>
    <div v-if="batches.length" class="carton-table-wrap overflow-x-auto rounded-lg border">
      <table aria-label="期初导入批次列表" class="carton-table-fit text-left text-xs"><thead class="bg-slate-50 text-slate-500"><tr><th class="p-3">原文件 / 导入时间</th><th class="p-3">原期初日期</th><th class="p-3 text-right">入账笔数</th><th class="p-3">经手人</th><th class="p-3">状态</th><th class="p-3">操作</th></tr></thead>
        <tbody><tr v-for="batch in batches" :key="batch.batch_id" class="border-t">
          <td data-label="原文件 / 导入时间" class="p-3"><b>{{ batch.filename }}</b><p class="mt-1 text-slate-500">{{ dateText(batch.imported_at) }}</p></td>
          <td data-label="原期初日期" class="p-3">{{ batch.date_from }} ～ {{ batch.date_to }}</td><td data-label="入账笔数" class="p-3 text-right font-bold">{{ batch.row_count }}</td><td data-label="经手人" class="p-3">{{ batch.actor_name }}</td><td data-label="状态" class="p-3">{{ statuses[batch.status] }}</td>
          <td data-label="操作" class="p-3"><button v-if="batch.status !== 'REVERSED' || stored(batch.batch_id)" type="button" :aria-label="`预览撤销期初批次 ${batch.filename}`" :disabled="busy || !enabled" class="rounded-lg border border-red-200 px-3 py-2 font-semibold text-red-700 disabled:opacity-40" @click="begin(batch)">{{ stored(batch.batch_id) ? '核对上次撤销' : '预览整批撤销' }}</button><span v-else class="text-slate-400">原记录已保留</span></td>
        </tr></tbody></table>
    </div>
    <p v-else-if="enabled && !loading && !listError" class="py-3 text-xs text-slate-500">本厂暂无已入账的期初导入批次。文件预览不会生成批次。</p>
    <nav v-if="total > 20" aria-label="期初导入批次分页" class="flex items-center justify-end gap-3 text-xs"><span>共 {{ total }} 批</span><button :disabled="busy || offset === 0" class="rounded border px-3 py-2 disabled:opacity-40" @click="offset -= 20; closePreview(); load()">上一页</button><button :disabled="busy || offset + 20 >= total" class="rounded border px-3 py-2 disabled:opacity-40" @click="offset += 20; closePreview(); load()">下一页</button></nav>
    <p v-if="previewing" role="status" class="text-xs text-slate-500">正在核对整批撤销条件…</p>
    <section v-if="preview" aria-label="整批撤销预览" class="space-y-3 rounded-xl border border-red-200 bg-red-50/30 p-4">
      <div class="flex items-start justify-between gap-3"><div><h4 class="text-sm font-bold text-slate-900">撤销预览：{{ preview.filename }}</h4><p class="mt-1 text-xs text-slate-600">将抵消 {{ preview.row_count }} 笔期初记录：<span v-for="item in preview.totals" :key="item.unit" class="mr-3 font-semibold">{{ quantityText(item.quantity) }} {{ item.unit }}</span></p></div><button :disabled="saving" type="button" aria-label="关闭整批撤销预览" class="rounded-lg border bg-white px-3 py-2 text-xs disabled:opacity-40" @click="closePreview">关闭</button></div>
      <p class="text-xs leading-6 text-slate-600">反向流水归属原期初日期，实际操作时间另行留痕。已锁账、已有其他收发或调仓、正在盘点及已逐笔冲销的批次须先核实；任一项不能撤销时整批不处理。</p>
      <div v-if="preview.errors.length" role="alert" class="rounded-lg bg-red-50 p-3 text-xs leading-6 text-red-700"><b>本批暂不能整批撤销：</b><p v-for="item in preview.errors" :key="item">{{ item }}</p></div>
      <div class="carton-table-wrap max-h-96 overflow-auto rounded-lg border bg-white"><table aria-label="整批撤销明细" class="carton-table-fit text-left text-xs"><thead class="bg-slate-50 text-slate-500"><tr><th class="p-3">客户 / 合同号</th><th class="p-3">货号 / 纸品</th><th class="p-3">规格</th><th class="p-3">原期初时间</th><th class="p-3">原仓位</th><th class="p-3 text-right">撤销数量</th></tr></thead><tbody><tr v-for="row in preview.rows" :key="row.movement_id" class="border-t"><td data-label="客户 / 合同号" class="p-3">{{ row.customer_name }}<p>{{ row.contract_no }}</p></td><td data-label="货号 / 纸品" class="p-3">{{ row.item_no }}<p>{{ row.packaging_type }} · {{ row.paper_quality }}</p></td><td data-label="规格" class="p-3">{{ formatCartonSpecification(row.specification) }}</td><td data-label="原期初时间" class="p-3">{{ dateText(row.occurred_at) }}</td><td data-label="原仓位" class="p-3">{{ row.location }}</td><td data-label="撤销数量" class="p-3 text-right font-bold text-red-700">-{{ quantityText(row.quantity) }} {{ row.unit }}</td></tr></tbody></table></div>
      <label class="block space-y-1 text-xs"><span>撤销原因 *</span><input v-model="reason" aria-label="期初整批撤销原因" maxlength="500" :disabled="saving || Boolean(pending)" class="h-10 w-full rounded-lg border bg-white px-3 disabled:bg-slate-100"></label>
      <label class="flex items-start gap-2 text-xs leading-6"><input v-model="reviewed" aria-label="已核对整批撤销" type="checkbox" :disabled="saving || Boolean(preview.errors.length) || Boolean(pending)" class="mt-1 accent-red-700"><span>已核对这是需要撤回的原导入批次，确认撤销以上全部记录，并保留原记录与原因。</span></label>
      <p v-if="storageWarning" class="text-xs text-amber-700">{{ storageWarning }}</p>
      <button type="button" :disabled="busy || !enabled || !reviewed || !reason.trim() || Boolean(preview.errors.length)" class="rounded-lg bg-red-700 px-4 py-2 text-xs font-bold text-white disabled:opacity-40" @click="confirmReversal">{{ saving ? '正在整批撤销…' : pending ? '核对并重试原撤销请求' : '确认整批撤销' }}</button>
    </section>
  </section>
</template>
