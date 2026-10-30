<script setup lang="ts">
import { lostRecordAccess } from './recordAccess'
import RecordResponsibility from './RecordResponsibility.vue'
import { computed, ref, watch } from 'vue'
import { FileInput } from '@lucide/vue'
import SectionPanel from './MaterialsPanel.vue'
import type { MaterialRecord } from '@/api/indonesiaMaterials'
import { showStatus } from './forms'
import { useMaterials } from './workspace'
import { customerProducts, fixedCustomers } from './catalog'
import { useMaterialDraft } from './useDraft'
import { newDraftId, recordDraftId, recordRef, restoreRecord } from './draftPersistence'
const ws = useMaterials()
const scheduleImports = () => ws.kind('import').filter(row => !['warehouse_receipt', 'material_master'].includes(row.data.import_type))
const customer = ref('')
const recipient = ref('RRI')
const file = ref<File | null>(null)
const preview = ref<MaterialRecord | null>(null)
const selected = ref<number[]>([])
const context = ref({ customer: '', recipient: 'RRI' })
const accessLost = computed(() => lostRecordAccess(ws, preview.value))
const draft = useMaterialDraft(() => ({ customer: customer.value, recipient: recipient.value, file: file.value ? [file.value.name, file.value.size, file.value.lastModified] : null, selected: selected.value }), {
  id: 'import', multiple: true, capture: () => customer.value || file.value || preview.value ? { customer: customer.value, recipient: recipient.value, file: file.value, preview: recordRef(preview.value), selected: selected.value, context: context.value,
    label: [customer.value, recipient.value, file.value?.name || preview.value?.data.filename || '新导入'].filter(Boolean).join(' · ') } : null,
  restore: saved => {
    if (saved.customer && !fixedCustomers(ws.records).some(row => row.data.name === saved.customer)) throw new Error('原固定客人已停用或不可用，请先核对；草稿仍保留。')
    const source = restoreRecord(ws.records, saved.preview, 'import') ?? null
    if (saved.file && !(saved.file instanceof File)) throw new Error('来源文件草稿无法读取，请保留草稿并核对浏览器存储。')
    const indexes: number[] = Array.isArray(saved.selected) ? saved.selected : []
    const valid = indexes.filter(index => source?.data.status !== 'confirmed' && source?.data.rows.some((row: { index: number; blocked: boolean; imported_order_id?: string }) => row.index === index && !row.blocked && !row.imported_order_id))
    if (valid.length !== indexes.length) throw new Error('来源行已确认或发生变化，不能恢复原勾选；请查看最新导入记录，草稿仍保留。')
    customer.value = saved.customer || ''; recipient.value = saved.recipient || 'RRI'; file.value = saved.file || null; preview.value = source; selected.value = indexes; context.value = saved.context || { customer: customer.value, recipient: recipient.value }
  },
  reset: () => { customer.value = ''; recipient.value = 'RRI'; file.value = null; preview.value = null; selected.value = []; context.value = { customer: '', recipient: 'RRI' } },
})
const customers = computed(() => fixedCustomers(ws.records))
const products = computed(() => customerProducts(ws.records, customer.value))
const selectableIndexes = computed<number[]>(() => preview.value?.data.status === 'confirmed' ? [] :
  (preview.value?.data.rows || []).filter((row: { blocked?: boolean; imported_order_id?: string }) => !row.blocked && !row.imported_order_id)
    .map((row: { index: number }) => row.index))
const canChangeSelection = computed(() => !accessLost.value && !!preview.value && preview.value.data.status !== 'confirmed' && ws.canWrite && !ws.locked && !draft.switching.value)
function selectAll(checked: boolean) {
  if (!canChangeSelection.value) return
  selected.value = checked ? [...selectableIndexes.value] : []
}
async function changeContext(_key: 'customer' | 'recipient', _event: Event) {
  const next = { customer: customer.value, recipient: recipient.value }
  if (file.value || preview.value || selected.value.length) {
    const originalFile = file.value
    customer.value = context.value.customer; recipient.value = context.value.recipient
    await draft.openRecord(newDraftId('import'), () => { customer.value = next.customer; recipient.value = next.recipient; file.value = originalFile; preview.value = null; selected.value = []; context.value = next })
  } else {
    context.value = next; preview.value = null; selected.value = []
  }
}
watch(() => preview.value ? ws.record(preview.value.id) : undefined, saved => {
  if (!saved) return
  preview.value = saved
  selected.value = selected.value.filter(index => saved.data.status !== 'confirmed' && saved.data.rows.some((row: { index: number; blocked: boolean; imported_order_id?: string }) => row.index === index && !row.blocked && !row.imported_order_id))
})
function newImport() { return draft.openRecord(newDraftId('import'), () => { customer.value = ''; recipient.value = 'RRI'; file.value = null; preview.value = null; selected.value = []; context.value = { customer: '', recipient: 'RRI' } }) }
async function fileChanged(event: Event) {
  const input = event.target as HTMLInputElement, next = input.files?.[0]
  input.value = ''
  if (!next) return
  if (file.value || preview.value) await draft.openRecord(newDraftId('import'), () => { file.value = next; preview.value = null; selected.value = [] })
  else file.value = next
}
async function upload() {
  if (!file.value || !customers.value.some(row => row.data.name === customer.value)) return
  if (preview.value && !await draft.openRecord(newDraftId('import'), () => { preview.value = null; selected.value = [] })) return
  const owner = draft.activeId.value
  const result = await ws.preview(customer.value, recipient.value, file.value)
  if (result && draft.activeId.value === owner) { preview.value = result; selected.value = []; draft.accept() }
}
function inspect(record: MaterialRecord) { return draft.openRecord(recordDraftId('import', 'inspect', record.id), () => { preview.value = record; selected.value = []; file.value = null; customer.value = record.data.customer || record.data.rows?.[0]?.customer || ''; recipient.value = record.data.recipient || record.data.rows?.[0]?.recipient || 'RRI'; context.value = { customer: customer.value, recipient: recipient.value } }) }
async function confirm() {
  if (accessLost.value || !preview.value || preview.value.data.status === 'confirmed' || !selected.value.length) return
  await draft.run('import_confirm', { indexes: selected.value }, preview.value, () => {
    if (!preview.value) return
    preview.value = ws.record(preview.value.id) ?? null
    selected.value = []
    draft.accept()
  })
}
</script>
<template>
  <SectionPanel title="统一排期导入" subtitle="上传仅生成预览。核对客户、接收方、来源坐标及重复提示后，勾选行确认入合同。">
    <p v-if="accessLost" class="im-message" role="alert">此待办已转交其他跟客或不可用，不能继续处理。原本机草稿保留，可新建或打开其他单据。</p>
    <template #action><button type="button" :disabled="!ws.canWrite || (ws.locked || draft.switching.value)" @click="newImport">新建导入表单</button></template>
    <div class="im-steps" aria-label="排期导入步骤"><div class="im-step is-active"><b>1</b><div>选择排期文件<small>现有统一排期格式</small></div></div><div class="im-step" :class="{ 'is-active': preview }"><b>2</b><div>核对合同批次<small>检查字段与重复记录</small></div></div><div class="im-step" :class="{ 'is-active': preview?.data.status === 'confirmed' }"><b>3</b><div>确认导入<small>生成需求与倒排</small></div></div></div>
    <form class="im-upload-form" @submit.prevent="upload">
      <p v-if="draft.recoveryWaiting.value" class="im-message">已有本机导入草稿。可在上方继续填写，或新建另一份导入表单，原草稿会保留。</p>
      <fieldset :disabled="!ws.canWrite || (ws.locked || draft.switching.value) || draft.recoveryWaiting.value" class="im-fields">
        <label class="im-field"><span>客户 *</span><select v-model="customer" required @change="changeContext('customer', $event)"><option value="">请选择当前厂区的固定客人</option><option v-if="customer && !customers.some(row => row.data.name === customer)" :value="customer" disabled>{{ customer }}（已不可用，请重新选择）</option><option v-for="row in customers" :key="row.id" :value="row.data.name">{{ row.data.name }}</option></select></label>
        <label class="im-field"><span>本次接收方 *</span><select v-model="recipient" @change="changeContext('recipient', $event)"><option>RRI</option><option>RRM</option></select></label>
        <label class="im-field"><span>统一排期文件（.xlsx） *</span><input type="file" accept=".xlsx" :required="!file" @change="fileChanged"><small v-if="file">已保留文件：{{ file.name }}，可继续预览或重新选择。</small></label>
      </fieldset>
      <p v-if="!customers.length" class="im-message">请先到基础资料库新增本厂区的固定客人，再配置该客人的货号与物料用量。</p>
      <p v-else-if="customer" class="im-note">此客人已配置 {{ products.length }} 款上印尼货号。导入逐行核对货号及物料用量，未配置项须补齐后再确认。</p>
      <div class="im-actions"><button class="im-primary" type="submit" :disabled="!ws.canWrite || (ws.locked || draft.switching.value) || !file || !customer"><FileInput :size="15" />上传并预览</button><span class="im-note">上传后先核对，勾选确认才生成合同。</span></div>
    </form>
    <div v-if="preview" class="im-editor im-stack">
      <h3>预览：{{ preview.data.filename }} · {{ showStatus(preview.data.status || 'preview') }}</h3>
      <ul v-if="preview.data.issues?.length" class="im-message list-disc pl-8"><li v-for="(issue, index) in preview.data.issues" :key="index">{{ typeof issue === 'string' ? issue : issue.message ?? issue.detail ?? '来源行需要核对' }}</li></ul>
      <div v-if="preview.data.rows?.length" class="im-scroll"><table><thead><tr><th>选择</th><th>客户／接收方</th><th>合同／PO</th><th>货号</th><th>数量</th><th>走货期</th><th>来源</th><th>核对提示</th></tr></thead><tbody>
        <tr v-for="row in preview.data.rows" :key="row.index"><td><input v-model="selected" type="checkbox" :value="row.index" :aria-label="`选择来源行 ${row.source_row}`" :disabled="accessLost || row.blocked || !!row.imported_order_id || preview.data.status === 'confirmed' || !ws.canWrite || (ws.locked || draft.switching.value)"></td><td>{{ row.customer }} / {{ row.recipient }}</td><td>{{ row.contract_no }}<br>{{ row.po_no }}</td><td>{{ row.item_no }}<small v-if="row.batch">历史批次 {{ row.batch }}</small></td><td>{{ row.quantity }} {{ row.unit }}</td><td>{{ row.delivery_date }}</td><td>{{ row.source_sheet }} · 第 {{ row.source_row }} 行</td><td><b>{{ row.imported_order_id ? '已在本批确认' : row.match_status === 'changed' ? '已有合同有变更' : row.match_status === 'unchanged' ? '已有记录，无变化' : '新增行' }}</b><p>{{ row.issues?.join('；') || (row.blocked ? '不可导入' : '可核对导入') }}</p><p v-for="change in row.changes || []" :key="change.field">{{ change.field === 'quantity' ? '数量' : change.field === 'delivery_date' ? '成品交期' : change.field }}：{{ change.old }} → {{ change.new }}</p></td></tr>
      </tbody></table></div>
      <p v-else class="im-empty">未识别到可导入的合同明细，请核对文件及识别提示。</p>
      <div class="im-actions">
        <template v-if="preview.data.status !== 'confirmed'">
          <button type="button" :disabled="!canChangeSelection || !selectableIndexes.length || selected.length === selectableIndexes.length" @click="selectAll(true)">全选可导入行</button>
          <button type="button" :disabled="!canChangeSelection || !selected.length" @click="selectAll(false)">取消全选</button>
          <button type="button" class="im-primary" :disabled="!canChangeSelection || !selected.length" @click="confirm">确认导入选中 {{ selected.length }} 行</button>
        </template>
        <button v-if="preview.data.source_asset_id || preview.data.asset_id" type="button" :disabled="ws.busy" @click="ws.download(preview.data.source_asset_id || preview.data.asset_id, preview.data.filename, 'asset')">下载来源原件</button>
      </div>
    </div>
    <h3 class="mt-6">导入记录</h3>
    <div v-if="scheduleImports().length" class="im-scroll"><table><thead><tr><th>来源文件</th><th>状态</th><th>来源行数</th><th>上传人／负责人</th><th>操作</th></tr></thead><tbody><tr v-for="row in scheduleImports()" :key="row.id" :data-import-id="row.id"><td>{{ row.data.filename }}</td><td>{{ showStatus(row.data.status || 'preview') }}</td><td>{{ row.data.rows?.length ?? 0 }}</td><td><RecordResponsibility :record="row" /></td><td><button type="button" :disabled="(ws.locked || draft.switching.value)" @click="inspect(row)">查看核对</button></td></tr></tbody></table></div>
    <p v-else class="im-empty">暂无已保存的导入记录。</p>
  </SectionPanel>
</template>
