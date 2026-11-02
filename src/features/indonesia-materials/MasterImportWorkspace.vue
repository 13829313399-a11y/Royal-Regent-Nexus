<script setup lang="ts">
import { lostRecordAccess } from './recordAccess'
import RecordResponsibility from './RecordResponsibility.vue'
import { computed, ref } from 'vue'
import type { Data, MaterialRecord } from '@/api/indonesiaMaterials'
import Panel from './MaterialsPanel.vue'
import Fields from './Fields.vue'
import { useMaterials } from './workspace'
import { fixedCustomers, customerProducts } from './catalog'
import { useMaterialDraft } from './useDraft'
import { clone, materialFields } from './forms'
import { choiceFields } from './options'
import { newDraftId, recordDraftId, recordRef, restoreRecord } from './draftPersistence'
import { importChoices, incomingMaterial, importFields, importPayload, sourceUsages, masterParserRevision, restoreImportEdits } from './masterImport'

const ws = useMaterials()
const customer = ref(''), productIds = ref<string[]>([]), file = ref<File | null>(null)
const preview = ref<MaterialRecord | null>(null), choices = ref<Data[]>([]), mappings = ref<Data[]>([])
const customers = computed(() => fixedCustomers(ws.records))
const products = computed(() => customerProducts(ws.records, customer.value))
const history = computed(() => ws.kind('import').filter(row => row.data.import_type === 'material_master'))
const originalMappings = () => (preview.value?.data.sheets || []).map(({ sheet, header_row, columns, enabled }: Data) => ({ sheet, header_row, columns, enabled }))
const mappingChanged = computed(() => JSON.stringify(mappings.value) !== JSON.stringify(originalMappings()))
const groups = computed<Data[]>(() => preview.value?.data.groups || [])
const headers = (index: number): string[] => preview.value?.data.sheets[index]?.headers || []
const confirmed = computed(() => preview.value?.data.status === 'confirmed')
const rulesCurrent = computed(() => preview.value?.data.identity_rule === 'name-spec-v2' && preview.value?.data.format_rule === 'unified-template-v1')
const parserCurrent = computed(() => preview.value?.data.parser_revision === masterParserRevision)
const activeChoices = computed(() => choices.value.filter(choice => choice.selected))
const capture = () => !confirmed.value && (customer.value || file.value || preview.value) ? {
  customer: customer.value, productIds: productIds.value, file: file.value, preview: recordRef(preview.value), choices: choices.value, mappings: mappings.value,
  label: [customer.value, products.value.filter(row => productIds.value.includes(row.id)).map(row => row.data.code).join('/'),
    file.value?.name || preview.value?.data.filename || '新导入', preview.value ? '核对中' : '待上传'].filter(Boolean).join(' · '),
} : null
const accessLost = computed(() => lostRecordAccess(ws, preview.value))
const draft = useMaterialDraft(capture, {
  id: 'masterimport', multiple: true, capture,
  restore: saved => {
    if (!customers.value.some(row => row.data.name === saved.customer)) throw new Error('原客人已停用或不可用，草稿仍保留。')
    const available = customerProducts(ws.records, saved.customer)
    if (!Array.isArray(saved.productIds) || saved.productIds.some((id: string) => !available.some(row => row.id === id))) throw new Error('所选货号已变化，草稿仍保留，请先核对基础资料。')
    const source = restoreRecord(ws.records, saved.preview, 'import') || null
    if (source && (source.data.import_type !== 'material_master' || source.data.status === 'confirmed')) throw new Error('原导入已确认或类型不符，请查看导入记录；草稿仍保留。')
    if (saved.file && !(saved.file instanceof File)) throw new Error('草稿文件无法读取，原草稿仍保留。')
    customer.value = saved.customer; productIds.value = saved.productIds; file.value = saved.file || null
    preview.value = source; choices.value = saved.choices || []; mappings.value = saved.mappings || []
  },
  reset: () => reset(),
})
const locked = computed(() => accessLost.value || !ws.canWrite || ws.locked || draft.switching.value || draft.recoveryWaiting.value)
function reset() { customer.value = ''; productIds.value = []; file.value = null; preview.value = null; choices.value = []; mappings.value = [] }
function newImport() { return draft.openRecord(newDraftId('masterimport'), reset) }
async function changeCustomer(event: Event) {
  const next = (event.target as HTMLSelectElement).value
  ;(event.target as HTMLSelectElement).value = customer.value
  if (file.value || preview.value || productIds.value.length) {
    await draft.openRecord(newDraftId('masterimport'), () => { reset(); customer.value = next })
  } else customer.value = next
}
async function fileChanged(event: Event) {
  const input = event.target as HTMLInputElement, next = input.files?.[0]
  input.value = ''
  if (!next) return
  if (!next.size || next.size > 200 * 1024 * 1024) { ws.error = '文件为空或超过 200 MB，请重新选择；已有草稿保留。'; return }
  ws.error = ''
  if (file.value || preview.value) {
    const selectedCustomer = customer.value, selectedProducts = [...productIds.value]
    await draft.openRecord(newDraftId('masterimport'), () => { reset(); customer.value = selectedCustomer; productIds.value = selectedProducts; file.value = next })
  } else file.value = next
}
async function upload(remap = false) {
  if (!file.value || !productIds.value.length || locked.value) return
  const previousGroups = clone(groups.value), previousChoices = clone(choices.value)
  // Preserve the previous comparison and any manual entries when producing a new preview.
  if (preview.value) {
    const selected = { customer: customer.value, ids: [...productIds.value], file: file.value, mappings: remap ? clone(mappings.value) : [], preview: preview.value, choices: clone(choices.value) }
    if (!await draft.openRecord(newDraftId('masterimport'), () => {
      reset(); customer.value = selected.customer; productIds.value = selected.ids; file.value = selected.file
      mappings.value = selected.mappings; preview.value = selected.preview; choices.value = selected.choices
    })) return
  }
  const owner = draft.activeId.value
  const result = await ws.masterPreview(customer.value, productIds.value, file.value!, mappings.value)
  if (result && draft.activeId.value === owner) { preview.value = result; mappings.value = clone(originalMappings()); choices.value = restoreImportEdits(previousGroups, previousChoices, result.data.groups); draft.accept() }
}
function inspect(row: MaterialRecord) {
  return draft.openRecord(recordDraftId('masterimport', 'inspect', row.id), () => {
    reset(); customer.value = row.data.customer; productIds.value = row.data.products.map((p: Data) => p.id)
    preview.value = row; choices.value = importChoices(row.data.groups); mappings.value = clone(originalMappings())
  }, row.data.status !== 'confirmed' && ws.canWrite)
}
function mapColumn(mapping: Data, key: string, event: Event) {
  const value = Number((event.target as HTMLSelectElement).value)
  if (value) mapping.columns[key] = value
  else delete mapping.columns[key]
}
function chooseSource(group: Data, choice: Data) {
  choice.material = incomingMaterial(group, choice.source_index)
}
function editFields(group: Data, choice: Data) {
  return choiceFields(materialFields, ws.records, ws.optionDefaults, choice.material).map(field => ({ ...field, readonly: !!group.existing?.data.code && field.key === 'code' }))
}
const ready = computed(() => rulesCurrent.value && !confirmed.value && !mappingChanged.value && activeChoices.value.length > 0 && activeChoices.value.every(choice =>
  choice.source_index >= 0 && ['keep', 'import'].includes(choice.decision) && choice.recipes.every((r: Data) => r.decision === 'keep' || Number(r.usage) > 0)))
async function confirm() {
  if (!ready.value || !preview.value || locked.value) return
  await draft.run('master_import_confirm', importPayload(choices.value), preview.value, () => {
    preview.value = ws.record(preview.value!.id) || null
    choices.value = []; draft.accept(); ws.notice = '所选物料已导入基础资料库。'
  })
}
defineExpose({ permitDiscard: draft.permitDiscard })
</script>

<template>
  <Panel title="统一资料导入" subtitle="选择已有货号，核对物料后保存到基础资料库。">
    <p v-if="accessLost" class="im-message" role="alert">此待办已转交其他跟客或不可用，不能继续处理。原本机草稿保留，可新建或打开其他单据。</p>
    <template #action><button type="button" :disabled="!ws.canWrite || ws.locked || draft.switching.value" @click="newImport">新建导入</button></template>
    <ol class="im-import-progress" aria-label="统一资料导入步骤"><li :class="{ active: !preview }">1 选择货号与文件</li><li :class="{ active: preview && !confirmed }">2 对比与补充</li><li :class="{ active: confirmed }">3 确认保存</li></ol>
    <p v-if="draft.recoveryWaiting.value" class="im-message">已有导入草稿，可从“草稿”继续填写，或新建一份。</p>
    <form class="im-stack" @submit.prevent="upload()">
      <fieldset :disabled="locked || !!preview" class="im-stack">
        <label class="im-field"><span>固定客人 *</span><select :value="customer" required @change="changeCustomer"><option value="">请选择固定客人</option><option v-for="row in customers" :key="row.id">{{ row.data.name }}</option></select></label>
        <div v-if="customer" class="im-stack"><strong>导入到哪些货号 *</strong><div class="im-import-products"><label v-for="row in products" :key="row.id"><input v-model="productIds" type="checkbox" :value="row.id"> {{ row.data.code }} · {{ row.data.name || '未填名称' }}</label></div><p v-if="!products.length" class="im-note">请先在“货号与物料”新增该客人的货号。</p></div>
      </fieldset>
      <label class="im-field"><span>统一资料文件（.xlsx） *</span><input type="file" accept=".xlsx" :disabled="locked" @change="fileChanged"><small>支持含图片的 Excel，最大 200 MB；超限物料图自动压缩，原文件不变。</small><small v-if="file">已选择：{{ file.name }}（{{ (file.size / 1024 / 1024).toFixed(1) }} MB）</small></label>
      <div v-if="!preview" class="im-actions"><button type="submit" class="im-primary" :disabled="locked || !file || !customer || !productIds.length">{{ ws.busy ? '正在读取并核对…' : '上传并核对' }}</button></div>
    </form>
    <div v-if="preview" class="im-stack im-master-import-review">
      <div class="im-inline"><strong>{{ preview.data.filename }}</strong><span class="im-tag">{{ confirmed ? '已导入' : '待核对' }}</span></div>
      <p class="im-note">匹配 {{ preview.data.matched_rows }} 行 · {{ preview.data.groups.length }} 种物料；其他货号 {{ preview.data.skipped_rows }} 行未选入。</p>
      <p v-if="preview.data.issues?.length" class="im-message" role="alert">{{ preview.data.issues.join('；') }}</p>
      <p v-if="!confirmed && !rulesCurrent" class="im-message" role="alert">模板识别规则已更新，请重新读取以识别单位、合并资料、净重和图片；原草稿保留。</p>
      <p v-if="!confirmed && rulesCurrent && !parserCurrent" class="im-note">识别规则已更新，重新读取可补齐来源资料；已填写内容保留。</p>
      <button v-if="!confirmed && file" type="button" :disabled="locked" @click="upload()">重新读取最新资料并对比</button>
      <details v-if="!confirmed" class="im-import-mapping" :open="!preview.data.groups.length">
        <summary>核对表头对应关系（单位或字段未识别时调整）</summary>
        <fieldset :disabled="locked" class="im-stack">
          <div v-for="(mapping, index) in mappings" :key="mapping.sheet" class="im-stack">
            <label><input v-model="mapping.enabled" type="checkbox"> {{ mapping.sheet }} · 第 {{ mapping.header_row }} 行为表头</label>
            <div v-if="mapping.enabled" class="im-fields"><label v-for="field in importFields" :key="field.key" class="im-field"><span>{{ field.label }}</span><select :value="mapping.columns[field.key] || ''" @change="mapColumn(mapping, field.key, $event)"><option value="">不读取此列</option><option v-for="(header, column) in headers(index)" :key="column" :value="column + 1">第 {{ column + 1 }} 列 · {{ header || '空表头' }}</option></select></label></div>
          </div>
          <p class="im-note">“单件用量”只对应每件成品的用量，不选择送货数量、需求数量或箱数。图片按所在物料行读取，未读到图片时保留原图。</p>
          <button type="button" :disabled="!file || !mappingChanged" @click="upload(true)">按新对应关系重新预览</button>
          <p v-if="!file" class="im-note">重新预览需重新选择来源文件；原核对草稿会保留。</p>
        </fieldset>
      </details>
      <p v-if="!preview.data.groups.length" class="im-message">未找到所选货号的物料，请核对货号列、物料名称列及文件。</p>
      <p v-if="mappingChanged && !confirmed" class="im-message">表头对应关系已修改，请先重新预览。</p>
      <form v-if="!confirmed && choices.length" class="im-stack" @submit.prevent="confirm">
        <fieldset :disabled="locked || mappingChanged" class="im-stack">
          <article v-for="(group, index) in groups" :key="group.index" class="im-import-material" :data-master-import-group="group.index">
            <div class="im-import-material-heading"><label><input v-model="choices[index].selected" type="checkbox" :disabled="!!group.blocked"> <strong>{{ [group.existing?.data.code || group.sources[0].source.code, group.existing?.data.name || group.sources[0].source.name].filter(Boolean).join(' · ') }}</strong></label><span class="im-tag" :class="group.existing ? 'im-tag-amber' : ''">{{ group.existing ? '已有资料 · 需选择' : '新增物料' }}</span></div>
            <p v-if="group.blocked" role="alert" class="im-error">{{ group.blocked }}</p>
            <p v-for="warning in group.code_warnings || []" :key="warning" class="im-message">{{ warning }}</p>
            <div v-if="choices[index].selected" class="im-stack">
              <label class="im-field"><span>采用哪条来源资料 *</span><select v-model="choices[index].source_index" required @change="chooseSource(group, choices[index])"><option :value="-1" disabled>请选择一条来源（同一物料不会重复新增）</option><option v-for="source in group.sources" :key="source.index" :value="source.index">{{ source.source_sheet }} · 第 {{ source.source_row }} 行 · {{ source.source.item_no }} · {{ source.source.name }} · {{ source.source.specification || '无规格' }}</option></select></label>
              <p v-for="source in group.sources.filter((row: Data) => row.index === choices[index].source_index && row.warnings.length)" :key="source.index" class="im-message">{{ source.warnings.join('；') }}</p>
              <details v-for="source in group.sources.filter((row: Data) => row.index === choices[index].source_index && row.notes?.length)" :key="`notes-${source.index}`"><summary>识别来源（{{ source.notes.length }} 项）</summary><ul class="im-note"><li v-for="note in source.notes" :key="note">{{ note }}</li></ul></details>
              <template v-if="group.existing">
                <div class="im-scroll"><table class="im-import-comparison"><thead><tr><th>字段</th><th>已有资料</th><th>本次导入（空白保留已有值）</th></tr></thead><tbody><tr v-for="field in materialFields.filter(field => String(group.existing.data[field.key] ?? '') !== String(choices[index].material[field.key] ?? ''))" :key="field.key"><td>{{ field.label }}</td><td>{{ group.existing.data[field.key] ?? '—' }}</td><td>{{ choices[index].material[field.key] ?? '—' }}</td></tr><tr v-if="materialFields.every(field => String(group.existing.data[field.key] ?? '') === String(choices[index].material[field.key] ?? ''))"><td colspan="3">文字资料一致，仍需确认保留。</td></tr></tbody></table></div>
                <label class="im-field"><span>重复资料处理 *</span><select v-model="choices[index].decision" required><option value="" disabled>请选择保留哪份资料</option><option value="keep">保留已有资料</option><option value="import">采用本次导入资料</option></select></label>
                <div v-if="group.existing.data.image_data !== choices[index].material.image_data && choices[index].material.image_data" class="im-fields"><div><p class="im-note">已有图片</p><div class="im-material-image"><img v-if="group.existing.data.image_data" :src="group.existing.data.image_data" alt="已有物料图片"><span v-else>无图片</span></div></div><div><p class="im-note">本次导入图片</p><div class="im-material-image"><img :src="choices[index].material.image_data" alt="本次导入物料图片"></div></div></div>
                <p v-if="group.affected_products.length" class="im-note">共用物料：{{ group.affected_products.map((p: Data) => `${p.customer} / ${p.code}`).join('、') }}。采用导入资料会更新这些货号引用的物料；历史合同和出货资料保持原快照。</p>
              </template>
              <details v-if="choices[index].decision === 'import'" :open="!group.existing"><summary>补充或调整物料资料</summary><div v-if="!group.existing && choices[index].material.image_data" class="im-material-image"><img :src="choices[index].material.image_data" alt="本次导入物料图片"></div><Fields :model="choices[index].material" :fields="editFields(group, choices[index])" /></details>
              <div class="im-scroll"><table><thead><tr><th>对应货号</th><th>已有单件用量</th><th>用量处理</th><th>本次单件用量</th></tr></thead><tbody><tr v-for="(product, n) in group.products" :key="product.id"><td>{{ product.code }}<small class="im-note">来源用量：{{ sourceUsages(group, product.id).join(' / ') || '未提供' }}</small></td><td>{{ product.existing_usage || '未配置' }}</td><td><select v-model="choices[index].recipes[n].decision" :aria-label="`${product.code} 用量处理`"><option v-if="product.existing_usage" value="keep">保留已有用量</option><option value="import">填写／采用新用量</option></select></td><td><input v-if="choices[index].recipes[n].decision === 'import'" v-model="choices[index].recipes[n].usage" type="number" min="0.00000001" step="any" required :aria-label="`${product.code} 单件用量`"><span v-else>{{ product.existing_usage }}</span></td></tr></tbody></table></div>
            </div>
          </article>
        </fieldset>
        <div class="im-actions"><button type="submit" class="im-primary" :disabled="locked || !ready">确认导入 {{ activeChoices.length }} 种物料</button><span v-if="!ready" class="im-note">请完成来源、重复资料和单件用量的选择。</span></div>
      </form>
      <p v-if="confirmed" role="status" class="im-message">本次已导入 {{ preview.data.choices?.length || 0 }} 种物料，可到“货号与物料”查看。</p>
      <button type="button" :disabled="ws.busy" @click="ws.download(preview.data.asset_id, preview.data.filename, 'asset')">下载来源原件</button>
    </div>
    <details v-if="history.length" class="im-master-import-review"><summary>导入记录（{{ history.length }}）</summary><div class="im-scroll"><table><thead><tr><th>来源文件</th><th>货号</th><th>状态</th><th>上传人／负责人</th><th>操作</th></tr></thead><tbody><tr v-for="row in history" :key="row.id"><td>{{ row.data.filename }}</td><td>{{ row.data.products.map((p: Data) => p.code).join('、') }}</td><td>{{ row.data.status === 'confirmed' ? '已导入' : '待核对' }}</td><td><RecordResponsibility :record="row" /></td><td><button type="button" :disabled="!ws.canWrite || ws.locked || draft.switching.value" @click="inspect(row)">查看核对</button></td></tr></tbody></table></div></details>
  </Panel>
</template>
