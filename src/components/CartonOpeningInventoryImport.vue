<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { cartonProcurementApi as api, type OpeningInventoryOptions, type OpeningInventoryPreview, type CartonHistoryInventoryImportResponse } from '@/api/cartonProcurement'
import type { CartonLocation } from '@/api/cartonPositions'
import { getApiErrorMessage } from '@/lib/http'

const props = defineProps<{
  factoryId: string; connected: boolean; canImport: boolean
  customers: Array<{ customer_name: string; customer_code: string; status?: string }>
  locations: CartonLocation[]
}>()
const emit = defineEmits<{ close: []; imported: [result: CartonHistoryInventoryImportResponse] }>()
const options = reactive({ customer_name: '', warehouse: '', dimension_unit: '' as '' | 'cm' | 'in', currency: 'CNY' })
const input = ref<HTMLInputElement | null>(null), file = ref<File | null>(null)
const preview = ref<OpeningInventoryPreview | null>(null), busy = ref(false), saving = ref(false), reviewed = ref(false)
const error = ref(''), success = ref('')
let generation = 0
const warehouses = computed(() => [...new Set(props.locations.filter(row => row.status !== 'INACTIVE').map(row => row.warehouse))])
const configured = computed(() => !!(options.dimension_unit && options.currency.trim()))
const canChoose = computed(() => props.connected && props.canImport && !busy.value && !saving.value)
const missingSettings = computed(() => [!options.dimension_unit && '尺寸单位'].filter(Boolean).join('、'))
const canPreview = computed(() => configured.value && props.connected && props.canImport && !busy.value && !saving.value)
const readyRows = computed(() => preview.value?.rows.filter(row => row.status === 'READY').length ?? 0)
function settings(): OpeningInventoryOptions {
  return { ...options, currency: options.currency.trim().toUpperCase(), dimension_unit: options.dimension_unit as 'cm' | 'in' }
}
function invalidate() {
  generation++; preview.value = null; reviewed.value = false; busy.value = false; error.value = ''; success.value = ''
}
watch(options, invalidate)
watch(() => props.factoryId, () => {
  invalidate(); file.value = null; saving.value = false
  Object.assign(options, { customer_name: '', warehouse: '', dimension_unit: '', currency: 'CNY' })
})
onBeforeUnmount(() => { generation++ })
async function choose(event: Event) {
  const target = event.target as HTMLInputElement
  const selected = target.files?.[0]; target.value = ''
  if (!selected) return
  invalidate(); file.value = null
  if (!/\.(xlsx|xlsm|xls)$/i.test(selected.name)) { error.value = '请选择 Excel 文件（xlsx、xlsm 或 xls）。'; return }
  if (selected.size > 20 * 1024 * 1024) { error.value = '文件不能超过 20MB。'; return }
  file.value = selected
  await loadPreview()
}
async function loadPreview() {
  if (file.value && !configured.value) { error.value = `文件已选择，请补填${missingSettings.value}，再点击“重新预览”。`; return }
  if (!file.value || !canPreview.value) return
  const token = ++generation, factory = props.factoryId, selected = file.value
  preview.value = null; reviewed.value = false; error.value = ''; success.value = ''; busy.value = true
  try {
    const result = await api.previewHistoryInventory(factory, selected, settings())
    if (token === generation && factory === props.factoryId) preview.value = result
  } catch (e) { if (token === generation) error.value = getApiErrorMessage(e) }
  finally { if (token === generation) busy.value = false }
}
async function confirmImport() {
  if (!preview.value || !file.value || !reviewed.value || preview.value.errors.length || !readyRows.value || !canPreview.value) return
  const token = generation, factory = props.factoryId, selected = file.value, fingerprint = preview.value.source_fingerprint
  saving.value = true; error.value = ''
  try {
    const result = await api.uploadHistoryInventory(factory, selected, settings(), fingerprint)
    if (token !== generation || factory !== props.factoryId) return
    success.value = `期初库存已入账 ${result.imported_count} 行，跳过 ${result.skipped_count} 行。`
    preview.value = null; reviewed.value = false; file.value = null
    emit('imported', result)
  } catch (e) {
    if (token === generation) { error.value = `${getApiErrorMessage(e)} 请重新预览，核实本次是否已入账。`; preview.value = null; reviewed.value = false }
  } finally { if (token === generation) saving.value = false }
}
function statusLabel(status: string) { return ({ READY: '待入账', DUPLICATE: '重复，跳过', ZERO: '零结余，跳过' } as Record<string, string>)[status] || status }
</script>

<template>
  <article aria-label="期初库存管理" class="overflow-hidden rounded-xl border border-teal-200 bg-white shadow-sm">
    <header class="flex flex-wrap items-start justify-between gap-3 border-b p-5">
      <div><h2 class="text-lg font-bold text-slate-950">期初库存管理</h2><p class="mt-1 text-xs leading-6 text-slate-500">登记系统启用时实际剩余的库存。数量取“结余”，不重放历史入库和出库，不计为本期供应商进货。</p></div>
      <button type="button" :disabled="saving" class="rounded-lg border px-3 py-2 text-xs disabled:opacity-40" @click="emit('close')">返回库存台账</button>
    </header>
    <div class="space-y-5 p-5">
      <section class="rounded-xl bg-slate-50 p-4">
        <h3 class="mb-3 text-sm font-bold text-slate-800">1. 选择本批库存的共同资料</h3>
        <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <label class="space-y-1 text-xs"><span>默认客户（选填）</span><select v-model="options.customer_name" aria-label="期初库存客户" :disabled="saving" class="h-10 w-full rounded-lg border border-slate-200 bg-white px-2"><option value="">按文件逐行读取</option><option v-for="customer in customers.filter(row => row.status !== 'INACTIVE')" :key="customer.customer_code" :value="customer.customer_name">{{ customer.customer_name }}</option></select></label>
          <label class="space-y-1 text-xs"><span>默认仓库（选填）</span><select v-model="options.warehouse" aria-label="期初库存仓库" :disabled="saving" class="h-10 w-full rounded-lg border border-slate-200 bg-white px-2"><option value="">按文件逐行匹配</option><option v-for="warehouse in warehouses" :key="warehouse" :value="warehouse">{{ warehouse }}</option></select></label>
          <label class="space-y-1 text-xs"><span>尺寸单位 *</span><select v-model="options.dimension_unit" aria-label="期初尺寸单位" :disabled="saving" class="h-10 w-full rounded-lg border border-slate-200 bg-white px-2"><option value="">请确认单位</option><option value="cm">厘米（cm）</option><option value="in">英寸（in）</option></select></label>
          <label class="space-y-1 text-xs"><span>单价币种</span><input value="CNY（人民币）" aria-label="期初库存币种" readonly class="h-10 w-full rounded-lg border border-slate-200 bg-slate-100 px-2"></label>
        </div>
        <p class="mt-3 text-xs leading-6 text-slate-500">入库时间按文件每行填写的完整日期或时间读取，并归属对应库存月份。导入的是实际剩余数量，不代表完整还原历史每月库存。一份表可含多个客户、仓库和仓位；行内客户、仓库优先，空白时才使用上方默认值。尺寸单位不同请分批导入。仓位先在基础资料维护；不确定时在文件中明确填写“待核仓位”。</p>
      </section>
      <section class="space-y-3">
        <h3 class="text-sm font-bold text-slate-800">2. 选择文件并核对预览</h3>
        <p class="text-xs leading-6 text-slate-500">客户可不填，按“未指定客户”入账；需要区分时可增加“客户”列。模板包含“仓库”和“入库时间”列；入库时间必填，用于该行期初入账，支持原模板“原入库时间”列。日常填写：PO、货号、纸品／纸质、长、宽、高、仓位、期初库存数量；单价选填。零结余跳过，缺单价保留为待核价。</p>
        <div class="flex flex-wrap items-center gap-3">
          <a href="/templates/carton-history-inventory-import-template.xlsx?v=row-inbound-time" download="纸箱期初库存导入模板.xlsx" class="rounded-lg border px-3 py-2 text-xs font-semibold text-slate-700">下载期初库存模板</a>
          <input ref="input" type="file" accept=".xlsx,.xlsm,.xls" aria-label="选择历史库存文件" class="hidden" @change="choose">
          <button type="button" :disabled="!canChoose" class="rounded-lg bg-teal-700 px-4 py-2 text-xs font-bold text-white disabled:opacity-40" @click="input?.click()">{{ busy ? '正在核对…' : '导入期初库存' }}</button>
          <button v-if="file" type="button" :disabled="!canChoose" class="rounded-lg border px-3 py-2 text-xs disabled:opacity-40" @click="loadPreview">重新预览</button>
          <span v-if="file" class="text-xs text-slate-500">{{ file.name }}</span>
        </div>
        <p v-if="!canImport" class="text-xs text-amber-700">当前账号可下载模板，导入需要库存写入权限。</p>
        <p v-else-if="!connected" class="text-xs text-amber-700">后端未连接，恢复连接后才能预览和入账。</p>
        <p v-else-if="!configured" class="text-xs text-amber-700">可以先选择文件；预览前还需填写：{{ missingSettings }}。客户可不填；仓库可在文件中填写或按唯一仓位匹配。</p>
      </section>
      <p v-if="error" role="alert" class="rounded-lg bg-red-50 p-3 text-sm text-red-700">{{ error }}</p>
      <p v-if="success" role="status" class="rounded-lg bg-teal-50 p-3 text-sm text-teal-800">{{ success }}</p>
      <section v-if="preview" class="space-y-3">
        <div class="flex flex-wrap gap-4 rounded-lg bg-teal-50 p-3 text-xs"><b>识别 {{ preview.row_count }} 行</b><span>待入账 {{ readyRows }} 行</span><span>跳过 {{ preview.skipped_count }} 行</span><span>待核价 {{ preview.missing_price_count }} 行</span></div>
        <div v-if="preview.errors.length" role="alert" class="rounded-lg bg-red-50 p-3 text-xs leading-6 text-red-700"><b>请修正后重新预览，本批尚未入账：</b><p v-for="(message, i) in preview.errors" :key="i">{{ message }}</p></div>
        <div v-if="preview.warnings.length" class="rounded-lg bg-amber-50 p-3 text-xs leading-6 text-amber-800"><p v-for="(message, i) in preview.warnings" :key="i">{{ message }}</p></div>
        <div class="overflow-x-auto rounded-lg border"><table aria-label="期初库存导入预览" class="w-full min-w-[1000px] text-left text-xs"><thead class="bg-slate-50 text-slate-500"><tr><th class="p-3">客户 / 原表行 / PO</th><th class="p-3">货号</th><th class="p-3">纸品类型 / 纸质</th><th class="p-3">规格</th><th class="p-3">仓库 / 仓位</th><th class="p-3">入库时间</th><th class="p-3 text-right">期初数量</th><th class="p-3 text-right">单价</th><th class="p-3 text-right">期初金额</th><th class="p-3">核对结果</th></tr></thead><tbody><tr v-for="(row, index) in preview.rows" :key="index" class="border-t" :class="row.status !== 'READY' ? 'text-slate-400' : ''"><td class="p-3"><b>{{ row.customer_name }}</b><br><span class="text-slate-400">{{ row.source }}</span><div>{{ row.contract_no || '未记录' }}</div></td><td class="p-3">{{ row.item_no }}</td><td class="p-3">{{ row.packaging_type }} · {{ row.paper_quality }}</td><td class="p-3">{{ row.specification }}</td><td class="p-3">{{ row.location }}</td><td class="p-3">{{ (row.occurred_at || row.original_inbound_at || '未记录').replace('T', ' ').replace('+08:00', '') }}</td><td class="p-3 text-right font-bold">{{ row.opening_quantity }} {{ row.unit }}</td><td class="p-3 text-right">{{ row.unit_price ?? '待核价' }}</td><td class="p-3 text-right">{{ row.amount ?? '待核价' }} {{ row.currency }}</td><td class="p-3">{{ statusLabel(row.status) }}<p v-for="(message, i) in row.warnings" :key="i" class="mt-1 text-amber-700">{{ message }}</p></td></tr></tbody></table></div>
        <div class="flex flex-wrap gap-3 text-xs"><p v-for="total in preview.totals" :key="`${total.unit}-${total.currency}`" class="rounded-lg bg-slate-50 px-3 py-2">本次新增 {{ total.quantity }} {{ total.unit }} · {{ total.currency }} 金额 {{ total.amount ?? '待核价，合计暂不完整' }}<span v-if="total.missing_price_count">（{{ total.missing_price_count }} 行缺价）</span></p></div>
        <div class="space-y-3 rounded-xl border border-teal-200 bg-teal-50/40 p-4"><h3 class="text-sm font-bold">3. 核对后确认入账</h3><label class="flex items-start gap-2 text-xs leading-6"><input v-model="reviewed" :disabled="saving || !!preview.errors.length || !readyRows" type="checkbox" aria-label="已核对期初库存" class="mt-1 accent-teal-700"><span>已逐行核对入库时间、实际结余、纸品、仓位及价格情况；这批库存尚未重复登记。确认后会增加库存流水。</span></label><button type="button" :disabled="!reviewed || !readyRows || !!preview.errors.length || !canPreview" class="rounded-lg bg-teal-700 px-5 py-2 text-xs font-bold text-white disabled:opacity-40" @click="confirmImport">{{ saving ? '正在入账…' : '确认导入期初库存' }}</button></div>
      </section>
    </div>
  </article>
</template>
