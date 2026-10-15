<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
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
const error = ref('')
const notice = ref('')
const records = ref<JPExportRecord[]>([])
const totalRecords = ref(0)
const page = ref(1)
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
const canExport = computed(() => canPreview.value && caps.value.export && preview.value && selected.value.length > 0
  && !preview.value.failed_sources.length && !preview.value.quantity_selections.length && confirmed.value && reason.value.trim().length >= 4 && Boolean(merchandiser.value.trim()))

function invalidate() { preview.value = null; original.value = []; selected.value = []; confirmed.value = false; notice.value = '' }
function rowEdited(row: JPRow, field: string) {
  confirmed.value = false
  if (field === 'customer' || field === 'carton_t') {
    row.price_t = ''; row.factory_price_t = ''
    row.price_note = '客名或装箱数已更正，旧价格已清空；请按新条件重新填写核对货价及出厂价。'
  }
}
function clearProtected() { invalidate(); references.value = {}; records.value = []; caps.value = { ...emptyCaps } }
function handleError(cause: unknown) {
  error.value = getApiErrorMessage(cause)
  const status = (cause as { response?: { status?: number } })?.response?.status
  if (status === 401 || status === 403) clearProtected()
}
async function load() {
  controller.abort(); controller = new AbortController()
  const token = ++epoch
  clearProtected()
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
  } catch (cause) { if (token === epoch) handleError(cause) }
  finally { if (token === epoch) loading.value = false }
}
function fileChanged(event: Event, kind?: JPReferenceKind) {
  const input = event.target as HTMLInputElement
  if (kind) { refFiles.value[kind] = input.files?.[0]; if (kind === 'confirmed') confirmedCurrency.value = '' }
  else { mails.value = Array.from(input.files ?? []); quantityColumns.value = {}; invalidate() }
  input.value = ''
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
async function exportRows() {
  if (!canExport.value || !preview.value) return
  const token = epoch
  const body = form()
  const changes = preview.value.rows.filter(row => selected.value.includes(row.id)).flatMap(row => {
    const before = original.value.find(item => item.id === row.id)!
    const contextChanged = row.customer !== before.customer || row.carton_t !== before.carton_t
    return editable.flatMap(([field]) => !((field === 'price_t' || field === 'factory_price_t') && contextChanged)
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
  mails.value = []; html.value = ''; subject.value = ''; merchandiser.value = ''; refFiles.value = {}; confirmedCurrency.value = ''; quantityColumns.value = {}; busy.value = false; page.value = 1; void load()
}, { immediate: true })
onBeforeUnmount(() => { epoch += 1; controller.abort() })
</script>

<template>
  <section class="jp-intake" data-testid="huakang-b-jp-intake">
    <h2>华康B · JP问单录入</h2>
    <p>解析邮件、参照查重、核对货价并导出金山用的 44 列 Excel。问单不计入正式订单，不自动安排生产或调整库存。</p>
    <p v-if="loading">正在核对权限及参照…</p>
    <p v-else-if="!caps.read">没有华康B订单读取权限。</p>
    <p v-else-if="!caps.available">模块尚未部署数据库迁移，请联系管理员。不会自动修改旧业务库。</p>
    <p v-if="error" role="alert" class="jp-error">{{ error }}</p><p v-if="notice" role="status">{{ notice }}</p>
    <template v-if="caps.read && caps.available && factoryId === 'huakang-b'">
      <section><h3>1. 当前参照</h3><p>由有写入权限的人员更新，验证成功才切换版本。不会读取个人电脑共享盘或覆盖旧文件。</p>
        <div v-for="entry in referenceKinds" :key="entry.kind" class="jp-reference">
          <strong>{{ entry.label }}</strong><span>{{ references[entry.kind]?.name ?? '尚未上传' }} · V{{ references[entry.kind]?.revision ?? 0 }}</span>
          <label v-if="entry.kind === 'confirmed' && caps.write">确认表裸数字的币种<select v-model="confirmedCurrency" :disabled="busy"><option value="">必须由表内“确认币种”或 HK$/US$ 标签明确</option><option value="HKD">这份表的裸数字全部为港币 HKD</option><option value="USD">这份表的裸数字全部为美元 USD</option></select></label>
          <span v-if="entry.kind === 'confirmed' && references.confirmed?.options?.currency">当前数字币种：{{ references.confirmed.options.currency }}</span>
          <template v-if="caps.write"><input type="file" accept=".xlsx" :aria-label="entry.label" :disabled="busy || loading" @change="fileChanged($event, entry.kind)"><button :disabled="!canPreview || !refFiles[entry.kind]" @click="upload(entry.kind)">验证并更新</button></template>
          <button v-if="caps.write && entry.kind === 'confirmed' && references.confirmed" :disabled="!canPreview" @click="clearConfirmed">停用当前确认价</button>
        </div>
      </section>
      <section><h3>2. 上传或粘贴邮件</h3><p>单文件最多 20MB，文件合计最多 50MB；每批最多 100 封邮件、250 条明细。过大批次请拆分。</p>
        <label>业务跟单（金山人员名称）<input v-model="merchandiser" aria-label="业务跟单" maxlength="128" :disabled="busy" @input="invalidate"></label>
        <p>订单创建人取当前账号显示名：{{ caps.creator_name || '当前账号' }}。请确保名称与金山字段一致；服务器审计另外保留实际操作账号。</p>
        <label>来单日期（邮件无日期时使用）<input v-model="receivedDate" type="date" :disabled="busy" @input="invalidate"></label>
        <input type="file" accept=".eml,.zip" multiple aria-label="问单邮件" :disabled="busy" @change="fileChanged($event)">
        <p>{{ mails.map(file => file.name).join('、') || '尚未选择邮件' }}</p>
        <label>粘贴正文的邮件主题<input v-model="subject" maxlength="500" :disabled="busy" @input="invalidate"></label>
        <label>邮件 HTML 正文<textarea v-model="html" rows="5" :disabled="busy" @input="invalidate" /></label>
        <button :disabled="!canPreview" @click="parse">解析并核对</button>
      </section>
      <section v-if="preview"><h3>3. 核对明细</h3>
        <ul><li v-for="(warning, i) in preview.warnings" :key="i">{{ warning }}</li></ul>
        <p v-if="preview.failed_sources.length" class="jp-error">这些邮件尚未识别，请处理或移除后重新上传：{{ preview.failed_sources.join('、') }}</p>
        <label v-for="choice in preview.quantity_selections" :key="`${choice.source_id}:${choice.table_index}`">请选择 {{ choice.source }} 第 {{ choice.table_index + 1 }} 个表格的数量列
          <select v-model="quantityColumns[`${choice.source_id}:${choice.table_index}`]" aria-label="数量列" :disabled="busy" @change="confirmed = false"><option value="">待选择</option><option v-for="column in choice.columns" :key="column.index" :value="String(column.index)">第 {{ column.index + 1 }} 列：{{ column.sample }}</option></select>
        </label>
        <button v-if="preview.quantity_selections.length" :disabled="!canPreview" @click="parse">按所选数量列重新解析</button>
        <div class="jp-table"><table><thead><tr><th>选择</th><th>报关货号 / 长货号</th><th v-for="[field, label] in editable" :key="field">{{ label }}</th></tr></thead>
          <tbody><tr v-for="row in preview.rows" :key="row.id"><td><input v-model="selected" type="checkbox" :value="row.id" :disabled="row.exists || busy" aria-label="选择明细" @change="confirmed = false"><strong v-if="row.exists">排期已有，勿重录</strong><span v-if="row.price_confirm">货价待确认</span><small>{{ row.price_note }}</small></td>
            <td>{{ row.baby_item }}<br>{{ row.long_code }}<br><small>{{ row.source }}</small></td>
            <td v-for="[field, label] in editable" :key="field"><input v-model="row[field]" :aria-label="label" :disabled="busy || row.exists" maxlength="1000" @input="rowEdited(row, field)"></td>
          </tr></tbody></table></div>
        <p>行Q期D与截数期是不同字段；装箱数、数量、货价回退及版本覆盖均须人工核对。不得把待确认价格当成已批准报价。</p>
        <label>核对原因<textarea v-model="reason" rows="2" maxlength="500" :disabled="busy" @input="confirmed = false" /></label>
        <label><input v-model="confirmed" type="checkbox" :disabled="busy">已核对所选明细、数量、交期、包装、价格及警告；确认分配编号并保留导出记录。</label>
        <button :disabled="!canExport" @click="exportRows">确认并生成问单 Excel</button>
      </section>
      <section><h3>历史导出记录（{{ totalRecords }}）</h3><p>记录保存原始参照版本及核对依据；下载不会重复占号。导出不等于已录入金山或成为正式订单。</p>
        <ul><li v-for="record in records" :key="record.id">{{ record.created_at }} · {{ record.actor }} · {{ record.prefix }}-{{ record.first_number }} 至 {{ record.last_number }} · {{ record.row_count }} 行 <button :disabled="!canPreview || !caps.export" @click="download(record.id)">下载原导出</button></li></ul>
        <button :disabled="!canPreview || page <= 1" @click="historyPage(page - 1)">上一页</button><span> 第 {{ page }} 页 </span><button :disabled="!canPreview || page * 20 >= totalRecords" @click="historyPage(page + 1)">下一页</button>
      </section>
    </template>
  </section>
</template>

<style scoped>
.jp-intake{color:#1c2738;display:grid;gap:18px}.jp-intake h2,.jp-intake h3{margin:0}.jp-intake p{font-size:14px;line-height:1.6}.jp-intake section{display:grid;gap:12px;padding:20px;background:white;border:1px solid #cbd5e1;border-radius:12px}.jp-intake label{display:grid;gap:6px}.jp-intake input,.jp-intake textarea,.jp-intake select{border:1px solid #bbc7d9;border-radius:6px;padding:8px;font:inherit}.jp-intake input[type=checkbox]{width:auto}.jp-intake button{padding:9px 14px;border:1px solid #2a5f9e;border-radius:6px;color:#164b89;background:#edf5ff;cursor:pointer}.jp-intake button:disabled{opacity:.45;cursor:not-allowed}.jp-reference{display:flex;flex-wrap:wrap;gap:12px;align-items:center}.jp-error{color:#a31621}.jp-table{overflow:auto}.jp-table table{border-collapse:collapse;min-width:1900px}.jp-table th,.jp-table td{padding:9px;border-bottom:1px solid #dae0e9;text-align:left}.jp-table td input:not([type=checkbox]){width:120px}.jp-table small{font-size:11px;color:#6b7280}.jp-table strong{color:#a31621}
</style>
