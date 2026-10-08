<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { DialogRoot, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogDescription } from 'reka-ui'
import { Warehouse, Plus, Upload, Download } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { fabricMasterApi as api, type MasterRecord, type LocationPreview, type LocationApply, type WarehouseRename } from '@/api/fabricMaster'
import { getApiErrorMessage } from '@/lib/http'
import { warehouseRequestId } from './requestIdentity'

const props = defineProps<{ records: MasterRecord[]; warehouseTokens: Record<string, string>; canManage: boolean; busy: boolean; search: string; status: string }>()
const emit = defineEmits<{ edit: [record: MasterRecord]; history: [record: MasterRecord]; refresh: []; locked: [value: boolean] }>()
const groups = computed(() => [...new Set(props.records.map(row => row.data.warehouse || '待补所属仓库'))].map(warehouse => ({ warehouse,
  all: props.records.filter(row => (row.data.warehouse || '待补所属仓库') === warehouse),
  places: props.records.filter(row => (row.data.warehouse || '待补所属仓库') === warehouse && (props.status === 'ALL' || row.status === props.status)
    && `${row.code} ${row.name} ${JSON.stringify(row.data)}`.toLocaleLowerCase().includes(props.search.trim().toLocaleLowerCase())),
})).filter(group => group.places.length))
const mode = ref<'warehouse' | 'bins' | 'import' | 'rename'>(), warehouse = ref(''), bins = ref(''), original = ref('')
const groupToken = ref(''), file = ref<File>(), plan = ref<LocationPreview>(), submitted = ref<LocationApply | WarehouseRename>()
const busy = ref(false), error = ref(''), notice = ref(''), initial = ref('')
let alive = true, generation = 0
onBeforeUnmount(() => { alive = false; generation++; emit('locked', false) })
const content = () => JSON.stringify([warehouse.value, bins.value, file.value?.name, file.value?.lastModified])
const title = computed(() => mode.value === 'rename' ? '修改仓库' : mode.value === 'warehouse' ? '添加仓库' : mode.value === 'import' ? '导入仓库仓位' : '添加仓位')
function leave() { return !busy.value && (!mode.value || (!submitted.value && initial.value === content()) || window.confirm(submitted.value ? '保存结果待确认，请先核对资料。确定离开？' : '仓位资料尚未保存，确定离开？')) }
onBeforeRouteLeave(leave); onBeforeRouteUpdate(leave)
watch(() => !!mode.value, value => emit('locked', value))
function close() { if (leave()) { mode.value = undefined; submitted.value = undefined; plan.value = undefined; generation++ } }
function open(next: typeof mode.value, name = '') {
  if (!props.canManage || props.busy) return
  mode.value = next; warehouse.value = name; original.value = name; bins.value = ''; file.value = undefined; plan.value = undefined; submitted.value = undefined; error.value = ''
  groupToken.value = props.warehouseTokens[name] ?? ''
  initial.value = content(); generation++
}
watch([warehouse, bins, file], () => { if (!submitted.value) plan.value = undefined })
function choose(event: Event) { file.value = (event.target as HTMLInputElement).files?.[0]; error.value = '' }
async function download() {
  error.value = ''
  try { const blob = await api.locationTemplate(); if (!alive) return
    const url = URL.createObjectURL(blob), link = document.createElement('a'); link.href = url; link.download = '布料仓库仓位模板.xlsx'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (e) { if (alive) error.value = getApiErrorMessage(e) }
}
async function preview() {
  if (busy.value || !props.canManage) return
  if (mode.value === 'warehouse' && props.records.some(row => row.data.warehouse === warehouse.value.trim())) { error.value = '该仓库已存在，请在对应仓库旁添加仓位。'; return }
  const ticket = ++generation; busy.value = true; error.value = ''; plan.value = undefined
  try {
    const result = mode.value === 'import' ? await api.previewLocationFile(file.value!) : await api.previewLocations([{ warehouse: warehouse.value.trim(), bins: bins.value.trim() }])
    if (alive && ticket === generation) plan.value = result
  } catch (e) { if (alive && ticket === generation) error.value = getApiErrorMessage(e) }
  finally { if (alive && ticket === generation) busy.value = false }
}
async function save() {
  if (busy.value || !props.canManage) return
  if (!submitted.value) {
    if (mode.value === 'rename') { if (!groupToken.value) { error.value = '仓库版本未加载，请刷新资料后重试。'; return }; submitted.value = { factory_id: 'huakang-c', request_id: warehouseRequestId(), warehouse: original.value, name: warehouse.value.trim(), expected_group_token: groupToken.value } }
    else { if (!plan.value || plan.value.errors.length || !plan.value.new) return
      submitted.value = { factory_id: 'huakang-c', request_id: warehouseRequestId(), preview_token: plan.value.preview_token,
        rows: plan.value.rows ?? [{ warehouse: warehouse.value.trim(), bins: bins.value.trim() }] }
    }
  }
  busy.value = true; error.value = ''
  try {
    if ('expected_group_token' in submitted.value) await api.renameWarehouse(submitted.value)
    else await api.applyLocations(submitted.value)
    if (!alive) return
    mode.value = undefined; submitted.value = undefined; plan.value = undefined; notice.value = '仓库仓位已保存，历史单据保留原资料。'; emit('refresh')
  } catch (e) {
    if (!alive) return
    error.value = getApiErrorMessage(e)
    const status = (e as { response?: { status?: number } }).response?.status
    if (status && status < 500 && status !== 408) { submitted.value = undefined; plan.value = undefined
      if ([401,403,409].includes(status)) { mode.value = undefined; emit('refresh') }
    }
  } finally { if (alive) busy.value = false }
}
</script>

<template>
  <section class="fabric-location-settings" aria-label="仓库与仓位设置">
    <div class="fabric-master-card-heading"><div><h2><Warehouse :size="18" />仓库与仓位</h2><p>按仓库分别维护，收料时选择已启用仓位。</p></div><div v-if="canManage" class="fabric-master-tools"><Button size="sm" variant="outline" :disabled="props.busy" @click="download"><Download :size="14" />下载仓位模板</Button><Button size="sm" variant="outline" :disabled="props.busy" @click="open('import')"><Upload :size="14" />导入仓库仓位</Button><Button size="sm" :disabled="props.busy" @click="open('warehouse')"><Plus :size="14" />添加仓库</Button></div></div>
    <p v-if="error && !mode" class="fabric-error" role="alert">{{ error }}</p><p v-if="notice" class="fabric-success" role="status">{{ notice }}</p>
    <div class="fabric-warehouse-groups">
      <article v-for="group in groups" :key="group.warehouse" class="fabric-warehouse-group">
        <header><div><h3>{{ group.warehouse }}</h3><p>{{ group.all.length }} 个仓位 · {{ group.all.filter(row => row.status === 'ACTIVE').length }} 个启用</p></div><div v-if="canManage" class="fabric-master-tools"><Button size="sm" variant="outline" :disabled="props.busy" :aria-label="`添加 ${group.warehouse} 仓位`" @click="open('bins', group.warehouse)">＋ 添加仓位</Button><Button v-if="group.all.every(row => !!row.data.warehouse)" size="sm" variant="ghost" :disabled="props.busy" :aria-label="`修改仓库 ${group.warehouse}`" @click="open('rename', group.warehouse)">修改仓库</Button></div></header>
        <div class="fabric-location-chips"><div v-for="row in group.places" :key="row.id" class="fabric-location-chip" :data-status="row.status"><button type="button" :disabled="!canManage || props.busy" :aria-label="`修改仓位 ${group.warehouse} ${row.code}`" @click="emit('edit', row)"><strong>{{ row.code }}</strong><span v-if="row.name !== row.code">{{ row.name }}</span><small>{{ row.status === 'ACTIVE' ? '启用' : row.status === 'DRAFT' ? '待完善' : '停用' }}</small></button><button type="button" class="fabric-location-history" :disabled="props.busy" :aria-label="`查看仓位 ${row.code} 修改记录`" @click="emit('history', row)">记录</button></div></div>
      </article>
      <div v-if="!props.busy && !groups.length" class="fabric-master-empty"><Warehouse :size="28" /><h3>{{ records.length ? '没有符合筛选的仓位' : '先建立仓库和仓位' }}</h3><p>{{ records.length ? '调整关键字或状态后查看。' : '添加仓库并填写首个仓位，也可以用模板批量导入。' }}</p><Button v-if="canManage && !records.length" size="sm" @click="open('warehouse')">添加仓库</Button></div>
    </div>
    <p class="fabric-master-note">仓位编码唯一，建立后保留。停用仓位禁止新收料；更名只改资料，库存和历史单据保留。</p>
  </section>
  <DialogRoot :open="!!mode" @update:open="value => { if (!value) close() }"><DialogPortal><DialogOverlay class="warehouse-guide-overlay" /><DialogContent class="warehouse-guide fabric-edit-dialog fabric-master-dialog"><header class="warehouse-guide-heading"><div><DialogTitle>{{ title }}</DialogTitle><DialogDescription>{{ mode === 'rename' ? '整组仓位同步更名，保留编码、状态及历史单据。' : '先预览核对仓库与仓位，再一次保存。' }}</DialogDescription></div><Button size="sm" variant="ghost" :disabled="busy" @click="close">关闭</Button></header>
    <form class="warehouse-guide-body fabric-master-form" @submit.prevent="mode === 'rename' || submitted ? save() : preview()"><fieldset :disabled="busy || !!submitted">
      <template v-if="mode !== 'import'"><label class="fabric-master-wide">仓库名称 <span>*</span><input v-model="warehouse" aria-label="仓库名称" maxlength="128" :readonly="mode === 'bins'" required placeholder="例如 布料一仓" /></label><label v-if="mode !== 'rename'" class="fabric-master-wide">{{ mode === 'warehouse' ? '首个仓位 / 范围' : '仓位 / 范围' }} <span>*</span><textarea v-model="bins" aria-label="仓位或范围" maxlength="16000" required placeholder="例如 A01-A20，或 A01、A02、B01" /><small>支持同前缀升序范围，前导零保留；不同仓库请使用不同编码。</small></label></template>
      <label v-else class="fabric-master-wide">仓位模板文件 <span>*</span><input type="file" accept=".xlsx,.xlsm" aria-label="仓位模板文件" required @change="choose" /><small>仅导入“导入数据”页，最多 5 MB、1000 行及 1000 个展开仓位，禁止公式。</small></label>
    </fieldset>
    <section v-if="plan" class="fabric-location-preview" aria-label="仓位导入预览"><h3>新增 {{ plan.new }} 个 · 已有 {{ plan.unchanged }} 个</h3><p v-for="message in plan.errors" :key="message" class="fabric-row-error">{{ message }}</p><p>已有同仓仓位保持原状态；本次不增加库存。</p><div class="warehouse-table-scroll"><table><thead><tr><th>仓库</th><th>仓位</th><th>处理</th></tr></thead><tbody><tr v-for="(row, index) in plan.items.slice(0,100)" :key="index"><td>{{ row.warehouse }}</td><td>{{ row.code }}</td><td>{{ row.action === 'NEW' ? '新增并启用' : row.status === 'INACTIVE' ? '已有 · 保持停用' : '已有 · 跳过' }}</td></tr></tbody></table></div><p v-if="plan.items.length > 100">显示前 100 项，共 {{ plan.items.length }} 项。</p></section>
    <p v-if="error" class="fabric-error" role="alert">{{ error }}</p><p v-if="submitted" class="fabric-intake-alert">保存结果待确认，内容已锁定。重试使用同一个请求。</p>
    <div class="fabric-dialog-actions"><Button variant="outline" type="button" :disabled="busy" @click="close">返回</Button><Button v-if="mode !== 'rename' && !submitted" variant="outline" type="submit" :disabled="busy">{{ busy ? '正在预览…' : '预览仓位' }}</Button><Button v-if="mode === 'rename' || plan || submitted" :type="mode === 'rename' || submitted ? 'submit' : 'button'" :disabled="busy || (!submitted && mode !== 'rename' && (!plan?.new || !!plan.errors.length))" @click="mode !== 'rename' && !submitted && save()">{{ busy ? '正在保存…' : submitted ? '重试保存' : mode === 'rename' ? '保存仓库' : '确认保存' }}</Button></div>
    </form></DialogContent></DialogPortal></DialogRoot>
</template>
