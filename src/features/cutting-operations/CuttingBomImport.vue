<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, useId } from 'vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import { Button } from '@/components/ui/button'
import { errorMessage, type MasterRecord } from './api'
import { bomImportApi, type BomImportCommand, type BomImportResult, type BomPreview } from './bomImportApi'
import { CUTTING_FACTORY } from './navigation'

const emit = defineEmits<{ imported: [record: MasterRecord] }>()
const id = `cutting-bom-${useId()}`
const open = ref(false)
const file = ref<File>()
const fileInput = ref<HTMLInputElement>()
const preview = ref<BomPreview>()
const result = ref<BomImportResult>()
const reason = ref('')
const acknowledged = ref(false)
const error = ref('')
const busy = ref(false)
const pending = ref<{ file: File; command: BomImportCommand }>()
const uncertain = ref(false)
const unsettled = computed(() => busy.value || !!pending.value)
const canConfirm = computed(() => preview.value?.candidate && preview.value.fingerprint && acknowledged.value && reason.value.trim())
let alive = true

function discard() {
  if (unsettled.value) {
    error.value = '请先等待读取完成或核对原导入结果。'
    return false
  }
  return !file.value || window.confirm('有尚未导入的 BOM，确定放弃本次预览？')
}
defineExpose({ discard, unsettled })
function beforeUnload(event: BeforeUnloadEvent) {
  if (file.value || unsettled.value) event.preventDefault()
}
onMounted(() => window.addEventListener('beforeunload', beforeUnload))
onBeforeUnmount(() => {
  alive = false
  window.removeEventListener('beforeunload', beforeUnload)
})

function invalidatePreview() {
  preview.value = undefined
  acknowledged.value = false
}
function choose(event: Event) {
  file.value = (event.target as HTMLInputElement).files?.[0]
  error.value = ''
  result.value = undefined
  invalidatePreview()
  if (file.value && (!file.value.name.toLowerCase().endsWith('.xlsx') || file.value.size > 5 * 1024 * 1024)) {
    file.value = undefined
    error.value = '请选择不超过 5 MB 的 .xlsx 固定模板文件。'
  }
}
function close() {
  if (!discard()) return
  open.value = false
  file.value = undefined
  reason.value = ''
  error.value = ''
  invalidatePreview()
}
async function download() {
  busy.value = true
  error.value = ''
  try {
    const blob = await bomImportApi.template()
    if (!alive) return
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = '工程BOM导入模板.xlsx'
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (e) {
    if (alive) error.value = errorMessage(e)
  } finally { busy.value = false }
}
async function read() {
  if (!file.value || unsettled.value) return
  busy.value = true
  error.value = ''
  invalidatePreview()
  try {
    const response = await bomImportApi.preview(file.value)
    if (alive) preview.value = response
  } catch (e) {
    if (alive) error.value = errorMessage(e)
  } finally { busy.value = false }
}
function complete(response: BomImportResult) {
  result.value = response
  pending.value = undefined
  uncertain.value = false
  busy.value = false
  file.value = undefined
  reason.value = ''
  invalidatePreview()
  if (fileInput.value) fileInput.value.value = ''
  emit('imported', response.record)
}
async function confirmDraft() {
  if (busy.value) return
  if (!pending.value) {
    const current = preview.value
    if (!canConfirm.value || !file.value || !current?.candidate || !current.fingerprint) return
    pending.value = { file: file.value, command: { factory_id: CUTTING_FACTORY, operation_id: crypto.randomUUID(),
      expected_version: current.candidate.expected_version, reason: reason.value.trim(), fingerprint: current.fingerprint,
      file_name: current.file_name, file_sha256: current.file_sha256 } }
  }
  busy.value = true
  error.value = ''
  try {
    const response = await bomImportApi.confirm(pending.value.file, pending.value.command)
    if (alive) complete(response)
  } catch (e) {
    if (!alive) return
    const status = (e as { response?: { status?: number } }).response?.status
    error.value = errorMessage(e)
    if (uncertain.value || !status || status >= 500 || status === 408 || status === 401) {
      uncertain.value = true
      error.value += ' 结果尚未确认，请重试或核对原操作。'
    } else {
      pending.value = undefined
      invalidatePreview()
      error.value += ' 请重新预览并确认。'
    }
  } finally { busy.value = false }
}
async function recover() {
  if (!pending.value || busy.value) return
  busy.value = true
  error.value = ''
  try {
    const response = await bomImportApi.recover(pending.value.command)
    if (!alive) return
    if (response.state === 'committed') complete(response.result)
    else {
      pending.value = undefined
      uncertain.value = false
      invalidatePreview()
      error.value = '原导入未执行并已终止，请重新预览。'
    }
  } catch (e) {
    if (alive) error.value = errorMessage(e)
  } finally { busy.value = false }
}
</script>

<template>
  <SectionPanel title="工程 BOM Excel 导入" subtitle="使用固定模板生成草稿，工程核对后在 BOM 列表发布。" class="cutting-content-panel">
    <template #action>
      <Button v-if="!open" variant="outline" @click="open = true">导入工程 BOM</Button>
      <Button v-else variant="outline" :disabled="unsettled" @click="close">收起导入</Button>
    </template>
    <div v-if="open" class="bom-import-body">
      <p>每个文件填写一张 BOM，保留「产品与版本」「裁片组成」「物料用量」三张表。多个适用部件编码用逗号分隔，裁剪必需填“是”或“否”。</p>
      <div class="cutting-master-actions"><Button variant="outline" :disabled="unsettled" @click="download">下载 BOM 模板</Button></div>
      <div class="cutting-master-toolbar">
        <label :for="`${id}-file`">工程 BOM 文件<input :id="`${id}-file`" ref="fileInput" type="file" name="cutting_bom_file" accept=".xlsx" :disabled="unsettled" @change="choose" /></label>
        <Button :disabled="!file || unsettled" @click="read">预览并校验</Button>
      </div>
      <p v-if="busy" role="status">正在处理，请稍候。</p>
      <p v-if="error" role="alert" class="cutting-error">{{ error }}</p>
      <div v-if="preview?.issues.length" role="alert" class="cutting-error">
        <h3>校验未通过，请修正文件后重新预览</h3>
        <ul><li v-for="(issue, index) in preview.issues" :key="index">{{ issue.sheet }}{{ issue.row ? ` · 第 ${issue.row} 行` : '' }}：{{ issue.message }}</li></ul>
      </div>
      <template v-if="preview?.candidate">
        <p role="status">校验通过 · {{ preview.candidate.existing_id ? `从系统 V${preview.candidate.expected_version} 生成修订草稿` : '新增 BOM 草稿' }}</p>
        <p>{{ preview.candidate.code }} · {{ preview.candidate.data.item_no }} · {{ preview.candidate.data.name }} · {{ preview.candidate.data.style }} / {{ preview.candidate.data.color }} · 工程来源 {{ preview.candidate.data.source_reference }}</p>
        <div class="cutting-table-scroll" role="region" aria-label="裁片组成预览，可横向滚动" tabindex="0">
          <table><caption>裁片组成</caption><thead><tr><th>部件编码</th><th>部件名称</th><th>每套裁片数</th></tr></thead>
            <tbody><tr v-for="part in preview.candidate.data.parts" :key="part.code"><td>{{ part.code }}</td><td>{{ part.name }}</td><td>{{ part.pieces_per_set }}</td></tr></tbody>
          </table>
        </div>
        <div class="cutting-table-scroll" role="region" aria-label="物料用量预览，可横向滚动" tabindex="0">
          <table><caption>物料用量与匹配版本</caption><thead><tr><th>行号</th><th>物料与版本</th><th>适用部件</th><th>每套净用量</th><th>阶段／必需</th><th>备注</th></tr></thead>
            <tbody><tr v-for="row in preview.candidate.material_rows" :key="row.row"><td>{{ row.row }}</td><td>{{ row.material_code }} · {{ row.material_name }} · V{{ row.material_version }}</td><td>{{ row.part_codes.join('、') }}</td><td>{{ row.quantity_per_set }} {{ row.unit }}</td><td>{{ row.stage }}／{{ row.required_for_cutting ? '是' : '否' }}</td><td>{{ row.note || '—' }}</td></tr></tbody>
          </table>
        </div>
        <form class="cutting-master-form" @submit.prevent="confirmDraft">
          <label :for="`${id}-reason`">导入依据<input :id="`${id}-reason`" v-model="reason" name="cutting_bom_import_reason" maxlength="500" required :disabled="unsettled" /></label>
          <label class="cutting-master-checkbox"><input v-model="acknowledged" type="checkbox" :disabled="unsettled" />已核对裁片、物料版本及用量，本次保存为草稿</label>
          <div v-if="!pending" class="cutting-master-actions"><Button type="submit" :disabled="!canConfirm || busy">确认生成 BOM 草稿</Button></div>
        </form>
      </template>
      <div v-if="pending" class="cutting-master-actions">
        <Button :disabled="busy" @click="confirmDraft">重试原导入</Button><Button variant="outline" :disabled="busy" @click="recover">核对原导入结果</Button>
        <a href="/login" target="_blank" rel="noopener noreferrer">在新标签页重新登录</a>
      </div>
    </div>
    <p v-if="result" role="status" class="cutting-notice">已生成 BOM 草稿 {{ result.record.code }} V{{ result.record.version }}。工程核对后，可在 BOM 列表单独发布。</p>
  </SectionPanel>
</template>

<style scoped>
.bom-import-body { display: grid; gap: 14px; min-width: 0; overflow-wrap: anywhere; }
.bom-import-body input[type=file] { max-width: 100%; }
.bom-import-body td { padding: 10px 14px; }
</style>
