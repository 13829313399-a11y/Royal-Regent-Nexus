<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { FocusScope } from 'reka-ui'
import { Button } from '@/components/ui/button'
import { warehouseOperationsApi as api, type WarehouseLocation } from '@/api/warehouseOperations'
import { warehouseRequestId } from './requestIdentity'
import { getApiErrorMessage } from '@/lib/http'
const rows = ref<WarehouseLocation[]>([]), canManage = ref(false), loading = ref(false), saving = ref(false), error = ref(''), frozen = ref(false)
type Draft = Parameters<typeof api.saveLocation>[0]
const draft = ref<Draft>(), initial = ref('')
async function load() { loading.value = true; error.value = ''; try { const result = await api.workspace('semi'); rows.value = result.locations ?? []; canManage.value = !!result.permissions.master } catch(e) { rows.value = []; canManage.value = false; error.value = getApiErrorMessage(e) } finally { loading.value = false } }
onMounted(load)
function begin(row?: WarehouseLocation) { draft.value = { factory_id: 'huakang-c', request_id: warehouseRequestId(), id: row?.id ?? '', expected_revision: row?.revision ?? 0, warehouse: row?.warehouse ?? '', code: row?.code ?? '', status: row?.status === 'INACTIVE' ? 'INACTIVE' : 'ACTIVE' }; initial.value = JSON.stringify(draft.value); frozen.value = false }
function canLeave() { return !saving.value && !frozen.value && (!draft.value || JSON.stringify(draft.value) === initial.value || window.confirm('仓位资料尚未保存，确定放弃填写？')) }
function close() { if(canLeave()) draft.value = undefined }
onBeforeRouteLeave(canLeave); onBeforeRouteUpdate(canLeave)
async function save() { if (!draft.value || saving.value) return; saving.value = true; error.value = ''; try { await api.saveLocation(draft.value); draft.value = undefined; frozen.value = false; await load() } catch(e) { const status = (e as { response?: { status?: number } }).response?.status; frozen.value = !status || status === 408 || status >= 500; error.value = frozen.value ? '保存结果待确认，已保留原内容，请重试保存。' : getApiErrorMessage(e) } finally { saving.value = false } }
</script>
<template>
  <div class="semi-locations"><header><div><h2>仓库与仓位</h2><p>先建立正式仓位，再收料或调入。停用后可发出、调走已有库存。</p></div><Button variant="outline" :disabled="loading" @click="load">刷新</Button><Button :disabled="loading || !canManage" @click="begin()">新增仓库 / 仓位</Button></header>
    <p v-if="error" class="fabric-error" role="alert">{{ error }}</p><p v-if="!loading && !rows.length" class="warehouse-empty">尚未建立仓位。新增仓库时填写首个仓位，建档不会增加库存。</p>
    <table v-else><thead><tr><th>仓库</th><th>仓位</th><th>状态</th><th>操作</th></tr></thead><tbody><tr v-for="row in rows" :key="row.id"><td>{{ row.warehouse }}</td><td>{{ row.code }}</td><td>{{ row.status === 'ACTIVE' ? '启用' : '停用' }}</td><td><Button size="sm" variant="outline" :disabled="!canManage" @click="begin(row)">维护状态</Button></td></tr></tbody></table>
    <Teleport to="body"><div v-if="draft" class="semi-location-overlay"><FocusScope as-child loop trapped><form role="dialog" aria-modal="true" aria-label="维护半成品仓位" @submit.prevent="save" @keydown.esc.prevent="close"><h2>{{ draft.id ? '维护仓位' : '新增仓库 / 仓位' }}</h2><fieldset :disabled="saving || frozen"><label>所属仓库<input v-model.trim="draft.warehouse" required maxlength="64" :readonly="!!draft.id" aria-label="所属仓库" placeholder="例如半成品一仓" /></label><label>仓位编码<input v-model.trim="draft.code" required maxlength="64" :readonly="!!draft.id" aria-label="仓位编码" placeholder="例如 A01" /></label><label>状态<select v-model="draft.status" aria-label="仓位状态"><option value="ACTIVE">启用</option><option value="INACTIVE">停用</option></select></label></fieldset><p v-if="error" class="fabric-error" role="alert">{{ error }}</p><footer><Button type="button" variant="outline" :disabled="saving || frozen" @click="close">取消</Button><Button type="submit" :disabled="saving">{{ frozen ? '重试保存' : '保存仓位' }}</Button></footer></form></FocusScope></div></Teleport>
  </div>
</template>
<style scoped>
.semi-locations{padding:24px}header{display:flex;align-items:center;gap:16px;margin-bottom:24px}header>div{flex:1}h2{font-size:18px;font-weight:650}p{font-size:13px;color:var(--muted-foreground);margin-top:6px}table{width:100%;text-align:left;border-collapse:collapse}th,td{padding:14px;border-bottom:1px solid var(--border)}th{background:var(--muted)}.semi-location-overlay{position:fixed;inset:0;z-index:90;background:#0f172a80;display:grid;place-items:center;padding:20px}form{width:min(520px,100%);background:var(--card);padding:24px;border-radius:12px}fieldset{border:0;display:grid;gap:16px;margin:20px 0}label{display:grid;gap:6px;font-size:13px}input,select{border:1px solid var(--border);padding:10px;border-radius:6px}footer{display:flex;justify-content:flex-end;gap:12px}
</style>
