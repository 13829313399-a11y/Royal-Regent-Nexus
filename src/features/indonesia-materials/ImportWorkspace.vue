<script setup lang="ts">
import { ref } from 'vue'
import { FileInput } from '@lucide/vue'
import SectionPanel from './MaterialsPanel.vue'
import type { MaterialRecord } from '@/api/indonesiaMaterials'
import { showStatus } from './forms'
import { useMaterials } from './workspace'
const ws = useMaterials()
const customer = ref('')
const recipient = ref('RRI')
const file = ref<File | null>(null)
const preview = ref<MaterialRecord | null>(null)
const selected = ref<number[]>([])
function fileChanged(event: Event) { file.value = (event.target as HTMLInputElement).files?.[0] ?? null }
async function upload() {
  if (!file.value) return
  const result = await ws.preview(customer.value, recipient.value, file.value)
  if (result) { preview.value = result; selected.value = [] }
}
function inspect(record: MaterialRecord) { preview.value = record; selected.value = [] }
async function confirm() {
  if (!preview.value || preview.value.data.status === 'confirmed' || !selected.value.length) return
  if (await ws.run('import_confirm', { indexes: selected.value }, preview.value)) {
    preview.value = ws.record(preview.value.id) ?? null
    selected.value = []
  }
}
</script>
<template>
  <SectionPanel title="统一排期导入" subtitle="上传仅生成预览。核对客户、接收方、来源坐标及重复提示后，勾选行确认入合同。">
    <div class="im-steps" aria-label="排期导入步骤"><div class="im-step is-active"><b>1</b><div>选择排期文件<small>现有统一排期格式</small></div></div><div class="im-step" :class="{ 'is-active': preview }"><b>2</b><div>核对合同批次<small>检查字段与重复记录</small></div></div><div class="im-step" :class="{ 'is-active': preview?.data.status === 'confirmed' }"><b>3</b><div>确认导入<small>生成需求与倒排</small></div></div></div>
    <form class="im-upload-form" @submit.prevent="upload">
      <fieldset :disabled="!ws.canWrite || ws.locked" class="im-fields">
        <label class="im-field"><span>客户 *</span><input v-model="customer" required></label>
        <label class="im-field"><span>本次接收方 *</span><select v-model="recipient"><option>RRI</option><option>RRM</option></select></label>
        <label class="im-field"><span>统一排期文件（.xlsx） *</span><input type="file" accept=".xlsx" required @change="fileChanged"></label>
      </fieldset>
      <div class="im-actions"><button class="im-primary" type="submit" :disabled="!ws.canWrite || ws.locked || !file"><FileInput :size="15" />上传并预览</button><span class="im-note">上传后先核对，勾选确认才生成合同。</span></div>
    </form>
    <div v-if="preview" class="im-editor im-stack">
      <h3>预览：{{ preview.data.filename }} · {{ showStatus(preview.data.status || 'preview') }}</h3>
      <ul v-if="preview.data.issues?.length" class="im-message list-disc pl-8"><li v-for="(issue, index) in preview.data.issues" :key="index">{{ typeof issue === 'string' ? issue : issue.message ?? issue.detail ?? '来源行需要核对' }}</li></ul>
      <div v-if="preview.data.rows?.length" class="im-scroll"><table><thead><tr><th>选择</th><th>客户／接收方</th><th>合同／PO</th><th>货号／批次</th><th>数量</th><th>走货期</th><th>来源</th><th>核对提示</th></tr></thead><tbody>
        <tr v-for="row in preview.data.rows" :key="row.index"><td><input v-model="selected" type="checkbox" :value="row.index" :aria-label="`选择来源行 ${row.source_row}`" :disabled="row.blocked || !!row.imported_order_id || preview.data.status === 'confirmed' || !ws.canWrite || ws.locked"></td><td>{{ row.customer }} / {{ row.recipient }}</td><td>{{ row.contract_no }}<br>{{ row.po_no }}</td><td>{{ row.item_no }}<br>{{ row.batch }}</td><td>{{ row.quantity }} {{ row.unit }}</td><td>{{ row.delivery_date }}</td><td>{{ row.source_sheet }} · 第 {{ row.source_row }} 行</td><td><b>{{ row.imported_order_id ? '已在本批确认' : row.match_status === 'changed' ? '已有合同有变更' : row.match_status === 'unchanged' ? '已有记录，无变化' : '新增行' }}</b><p>{{ row.issues?.join('；') || (row.blocked ? '不可导入' : '可核对导入') }}</p><p v-for="change in row.changes || []" :key="change.field">{{ change.field === 'quantity' ? '数量' : change.field === 'delivery_date' ? '成品交期' : change.field }}：{{ change.old }} → {{ change.new }}</p></td></tr>
      </tbody></table></div>
      <p v-else class="im-empty">未识别到可导入的合同明细，请核对文件及识别提示。</p>
      <div class="im-actions"><button v-if="preview.data.status !== 'confirmed'" type="button" class="im-primary" :disabled="!ws.canWrite || ws.locked || !selected.length" @click="confirm">确认导入选中 {{ selected.length }} 行</button><button v-if="preview.data.source_asset_id || preview.data.asset_id" type="button" :disabled="ws.busy" @click="ws.download(preview.data.source_asset_id || preview.data.asset_id, preview.data.filename, 'asset')">下载来源原件</button></div>
    </div>
    <h3 class="mt-6">导入记录</h3>
    <div v-if="ws.kind('import').length" class="im-scroll"><table><thead><tr><th>来源文件</th><th>状态</th><th>来源行数</th><th>操作</th></tr></thead><tbody><tr v-for="row in ws.kind('import')" :key="row.id"><td>{{ row.data.filename }}</td><td>{{ showStatus(row.data.status || 'preview') }}</td><td>{{ row.data.rows?.length ?? 0 }}</td><td><button type="button" :disabled="ws.locked" @click="inspect(row)">查看核对</button></td></tr></tbody></table></div>
    <p v-else class="im-empty">暂无已保存的导入记录。</p>
  </SectionPanel>
</template>
