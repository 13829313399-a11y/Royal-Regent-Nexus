<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { CircleAlert, ClipboardList, Copy, Download, FileInput, FileSpreadsheet, Inbox, LockKeyhole } from '@lucide/vue'
import PageHeader from '@/components/common/PageHeader.vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import { Button } from '@/components/ui/button'
import { huakangBJPApi as api, type JPCapabilities, type JPReferenceKind, type JPReference, type JPPreview, type JPRow, type JPExportRecord } from '@/api/huakangBJP'
import { getApiErrorMessage } from '@/lib/http'

const props = defineProps<{ factoryId: string }>()
const emptyCaps: JPCapabilities = { read: false, write: false, export: false, available: false }
const caps = ref<JPCapabilities>({ ...emptyCaps })
const references = ref<Partial<Record<JPReferenceKind, JPReference>>>({})
const refFiles = ref<Partial<Record<JPReferenceKind, File>>>({})
const confirmedCurrency = ref('')
const mails = ref<File[]>([])
const html = ref('')
const pastedText = ref('')
const pastedRichText = ref(false)
const subject = ref('')
const merchandiser = ref('')
const receivedDate = ref(new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai' }).format(new Date()))
const preview = ref<JPPreview | null>(null)
const original = ref<JPRow[]>([])
const selected = ref<string[]>([])
const quantityColumns = ref<Record<string, string>>({})
const reason = ref('')
const confirmed = ref(false)
const busy = ref(false)
const loading = ref(false)
const loadFailed = ref(false)
const error = ref('')
const notice = ref('')
const records = ref<JPExportRecord[]>([])
const totalRecords = ref(0)
const page = ref(1)
const clipboardText = ref('')
const clipboardMessage = ref('')
const clipboardTextarea = ref<HTMLTextAreaElement | null>(null)
let epoch = 0
let controller = new AbortController()
const referenceKinds = [
  { kind: 'schedule' as const, label: '排期参照' }, { kind: 'price' as const, label: '货价表' }, { kind: 'confirmed' as const, label: '文员已确认货价表（可选）' },
]
const editable = [
  ['customer', '客名'], ['customer_po', '客PO'], ['qty', '数量'], ['pkg', '版本'], ['country', '国家'],
  ['carton_t', '装箱数'], ['ship_date', '行Q期D'], ['cutoff_date', '截数期'], ['price_t', '货价HKD'],
  ['factory_price_t', '出厂价HKD'], ['note', '备注'],
] as const
const canPreview = computed(() => props.factoryId === 'huakang-b' && caps.value.read && caps.value.available && !busy.value && !loading.value)
const exportBlockers = computed(() => {
  if (!preview.value) return []
  const blockers: string[] = []
  if (!references.value.schedule || !references.value.price) blockers.push('先上传并验证排期参照和货价表。')
  if (preview.value.failed_sources.length) blockers.push('仍有未识别来源，请移除或修正后重新解析。')
  if (preview.value.quantity_selections.length) blockers.push('先选定数量列，再按所选数量列重新解析。')
  if (!selected.value.length) blockers.push('至少选择一条未重复的问单明细。')
  const missingPrices = preview.value.rows.filter(row => selected.value.includes(row.id) && !row.price_t.trim())
  if (missingPrices.length) blockers.push(`${missingPrices.length} 条所选明细的货价HKD为空，请按当前客名和装箱数重新核价。`)
  if (!merchandiser.value.trim()) blockers.push('填写金山业务跟单名称。')
  if (reason.value.trim().length < 4 || reason.value.trim().length > 500) blockers.push('填写 4–500 字的核对原因。')
  if (!confirmed.value) blockers.push('核对所选明细和两项价格后勾选确认。')
  return blockers
})
const canExport = computed(() => canPreview.value && caps.value.export && preview.value && selected.value.length > 0
  && !exportBlockers.value.length)
const pageStatus = computed<{ label: string; tone: 'slate' | 'teal' | 'amber' | 'red' }>(() => {
  if (loading.value) return { label: '正在加载', tone: 'slate' }
  if (props.factoryId !== 'huakang-b') return { label: '华康B专用', tone: 'slate' }
  if (loadFailed.value) return { label: '加载未完成', tone: 'red' }
  if (error.value && !caps.value.read) return { label: '暂不可用', tone: 'red' }
  if (!caps.value.read) return { label: '无读取权限', tone: 'slate' }
  if (!caps.value.available) return { label: '尚未启用', tone: 'amber' }
  if (busy.value) return { label: '处理中', tone: 'teal' }
  if (!caps.value.export) return { label: '仅可核对', tone: 'slate' }
  return preview.value ? { label: '待核对明细', tone: 'amber' } : { label: '可开始录入', tone: 'teal' }
})
const reviewCounts = computed(() => ({
  selected: selected.value.length,
  existing: preview.value?.rows.filter(row => row.exists).length ?? 0,
  priceReview: preview.value?.rows.filter(priceNeedsReview).length ?? 0,
}))

function invalidate() { preview.value = null; original.value = []; selected.value = []; confirmed.value = false; notice.value = '' }
function priceNeedsReview(row: JPRow) {
  const before = original.value.find(item => item.id === row.id)
  return row.price_confirm || !row.price_t.trim() || Boolean(before && (row.customer !== before.customer || row.carton_t !== before.carton_t))
}
function rowEdited(row: JPRow, field: string) {
  confirmed.value = false
  if (field === 'customer' || field === 'carton_t') {
    row.price_t = ''; row.factory_price_t = ''
    row.price_note = '客名或装箱数已更正，旧价格已清空；请按新条件重新填写核对货价及出厂价。'
  }
}
function clearProtected() { invalidate(); references.value = {}; records.value = []; caps.value = { ...emptyCaps }; clipboardText.value = ''; clipboardMessage.value = '' }
function handleError(cause: unknown) {
  error.value = getApiErrorMessage(cause)
  const status = (cause as { response?: { status?: number } })?.response?.status
  if (status === 401 || status === 403) clearProtected()
}
async function load() {
  controller.abort(); controller = new AbortController()
  const token = ++epoch
  clearProtected()
  loadFailed.value = false
  if (props.factoryId !== 'huakang-b') return
  loading.value = true
  error.value = ''
  try {
    const capabilities = await api.capabilities(props.factoryId, controller.signal)
    if (token !== epoch) return
    caps.value = capabilities
    if (!capabilities.read || !capabilities.available) return
    const [refs, history] = await Promise.all([api.references(props.factoryId, controller.signal), api.exports(props.factoryId, page.value, controller.signal)])
    if (token !== epoch) return
    references.value = refs; records.value = history.items; totalRecords.value = history.total
  } catch (cause) { if (token === epoch) { loadFailed.value = true; handleError(cause) } }
  finally { if (token === epoch) loading.value = false }
}
function fileChanged(event: Event, kind?: JPReferenceKind) {
  const input = event.target as HTMLInputElement
  if (kind) { refFiles.value[kind] = input.files?.[0]; if (kind === 'confirmed') confirmedCurrency.value = '' }
  else { mails.value = Array.from(input.files ?? []); quantityColumns.value = {}; invalidate() }
  input.value = ''
}
function removeMail(index: number) {
  if (busy.value) return
  mails.value = mails.value.filter((_, position) => position !== index)
  quantityColumns.value = {}; invalidate()
  notice.value = '已移除所选文件；请重新解析当前来源。'
}
function editPastedText(event: Event) {
  pastedText.value = (event.target as HTMLTextAreaElement).value
  html.value = pastedText.value; pastedRichText.value = false
  quantityColumns.value = {}; invalidate()
}
function pasteBody(event: ClipboardEvent) {
  if (busy.value || !event.clipboardData) return
  const rich = event.clipboardData.getData('text/html')
  const plain = event.clipboardData.getData('text/plain')
  if (!rich && !plain) return
  event.preventDefault()
  html.value = rich || plain
  // Never render clipboard HTML. Only its readable text is displayed; the
  // original table markup is retained for the server until the user edits it.
  if (plain) pastedText.value = plain
  else {
    const template = document.createElement('template')
    template.innerHTML = rich
    template.content.querySelectorAll('script, style, noscript, template').forEach(node => node.remove())
    template.content.querySelectorAll('td, th').forEach(node => node.append('\t'))
    template.content.querySelectorAll('tr, p, div, li').forEach(node => node.append('\n'))
    pastedText.value = template.content.textContent || ''
  }
  pastedRichText.value = Boolean(rich)
  quantityColumns.value = {}; invalidate()
}
function clearPastedBody() {
  if (busy.value) return
  html.value = ''; pastedText.value = ''; pastedRichText.value = false; subject.value = ''
  quantityColumns.value = {}; invalidate()
  notice.value = '已移除粘贴正文；上传的邮件文件仍保留，请重新解析。'
}
async function removePastedAndParse() {
  if (busy.value) return
  clearPastedBody()
  if (mails.value.length) await parse()
}
async function upload(kind: JPReferenceKind) {
  const file = refFiles.value[kind]
  if (!canPreview.value || !caps.value.write || !file) return
  const token = epoch
  busy.value = true; error.value = ''; invalidate()
  const body = new FormData()
  body.append('factory_id', props.factoryId); body.append('expected_revision', String(references.value[kind]?.revision ?? 0)); body.append('file', file)
  if (kind === 'confirmed') body.append('currency', confirmedCurrency.value)
  try {
    const refs = await api.upload(kind, body, controller.signal)
    if (token !== epoch) return
    references.value = refs; notice.value = '参照验证成功，已保存新版本；旧版本与历史导出仍保留。'
  } catch (cause) { if (token === epoch) handleError(cause) }
  finally { if (token === epoch) busy.value = false }
}
async function clearConfirmed() {
  if (!canPreview.value || !caps.value.write) return
  if (!window.confirm('停用当前文员确认价？历史确认表和导出记录会保留。')) return
  const token = epoch
  busy.value = true; error.value = ''; invalidate()
  const body = new FormData()
  body.append('factory_id', props.factoryId)
  body.append('expected_revision', String(references.value.confirmed?.revision ?? 0))
  try {
    const refs = await api.clearConfirmed(body, controller.signal)
    if (token !== epoch) return
    references.value = refs; notice.value = '当前确认价已停用，历史版本仍保留；请重新解析核对。'
  } catch (cause) { if (token === epoch) handleError(cause) }
  finally { if (token === epoch) busy.value = false }
}
function form() {
  const body = new FormData()
  body.append('factory_id', props.factoryId); body.append('received_date', receivedDate.value)
  body.append('html', html.value); body.append('subject', subject.value)
  body.append('merchandiser', merchandiser.value.trim())
  for (const file of mails.value) body.append('files', file)
  body.append('quantity_selections', JSON.stringify(Object.entries(quantityColumns.value).filter(([, value]) => value !== '').map(([key, value]) => {
    const [source_id, index] = key.split(':')
    return { source_id, table_index: Number(index), column_index: Number(value) }
  })))
  return body
}
async function parse() {
  if (!canPreview.value) return
  const token = epoch
  busy.value = true; error.value = ''; invalidate()
  try {
    const result = await api.preview(form(), controller.signal)
    if (token !== epoch) return
    if (result.factory_id !== props.factoryId) throw new Error('返回的厂区不一致，结果已拒绝显示')
    preview.value = result; original.value = JSON.parse(JSON.stringify(result.rows)) as JPRow[]
    selected.value = result.rows.filter(row => !row.exists).map(row => row.id)
  } catch (cause) { if (token === epoch) handleError(cause) }
  finally { if (token === epoch) busy.value = false }
}
async function download(id: string) {
  if (!canPreview.value || !caps.value.export) return
  const token = epoch
  busy.value = true; error.value = ''
  try {
    const blob = await api.download(props.factoryId, id, controller.signal)
    if (token !== epoch) return
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a'); a.href = url; a.download = `JP问单-${id}.xlsx`; a.click()
    URL.revokeObjectURL(url)
  } catch (cause) { if (token === epoch) handleError(cause) }
  finally { if (token === epoch) busy.value = false }
}
async function copyExport(id: string) {
  if (!canPreview.value || !caps.value.export) return
  const token = epoch
  busy.value = true; error.value = ''; clipboardText.value = ''; clipboardMessage.value = ''
  try {
    const result = await api.clipboard(props.factoryId, id, controller.signal)
    if (token !== epoch) return
    if (result.column_count !== 44 || !result.text || result.row_count < 1) throw new Error('已生成记录的复制数据不完整，请下载原导出核对。')
    clipboardText.value = result.text
    const record = records.value.find(item => item.id === id)
    const label = record ? `${record.prefix}-${record.first_number} 至 ${record.last_number}` : '所选记录'
    clipboardMessage.value = `已读取 ${label} 的 ${result.row_count} 行已生成数据，每行 44 列，不含表头；不会重新分配编号。`
    let timer: ReturnType<typeof setTimeout> | undefined
    try {
      if (!navigator.clipboard?.writeText) throw new Error('clipboard unavailable')
      await Promise.race([
        navigator.clipboard.writeText(result.text),
        new Promise<never>((_, reject) => { timer = setTimeout(() => reject(new Error('clipboard timeout')), 10_000) }),
      ])
      if (token === epoch) clipboardMessage.value += ' 已复制，可粘贴到 Excel。'
    } catch {
      if (token === epoch) clipboardMessage.value += ' 浏览器未完成自动复制，请点击“选中全部文本”后手动复制。'
    } finally { if (timer !== undefined) clearTimeout(timer) }
  } catch (cause) { if (token === epoch) handleError(cause) }
  finally { if (token === epoch) busy.value = false }
}
function selectClipboardText() { clipboardTextarea.value?.focus(); clipboardTextarea.value?.select() }
async function exportRows() {
  if (!canExport.value || !preview.value) return
  const token = epoch
  const body = form()
  const changes = preview.value.rows.filter(row => selected.value.includes(row.id)).flatMap(row => {
    const before = original.value.find(item => item.id === row.id)!
    const contextChanged = row.customer !== before.customer || row.carton_t !== before.carton_t
    const priceReviewRequired = contextChanged || before.price_confirm
    return editable.flatMap(([field]) => !((field === 'price_t' || field === 'factory_price_t') && priceReviewRequired)
      && String(row[field] ?? '') === String(before[field] ?? '') ? [] : [{ id: row.id, field, value: String(row[field] ?? '') }])
  })
  body.append('fingerprint', preview.value.fingerprint); body.append('selected', JSON.stringify(selected.value))
  body.append('overrides', JSON.stringify(changes)); body.append('reason', reason.value.trim()); body.append('confirmed', 'true')
  busy.value = true; error.value = ''
  try {
    const result = await api.export(body, controller.signal)
    if (token !== epoch) return
    confirmed.value = false
    const history = await api.exports(props.factoryId, 1, controller.signal)
    if (token !== epoch) return
    records.value = history.items; totalRecords.value = history.total; page.value = 1
    notice.value = `已保留 ${result.row_count} 行的编号与导出记录。请从下方下载；重复下载不会分配新号。未写入正式订单或下发生产。`
  } catch (cause) { if (token === epoch) handleError(cause) }
  finally { if (token === epoch) busy.value = false }
}
async function historyPage(next: number) {
  if (!canPreview.value || next < 1 || next > Math.ceil(totalRecords.value / 20)) return
  const token = epoch
  busy.value = true
  try {
    const result = await api.exports(props.factoryId, next, controller.signal)
    if (token !== epoch) return
    records.value = result.items; totalRecords.value = result.total; page.value = next
  } catch (cause) { if (token === epoch) handleError(cause) }
  finally { if (token === epoch) busy.value = false }
}
watch(() => props.factoryId, () => {
  mails.value = []; html.value = ''; pastedText.value = ''; pastedRichText.value = false; subject.value = ''; merchandiser.value = ''; refFiles.value = {}; confirmedCurrency.value = ''; quantityColumns.value = {}; busy.value = false; page.value = 1; void load()
}, { immediate: true })
onBeforeUnmount(() => { epoch += 1; controller.abort() })
</script>

<template>
  <section class="jp-intake" data-testid="huakang-b-jp-intake" :aria-busy="loading || busy">
    <PageHeader title="华康B · JP问单录入" eyebrow="客户订单中心"
      description="解析邮件、核对排期与货价，生成金山用的 44 列问单 Excel。">
      <template #actions>
        <StatusPill :label="pageStatus.label" :tone="pageStatus.tone" />
      </template>
    </PageHeader>

    <div class="jp-boundary surface-subtle" role="note">
      <ClipboardList aria-hidden="true" />
      <p>仅用于问单核对与导出。问单不计入正式订单，不自动安排生产或调整库存。</p>
    </div>

    <div v-if="error" class="jp-message jp-message--error" role="alert">
      <CircleAlert aria-hidden="true" />
      <div class="jp-message__content"><strong>{{ loadFailed ? (caps.read ? '参照与历史读取失败' : '页面加载失败') : '操作未完成' }}</strong><p>{{ error }}</p></div>
      <Button v-if="(loadFailed || !caps.read) && factoryId === 'huakang-b'" variant="outline" :disabled="loading || busy" @click="load">重新加载</Button>
    </div>
    <div v-if="notice" class="jp-message jp-message--success" role="status">
      <ClipboardList aria-hidden="true" /><p>{{ notice }}</p>
    </div>

    <SectionPanel v-if="loading" class="jp-panel">
      <div class="jp-empty" role="status">
        <div class="jp-state-icon"><FileSpreadsheet aria-hidden="true" /></div>
        <h2>正在核对权限及参照…</h2>
        <p>读取当前厂区的参照版本与历史记录，请稍候。</p>
      </div>
    </SectionPanel>
    <SectionPanel v-else-if="factoryId !== 'huakang-b'" class="jp-panel">
      <div class="jp-empty"><div class="jp-state-icon"><LockKeyhole aria-hidden="true" /></div>
        <h2>请切换至华康B</h2><p>JP 问单录入仅提供华康B的参照与导出记录。</p>
      </div>
    </SectionPanel>
    <SectionPanel v-else-if="!caps.read && !error" class="jp-panel">
      <div class="jp-empty"><div class="jp-state-icon"><LockKeyhole aria-hidden="true" /></div>
        <h2>没有华康B订单读取权限。</h2><p>请联系管理员确认当前账号的访问权限。</p>
      </div>
    </SectionPanel>
    <SectionPanel v-else-if="caps.read && !caps.available" class="jp-panel">
      <div class="jp-empty"><div class="jp-state-icon"><CircleAlert aria-hidden="true" /></div>
        <h2>JP问单录入尚未启用</h2><p>请联系管理员完成启用后再试。</p>
      </div>
    </SectionPanel>

    <template v-if="!loading && !loadFailed && caps.read && caps.available && factoryId === 'huakang-b'">
      <p v-if="busy" class="jp-processing" role="status">正在处理，请稍候。完成后可继续核对或下载。</p>

      <SectionPanel title="01 · 当前参照" subtitle="使用当前版本查重和核价；更新后保留旧版本与历史导出。" class="jp-panel">
        <template #action><StatusPill v-if="!caps.write" label="参照只读" tone="slate" /></template>
        <div class="jp-reference-grid">
          <article v-for="entry in referenceKinds" :key="entry.kind" class="jp-reference surface-subtle">
            <div class="jp-reference__heading">
              <FileSpreadsheet aria-hidden="true" />
              <h3>{{ entry.label }}</h3>
              <StatusPill :label="references[entry.kind] ? `V${references[entry.kind]?.revision}` : '待上传'"
                :tone="references[entry.kind] ? 'teal' : entry.kind === 'confirmed' ? 'slate' : 'amber'" compact />
            </div>
            <p class="jp-reference__file" :title="references[entry.kind]?.name">{{ references[entry.kind]?.name ?? '尚未上传' }}</p>
            <template v-if="caps.write">
              <label class="jp-field">
                <span class="jp-muted">选择新的 XLSX 文件</span>
                <input class="jp-file-input" type="file" accept=".xlsx" :aria-label="entry.label"
                  :disabled="busy || loading" @change="fileChanged($event, entry.kind)">
              </label>
              <p v-if="refFiles[entry.kind]" class="jp-file-pending">待验证：{{ refFiles[entry.kind]?.name }}</p>
              <label v-if="entry.kind === 'confirmed'" class="jp-field">
                <span>确认表裸数字的币种</span>
                <select v-model="confirmedCurrency" :disabled="busy">
                  <option value="">由表内确认币种或 HK$/US$ 标签明确</option>
                  <option value="HKD">这份表的裸数字全部为港币 HKD</option>
                  <option value="USD">这份表的裸数字全部为美元 USD</option>
                </select>
              </label>
            </template>
            <p v-if="entry.kind === 'confirmed' && references.confirmed?.options?.currency" class="jp-muted">
              当前数字币种：{{ references.confirmed.options.currency }}
            </p>
            <div v-if="caps.write" class="jp-reference__actions">
              <Button variant="outline" :disabled="!canPreview || !refFiles[entry.kind]" @click="upload(entry.kind)">验证并更新</Button>
              <Button v-if="entry.kind === 'confirmed' && references.confirmed" variant="ghost" :disabled="!canPreview" @click="clearConfirmed">停用当前确认价</Button>
            </div>
          </article>
        </div>
        <p class="jp-help">排期参照和货价表由有更新权限的人员维护。确认价表为可选项，请核对币种后上传。</p>
      </SectionPanel>

      <SectionPanel title="02 · 上传或粘贴邮件" subtitle="填写来单信息，再选择邮件文件或粘贴邮件正文。" class="jp-panel">
        <div class="jp-form-grid">
          <label class="jp-field"><span>业务跟单（金山人员名称）<span class="jp-required">必填</span></span>
            <input v-model="merchandiser" aria-label="业务跟单" maxlength="128" placeholder="填写金山中的人员名称" :disabled="busy" @input="invalidate">
          </label>
          <label class="jp-field"><span>来单日期（邮件无日期时使用）</span>
            <input v-model="receivedDate" type="date" :disabled="busy" @input="invalidate">
          </label>
        </div>
        <p class="jp-help">订单创建人：{{ caps.creator_name || '当前账号' }}。业务跟单名称请与金山人员字段一致。</p>
        <div class="jp-mail-grid">
          <div class="jp-upload-area surface-subtle">
            <span class="jp-state-icon"><FileInput aria-hidden="true" /></span>
            <div><h3>上传问单邮件</h3><p class="jp-muted">支持 EML 邮件及 ZIP 邮件包，可一次选择多份。</p></div>
            <input class="jp-file-input" type="file" accept=".eml,.zip" multiple aria-label="问单邮件" :disabled="busy" @change="fileChanged($event)">
            <ul v-if="mails.length" class="jp-file-list" aria-label="已选择邮件"><li v-for="(file, index) in mails" :key="`${index}-${file.name}`"><FileInput aria-hidden="true" /><span>{{ file.name }}</span><Button size="sm" variant="ghost" :aria-label="`移除 ${file.name}`" :disabled="busy" @click="removeMail(index)">移除</Button></li></ul>
            <p v-else class="jp-muted">尚未选择邮件</p>
            <p class="jp-upload-limit">单文件最多 20MB，合计最多 50MB；每批最多 100 封邮件、250 条明细。过大批次请拆分。</p>
          </div>
          <div class="jp-paste-area">
            <h3>或粘贴邮件正文</h3>
            <label class="jp-field"><span>粘贴正文的邮件主题</span>
              <input v-model="subject" maxlength="500" placeholder="填写原邮件主题" :disabled="busy" @input="invalidate">
            </label>
            <label class="jp-field"><span>邮件正文（可直接粘贴表格）</span>
              <textarea :value="pastedText" aria-label="邮件正文" rows="5" placeholder="从邮箱复制完整正文和订单表格，在这里粘贴；无需取得 HTML 源码" :disabled="busy" @paste="pasteBody" @input="editPastedText" />
            </label>
            <p class="jp-help">每次粘贴会替换本次正文，并自动保留可用的表格格式；手动改写后按当前文字重新解析。原邮件文件与粘贴正文通常任选一种，同一封邮件不必重复添加。</p>
            <p v-if="html.trim()" class="jp-muted" role="status">{{ pastedRichText ? '已保留原表格格式，下方显示可读文字。' : '当前为文字内容；表格请保留制表符或明确的列分隔。' }}</p>
            <Button v-if="html || subject" variant="outline" :disabled="busy" @click="clearPastedBody">清除粘贴正文</Button>
          </div>
        </div>
        <p v-if="mails.length || html.trim()" class="jp-help" data-testid="jp-source-summary">本批来源：{{ mails.length }} 份邮件文件{{ html.trim() ? '，另有 1 份粘贴正文' : '' }}。<template v-if="mails.length && html.trim()">将分别识别所有来源；有未识别来源时需修正或移除后重新解析。</template></p>
        <div class="jp-section-footer">
          <p class="jp-muted">解析后请逐项核对客户、货号、数量、日期和价格。</p>
          <Button :disabled="!canPreview" @click="parse"><ClipboardList aria-hidden="true" />解析并核对</Button>
        </div>
      </SectionPanel>

      <SectionPanel title="03 · 核对明细" subtitle="核对原邮件与参照，确认后生成问单 Excel。" class="jp-panel">
        <template #action><StatusPill :label="preview ? `${preview.rows.length} 条明细` : '等待解析'" :tone="preview ? 'teal' : 'slate'" /></template>
        <template v-if="preview">
          <div class="jp-review-summary" aria-label="明细核对概况">
            <span>已选择 <strong>{{ reviewCounts.selected }}</strong> 条</span>
            <span>排期已有 <strong>{{ reviewCounts.existing }}</strong> 条</span>
            <span>价格待确认 <strong>{{ reviewCounts.priceReview }}</strong> 条</span>
          </div>
          <div v-if="preview.warnings.length" class="jp-message jp-message--warning">
            <CircleAlert aria-hidden="true" /><div class="jp-message__content"><strong>请核对以下提醒</strong>
              <ul><li v-for="(warning, i) in preview.warnings" :key="i">{{ warning }}</li></ul>
            </div>
          </div>
          <div v-if="preview.failed_sources.length" class="jp-message jp-message--error" role="alert">
            <CircleAlert aria-hidden="true" /><div class="jp-message__content"><p>这些来源尚未识别：{{ preview.failed_sources.join('、') }}。当前已识别明细仍可查看，但须处理失败来源后重新解析才能生成。</p><p>可在上方移除对应文件；ZIP 内邮件需修正邮件包后重新选择。</p></div>
            <Button v-if="preview.failed_sources.includes('粘贴正文') && html.trim()" variant="outline" :disabled="busy" @click="removePastedAndParse">{{ mails.length ? '移除粘贴正文并重新解析' : '清除未识别的粘贴正文' }}</Button>
          </div>
          <div v-if="preview.quantity_selections.length" class="jp-quantity-choices surface-subtle">
            <label v-for="choice in preview.quantity_selections" :key="`${choice.source_id}:${choice.table_index}`" class="jp-field">
              <span>请选择 {{ choice.source }} 第 {{ choice.table_index + 1 }} 个表格的数量列</span>
              <select v-model="quantityColumns[`${choice.source_id}:${choice.table_index}`]" aria-label="数量列" :disabled="busy" @change="confirmed = false">
                <option value="">待选择</option><option v-for="column in choice.columns" :key="column.index" :value="String(column.index)">第 {{ column.index + 1 }} 列：{{ column.sample }}</option>
              </select>
            </label>
            <Button variant="outline" :disabled="!canPreview" @click="parse">按所选数量列重新解析</Button>
          </div>
          <template v-if="preview.rows.length">
            <p id="jp-table-help" class="jp-help">左右滚动查看全部字段。行Q期D与截数期是不同字段；装箱数、数量、货价回退及版本均须人工核对。</p>
            <div class="jp-table" tabindex="0" role="region" aria-label="问单核对明细" aria-describedby="jp-table-help">
              <table>
                <caption class="sr-only">问单明细核对与更正</caption>
                <thead><tr><th scope="col" class="jp-selection-column">选择与状态</th><th scope="col" class="jp-identity-column">报关货号 / 长货号</th><th v-for="[field, label] in editable" :key="field" scope="col" :class="`jp-col-${field}`">{{ label }}</th></tr></thead>
                <tbody><tr v-for="row in preview.rows" :key="row.id" :data-selected="selected.includes(row.id)" :class="{ 'jp-row-existing': row.exists }">
                  <td class="jp-selection-column"><div class="jp-row-status">
                    <label class="jp-row-check"><input v-model="selected" type="checkbox" :value="row.id" :disabled="row.exists || busy" aria-label="选择明细" @change="confirmed = false"><span>选择明细</span></label>
                    <StatusPill v-if="row.exists" label="排期已有，勿重录" tone="slate" compact />
                    <StatusPill v-if="priceNeedsReview(row)" label="货价待确认" tone="amber" compact />
                    <small v-if="row.price_note">{{ row.price_note }}</small>
                  </div></td>
                  <td class="jp-identity-column"><strong>{{ row.baby_item }}</strong><span class="jp-long-code">{{ row.long_code }}</span><small>{{ row.source }}</small></td>
                  <td v-for="[field, label] in editable" :key="field" :class="`jp-col-${field}`"><input v-model="row[field]" :aria-label="label" :disabled="busy || row.exists" maxlength="1000" @input="rowEdited(row, field)"></td>
                </tr></tbody>
              </table>
            </div>
            <div class="jp-confirm-area surface-subtle">
              <p class="jp-muted">不得把待确认价格当成已批准报价。勾选前请核对两项价格及全部提醒；修改明细后需重新确认。</p>
              <p class="jp-muted">客名或装箱数会影响价格匹配，修改后会清空旧价。请按新条件填写货价，并核对出厂价；系统不会替你沿用旧价。核对原因和勾选确认用于分配问单编号、保留核对依据。</p>
              <label class="jp-field"><span>核对原因<span class="jp-required">必填 · 至少 4 个字</span></span><textarea v-model="reason" rows="2" maxlength="500" placeholder="填写本次核对依据或更正原因" :disabled="busy" @input="confirmed = false" /></label>
              <label class="jp-confirmation"><input v-model="confirmed" type="checkbox" :disabled="busy"><span>已核对所选明细、数量、交期、包装、价格及警告；确认分配编号并保留导出记录。</span></label>
              <div v-if="exportBlockers.length" class="jp-message jp-message--warning" data-testid="jp-export-blockers"><div class="jp-message__content"><strong>生成前还需完成</strong><ul><li v-for="blocker in exportBlockers" :key="blocker">{{ blocker }}</li></ul></div></div>
              <div class="jp-section-footer">
                <p v-if="!caps.export" class="jp-muted">当前账号无导出权限，可核对明细后联系有权限的人员处理。</p>
                <p v-else class="jp-muted">确认后保留 {{ reviewCounts.selected }} 条所选明细的编号与导出记录。</p>
                <Button :disabled="!canExport" @click="exportRows"><Download aria-hidden="true" />确认并生成问单 Excel</Button>
              </div>
            </div>
          </template>
          <div v-else class="jp-empty"><div class="jp-state-icon"><Inbox aria-hidden="true" /></div><h3>暂未识别到可核对明细</h3><p>请按上方提醒检查邮件内容，再重新解析。</p></div>
        </template>
        <div v-else class="jp-empty"><div class="jp-state-icon"><ClipboardList aria-hidden="true" /></div><h3>等待解析邮件</h3><p>上传或粘贴邮件并点击“解析并核对”，明细与核对提醒会显示在这里。</p></div>
      </SectionPanel>

      <SectionPanel :title="`历史导出记录（${totalRecords}）`" subtitle="保留原始参照版本和核对依据；下载不会重复占号。" class="jp-panel">
        <ul v-if="records.length" class="jp-history-list">
          <li v-for="record in records" :key="record.id">
            <span class="jp-history-icon"><FileSpreadsheet aria-hidden="true" /></span>
            <div class="jp-history-content"><h3>{{ record.prefix }}-{{ record.first_number }} 至 {{ record.last_number }}</h3><p>{{ record.created_at }} · {{ record.actor }}</p></div>
            <StatusPill :label="`${record.row_count} 行`" tone="slate" compact />
            <Button variant="outline" :disabled="!canPreview || !caps.export" @click="copyExport(record.id)"><Copy aria-hidden="true" />复制全部44列</Button>
            <Button variant="outline" :disabled="!canPreview || !caps.export" @click="download(record.id)"><Download aria-hidden="true" />下载原导出</Button>
          </li>
        </ul>
        <div v-else class="jp-empty"><div class="jp-state-icon"><Inbox aria-hidden="true" /></div><h3>暂无历史导出记录</h3><p>完成核对并生成 Excel 后，可在这里重复下载原导出。</p></div>
        <div v-if="clipboardText" class="jp-copy-result surface-subtle" data-testid="jp-copy-result">
          <p role="status">{{ clipboardMessage }}</p>
          <p class="jp-muted">复制的是这条已生成记录的完整数据，不含表头。粘贴到 Excel 对应的首个数据单元格；文本保护符用于保留前导零、避免公式执行，请勿自行删除。</p>
          <label class="jp-field"><span>已生成的44列数据（只读）</span><textarea ref="clipboardTextarea" :value="clipboardText" readonly rows="4" wrap="off" spellcheck="false" aria-label="已生成的44列数据" /></label>
          <Button variant="outline" :disabled="busy" @click="selectClipboardText">选中全部文本</Button>
        </div>
        <div class="jp-history-footer">
          <p class="jp-muted">导出不等于已录入金山或成为正式订单。</p>
          <nav class="jp-pagination" aria-label="历史导出分页">
            <Button variant="outline" :disabled="!canPreview || page <= 1" @click="historyPage(page - 1)">上一页</Button><span>第 {{ page }} 页</span><Button variant="outline" :disabled="!canPreview || page * 20 >= totalRecords" @click="historyPage(page + 1)">下一页</Button>
          </nav>
        </div>
      </SectionPanel>
    </template>
  </section>
</template>

<style scoped>
.jp-intake { display: grid; min-width: 0; gap: 24px; color: var(--foreground); font-size: 14px; line-height: 1.6; }
.jp-intake h2, .jp-intake h3, .jp-intake p { margin: 0; }
.jp-intake h3 { font-size: 14px; font-weight: 600; }
.jp-panel { min-width: 0; }
.jp-muted, .jp-help { color: var(--muted-foreground); font-size: 13px; line-height: 1.6; overflow-wrap: anywhere; }
.jp-help { margin-top: 12px !important; }
.jp-boundary { display: flex; gap: 10px; align-items: flex-start; border-radius: var(--radius); padding: 12px 16px; color: var(--muted-foreground); }
.jp-boundary > svg, .jp-message > svg { width: 18px; height: 18px; flex: 0 0 auto; margin-top: 2px; }
.jp-boundary > svg { color: var(--primary); }
.jp-message { display: flex; flex-wrap: wrap; align-items: flex-start; gap: 10px; border: 1px solid var(--border); border-radius: var(--radius); padding: 12px 16px; overflow-wrap: anywhere; }
.jp-message__content { flex: 1; min-width: 0; }
.jp-message ul { margin: 6px 0 0; padding-left: 18px; }
.jp-message--error { color: var(--destructive); border-color: color-mix(in srgb, var(--destructive) 22%, var(--border)); background: color-mix(in srgb, var(--destructive) 4%, var(--card)); }
.jp-message--success { color: var(--primary); border-color: color-mix(in srgb, var(--primary) 25%, var(--border)); background: var(--accent); }
.jp-message--warning { color: var(--color-amber-900); border-color: var(--color-amber-200); background: var(--color-amber-50); }
.jp-processing { color: var(--primary); padding: 10px 14px; background: var(--accent); border-radius: var(--radius); }
.jp-reference-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }
.jp-reference { display: flex; flex-direction: column; min-width: 0; gap: 12px; padding: 16px; border-radius: var(--radius); }
.jp-reference__heading { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.jp-reference__heading > svg { width: 18px; height: 18px; color: var(--primary); flex: 0 0 auto; }
.jp-reference__heading h3 { flex: 1; min-width: 100px; }
.jp-reference__file { overflow-wrap: anywhere; font-weight: 500; }
.jp-reference__actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: auto; padding-top: 4px; }
.jp-file-pending { color: var(--primary); font-size: 12px; overflow-wrap: anywhere; }
.jp-field { display: grid; min-width: 0; gap: 7px; font-weight: 500; }
.jp-field > span { overflow-wrap: anywhere; }
.jp-required { display: inline-block; margin-left: 8px; color: var(--muted-foreground); font-size: 12px; font-weight: 400; }
.jp-intake input:not([type='checkbox']), .jp-intake select, .jp-intake textarea { width: 100%; min-width: 0; min-height: 40px; border: 1px solid var(--input); border-radius: var(--radius); background: var(--card); padding: 8px 10px; color: var(--foreground); font: inherit; font-weight: 400; line-height: 1.5; }
.jp-intake input::placeholder, .jp-intake textarea::placeholder { color: var(--muted-foreground); }
.jp-intake textarea { display: block; resize: vertical; }
.jp-intake :is(input, select, textarea):disabled { cursor: not-allowed; color: var(--muted-foreground); background: var(--muted); opacity: .75; }
.jp-intake input[type='checkbox'] { width: 16px; height: 16px; flex: 0 0 auto; accent-color: var(--primary); }
.jp-intake input[type='checkbox']:focus-visible, .jp-table:focus-visible { outline: 3px solid color-mix(in srgb, var(--ring) 35%, transparent); outline-offset: 3px; }
.jp-intake .jp-file-input { padding: 0; overflow: hidden; font-size: 12px; line-height: 38px; }
.jp-file-input::file-selector-button { min-height: 38px; margin-right: 10px; border: 0; border-right: 1px solid var(--input); background: var(--secondary); padding: 0 12px; color: var(--secondary-foreground); font: inherit; font-weight: 600; cursor: pointer; }
.jp-file-input:disabled::file-selector-button { cursor: not-allowed; }
.jp-form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.jp-mail-grid { display: grid; grid-template-columns: minmax(0, .9fr) minmax(0, 1.1fr); gap: 24px; margin-top: 20px; }
.jp-upload-area { display: flex; min-width: 0; flex-direction: column; align-items: flex-start; gap: 12px; border-style: dashed; border-radius: var(--radius); padding: 20px; }
.jp-upload-area .jp-file-input { background: var(--card); }
.jp-upload-limit { color: var(--muted-foreground); font-size: 12px; line-height: 1.7; }
.jp-paste-area { display: grid; min-width: 0; gap: 12px; }
.jp-file-list { display: grid; gap: 6px; width: 100%; margin: 0; padding: 0; list-style: none; }
.jp-file-list li { display: flex; align-items: flex-start; gap: 8px; color: var(--foreground); font-size: 13px; }
.jp-file-list svg { flex: 0 0 auto; width: 16px; height: 16px; margin-top: 3px; color: var(--primary); }
.jp-file-list span { flex: 1; min-width: 0; overflow-wrap: anywhere; }
.jp-file-list button { flex: 0 0 auto; }
.jp-section-footer { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; margin-top: 20px; }
.jp-section-footer p { flex: 1; min-width: 180px; }
.jp-review-summary { display: flex; flex-wrap: wrap; gap: 12px 24px; margin-bottom: 16px; color: var(--muted-foreground); }
.jp-review-summary strong { margin: 0 4px; color: var(--foreground); font-size: 16px; font-weight: 600; font-variant-numeric: tabular-nums; }
.jp-review-summary ~ .jp-message { margin-bottom: 12px; }
.jp-quantity-choices { display: grid; gap: 12px; margin: 12px 0; border-radius: var(--radius); padding: 16px; }
.jp-quantity-choices > button { justify-self: start; }
.jp-table { width: 100%; max-height: 640px; overflow: auto; margin-top: 12px; border: 1px solid var(--border); border-radius: var(--radius); background: var(--card); }
.jp-table table { width: 100%; min-width: 2100px; border-collapse: separate; border-spacing: 0; text-align: left; font-variant-numeric: tabular-nums; }
.jp-table th, .jp-table td { padding: 12px; border-bottom: 1px solid var(--border); vertical-align: top; }
.jp-table th { position: sticky; top: 0; z-index: 1; color: var(--muted-foreground); background: var(--muted); font-size: 12px; font-weight: 600; white-space: nowrap; }
.jp-table tbody tr:last-child td { border-bottom: 0; }
.jp-table tbody tr[data-selected='true'] { background: color-mix(in srgb, var(--accent) 35%, var(--card)); }
.jp-table tbody tr.jp-row-existing { background: var(--muted); }
.jp-selection-column { width: 200px; min-width: 200px; }
.jp-identity-column { width: 230px; min-width: 230px; }
.jp-identity-column strong, .jp-long-code, .jp-table small { display: block; overflow-wrap: anywhere; }
.jp-identity-column strong { margin-bottom: 4px; font-size: 14px; font-weight: 600; }
.jp-long-code { margin-bottom: 6px; }
.jp-table small { color: var(--muted-foreground); font-size: 12px; line-height: 1.6; }
.jp-row-status { display: grid; justify-items: start; gap: 8px; }
.jp-row-check { display: flex; min-height: 32px; align-items: center; gap: 8px; font-size: 13px; }
.jp-table td input:not([type='checkbox']) { min-width: 125px; font-variant-numeric: tabular-nums; }
.jp-table .jp-col-note input { min-width: 280px; }
.jp-col-qty input, .jp-col-carton_t input, .jp-col-price_t input, .jp-col-factory_price_t input { text-align: right; }
.jp-confirm-area { display: grid; gap: 16px; margin-top: 20px; padding: 20px; border-radius: var(--radius); }
.jp-confirm-area .jp-section-footer { margin-top: 0; }
.jp-confirmation { display: flex; align-items: flex-start; gap: 10px; cursor: pointer; }
.jp-confirmation input { margin-top: 3px; }
.jp-empty { display: grid; justify-items: center; gap: 10px; padding: 28px 16px; text-align: center; }
.jp-empty h2, .jp-empty h3 { color: var(--foreground); font-size: 16px; font-weight: 600; }
.jp-empty p { max-width: 500px; color: var(--muted-foreground); font-size: 14px; overflow-wrap: anywhere; }
.jp-state-icon, .jp-history-icon { display: inline-grid; width: 42px; height: 42px; flex: 0 0 auto; place-items: center; border: 1px solid var(--border); border-radius: var(--radius); background: var(--card); color: var(--primary); }
.jp-state-icon > svg { width: 22px; height: 22px; }
.jp-history-list { display: grid; margin: 0; padding: 0; list-style: none; }
.jp-history-list > li { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; padding: 16px 0; border-bottom: 1px solid var(--border); }
.jp-history-list > li:first-child { padding-top: 0; }
.jp-history-icon > svg { width: 20px; height: 20px; }
.jp-history-content { flex: 1; min-width: 200px; overflow-wrap: anywhere; }
.jp-history-content h3 { font-variant-numeric: tabular-nums; }
.jp-history-content p { margin-top: 4px; color: var(--muted-foreground); font-size: 12px; }
.jp-history-footer { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 16px; padding-top: 16px; }
.jp-copy-result { display: grid; gap: 12px; margin-top: 16px; border-radius: var(--radius); padding: 16px; }
.jp-copy-result button { justify-self: start; }
.jp-copy-result textarea { font-family: monospace; }
.jp-pagination { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; color: var(--muted-foreground); font-size: 13px; font-variant-numeric: tabular-nums; }
@media (max-width: 1279px) { .jp-reference-grid { grid-template-columns: 1fr; } .jp-reference__heading h3 { min-width: 0; } }
@media (max-width: 639px) {
  .jp-intake { gap: 20px; }
  .jp-form-grid, .jp-mail-grid { grid-template-columns: 1fr; }
  .jp-mail-grid { gap: 16px; }
  .jp-upload-area, .jp-confirm-area { padding: 16px; }
  .jp-section-footer { align-items: stretch; }
  .jp-section-footer p { min-width: 0; flex-basis: 100%; }
  .jp-section-footer > button { width: 100%; white-space: normal; min-height: 44px; height: auto; padding-block: 10px; }
  .jp-reference__actions > button, .jp-history-list > li > button, .jp-pagination > button { min-height: 44px; }
  .jp-history-content { min-width: 0; flex-basis: calc(100% - 60px); }
  .jp-history-list > li > button { margin-left: auto; }
  .jp-reference__heading { align-items: flex-start; }
  .jp-reference__heading h3 { flex-basis: calc(100% - 26px); }
}
</style>
