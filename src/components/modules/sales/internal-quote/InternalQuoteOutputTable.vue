<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch, type CSSProperties } from 'vue'
import { registerQuoteNavigationGuard } from '@/features/internal-quote/navigationGuard'
import { ArrowLeft, Check, FileSpreadsheet, LoaderCircle, RotateCcw, Save, Search, X } from '@lucide/vue'
import { internalQuoteOutputApi, type OutputCell, type OutputField, type OutputLayout } from '@/api/internalQuoteOutput'
import { useInternalQuoteDeskStore } from '@/stores/internalQuoteDesk'
import { getApiErrorMessage } from '@/lib/http'

const props = defineProps<{ quoteId: string; collaborationRoute: string }>()
const emit = defineEmits<{ saved: []; dirty: [value: boolean] }>()
const store = useInternalQuoteDeskStore()
const base = ref<OutputLayout>()
const display = ref<OutputLayout>()
const edits = ref<Record<string, string | number | null>>({})
const loading = ref(false)
const saving = ref(false)
const previewing = ref(false)
const error = ref('')
const notice = ref('')
const sheetName = ref('')
const zoom = ref(85)
const selectedCell = ref('')
const selectedGroups = ref<string[] | null>(null)
const drawer = ref(false)
const search = ref('')
let generation = 0
let previewSequence = 0
let timer: ReturnType<typeof setTimeout> | undefined
const changedCount = computed(() => Object.keys(edits.value).length)
const dirty = computed(() => changedCount.value > 0)
const sheet = computed(() => display.value?.sheets.find(s => s.name === sheetName.value) ?? display.value?.sheets[0])
const groupMap = computed(() => new Map((base.value?.groups ?? []).map(g => [g.id, g])))
const visibleGroups = computed(() => (base.value?.groups ?? []).filter(g =>
  (!selectedGroups.value || selectedGroups.value.includes(g.id))
  && (!search.value.trim() || `${g.label} ${g.section_name} ${g.category}`.toLowerCase().includes(search.value.trim().toLowerCase())),
))
const width = computed(() => (sheet.value?.widths ?? []).reduce((sum, w) => sum + w, 0))
watch(dirty, value => emit('dirty', value))

function messageOf(cause: unknown) {
  const response = cause as { response?: { data?: { detail?: unknown } } }
  return typeof response.response?.data?.detail === 'string' ? response.response.data.detail : getApiErrorMessage(cause)
}
function valueOf(field: OutputField) { return edits.value[field.id] !== undefined ? edits.value[field.id] : field.value }
function payload() {
  return { base_token: base.value!.base_token, edits: Object.entries(edits.value).map(([field_id, value]) => ({ field_id, value })) }
}
function setField(field: OutputField, value: string) {
  if (saving.value || loading.value) return
  const next = field.nullable && value === '' ? null : value
  const equal = field.kind === 'name' ? next === field.value : next == null ? field.value == null : next !== '' && field.value != null && field.value !== '' && Number(next) === Number(field.value)
  if (equal) delete edits.value[field.id]
  else edits.value[field.id] = next
  notice.value = ''
  error.value = ''
  ++previewSequence
  clearTimeout(timer)
  if (dirty.value) timer = setTimeout(preview, 650)
  else { display.value = base.value; previewing.value = false }
}
function update(field: OutputField, event: Event) { setField(field, (event.target as HTMLInputElement).value) }
function fieldsForCell(cell: OutputCell) {
  const group = cell.binding?.group && groupMap.value.get(cell.binding.group)
  return group ? group.fields.filter(f => f.kind === cell.binding?.kind) : []
}
function canEditCell(cell: OutputCell) {
  const binding = cell.binding
  if (!binding || saving.value || loading.value) return false
  return [binding.group, ...(binding.groups ?? [])].some(id => id && groupMap.value.get(id)?.editable)
}
function isInline(cell: OutputCell) {
  return selectedCell.value === cell.address && canEditCell(cell) && fieldsForCell(cell).length === 1
}
async function selectCell(cell: OutputCell) {
  if (!canEditCell(cell)) return
  selectedCell.value = cell.address
  if (fieldsForCell(cell).length !== 1) {
    selectedGroups.value = cell.binding?.group ? [cell.binding.group] : cell.binding?.groups ?? []
    search.value = ''
    drawer.value = true
  } else {
    await nextTick()
    document.querySelector<HTMLInputElement>('.output-cell-input')?.focus()
  }
}
function changedCell(cell: OutputCell) {
  const ids = [cell.binding?.group, ...(cell.binding?.groups ?? [])]
  return ids.some(id => id && groupMap.value.get(id)?.fields.some(f => Object.hasOwn(edits.value, f.id)))
}
async function load() {
  const id = props.quoteId
  const current = ++generation
  ++previewSequence
  clearTimeout(timer)
  loading.value = true
  error.value = ''
  try {
    const result = await internalQuoteOutputApi.get(id)
    if (current !== generation) return
    base.value = result
    display.value = result
    edits.value = {}
    selectedCell.value = ''
    if (!result.sheets.some(s => s.name === sheetName.value)) sheetName.value = result.sheets[0]?.name ?? ''
  } catch (cause) {
    if (current === generation) error.value = messageOf(cause)
  } finally {
    if (current === generation) loading.value = false
  }
}
async function preview() {
  if (!dirty.value || !base.value || saving.value) return
  const current = ++previewSequence
  const context = generation
  previewing.value = true
  try {
    const result = await internalQuoteOutputApi.preview(props.quoteId, payload())
    if (context !== generation || current !== previewSequence) return
    display.value = result
    error.value = ''
  } catch (cause) {
    if (context === generation && current === previewSequence) error.value = messageOf(cause)
  } finally {
    if (context === generation && current === previewSequence) previewing.value = false
  }
}
async function save() {
  if (!base.value || !dirty.value || saving.value) return
  const id = props.quoteId
  const context = generation
  clearTimeout(timer)
  ++previewSequence
  previewing.value = false
  saving.value = true
  error.value = ''
  try {
    const receipt = await internalQuoteOutputApi.save(id, payload())
    // Acknowledge the successful write before any subsequent read can fail.
    store.applySavedSections(id, receipt.sections)
    if (context !== generation) return
    edits.value = {}
    selectedCell.value = ''
    notice.value = '已保存到当前报价，原填写页已同步。'
    emit('saved')
    await load()
    if (error.value) notice.value = '修改已保存；表格尚未完整刷新，请重新读取。'
  } catch (cause) {
    if (context === generation) error.value = messageOf(cause)
  } finally {
    saving.value = false
  }
}
function canLeave() {
  if (saving.value) return false
  return !dirty.value || window.confirm('表格还有未保存修改。离开并放弃这些修改？')
}
async function reset() {
  if (saving.value || (dirty.value && !window.confirm('放弃表格中的未保存修改，重新读取原报价？'))) return
  notice.value = ''
  await load()
}
function beforeUnload(event: BeforeUnloadEvent) {
  if (dirty.value || saving.value) { event.preventDefault(); event.returnValue = '' }
}
onBeforeUnmount(registerQuoteNavigationGuard(canLeave))
window.addEventListener('beforeunload', beforeUnload)
onBeforeUnmount(() => { ++generation; ++previewSequence; clearTimeout(timer); window.removeEventListener('beforeunload', beforeUnload) })
watch(() => props.quoteId, () => {
  base.value = undefined; display.value = undefined; edits.value = {}; drawer.value = false; notice.value = ''
  void load()
}, { immediate: true })
defineExpose({ save, dirty, canLeave })
</script>

<template>
  <section class="output-table" data-testid="output-table" aria-label="输出表格编辑">
    <header class="output-toolbar">
      <div class="output-title"><FileSpreadsheet :size="22" /><span><strong>报价表格</strong><small>与输出表格相同版式 · 名称、原始单价可直接修改</small></span></div>
      <div class="output-actions">
        <RouterLink :to="collaborationRoute"><ArrowLeft :size="15" />返回填写 / 新增内容</RouterLink>
        <button :disabled="loading || saving" @click="reset"><RotateCcw :size="15" />重新读取</button>
        <button class="primary" data-testid="save-output-table" :disabled="!dirty || saving || loading" @click="save"><LoaderCircle v-if="saving" class="spinning" :size="16" /><Save v-else :size="16" />{{ saving ? '保存中…' : `保存修改${dirty ? `（${changedCount}）` : ''}` }}</button>
      </div>
    </header>
    <div class="output-status">
      <span v-if="base?.read_only">当前版本只读；需要修改时，请返回填写页复制新版本。</span>
      <span v-else>点击有绿色标记的单元格修改。合计及换算结果自动计算。</span>
      <span v-if="previewing"><LoaderCircle class="spinning" :size="13" />正在重算…</span>
      <span v-else-if="dirty" class="dirty">{{ changedCount }} 处未保存 · {{ error ? '需核对' : '表格显示试算结果' }}</span>
      <span v-else-if="notice"><Check :size="14" />{{ notice }}</span>
    </div>
    <div class="output-view-tools">
      <button @click="selectedGroups = null; search = ''; drawer = true"><Search :size="14" />查找名称 / 单价</button>
      <span>仅当前方案 {{ base?.version_label }}</span>
      <label>缩放 <select v-model.number="zoom" aria-label="表格缩放"><option v-for="size in [60, 70, 85, 100, 120]" :key="size" :value="size">{{ size }}%</option></select></label>
    </div>
    <p v-if="error" class="output-error" role="alert">{{ error }}<span v-if="dirty"> · 修改仍保留在本页，尚未确认保存。</span></p>
    <p v-if="display?.formula_errors.length" class="output-error">部分表格结果暂未算出，已标记“待核算”。请核对后再输出。</p>
    <p v-if="display?.warnings.length" class="output-error">{{ display.warnings.map(w => w.message).filter(Boolean).join(' ') }}</p>
    <div v-if="loading && !display" class="output-empty"><LoaderCircle class="spinning" />正在生成报价表格…</div>
    <div v-else-if="sheet" class="output-grid-scroll" :aria-busy="previewing || loading">
      <div :style="{ zoom: zoom / 100, width: `${width + 38}px`, position: 'relative' }" class="output-paper">
        <table class="output-grid" :style="{ width: `${width + 38}px` }" :aria-label="sheet.name">
          <colgroup><col style="width:38px"><col v-for="(w, i) in sheet.widths" :key="i" :style="{ width: `${w}px` }"></colgroup>
          <thead><tr><th class="output-corner" /><th v-for="(_, i) in sheet.widths" :key="i">{{ String.fromCharCode(65 + i) }}</th></tr></thead>
          <tbody><tr v-for="row in sheet.rows" :key="row.index" :style="{ height: `${row.height}px` }">
            <th class="output-row-number">{{ row.index }}</th>
            <td v-for="cell in row.cells" :key="cell.address" :rowspan="cell.rowspan" :colspan="cell.colspan" :style="cell.style as CSSProperties"
              :data-cell="cell.address" :class="{ editable: canEditCell(cell), changed: changedCell(cell), selected: selectedCell === cell.address, unavailable: cell.unavailable }">
              <template v-if="isInline(cell)">
                <label v-for="field in fieldsForCell(cell)" :key="field.id" class="output-inline-field">
                  <small v-if="field.kind === 'price'">{{ field.label }} {{ field.currency }}</small>
                  <input class="output-cell-input" :aria-label="`${field.label} ${field.currency}`.trim()" :value="valueOf(field) ?? ''" :type="field.kind === 'price' ? 'number' : 'text'" min="0" step="any" :disabled="saving" @input="update(field, $event)" @keydown.enter="selectedCell = ''" @keydown.esc="selectedCell = ''">
                </label>
              </template>
              <button v-else-if="canEditCell(cell)" class="output-cell-button" :aria-label="`修改 ${cell.address} ${cell.text}`" @click="selectCell(cell)">{{ cell.text || '　' }}</button>
              <span v-else>{{ cell.text }}</span>
            </td>
          </tr></tbody>
        </table>
        <img v-for="(picture, i) in sheet.images" :key="i" :src="picture.src" alt="报价产品图片" :style="{ position: 'absolute', left: `${picture.left + 38}px`, top: `${picture.top + 23}px`, width: `${picture.width}px`, height: `${picture.height}px`, objectFit: 'contain', pointerEvents: 'none' }">
      </div>
    </div>
    <footer class="output-tabs"><button v-for="s in display?.sheets" :key="s.name" :class="{ active: s.name === sheet?.name }" @click="sheetName = s.name; selectedCell = ''"><FileSpreadsheet :size="14" />{{ s.name }}</button><span>原始上传附件不附带</span></footer>
    <div v-if="drawer" class="output-drawer-backdrop" @click.self="drawer = false">
      <aside class="output-drawer" role="dialog" aria-modal="true" aria-label="修改原始名称与单价" @keydown.esc="drawer = false">
        <header><div><strong>名称与原始单价</strong><p>修改现有明细，保存到同一张报价。</p></div><button aria-label="关闭明细" @click="drawer = false"><X :size="20" /></button></header>
        <input v-model="search" class="output-search" placeholder="查找物料、部门或工序" aria-label="查找原始明细">
        <div class="output-source-list">
          <article v-for="group in visibleGroups" :key="group.id"><header><strong>{{ group.label }}</strong><small>{{ group.section_name }} · {{ group.category }}</small></header>
            <label v-for="field in group.fields" :key="field.id"><span>{{ field.label }} <b>{{ field.currency }}</b></span><input :aria-label="`${group.label} ${field.label} ${field.currency}`.trim()" :value="valueOf(field) ?? ''" :type="field.kind === 'price' ? 'number' : 'text'" min="0" step="any" :placeholder="field.nullable ? '留空时按原规则自动计算' : ''" :disabled="!group.editable || saving || loading" @input="update(field, $event)"></label>
          </article>
          <p v-if="!visibleGroups.length" class="output-empty">没有对应明细。新增内容请返回填写页。</p>
        </div>
        <p v-if="error" class="output-error" role="alert">{{ error }}</p>
        <footer><button @click="drawer = false">返回表格</button><button class="primary" :disabled="!dirty || saving || loading" @click="save">{{ saving ? '保存中…' : '保存修改' }}</button></footer>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.output-table{position:relative;min-width:0;border:1px solid #bddbd4;border-radius:14px;background:#fff;overflow:hidden;color:#234b45}.output-toolbar{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:18px 20px;background:#f3fbf8;flex-wrap:wrap}.output-title,.output-actions{display:flex;align-items:center;gap:10px}.output-title span{display:grid;gap:5px}.output-title strong{font-size:17px}.output-title small{font-size:12px;color:#607d77}.output-actions{flex-wrap:wrap}.output-table button,.output-actions a{display:inline-flex;align-items:center;justify-content:center;gap:6px;cursor:pointer}.output-actions button,.output-actions a,.output-view-tools button,.output-drawer footer button{border:1px solid #bddbd4;border-radius:7px;background:#fff;padding:9px 12px;color:#19685b;font-size:12px;text-decoration:none}.output-table button:disabled{opacity:.5;cursor:not-allowed}.output-table button.primary{background:#14796b;color:#fff;border-color:#14796b}.output-status{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:10px 20px;font-size:12px;border-top:1px solid #e4efeb;border-bottom:1px solid #e4efeb}.output-status span{display:inline-flex;align-items:center;gap:5px}.output-status .dirty{color:#a16a0a}.output-view-tools{display:flex;align-items:center;gap:16px;padding:9px 18px;background:#fafcfb;font-size:12px}.output-view-tools label{margin-left:auto}.output-view-tools select{padding:5px;border:1px solid #ccdcd7;border-radius:5px}.output-grid-scroll{overflow:auto;max-height:76vh;min-height:320px;background:#e7eeeb;padding:18px 20px 28px}.output-paper{background:white;box-shadow:0 3px 16px #163d3520}.output-grid{border-collapse:collapse;table-layout:fixed;line-height:1.3}.output-grid th{font-family:Arial,sans-serif;font-size:11px;font-weight:400;color:#61756e;background:#edf3f0;border:1px solid #d6e1dc;height:23px}.output-grid thead{position:sticky;top:-22px;z-index:2}.output-grid td{position:relative;padding:2px 4px;vertical-align:middle;overflow-wrap:anywhere}.output-grid td.editable:after{content:'';position:absolute;right:0;top:0;border-top:6px solid #24a58a;border-left:6px solid transparent;pointer-events:none}.output-grid td.editable:hover{box-shadow:inset 0 0 0 2px #7bccb8}.output-grid td.selected{outline:2px solid #169e83;outline-offset:-2px}.output-grid td.changed{background-color:#fff1bd!important}.output-grid td.unavailable{color:#aa5414!important}.output-table .output-cell-button{display:block;width:100%;min-height:18px;text-align:inherit;font:inherit;color:inherit;white-space:inherit;border:0;background:transparent;padding:0}.output-inline-field{display:flex;flex-direction:column;gap:2px;min-width:80px}.output-inline-field small{font:10px Arial;color:#276e60}.output-cell-input{width:100%;box-sizing:border-box;border:1px solid #269c81;background:#f5fffb;min-height:24px;font:inherit;color:#155d4e;padding:2px}.output-tabs{display:flex;align-items:center;gap:3px;padding:9px 12px;border-top:1px solid #d5e4df;background:#f5f9f7;flex-wrap:wrap}.output-tabs button{padding:9px 14px;background:transparent;border:0;border-radius:6px;font-size:12px;color:#56736a}.output-tabs button.active{color:#087762;background:#def2e9;font-weight:700}.output-tabs span{margin-left:auto;font-size:11px;color:#83938e}.output-error{margin:0;padding:11px 18px;background:#fff1ed;color:#a13620;font-size:13px;line-height:1.6}.output-empty{display:flex;align-items:center;justify-content:center;gap:10px;min-height:100px;padding:20px;color:#71877f}.output-drawer-backdrop{position:fixed;inset:0;z-index:120;background:#133d343b;display:flex;justify-content:flex-end}.output-drawer{display:flex;flex-direction:column;width:min(470px,100vw);height:100%;background:#fff;box-shadow:-12px 0 40px #102f2920}.output-drawer>header{display:flex;justify-content:space-between;align-items:flex-start;padding:22px 24px;background:#f0faf6}.output-drawer header p{margin:8px 0 0;font-size:12px;color:#647f74}.output-drawer header button{background:none;border:0;color:#426b5f}.output-search{margin:16px 20px;padding:10px 12px;border:1px solid #c7dbd1;border-radius:7px;font-size:13px}.output-source-list{overflow:auto;flex:1;padding:0 20px}.output-source-list article{border:1px solid #dce8e1;border-radius:9px;padding:15px;margin-bottom:14px}.output-source-list article header{display:grid;gap:5px;margin-bottom:13px}.output-source-list article header strong{font-size:14px}.output-source-list article header small{font-size:11px;color:#7a8d84}.output-source-list label{display:grid;grid-template-columns:110px minmax(0,1fr);align-items:center;gap:10px;margin-top:9px;font-size:12px}.output-source-list label b{font-size:10px;color:#719083}.output-source-list input{min-width:0;width:100%;box-sizing:border-box;padding:8px;border:1px solid #cdded4;border-radius:5px;font-size:13px}.output-source-list input:disabled{background:#f5f7f6;color:#718277}.output-drawer footer{display:flex;justify-content:flex-end;gap:10px;padding:18px 20px;border-top:1px solid #dbe8e0}.spinning{animation:output-spin 1s linear infinite}@keyframes output-spin{to{transform:rotate(360deg)}}@media(max-width:700px){.output-toolbar{padding:13px}.output-title small{font-size:11px}.output-grid-scroll{padding:10px}.output-view-tools{gap:8px}.output-view-tools>span{display:none}}
</style>
