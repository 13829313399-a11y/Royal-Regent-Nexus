<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { identityApi, changeLabels, stateLabels, type ChangeRecord, type ChangePreview, type HandoverItem } from '@/api/identity'
import { http, getApiErrorMessage } from '@/lib/http'
import { createRandomUuid } from '@/lib/randomUuid'
import { formatBusinessDateTime } from '@/lib/dateTime'
import { Button } from '@/components/ui/button'
import IdentityShell from './IdentityShell.vue'
import AccessImpact from './AccessImpact.vue'
const route = useRoute(); const audit = computed(() => route.path.endsWith('/audit'))
const rows = ref<ChangeRecord[]>([]); const events = ref<{ id: string; event_type: string; reason: string; created_at: string; target_user_id: string }[]>([])
const selected = ref<ChangeRecord>(); const preview = ref<ChangePreview>(); const items = ref<HandoverItem[]>([])
const successors = ref<Record<string, string>>({}); const candidates = ref<Record<string, { id: string; display_name: string }[]>>({})
const busy = ref(false); const error = ref(''); const state = ref(''); const reason = ref(''); const page = ref(1); const total = ref(0); const confirmed = ref(false)
const key = ref(createRandomUuid())
let selectionGeneration = 0
async function load() {
  busy.value = true; error.value = ''
  try {
    if (audit.value) events.value = (await http.get<typeof events.value>('/iam/audit-events', { params: { limit: 100 } })).data
    else { const result = await identityApi.changes({ state: state.value, page: page.value, target_user_id: typeof route.query.person === 'string' ? route.query.person : '' }); rows.value = result.items; total.value = result.total }
  } catch (e) { error.value = getApiErrorMessage(e) } finally { busy.value = false }
}
async function select(row: ChangeRecord) {
  const generation = ++selectionGeneration
  selected.value = row; preview.value = undefined; confirmed.value = false; error.value = ''; items.value = []; candidates.value = {}; successors.value = {}
  try {
    const handovers = (await identityApi.handovers(row.id)).items
    const people = await Promise.all(handovers.filter(i => i.status === 'pending').map(async item => [item.id, (await identityApi.handoverCandidates(item.id)).items] as const))
    if (generation !== selectionGeneration) return
    items.value = handovers; candidates.value = Object.fromEntries(people)
  } catch (e) { if (generation === selectionGeneration) error.value = getApiErrorMessage(e) }
}
async function previewSelected() {
  if (!selected.value) return
  busy.value = true; error.value = ''
  try { preview.value = await identityApi.preview(selected.value.id); key.value = createRandomUuid(); confirmed.value = false }
  catch (e) { error.value = getApiErrorMessage(e) } finally { busy.value = false }
}
async function apply() {
  if (!selected.value || !preview.value || !confirmed.value) return
  busy.value = true; error.value = ''
  try { selected.value = await identityApi.commit(selected.value, preview.value, key.value, selected.value.state === 'pending_approval'); preview.value = undefined; await load() }
  catch (e) { error.value = getApiErrorMessage(e) } finally { busy.value = false }
}
async function decide(action: 'cancel' | 'reject') {
  if (!selected.value || !reason.value.trim()) { error.value = '请填写办理原因'; return }
  busy.value = true
  try { selected.value = await identityApi.decide(selected.value, action, reason.value); preview.value = undefined; await load() }
  catch (e) { error.value = getApiErrorMessage(e) } finally { busy.value = false }
}
async function refreshHandover() {
  if (!selected.value) return
  busy.value = true
  try { await identityApi.refreshHandover(selected.value.id); await select(selected.value) }
  catch (e) { error.value = getApiErrorMessage(e) } finally { busy.value = false }
}
async function reassign(item: HandoverItem) {
  if (!successors.value[item.id]) return
  busy.value = true; error.value = ''
  try { await identityApi.reassign(item, successors.value[item.id]!); if (selected.value) await select(selected.value) }
  catch (e) { error.value = getApiErrorMessage(e) } finally { busy.value = false }
}
watch(() => route.fullPath, () => { selectionGeneration++; selected.value = undefined; page.value = 1; void load() })
onMounted(load)
</script>
<template><IdentityShell><div class="iam-panel"><div class="iam-panel-heading"><h2>{{ audit ? '授权与人员变更记录' : '变更办理' }}</h2><Button variant="outline" :disabled="busy" @click="load">刷新</Button></div>
  <p v-if="error" role="alert" class="iam-error">{{ error }}</p><p v-if="busy" role="status" class="iam-notice">正在读取 / 办理…</p>
  <template v-if="audit"><p class="iam-muted">显示最近 100 条可见记录，历史事实保留在审计中。</p><article v-for="event in events" :key="event.id" class="iam-record"><strong>{{ event.event_type }}</strong><p>{{ event.reason }}</p><small>{{ formatBusinessDateTime(event.created_at) }} · {{ event.target_user_id }}</small></article><p v-if="!events.length && !busy && !error" class="iam-empty">当前范围没有审计记录。</p></template>
  <template v-else><label class="iam-filters">办理状态<select v-model="state" @change="page = 1; load()"><option value="">全部</option><option v-for="s in ['draft', 'pending_approval', 'scheduled', 'applied', 'cancelled', 'rejected']" :key="s" :value="s">{{ stateLabels[s] }}</option></select></label>
    <div class="iam-records-layout"><div><button v-for="row in rows" :key="row.id" class="iam-record" :disabled="busy" :aria-pressed="selected?.id === row.id" @click="select(row)"><strong>{{ changeLabels[row.request_type] }}</strong><span class="iam-tag">{{ stateLabels[row.state] }}</span><p>{{ row.reason }}</p><small>{{ formatBusinessDateTime(row.created_at) }} · {{ row.target_user_id }}</small></button><p v-if="!rows.length && !busy && !error" class="iam-empty">当前筛选没有变更单。</p><div class="iam-pagination"><span>{{ total }} 条</span><Button variant="outline" :disabled="page === 1" @click="page--; load()">上一页</Button><Button variant="outline" :disabled="page * 30 >= total" @click="page++; load()">下一页</Button></div></div>
      <section v-if="selected" class="iam-record-detail"><h3>{{ changeLabels[selected.request_type] }} · {{ stateLabels[selected.state] }}</h3><p>{{ selected.reason }}</p><RouterLink :to="`/system/users?person=${selected.target_user_id}`">查看人员与任职</RouterLink><p v-if="selected.effective_at">生效：{{ formatBusinessDateTime(selected.effective_at) }}</p>
        <template v-if="['draft', 'pending_approval'].includes(selected.state)"><Button :disabled="busy" @click="previewSelected">重新核对并预览</Button><AccessImpact v-if="preview" :preview="preview" /><template v-if="preview"><label class="iam-check"><input v-model="confirmed" type="checkbox" />已核对变更影响</label><Button :disabled="busy || !confirmed" @click="apply">{{ selected.state === 'pending_approval' ? '批准办理' : '确认办理' }}</Button></template></template>
        <div v-if="['draft', 'pending_approval', 'scheduled'].includes(selected.state)" class="iam-decision"><label>撤回 / 驳回原因<textarea v-model="reason" rows="2" /></label><Button variant="outline" :disabled="busy" @click="decide('cancel')">撤回变更</Button><Button v-if="selected.state === 'pending_approval'" variant="destructive" :disabled="busy" @click="decide('reject')">驳回</Button></div>
        <h3>工作接管</h3><p v-if="selected.handover_refresh_pending" role="status" class="iam-notice">任职已按服务器时间生效。交接清单仍待后台重新评估，可点击下方按钮刷新。</p><Button v-if="['applied', 'scheduled'].includes(selected.state)" variant="outline" :disabled="busy" @click="refreshHandover">重新评估 / 重试</Button><p class="iam-muted">接管会再次检查单据版本、未完成状态和接管人的实际资格。</p><article v-for="item in items" :key="item.id" class="iam-assignment"><strong>{{ item.resource_id }}</strong><p>{{ item.factory_id }} · {{ stateLabels[item.status] }}</p><template v-if="item.status === 'pending'"><label>接管人<select v-model="successors[item.id]"><option value="">请选择</option><option v-for="person in candidates[item.id]" :key="person.id" :value="person.id">{{ person.display_name }}</option></select></label><Button :disabled="busy || !successors[item.id]" @click="reassign(item)">确认接管</Button></template></article><p v-if="!items.length">暂无已识别的个人交接项，未适配模块仍需人工核实。</p>
      </section><p v-else class="iam-empty">选择一条变更，查看影响和工作交接。</p>
    </div>
  </template>
</div></IdentityShell></template>
