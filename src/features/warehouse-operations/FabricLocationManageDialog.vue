<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, type RouteLocationNormalized } from 'vue-router'
import { DialogRoot, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogDescription } from 'reka-ui'
import { Button } from '@/components/ui/button'
import { fabricMasterApi as api, type MasterRecord, type LocationManage } from '@/api/fabricMaster'
import { getApiErrorMessage } from '@/lib/http'
import { warehouseRequestId } from './requestIdentity'
import { locationCategoryLabels } from './fabricLocationZones'
import { useAuthStore } from '@/stores/auth'
import { pendingFabricLocationManage } from './pendingFabricRequests'

const props = defineProps<{ action: LocationManage['action']; records: MasterRecord[]; initialIds: string[] }>()
const emit = defineEmits<{ close: []; saved: [message: string] }>()
const auth = useAuthStore()
const actorId = auth.currentUser?.id
const operation = computed(() => pendingFabricLocationManage.get(actorId ?? ''))
const selected = ref([...props.initialIds]), category = ref<LocationManage['category'] | 'GENERAL' | 'UNSET'>('UNSET')
const busy = computed(() => !!operation.value?.inFlight), error = ref(''), pending = computed(() => operation.value?.body)
if (pending.value) category.value = pending.value.category || 'GENERAL'
let alive = true
const title = computed(() => ({ CATEGORY: '设置分料区', DELETE: '删除所选仓位', RESTORE: '恢复所选仓位' })[props.action])
const allSelected = computed(() => !!props.records.length && props.records.every(row => selected.value.includes(row.id)))
function selectAll() { selected.value = allSelected.value ? [] : props.records.map(row => row.id) }
function leave(to?: RouteLocationNormalized) { return to?.name === 'login' || to?.name === 'forbidden' || !busy.value && (!pending.value || window.confirm('提交结果尚未确认，请优先重试原提交。确定离开？')) }
onBeforeRouteLeave(leave); onBeforeRouteUpdate(leave)
function beforeUnload(event: BeforeUnloadEvent) { if (pending.value || busy.value) { event.preventDefault(); event.returnValue = '' } }
window.addEventListener('beforeunload', beforeUnload)
onBeforeUnmount(() => { alive = false; window.removeEventListener('beforeunload', beforeUnload) })
function close() { if (leave()) emit('close') }
async function save() {
  if (busy.value || actorId !== auth.currentUser?.id) return
  if (!pending.value) {
    if (!selected.value.length || selected.value.length > 1000) { error.value = '请选择 1 至 1000 个仓位。'; return }
    if (props.action === 'CATEGORY' && category.value === 'UNSET') { error.value = '请选择分料区。'; return }
    const body: LocationManage = { factory_id: 'huakang-c', request_id: warehouseRequestId(), action: props.action,
      selections: props.records.filter(row => selected.value.includes(row.id)).map(row => ({ id: row.id, expected_revision: row.revision })),
      category: category.value === 'UNSET' || category.value === 'GENERAL' ? '' : category.value }
    pendingFabricLocationManage.set(actorId ?? '', { body, records: JSON.parse(JSON.stringify(props.records)), actorId, inFlight: false })
  }
  const request = operation.value!
  request.inFlight = true; error.value = ''
  try {
    const result = await api.manageLocations(request.body)
    pendingFabricLocationManage.delete(actorId ?? '')
    if (alive && actorId === auth.currentUser?.id) emit('saved', props.action === 'DELETE' ? `已删除 ${result.updated} 个仓位，可在“已删除”中恢复。` : props.action === 'RESTORE' ? `已恢复 ${result.updated} 个仓位。` : `已为 ${result.updated} 个仓位设置分料区，未新增仓位或库存。`)
  } catch (e) {
    const status = (e as { response?: { status?: number } }).response?.status
    if (status && status < 500 && ![401,403,408,429].includes(status)) pendingFabricLocationManage.delete(actorId ?? '')
    if (alive && actorId === auth.currentUser?.id) error.value = getApiErrorMessage(e)
  } finally { request.inFlight = false }
}
</script>

<template>
  <DialogRoot :open="true" @update:open="value => { if (!value) close() }"><DialogPortal><DialogOverlay class="warehouse-guide-overlay" /><DialogContent class="warehouse-guide fabric-edit-dialog fabric-master-dialog">
    <header class="warehouse-guide-heading"><div><DialogTitle>{{ title }}</DialogTitle><DialogDescription>{{ action === 'CATEGORY' ? '给已有仓位指定适用原料，不自动建立架号或区域。' : action === 'DELETE' ? '仅能删除没有库存及业务记录的仓位；资料和修改记录保留，误删可恢复。' : '恢复原仓库、仓位及删除前的启用状态，不增加库存。' }}</DialogDescription></div><Button variant="ghost" size="sm" :disabled="busy" @click="close">关闭</Button></header>
    <form class="warehouse-guide-body location-manage-form" @submit.prevent="save">
      <fieldset :disabled="busy || !!pending">
        <label v-if="action === 'CATEGORY'" class="zone-field">分料区<select v-model="category" aria-label="分料区"><option value="UNSET" disabled>请选择分料区</option><option v-for="(name, value) in locationCategoryLabels" :key="value" :value="value">{{ name }}</option><option value="GENERAL">通用（不限原料）</option></select></label>
        <label class="location-select-all"><input type="checkbox" :checked="allSelected" @change="selectAll" />全选本次列表（{{ records.length }} 个）</label>
        <div class="location-manage-list"><label v-for="row in records" :key="row.id"><input v-model="selected" type="checkbox" :value="row.id" :aria-label="`选择 ${row.data.warehouse} ${row.code}`" /><span>{{ row.data.warehouse }} / <strong>{{ row.code }}</strong></span><small>{{ locationCategoryLabels[row.data.category ?? ''] || '通用' }}</small></label></div>
      </fieldset>
      <p v-if="error" role="alert" class="fabric-error">{{ error }}</p><p v-if="pending" class="fabric-intake-alert">结果尚待确认，请用原内容重试，避免重复提交。</p>
      <footer class="fabric-dialog-actions"><span>已选 {{ selected.length }} 个</span><Button type="button" variant="outline" :disabled="busy" @click="close">返回</Button><Button type="submit" :disabled="busy || (!pending && (!selected.length || (action === 'CATEGORY' && category === 'UNSET')))">{{ busy ? '正在处理…' : pending ? '重试原提交' : action === 'DELETE' ? '确认删除' : action === 'RESTORE' ? '确认恢复' : '保存分料区' }}</Button></footer>
    </form>
  </DialogContent></DialogPortal></DialogRoot>
</template>

<style scoped>
.zone-field{display:grid;gap:8px;margin-bottom:18px;font-size:13px}.zone-field select{padding:9px;border:1px solid var(--border);border-radius:7px;background:var(--background)}
.location-select-all,.location-manage-list label{display:flex;align-items:center;gap:10px;font-size:13px}.location-select-all{padding:10px 0}
.location-manage-list{max-height:320px;overflow:auto;border:1px solid var(--border);border-radius:8px}.location-manage-list label{padding:10px 12px;border-bottom:1px solid var(--border)}.location-manage-list label:last-child{border-bottom:0}.location-manage-list small{margin-left:auto;color:var(--muted-foreground)}.location-manage-form input[type=checkbox]{width:16px;height:16px}.fabric-dialog-actions>span{margin-right:auto;color:var(--muted-foreground);font-size:13px}
</style>
