<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ArrowRight, Check, Download, FileSpreadsheet, GitMerge, RefreshCw } from '@lucide/vue'
import { spreadsheetMergeApi, type MergeResolution, type MergeTemplate, type SpreadsheetInspection, type SpreadsheetMergePreview, type SpreadsheetMergeRequest } from '@/api/spreadsheetMerge'
import SectionPanel from '@/components/common/SectionPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import { Button } from '@/components/ui/button'
import { getApiErrorMessage } from '@/lib/http'
import { getAuthenticationGeneration } from '@/lib/authenticationGeneration'
import { useAuthStore } from '@/stores/auth'
import { cellText, columnLabel, extractMergeTable, sameNameMapping, saveSpreadsheetBlob, validateSpreadsheetFile } from './mergeHelpers'
import SpreadsheetSourcePanel from './SpreadsheetSourcePanel.vue'
import SpreadsheetGrid from './SpreadsheetGrid.vue'

const props = defineProps<{ factoryId: string }>()
const authStore = useAuthStore()
type Side = 'primary' | 'secondary'
type SourceState = { inspection: SpreadsheetInspection | null; sheet: string; headerRow: number; loading: boolean; error: string; preset: string }
const emptySource = (): SourceState => ({ inspection: null, sheet: '', headerRow: 1, loading: false, error: '', preset: '' })
const sources = reactive({ primary: emptySource(), secondary: emptySource() })
const primaryMode = ref('upload'), templates = ref<MergeTemplate[]>([]), selectedTemplateId = ref('')
const mapping = ref<number[]>([]), keyColumns = ref<number[]>([]), remarksColumn = ref(-1), extraColumns = ref<number[]>([])
const preview = ref<SpreadsheetMergePreview | null>(null), resolutions = ref<Record<string, MergeResolution>>({})
const error = ref(''), notice = ref(''), loadingTemplates = ref(false), busy = ref<'preview' | 'export' | ''>(''), resultPage = ref(1)
const batchSize = ref<number | null>(null), batchEnabled = ref(false)
const templateError = ref(''), templatesLoaded = ref(false)
const conflictPage = ref(1)
let sequence = 0, templateSequence = 0, disposed = false
const controllers: Partial<Record<Side | 'result' | 'templates', AbortController>> = {}
const sourceSequences = { primary: 0, secondary: 0 }
const selectedTemplate = computed(() => templates.value.find(template => template.id === selectedTemplateId.value))
function sourceTable(side: Side) {
  const source = sources[side]
  return extractMergeTable(`${source.inspection?.filename ?? ''} / ${source.sheet}`, source.inspection?.sheets.find(sheet => sheet.name === source.sheet)?.rows ?? [], source.headerRow)
}
const primary = computed(() => primaryMode.value === 'template' && selectedTemplate.value
  ? { name: selectedTemplate.value.label, headers: selectedTemplate.value.headers, rows: [], header_row: selectedTemplate.value.header_row }
  : primaryMode.value === 'upload' ? sourceTable('primary') : null)
const secondary = computed(() => sourceTable('secondary'))
const profile = computed(() => primaryMode.value === 'template' ? selectedTemplate.value?.profile ?? 'generic' : 'generic')
const unmatched = computed(() => secondary.value?.headers.map((header, index) => ({ header, index })).filter(item => (mapping.value[item.index] ?? -1) < 0) ?? [])
const conflictsRemaining = computed(() => preview.value?.conflicts.filter(conflict => !conflict.resolution).length ?? 0)
const conflictPageCount = computed(() => Math.max(1, Math.ceil((preview.value?.conflicts.length ?? 0) / 20)))
const visibleConflicts = computed(() => preview.value?.conflicts.slice((conflictPage.value - 1) * 20, conflictPage.value * 20) ?? [])
const canPreview = computed(() => !!primary.value && !!secondary.value && secondary.value.rows.length > 0 && !busy.value && !sources.primary.loading && !sources.secondary.loading)
const pageCount = computed(() => Math.max(1, Math.ceil((preview.value?.rows.length ?? 0) / 50)))
const visibleRows = computed(() => preview.value?.rows.slice((resultPage.value - 1) * 50, resultPage.value * 50) ?? [])
const issues = computed(() => [...(preview.value?.validation_errors ?? []), ...(preview.value?.issues.map(issue => `${issue.message}${issue.rows.length ? `（输出第 ${issue.rows.slice(0, 20).map(row => row + 2).join('、')} 行${issue.rows.length > 20 ? '等' : ''}）` : ''}`) ?? [])])
const ready = computed(() => !!preview.value && preview.value.ready_for_import && conflictsRemaining.value === 0)

function invalidate(clearDecisions = true) {
  sequence++
  controllers.result?.abort()
  preview.value = null
  if (clearDecisions) resolutions.value = {}
  busy.value = ''
  resultPage.value = 1
  conflictPage.value = 1
  error.value = ''
  notice.value = ''
}
function seedMapping() {
  mapping.value = sameNameMapping(primary.value?.headers ?? [], secondary.value?.headers ?? [])
  keyColumns.value = []
  remarksColumn.value = primary.value?.headers.findIndex(header => header === '备注') ?? -1
  extraColumns.value = []
}
function changeSource(side: Side, field: 'sheet' | 'headerRow', value: string | number) {
  invalidate()
  if (field === 'sheet') sources[side].sheet = String(value)
  else sources[side].headerRow = Number(value)
  seedMapping()
}
function changePreset(value: string) {
  controllers.secondary?.abort()
  sourceSequences.secondary++
  sources.secondary = { ...emptySource(), preset: value }
  invalidate()
  seedMapping()
}
async function upload(side: Side, file: File) {
  invalidate()
  controllers[side]?.abort()
  const stamp = ++sourceSequences[side], auth = getAuthenticationGeneration()
  const source = sources[side], preset = source.preset
  source.inspection = null
  source.error = validateSpreadsheetFile(file)
  source.loading = false
  seedMapping()
  if (source.error) return
  const controller = new AbortController()
  controllers[side] = controller
  source.loading = true
  try {
    const result = await spreadsheetMergeApi.inspect(file, preset, controller.signal)
    if (disposed || stamp !== sourceSequences[side] || auth !== getAuthenticationGeneration()) return
    source.inspection = result
    source.sheet = result.sheets[0]?.name ?? ''
    source.headerRow = 1
    seedMapping()
  } catch (caught) {
    if (!disposed && stamp === sourceSequences[side] && auth === getAuthenticationGeneration() && !controller.signal.aborted) source.error = getApiErrorMessage(caught)
  } finally { if (stamp === sourceSequences[side]) source.loading = false }
}
function buildRequest(): SpreadsheetMergeRequest | null {
  if (!primary.value || !secondary.value) return null
  const auditTables = new Map<string, NonNullable<SpreadsheetMergeRequest['audit_tables']>[number]>()
  for (const side of ['primary', 'secondary'] as const) {
    if (side === 'primary' && primaryMode.value !== 'upload') continue
    const source = sources[side]
    if (source.preset !== 'carton-packaging-source') continue
    for (const sheet of source.inspection?.sheets ?? []) {
      if (sheet.name !== '原表文字索引' || sheet.name === source.sheet) continue
      const table = extractMergeTable(`${source.inspection?.filename ?? ''} / ${sheet.name}`, sheet.rows, 1)
      if (table) auditTables.set(table.name, table)
    }
  }
  return {
    primary: primary.value, secondary: secondary.value,
    ...(primaryMode.value === 'template' && selectedTemplate.value ? { template_id: selectedTemplate.value.id, factory_id: props.factoryId } : {}),
    ...(auditTables.size ? { audit_tables: [...auditTables.values()] } : {}),
    mapping: mapping.value.flatMap((target, source) => target >= 0 ? [{ source, target }] : []),
    key_columns: [...keyColumns.value], remarks_column: remarksColumn.value >= 0 ? remarksColumn.value : null,
    extra_columns_to_remarks: extraColumns.value.filter(index => (mapping.value[index] ?? -1) < 0),
    resolutions: { ...resolutions.value }, profile: profile.value, batch_size: batchEnabled.value ? batchSize.value : null,
  }
}
async function runPreview() {
  const request = buildRequest()
  if (!request || sources.primary.loading || sources.secondary.loading || busy.value) return
  invalidate(false)
  const stamp = sequence, auth = getAuthenticationGeneration()
  const controller = new AbortController()
  controllers.result = controller
  busy.value = 'preview'
  try {
    const result = await spreadsheetMergeApi.preview(request, controller.signal)
    if (disposed || stamp !== sequence || auth !== getAuthenticationGeneration()) return
    preview.value = result
  } catch (caught) { if (!disposed && stamp === sequence && auth === getAuthenticationGeneration() && !controller.signal.aborted) error.value = getApiErrorMessage(caught) }
  finally { if (stamp === sequence) busy.value = '' }
}
async function decide(id: string | null, resolution: MergeResolution) {
  if (!preview.value || busy.value) return
  if (id) resolutions.value = { ...resolutions.value, [id]: resolution }
  else resolutions.value = { ...resolutions.value, ...Object.fromEntries(preview.value.conflicts.filter(conflict => !conflict.resolution).map(conflict => [conflict.id, resolution])) }
  await runPreview()
}
async function exportResult() {
  const request = buildRequest()
  if (!request || !preview.value || conflictsRemaining.value || busy.value) return
  const stamp = sequence, auth = getAuthenticationGeneration()
  const controller = new AbortController()
  controllers.result = controller
  busy.value = 'export'
  error.value = ''
  try {
    const result = await spreadsheetMergeApi.export(request, controller.signal)
    if (disposed || stamp !== sequence || auth !== getAuthenticationGeneration()) return
    saveSpreadsheetBlob(result.blob, result.filename)
    notice.value = `已生成 ${result.filename}，请在浏览器下载记录中查看。`
  } catch (caught) { if (!disposed && stamp === sequence && auth === getAuthenticationGeneration() && !controller.signal.aborted) error.value = getApiErrorMessage(caught) }
  finally { if (stamp === sequence) busy.value = '' }
}
async function loadTemplates() {
  const stamp = ++templateSequence, auth = getAuthenticationGeneration()
  const factoryId = props.factoryId
  controllers.templates?.abort()
  const controller = new AbortController()
  controllers.templates = controller
  loadingTemplates.value = true
  templatesLoaded.value = false
  templateError.value = ''
  templates.value = []
  selectedTemplateId.value = ''
  if (primaryMode.value === 'template') primaryMode.value = 'upload'
  invalidate()
  try {
    const result = await spreadsheetMergeApi.templates(factoryId, controller.signal)
    if (disposed || stamp !== templateSequence || auth !== getAuthenticationGeneration() || factoryId !== props.factoryId) return
    templates.value = result
    selectedTemplateId.value = result[0]?.id ?? ''
    templatesLoaded.value = true
  } catch (caught) { if (!disposed && stamp === templateSequence && auth === getAuthenticationGeneration() && !controller.signal.aborted) templateError.value = `系统模板读取失败：${getApiErrorMessage(caught)}` }
  finally { if (stamp === templateSequence) loadingTemplates.value = false }
}
function resetContext() {
  invalidate()
  for (const side of ['primary', 'secondary'] as const) { controllers[side]?.abort(); sourceSequences[side]++; sources[side] = emptySource() }
  controllers.templates?.abort()
  templateSequence++
  templates.value = []
  selectedTemplateId.value = ''
  loadingTemplates.value = false
  templatesLoaded.value = false
  templateError.value = ''
  primaryMode.value = 'upload'
  seedMapping()
}
function sessionChanged() {
  resetContext()
  if (authStore.isAuthenticated) void loadTemplates()
}
const authorizationContext = computed(() => {
  // Session refreshes advance the server clock without changing access.
  const { server_now: _serverNow, ...identityAuthorization } = authStore.currentUser?.identity ?? {}
  return JSON.stringify([
    authStore.authorizationVersion, identityAuthorization, authStore.permissions,
    authStore.grants, authStore.effectiveAccess, authStore.authzMode,
  ])
})
watch([() => authStore.currentUser?.id, authorizationContext], ([userId], [previousId]) => {
  if (disposed) return
  if (userId !== previousId) sessionChanged()
  else void loadTemplates()
})
watch([primaryMode, selectedTemplateId], () => { invalidate(); seedMapping() }, { flush: 'sync' })
watch(mapping, () => {
  keyColumns.value = keyColumns.value.filter(column => mapping.value.includes(column))
  extraColumns.value = extraColumns.value.filter(index => (mapping.value[index] ?? -1) < 0)
}, { deep: true, flush: 'sync' })
watch(remarksColumn, value => { if (value < 0) extraColumns.value = [] }, { flush: 'sync' })
watch([mapping, keyColumns, remarksColumn, extraColumns, batchEnabled, batchSize], () => invalidate(), { deep: true, flush: 'sync' })
watch(() => props.factoryId, () => { resetContext(); void loadTemplates() }, { flush: 'sync' })
onMounted(() => { void loadTemplates(); window.addEventListener('auth-session-boundary-changed', sessionChanged) })
onBeforeUnmount(() => { disposed = true; resetContext(); window.removeEventListener('auth-session-boundary-changed', sessionChanged) })
</script>

<template>
  <section class="sm-workspace" aria-label="表格转换与合并">
    <div class="sm-intro"><div><div class="sm-eyebrow"><GitMerge :size="18" aria-hidden="true" />表格转换与合并</div><h2>把不同格式的表格，整理到一张主表</h2><p>选择字段对应与匹配规则，先检查差异，再生成 Excel。此操作只生成文件。</p></div><StatusPill :label="preview ? ready ? '字段检查通过' : '待复核 / 补资料' : '等待选择表格'" :tone="preview ? ready ? 'green' : 'amber' : 'slate'" /></div>
    <ol class="sm-steps" aria-label="处理流程"><li><span>1</span>选择表格</li><li><span>2</span>对应字段</li><li><span>3</span>核对并导出</li></ol>
    <SectionPanel title="选择主表与副表" subtitle="主表决定输出列；副表按字段对应补齐或追加。原始内容保留在下载文件中供核对。">
      <div class="sm-sources">
        <div class="sm-source-block"><label class="sm-field">主表来源<select v-model="primaryMode" aria-label="主表来源"><option value="upload">上传自己的主表</option><option v-if="templates.length" value="template">系统导入模板</option></select></label>
          <template v-if="primaryMode === 'template'"><label class="sm-field">选择模板<select v-model="selectedTemplateId" aria-label="选择系统模板" :disabled="loadingTemplates"><option v-if="!templates.length" value="">{{ loadingTemplates ? '正在读取模板…' : '暂无可用模板' }}</option><option v-for="template in templates" :key="template.id" :value="template.id">{{ template.label }}</option></select></label><div v-if="selectedTemplate" class="surface-subtle sm-template"><FileSpreadsheet :size="28" aria-hidden="true" /><strong>{{ selectedTemplate.label }}</strong><p>{{ selectedTemplate.headers.length }} 个标准字段 · 空主表</p><p>{{ selectedTemplate.description }}</p><p>缺少必填资料时保留空白，导出待补版；完成补充后再到对应业务模块预览导入。</p></div><Button v-if="!templates.length && !loadingTemplates" variant="outline" size="sm" @click="loadTemplates">重新读取模板</Button></template>
          <SpreadsheetSourcePanel v-else label="主表" v-bind="sources.primary" @file="upload('primary', $event)" @sheet="changeSource('primary', 'sheet', $event)" @header-row="changeSource('primary', 'headerRow', $event)" />
          <p v-if="loadingTemplates" class="sm-help" role="status">正在读取当前厂区的可用系统模板…</p>
          <div v-else-if="templateError" class="sm-template-error"><p role="alert" class="sm-help">{{ templateError }}</p><Button variant="outline" size="sm" @click="loadTemplates">重新读取模板</Button></div>
          <p v-else-if="templatesLoaded && !templates.length" class="sm-help">当前厂区没有可用系统模板，可继续上传自己的主表。</p>
        </div>
        <SpreadsheetSourcePanel label="副表" v-bind="sources.secondary" secondary @file="upload('secondary', $event)" @sheet="changeSource('secondary', 'sheet', $event)" @header-row="changeSource('secondary', 'headerRow', $event)" @preset="changePreset" />
      </div>
    </SectionPanel>

    <SectionPanel title="字段对应与合并规则" subtitle="同名字段会自动对应；请核对后选择用于匹配同一条记录的主表字段。">
      <div v-if="!primary || !secondary" class="sm-empty"><GitMerge :size="28" aria-hidden="true" /><p>先选择有效的主表和副表，再设置字段对应。</p></div>
      <div v-else class="sm-rules">
        <div class="sm-mapping-wrap"><table class="sm-mapping"><thead><tr><th>副表字段</th><th aria-label="对应方向"></th><th>输出到主表字段</th></tr></thead><tbody><tr v-for="(header, index) in secondary.headers" :key="index"><td><span class="sm-column">{{ columnLabel(index) }}</span>{{ header }}</td><td><ArrowRight :size="14" aria-hidden="true" /></td><td><select v-model="mapping[index]" :aria-label="`副表字段 ${header} 对应主表字段`"><option :value="-1">不对应主表列</option><option v-for="(target, column) in primary.headers" :key="column" :value="column" :disabled="mapping.includes(column) && mapping[index] !== column">{{ columnLabel(column) }} · {{ target }}</option></select></td></tr></tbody></table></div>
        <div class="sm-rule-options"><fieldset><legend>匹配字段（可多选组成唯一条件）</legend><p class="sm-help">{{ keyColumns.length ? '所有选中字段相同才合并；空白仅补齐，已有不同值会列为冲突。' : '未选择匹配字段：副表全部追加为新行，不自动覆盖主表。' }}</p><p v-if="profile === 'carton-packaging'" class="sm-help">包装模板建议按货号、配置组、纸品类型、纸质、长宽高、尺寸单位、每箱装产品数、纸品行号、计算方式、对应箱行号和每箱配套用量组合匹配；请避免把不同包装或配套关系并成一条。</p><div class="sm-checks"><label v-for="(header, index) in primary.headers" :key="index"><input v-model="keyColumns" type="checkbox" :value="index" :aria-label="`匹配字段 ${header}`" :disabled="!mapping.includes(index)" />{{ header }}</label></div></fieldset>
          <label class="sm-field">备注输出列<select v-model="remarksColumn" aria-label="备注输出列"><option :value="-1">不合并额外字段到备注</option><option v-for="(header, index) in primary.headers" :key="index" :value="index">{{ header }}</option></select></label>
          <fieldset v-if="unmatched.length"><legend>把哪些副表额外字段拼入备注</legend><p class="sm-help">以“字段名：值”保留原意。未选字段仍在原表留档页中。</p><div class="sm-checks"><label v-for="item in unmatched" :key="item.index"><input v-model="extraColumns" type="checkbox" :value="item.index" :disabled="remarksColumn < 0" />{{ item.header }}</label></div></fieldset>
          <div><label class="sm-checkbox"><input v-model="batchEnabled" type="checkbox" />分批导出为 ZIP</label><label v-if="batchEnabled" class="sm-field mt-3">每份数据行数（1–1000）<input v-model.number="batchSize" type="number" min="1" max="1000" aria-label="每份数据行数" /></label></div>
        </div>
      </div>
      <div class="sm-section-actions"><p class="sm-help">调整来源或规则后，需要重新预览。</p><Button :disabled="!canPreview || (batchEnabled && (!batchSize || batchSize < 1 || batchSize > 1000))" @click="runPreview"><RefreshCw :size="16" aria-hidden="true" />{{ busy === 'preview' ? '正在核对…' : '预览合并结果' }}</Button></div>
    </SectionPanel>
    <div v-if="error" class="sm-error-box" role="alert">{{ error }}</div><p v-if="notice" class="sm-notice" role="status">{{ notice }}</p>

    <SectionPanel v-if="preview" title="核对合并结果" subtitle="核对问题与冲突后下载。模板字段检查通过后，导入前仍需业务预览。">
      <template #action><Button :disabled="!!busy || conflictsRemaining > 0" @click="exportResult"><Download :size="16" aria-hidden="true" />{{ busy === 'export' ? '正在生成…' : ready ? '下载合并结果' : '下载待补版' }}</Button></template>
      <div class="sm-stats"><div><strong>{{ preview.stats.output_rows }}</strong><span>输出行</span></div><div><strong>{{ preview.stats.added_rows }}</strong><span>新增行</span></div><div><strong>{{ preview.stats.filled_cells }}</strong><span>补齐单元格</span></div><div><strong>{{ conflictsRemaining }}</strong><span>待决定冲突</span></div></div>
      <div v-if="!ready" class="sm-review-note"><strong>{{ conflictsRemaining ? '先决定冲突的取值' : '资料待补充，请下载待补版继续整理' }}</strong><p>{{ conflictsRemaining ? '每项冲突必须明确选择保留主表或副表的值。' : '表格仍有缺项或需要复核的内容，不能据此认定可直接导入。' }}</p></div>
      <div v-if="preview.conflicts.length" class="sm-conflicts"><div class="sm-conflict-heading"><h3>值有差异的字段</h3><div v-if="conflictsRemaining" class="sm-button-row"><Button variant="outline" size="sm" :disabled="!!busy" @click="decide(null, 'primary')">全部未决项保留主表</Button><Button variant="outline" size="sm" :disabled="!!busy" @click="decide(null, 'secondary')">全部未决项采用副表</Button></div></div><div v-for="conflict in visibleConflicts" :key="conflict.id" class="sm-conflict"><div><strong>第 {{ conflict.row + 2 }} 行 · {{ preview.headers[conflict.column] }}</strong><span v-if="conflict.resolution" class="sm-resolved"><Check :size="14" aria-hidden="true" />已{{ conflict.resolution === 'primary' ? '保留主表' : '采用副表' }}</span></div><div class="sm-conflict-values"><p><span>主表</span>{{ cellText(conflict.primary) || '（空白）' }}</p><p><span>副表</span>{{ cellText(conflict.secondary) || '（空白）' }}</p></div><div class="sm-button-row"><Button variant="outline" size="sm" :disabled="!!busy" :aria-pressed="conflict.resolution === 'primary'" @click="decide(conflict.id, 'primary')">保留主表</Button><Button variant="outline" size="sm" :disabled="!!busy" :aria-pressed="conflict.resolution === 'secondary'" @click="decide(conflict.id, 'secondary')">采用副表</Button></div></div></div>
      <div v-if="preview.conflicts.length > 20" class="sm-pagination"><span>冲突第 {{ conflictPage }} / {{ conflictPageCount }} 页</span><div class="sm-button-row"><Button variant="outline" size="sm" :disabled="conflictPage <= 1" @click="conflictPage--">上一组冲突</Button><Button variant="outline" size="sm" :disabled="conflictPage >= conflictPageCount" @click="conflictPage++">下一组冲突</Button></div></div>
      <details v-if="issues.length || preview.warnings.length" open class="sm-issues"><summary>问题与提示 · {{ issues.length + preview.warnings.length }} 项</summary><ul><li v-for="(issue, index) in issues.slice(0, 100)" :key="`issue-${index}`">{{ issue }}</li><li v-for="(warning, index) in preview.warnings.slice(0, 100)" :key="`warning-${index}`">{{ warning }}</li></ul><p v-if="issues.length > 100 || preview.warnings.length > 100" class="sm-help">页面各显示前 100 项；完整问题请查看下载文件的说明页。</p></details>
      <SpreadsheetGrid :headers="preview.headers" :rows="visibleRows" :start-row="(resultPage - 1) * 50 + 2" caption="合并结果预览" />
      <div class="sm-pagination"><span>共 {{ preview.rows.length }} 行 · 第 {{ resultPage }} / {{ pageCount }} 页，每页最多 50 行</span><div class="sm-button-row"><Button variant="outline" size="sm" :disabled="resultPage <= 1" @click="resultPage--">上一页</Button><Button variant="outline" size="sm" :disabled="resultPage >= pageCount" @click="resultPage++">下一页</Button></div></div>
      <details v-if="preview.provenance.length" class="sm-provenance"><summary>查看本页记录的来源行</summary><ul><li v-for="(refs, index) in preview.provenance.slice((resultPage - 1) * 50, resultPage * 50)" :key="index"><strong>输出第 {{ (resultPage - 1) * 50 + index + 2 }} 行：</strong>{{ refs.map(item => `${item.table === 'primary' ? '主表' : '副表'} ${item.name} 第 ${item.row} 行`).join('；') }}</li></ul></details>
    </SectionPanel>
  </section>
</template>

<style scoped>
.sm-workspace { display: flex; flex-direction: column; gap: 24px; min-width: 0; }
.sm-intro { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap; }
.sm-eyebrow { color: var(--primary); font-size: 13px; font-weight: 600; display: flex; gap: 8px; align-items: center; margin-bottom: 8px; }
.sm-intro h2 { font-size: 22px; font-weight: 600; line-height: 1.5; }.sm-intro p { margin-top: 6px; font-size: 14px; color: var(--muted-foreground); line-height: 1.7; }
.sm-steps { display: flex; flex-wrap: wrap; gap: 12px 32px; font-size: 13px; color: var(--muted-foreground); }.sm-steps li { display: flex; gap: 8px; align-items: center; }.sm-steps li span { display: inline-grid; place-items: center; width: 24px; height: 24px; background: var(--accent); color: var(--primary); border-radius: 50%; font-weight: 600; }
.sm-sources { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 28px; }.sm-source-block { display: flex; flex-direction: column; gap: 14px; min-width: 0; }
.sm-template { display: flex; flex-direction: column; align-items: flex-start; gap: 10px; padding: 24px; border-radius: var(--radius); font-size: 14px; }.sm-template > svg { color: var(--primary); }.sm-template p { font-size: 13px; line-height: 1.7; color: var(--muted-foreground); }
.sm-field { display: flex; flex-direction: column; gap: 6px; font-size: 13px; font-weight: 500; min-width: 0; }
select, input[type=number] { width: 100%; border: 1px solid var(--input); border-radius: var(--radius); background: var(--card); padding: 8px 10px; height: 38px; font-size: 13px; min-width: 0; }
input[type=checkbox] { accent-color: var(--primary); width: 16px; height: 16px; flex-shrink: 0; }
.sm-empty { display: flex; align-items: center; flex-direction: column; padding: 24px; gap: 12px; color: var(--muted-foreground); font-size: 14px; text-align: center; }.sm-rules { display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr); gap: 28px; }
.sm-mapping-wrap { min-width: 0; overflow: auto; max-height: 530px; border: 1px solid var(--border); border-radius: var(--radius); }.sm-mapping { width: 100%; min-width: 410px; font-size: 13px; border-collapse: collapse; }.sm-mapping th, .sm-mapping td { padding: 10px 12px; border-bottom: 1px solid var(--border); text-align: left; }.sm-mapping th { font-size: 12px; background: var(--muted); position: sticky; top: 0; }.sm-mapping td:first-child { overflow-wrap: anywhere; }.sm-mapping select { min-width: 170px; }.sm-column { font-size: 11px; color: var(--muted-foreground); margin-right: 8px; }
.sm-rule-options { display: flex; flex-direction: column; gap: 22px; min-width: 0; }legend { font-size: 13px; font-weight: 600; margin-bottom: 8px; }.sm-help { font-size: 12px; line-height: 1.7; color: var(--muted-foreground); }.sm-checks { display: flex; flex-wrap: wrap; gap: 10px 16px; margin-top: 10px; }.sm-checks label, .sm-checkbox { display: flex; align-items: center; gap: 8px; font-size: 13px; overflow-wrap: anywhere; }
.sm-section-actions { margin-top: 24px; padding-top: 20px; border-top: 1px solid var(--border); display: flex; gap: 12px; justify-content: space-between; align-items: center; flex-wrap: wrap; }.sm-error-box { padding: 16px; border: 1px solid var(--destructive); color: var(--destructive); background: var(--card); border-radius: var(--radius); font-size: 14px; }.sm-notice { font-size: 14px; color: var(--primary); }
.sm-stats { display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 12px; margin-bottom: 22px; }.sm-stats > div { display: flex; flex-direction: column; gap: 4px; padding: 16px; border: 1px solid var(--border); border-radius: var(--radius); }.sm-stats strong { font-size: 25px; font-weight: 600; font-variant-numeric: tabular-nums; }.sm-stats span { font-size: 12px; color: var(--muted-foreground); }
.sm-review-note { padding: 14px 16px; border-left: 3px solid var(--primary); background: var(--muted); font-size: 14px; margin-bottom: 20px; border-radius: 0 var(--radius) var(--radius) 0; }.sm-review-note p { color: var(--muted-foreground); margin-top: 5px; font-size: 13px; }
.sm-conflicts { margin-bottom: 24px; }.sm-conflict-heading { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }.sm-conflict-heading h3 { font-size: 15px; font-weight: 600; }.sm-button-row { display: flex; flex-wrap: wrap; gap: 8px; }.sm-conflict { border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; margin-top: 12px; font-size: 13px; }.sm-conflict > div:first-child { display: flex; flex-wrap: wrap; gap: 12px; }.sm-resolved { color: var(--primary); display: flex; gap: 4px; align-items: center; }.sm-conflict-values { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 12px; padding: 12px 0; }.sm-conflict-values p { white-space: pre-wrap; overflow-wrap: anywhere; }.sm-conflict-values span { display: block; font-size: 12px; color: var(--muted-foreground); margin-bottom: 4px; }
.sm-issues { padding: 16px; border: 1px solid var(--border); background: var(--muted); border-radius: var(--radius); margin-bottom: 20px; font-size: 13px; }.sm-issues ul { max-height: 320px; overflow: auto; }.sm-issues ul, .sm-provenance ul { padding-left: 18px; margin-top: 10px; line-height: 1.8; overflow-wrap: anywhere; }.sm-pagination { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; margin-top: 14px; font-size: 12px; color: var(--muted-foreground); }.sm-provenance { margin-top: 18px; font-size: 12px; }summary { cursor: pointer; font-weight: 600; }
@media(max-width: 1000px) { .sm-rules { grid-template-columns: 1fr; } }
@media(max-width: 700px) { .sm-sources { grid-template-columns: 1fr; }.sm-source-block { border-bottom: 1px solid var(--border); padding-bottom: 24px; }.sm-intro h2 { font-size: 19px; }.sm-stats { grid-template-columns: repeat(2,minmax(0,1fr)); }.sm-conflict-values { grid-template-columns: 1fr; } }
</style>
