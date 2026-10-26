<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { DialogRoot, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogDescription, DialogClose } from 'reka-ui'
import { isAxiosError } from 'axios'
import { Button } from '@/components/ui/button'
import { getApiErrorMessage } from '@/lib/http'
import { fabricLegacyStockApi as api, type LegacyStockPreview } from '@/api/fabricLegacyStock'

const emit = defineEmits<{ close: [] }>()
const file = ref<File>(), result = ref<LegacyStockPreview>(), busy = ref(false), error = ref('')
let generation = 0, controller: AbortController | undefined
const summaries = computed(() => result.value ? [
  ['数据行', result.value.summary.total_rows], ['无问题行', result.value.summary.valid_rows], ['零数量行', result.value.summary.zero_rows],
  ['缺数量 / 非法数量', `${result.value.summary.missing_qty} / ${result.value.summary.invalid_qty}`],
  ['缺单位', result.value.summary.missing_unit], ['重复行（后续）', result.value.summary.duplicate_rows],
  ['重复组数', result.value.summary.duplicate_groups], ['转算专用行数', result.value.summary.conversion_only_rows],
] : [])
const totalSections = computed(() => result.value ? [
  { title: '原表合计', values: result.value.totals, basis: result.value.totals_basis },
  { title: '非重复合计', values: result.value.unique_totals, basis: result.value.unique_totals_basis },
  { title: '已匹配且非重复合计', values: result.value.matched_unique_totals, basis: result.value.matched_unique_totals_basis },
] : [])
const families = { material: '物料', location: '仓位', supplier: '供应商' } as const
function reset() { generation++; controller?.abort(); controller = undefined; result.value = undefined; error.value = ''; busy.value = false }
function chooseFile(event: Event) {
  reset()
  const input = event.target as HTMLInputElement
  file.value = input.files?.[0]; input.value = ''
  if (file.value && (!file.value.name.toLowerCase().endsWith('.xlsx') || file.value.size > 10 * 1024 * 1024)) {
    error.value = file.value.size > 10 * 1024 * 1024 ? '文件超过 10 MiB，请精简后重新选择。' : '请选择 .xlsx 旧库存表。'
    file.value = undefined
  }
}
async function inspectFile() {
  if (!file.value || busy.value) return
  const ticket = ++generation
  controller?.abort(); controller = new AbortController()
  busy.value = true; error.value = ''; result.value = undefined
  try {
    const preview = await api.preview(file.value, controller.signal)
    if (ticket === generation) result.value = preview
  } catch (e) {
    if (ticket === generation) error.value = isAxiosError(e) && e.response?.status === 403
      ? '没有布料仓收发查询权限，无法预检旧库存表。'
      : isAxiosError(e) && e.response?.status === 413 ? '文件超过 10 MiB，请精简后重新选择。' : getApiErrorMessage(e)
  } finally { if (ticket === generation) busy.value = false }
}
function close() { reset(); file.value = undefined; emit('close') }
onBeforeUnmount(() => { reset(); file.value = undefined })
</script>

<template>
  <DialogRoot :open="true" @update:open="value => { if (!value) close() }">
    <DialogPortal>
      <DialogOverlay class="legacy-stock-overlay" />
      <DialogContent class="legacy-stock-dialog">
        <header>
          <div><DialogTitle class="legacy-stock-title">旧库存表预检</DialogTitle><DialogDescription class="legacy-stock-description">仅预检，不入账。核对原表数量和基础资料匹配情况，不创建库存、期初批次或主数据。</DialogDescription></div>
          <DialogClose as-child><Button variant="outline">关闭预检</Button></DialogClose>
        </header>
        <main>
          <form class="legacy-stock-upload" @submit.prevent="inspectFile">
            <label>选择旧库存表<input type="file" accept=".xlsx" aria-label="旧库存表文件" @change="chooseFile" /></label>
            <Button type="submit" :disabled="!file || busy">{{ busy ? '正在预检…' : '开始预检' }}</Button>
            <p>{{ file?.name || '仅支持 .xlsx，最多 10 MiB、5000 行；读取“物料”工作表。' }}</p>
          </form>
          <p v-if="busy" class="legacy-stock-notice" role="status">正在读取原表并核对基础资料…</p>
          <p v-if="error" class="legacy-stock-error" role="alert">{{ error }}</p>
          <template v-if="result">
            <p class="legacy-stock-notice">{{ result.filename }} · {{ result.sheet }} · 表头第 {{ result.header_row }} 行 · 工作表 {{ result.sheet_rows }} 行 · 数量列：{{ result.quantity_column }}</p>
            <dl class="legacy-stock-summary"><div v-for="[label, value] in summaries" :key="label"><dt>{{ label }}</dt><dd>{{ value }}</dd></div></dl>
            <h3>基础资料匹配</h3>
            <div class="legacy-stock-matches"><p v-for="(label, key) in families" :key="key"><strong>{{ label }}</strong><span>匹配 {{ result.matching[key].matched }}</span><span>未匹配 {{ result.matching[key].unmatched }}</span><span>多个匹配 {{ result.matching[key].ambiguous }}</span></p></div>
            <h3>单位归并</h3>
            <p class="legacy-stock-notice">只归并显示，不换算数量。占位值按缺单位处理；其他单位保留原样。</p>
            <div class="legacy-stock-table legacy-stock-unit-table" tabindex="0" role="region" aria-label="单位归并">
              <table><thead><tr><th>原单位</th><th>归并单位</th><th class="legacy-stock-number">行数</th><th>是否转算专用</th></tr></thead>
                <tbody><tr v-for="alias in result.unit_aliases" :key="`${alias.raw}:${alias.canonical}`">
                  <td data-label="原单位">{{ alias.raw || '（空白）' }}</td><td data-label="归并单位">{{ alias.canonical || '缺单位' }}</td>
                  <td data-label="行数" class="legacy-stock-number">{{ alias.rows }}</td><td data-label="是否转算专用">{{ alias.conversion_only ? '是 · 不计实物合计' : '否' }}</td>
                </tr></tbody></table>
            </div>
            <h3>数量核对</h3>
            <p class="legacy-stock-notice">{{ result.quantity_basis }} 以下均为预检测算，不会生成系统库存。</p>
            <section v-for="section in totalSections" :key="section.title" class="legacy-stock-total-section" :aria-label="section.title">
              <h4>{{ section.title }}</h4><p class="legacy-stock-notice">{{ section.basis }}</p>
              <div class="legacy-stock-totals"><span v-for="(quantity, unit) in section.values" :key="unit"><strong>{{ quantity }}</strong> {{ unit }}</span><span v-if="!Object.keys(section.values).length">0（没有符合此口径的实物数量）</span></div>
            </section>
            <section class="legacy-stock-total-section" aria-label="转算专用数量">
              <h4>转算专用数量</h4><p class="legacy-stock-notice">{{ result.conversion_totals_basis }}</p>
              <div class="legacy-stock-totals"><span v-for="(quantity, unit) in result.conversion_totals" :key="unit"><strong>{{ quantity }}</strong> {{ unit }}</span><span v-if="!Object.keys(result.conversion_totals).length">0（没有数量有效的转算专用行）</span></div>
            </section>
            <section aria-label="重复行待确认">
              <h3>重复行待确认 <span>{{ result.summary.duplicate_groups }} 组 · {{ result.summary.duplicate_rows + result.summary.duplicate_groups }} 行（含各组首行）</span></h3>
              <p class="legacy-stock-notice">系统不自动合并，入账前必须人工确认。按原始字段判断重复，单位归并不会改变重复身份。展开各组可核对原表行。</p>
              <p v-if="result.duplicate_groups_truncated" class="legacy-stock-notice" role="status">重复组明细已截断：最多展示 200 组、1000 行（含首行）。组数、重复行数和数量合计仍覆盖全部数据，请分批核对剩余行。</p>
              <p v-if="!result.summary.duplicate_groups" class="legacy-stock-notice">未发现重复组。</p>
              <details v-for="(group, index) in result.duplicate_groups" :key="group.key" class="legacy-stock-duplicate-group" :open="index === 0">
                <summary>第 {{ index + 1 }} 组 · 原表第 {{ group.rows[0]?.row_number }} 行起 · {{ group.count }} 行 · {{ group.rows[0]?.item_name || '未填写物料名称' }}</summary>
                <p v-if="group.rows_truncated" class="legacy-stock-notice">本组仅展示 {{ group.rows.length }} / {{ group.count }} 行。</p>
                <div class="legacy-stock-table" tabindex="0" role="region" :aria-label="`重复组 ${index + 1} 原表行`">
                  <table><thead><tr><th>原表行</th><th>物料</th><th>供应商 / 仓位</th><th class="legacy-stock-number">数量 / 单位</th></tr></thead>
                    <tbody><tr v-for="row in group.rows" :key="row.row_number">
                      <td data-label="原表行">{{ row.row_number }}<small>{{ row.duplicate_of ? `重复第 ${row.duplicate_of} 行` : '组内首行' }}</small></td>
                      <td data-label="物料">{{ row.item_name || '未填写物料名称' }}<small>新编号：{{ row.new_item_code || '—' }} · 原编号：{{ row.item_code || '—' }}</small></td>
                      <td data-label="供应商 / 仓位">{{ row.supplier || '未填写供应商' }}<small>{{ row.location || '未填写位置' }}</small></td>
                      <td data-label="数量 / 单位" class="legacy-stock-number">{{ row.quantity ?? (row.raw_quantity || '缺数量') }} {{ row.unit || '缺单位' }}<small>原单位：{{ row.raw_unit || '（空白）' }}{{ row.conversion_only ? ' · 转算专用' : '' }}</small></td>
                    </tr></tbody></table>
                </div>
              </details>
            </section>
            <h3>问题行 <span>{{ result.problem_count }} 行</span></h3>
            <p v-if="result.problems_truncated" class="legacy-stock-notice">仅展示前 {{ result.problems.length }} 条问题行，汇总覆盖全部数据行。请分批核对。</p>
            <p v-if="!result.problem_count" class="legacy-stock-notice">本轮预检未发现问题；结果仅供核对，不代表库存已登记。</p>
            <div v-else class="legacy-stock-table" tabindex="0" role="region" aria-label="旧库存表问题行">
              <table><thead><tr><th>原表行</th><th>物料 / 数量</th><th>供应商 / 位置</th><th>问题与建议</th></tr></thead>
                <tbody><tr v-for="row in result.problems" :key="row.row_number">
                  <td data-label="原表行">{{ row.row_number }}<small v-if="row.duplicate_of">重复第 {{ row.duplicate_of }} 行</small></td>
                  <td data-label="物料 / 数量"><strong>{{ row.values.item_name || '未填写物料名称' }}</strong><small>{{ row.values.new_item_code || row.values.item_code || '无物料编号' }}</small><span>{{ row.quantity ?? row.values[result.quantity_key] ?? '—' }} {{ row.unit || '缺单位' }}</span><small>原单位：{{ row.raw_unit || '（空白）' }}{{ row.conversion_only ? ' · 转算专用' : '' }}</small><small>{{ row.unit_basis }}</small></td>
                  <td data-label="供应商 / 位置">{{ row.values.supplier || '未填写供应商' }}<small>{{ row.values.location || '未填写位置' }}</small></td>
                  <td data-label="问题与建议"><ul><li v-for="(code, index) in row.issues" :key="code"><code>{{ code }}</code>：{{ row.suggestions[index] }}</li></ul>
                    <details><summary>查看原表字段</summary><dl><div v-for="(value, key) in row.raw" :key="key"><dt>{{ result.field_mapping[key]?.header || key }}</dt><dd>{{ value || '（空）' }}<template v-if="row.formula_fields.includes(key)"><br />文件缓存：{{ row.values[key] || '（空）' }}</template></dd></div></dl></details>
                  </td>
                </tr></tbody></table>
            </div>
          </template>
          <p v-else-if="!busy && !error" class="legacy-stock-empty">上传后查看数量、物料、仓位、供应商和重复行问题。关闭窗口会清除本次文件及结果。</p>
        </main>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<style scoped>
.legacy-stock-overlay { position: fixed; inset: 0; z-index: 90; background: #0f172a70; }
.legacy-stock-dialog { position: fixed; z-index: 91; top: 50%; left: 50%; transform: translate(-50%, -50%); width: min(1100px, calc(100vw - 48px)); max-height: 92dvh; display: flex; flex-direction: column; background: var(--card); color: var(--foreground); border: 1px solid var(--border); border-radius: 12px; box-shadow: 0 20px 60px #0003; font-size: 13px; }
header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; padding: 20px 24px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
header > div, main { min-width: 0; }
.legacy-stock-title { font-size: 20px; font-weight: 600; }
.legacy-stock-description { margin-top: 6px; color: var(--muted-foreground); line-height: 1.7; }
main { overflow: auto; padding: 20px 24px; }
.legacy-stock-upload { display: flex; align-items: end; flex-wrap: wrap; gap: 12px; }
.legacy-stock-upload label { display: grid; gap: 8px; flex: 1; min-width: 200px; }
input { max-width: 100%; min-width: 0; padding: 8px; border: 1px solid var(--border); border-radius: 6px; }
.legacy-stock-upload p { flex-basis: 100%; overflow-wrap: anywhere; color: var(--muted-foreground); }
.legacy-stock-notice, .legacy-stock-empty { margin: 16px 0; color: var(--muted-foreground); line-height: 1.7; overflow-wrap: anywhere; }
.legacy-stock-error { margin: 16px 0; padding: 12px; border: 1px solid var(--destructive); border-radius: 6px; color: var(--destructive); }
.legacy-stock-summary { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 16px 0; }
.legacy-stock-summary > div { padding: 12px 16px; border: 1px solid var(--border); border-radius: 8px; background: var(--muted); }
.legacy-stock-summary dt { color: var(--muted-foreground); font-size: 12px; }.legacy-stock-summary dd { font-size: 22px; font-weight: 600; margin-top: 4px; }
h3 { font-weight: 600; font-size: 15px; margin-top: 20px; margin-bottom: 10px; }h3 span { color: var(--muted-foreground); font-size: 12px; }
.legacy-stock-matches p, .legacy-stock-totals { display: flex; flex-wrap: wrap; gap: 8px 20px; margin: 8px 0; }.legacy-stock-totals span { padding: 6px 10px; background: var(--muted); border-radius: 6px; }
.legacy-stock-total-section { border: 1px solid var(--border); border-radius: 8px; padding: 12px 16px; margin-top: 12px; }.legacy-stock-total-section h4 { font-weight: 600; }.legacy-stock-total-section .legacy-stock-notice { margin: 8px 0; }.legacy-stock-number { text-align: right; font-variant-numeric: tabular-nums; }.legacy-stock-totals strong, .legacy-stock-summary dd { font-variant-numeric: tabular-nums; }.legacy-stock-duplicate-group { padding: 12px 0; border-top: 1px solid var(--border); }.legacy-stock-duplicate-group > summary { line-height: 1.7; overflow-wrap: anywhere; }.legacy-stock-unit-table td { width: auto; }
.legacy-stock-table { overflow: auto; }table { width: 100%; border-collapse: collapse; text-align: left; }th, td { padding: 12px; border-bottom: 1px solid var(--border); vertical-align: top; overflow-wrap: anywhere; }th { background: var(--muted); font-size: 12px; color: var(--muted-foreground); }td:first-child { width: 70px; }td:nth-child(2) { width: 25%; }td:nth-child(3) { width: 20%; }small { display: block; margin-top: 5px; color: var(--muted-foreground); }code { font-size: 11px; }li + li { margin-top: 6px; }details { margin-top: 10px; }summary { cursor: pointer; color: var(--primary); }details dl { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; padding-top: 8px; }details dt { color: var(--muted-foreground); }details dd { white-space: pre-wrap; }
@media(max-width:640px) { .legacy-stock-dialog { inset: 0; width: 100%; height: 100dvh; max-height: 100dvh; transform: none; border-radius: 0; }header, main { padding: 16px; }header { flex-wrap: wrap; }.legacy-stock-title { font-size: 18px; }.legacy-stock-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }.legacy-stock-dialog button, input { min-height: 44px; font-size: 16px; }.legacy-stock-upload label { min-width: 0; flex-basis: 100%; }table, tbody, tr, td { display: block; }thead { display: none; }tr { border: 1px solid var(--border); border-radius: 8px; margin-bottom: 12px; padding: 8px; }td, td:first-child, td:nth-child(2), td:nth-child(3) { width: auto; border: 0; padding: 8px; }td::before { content: attr(data-label); display: block; font-size: 12px; color: var(--muted-foreground); margin-bottom: 5px; }details dl { grid-template-columns: 1fr; } }
@media(max-width:640px) { .legacy-stock-number { text-align: left; }.legacy-stock-duplicate-group > summary { min-height: 44px; padding: 8px 0; } }
</style>
