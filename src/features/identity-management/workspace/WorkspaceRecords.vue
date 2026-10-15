<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { iamWorkspaceApi } from '@/api/iamWorkspace'
import { getApiErrorMessage } from '@/lib/http'
import { formatBusinessDateTime } from '@/lib/dateTime'
import { Button } from '@/components/ui/button'
import IamLeaveGuard from '@/components/iam/workspace/IamLeaveGuard.vue'
import PositionReviewPane from '../PositionReviewPane.vue'
import PasswordResetPanel from './PasswordResetPanel.vue'
import IdentityRecords from '../IdentityRecords.vue'
import AuditTimeline from '../AuditTimeline.vue'
import { identityApi, type OrganizationCatalog } from '@/api/identity'
import { taskLabels, taskStateLabels, taskStatusText, workspaceCapabilities, type WorkspaceTask } from './contracts'
import '../position-workbench.css'
import './workspace.css'
const route = useRoute(), router = useRouter(), auth = useAuthStore()
const caps = computed(() => workspaceCapabilities(p => auth.can(p)))
const source = computed(() => String(route.query.source || options.value[0]?.id || ''))
const options = computed(() => [
  ...(caps.value.people && caps.value.exceptions ? [{ id: 'position', name: '岗位与注册办理' }, { id: 'registration', name: '注册申请' }] : []),
  ...(caps.value.people ? [{ id: 'password-reset', name: '密码找回' }, { id: 'identity-change', name: '高级任职' }] : []),
  ...(caps.value.audit ? [{ id: 'audit', name: '权限操作审计' }] : []),
])
const localSelected = ref('')
const selected = computed(() => localSelected.value || String(route.query.task || '')), person = computed(() => String(route.query.person || ''))
const allowed = computed(() => options.value.some(o => o.id === source.value) && !route.query.route_error)
const page = computed(() => Math.max(1, Number(route.query.page) || 1))
const rows = ref<WorkspaceTask[]>([]), total = ref<number | null>(null), partial = ref(false), loading = ref(false), error = ref('')
const q = ref(''), state = ref(String(route.query.state || '')), from = ref(String(route.query.from_at || '')), to = ref(String(route.query.to_at || ''))
const catalog = ref<OrganizationCatalog>(), locked = ref(false), mobileDetail = ref(!!selected.value)
const dirty = ref(false), leaveGuard = ref<InstanceType<typeof IamLeaveGuard>>()
async function permitLeave() { const allowed = !locked.value && ((await leaveGuard.value?.permitLeave()) ?? !dirty.value); if (allowed) dirty.value = false; return allowed }
onBeforeRouteLeave(permitLeave); onBeforeRouteUpdate(permitLeave)
const beforeUnload = (event: BeforeUnloadEvent) => { if (locked.value || dirty.value) { event.preventDefault(); event.returnValue = '' } }
onMounted(() => window.addEventListener('beforeunload', beforeUnload))
onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload))
const viewer = computed(() => `${auth.currentUser?.id}:${auth.authorizationVersion}:${auth.currentUser?.identity?.employment_epoch}:${auth.currentUser?.identity?.effective_context_key}`)
let generation = 0
async function load() {
  const current = ++generation, actor = viewer.value
  rows.value = []; total.value = null; error.value = ''; loading.value = true
  try {
    if (!allowed.value || source.value === 'audit') return
    if (from.value && to.value && from.value > to.value) throw new Error('开始时间不能晚于结束时间')
    const data = await iamWorkspaceApi.tasks({ kind: source.value === 'position' ? 'position-registration' : source.value,
      target_user_id: person.value, state: state.value, q: q.value, page: page.value, page_size: 30,
      ...(from.value ? { from_at: new Date(from.value).toISOString() } : {}), ...(to.value ? { to_at: new Date(to.value).toISOString() } : {}) })
    if (current !== generation || actor !== viewer.value) return
    rows.value = data.items; total.value = data.visible_total; partial.value = data.partial
    if (caps.value.people && !catalog.value) {
      const organization = await identityApi.catalog()
      if (current === generation && actor === viewer.value) catalog.value = organization
    }
  } catch (e) { if (current === generation && actor === viewer.value) error.value = getApiErrorMessage(e) }
  finally { if (current === generation) loading.value = false }
}
async function filter(next = 1) {
  if (!(await permitLeave())) return
  localSelected.value = ''
  await router.replace({ query: { source: source.value, ...(person.value ? { person: person.value } : {}), state: state.value,
    ...(from.value ? { from_at: from.value } : {}), ...(to.value ? { to_at: to.value } : {}), page: next } }); void load()
}
async function choose(task: string) { if (person.value) { if (!(await permitLeave())) return; localSelected.value = task } else await router.replace({ query: { ...route.query, task } }); mobileDetail.value = true }
watch([source, person], () => { localSelected.value = '' })
watch([source, page, person, viewer], () => { catalog.value = undefined; void load() }, { immediate: true })
watch(viewer, () => { q.value = ''; error.value = '' }, { flush: 'sync' })
onBeforeUnmount(() => { ++generation })
</script>
<template>
  <section class="pw-root iw-root iw-records" :class="{ 'iw-mobile-detail': mobileDetail && selected }">
    <header class="iw-page-heading"><div><h1>操作记录</h1><p>按来源查询处理结果；数量仅对应当前来源和筛选</p></div></header>
    <nav class="iw-view-switch" aria-label="记录来源"><RouterLink v-for="o in options" :key="o.id" :aria-current="source === o.id ? 'page' : undefined" :to="{ query: { source: o.id, ...(person ? { person } : {}) } }">{{ o.name }}</RouterLink></nav>
    <p v-if="!allowed" class="pw-error" role="alert">当前链接无效或没有此来源的查看权限，请选择获授权的记录来源。</p>
    <AuditTimeline v-else-if="source === 'audit'" :key="`${person}:${viewer}`" :target-user-id="person" />
    <template v-else>
      <form class="iw-toolbar" @submit.prevent="filter()"><input v-model="q" aria-label="搜索记录中的姓名或账号" placeholder="搜索姓名或账号"><select v-model="state" aria-label="记录状态"><option value="">全部状态</option><option v-for="(label,key) in taskStateLabels" :key="key" :value="key">{{ label }}</option></select><label>从<input v-model="from" type="datetime-local"></label><label>至<input v-model="to" type="datetime-local"></label><Button variant="outline" type="submit" :disabled="loading || locked">查询</Button><span v-if="person">仅此人员的记录</span></form>
      <p v-if="error" class="pw-error" role="alert">{{ error }}<Button variant="outline" @click="load">重试</Button></p><p v-if="partial" class="pw-notice">当前来源读取不完整，统计暂不可用。</p>
      <div class="iw-workspace" :class="{ 'has-detail': mobileDetail && selected }">
        <aside class="iw-list" aria-label="操作记录列表"><header><strong>{{ options.find(o => o.id === source)?.name }}</strong><small>{{ total === null ? '统计暂不可用' : `${total} 条` }}</small></header><div class="iw-list-scroll"><p v-if="loading" role="status" class="pw-empty">正在读取…</p><button v-for="row in rows" :key="row.key" class="iw-row" :aria-pressed="selected === row.key" :disabled="locked" @click="choose(row.key)"><span><strong>{{ row.subject.display_name }}</strong><small>{{ taskLabels[row.kind] }}</small></span><span><strong>{{ row.proposed_position }}</strong><small>{{ taskStatusText(row) }}</small></span><span>{{ formatBusinessDateTime(row.created_at) }}</span></button><p v-if="!loading && !rows.length && !error" class="pw-empty">当前筛选没有记录。</p></div><footer class="iw-pagination"><span>第 {{ page }} 页</span><Button variant="ghost" :disabled="loading || locked || page <= 1" @click="filter(page - 1)">上一页</Button><Button variant="ghost" :disabled="loading || locked || (total !== null ? page * 30 >= total : rows.length < 30)" @click="filter(page + 1)">下一页</Button></footer></aside>
        <PositionReviewPane v-if="selected.startsWith('position:') || selected.startsWith('registration:')" :item-key="selected" :catalog="catalog" compact @dirty="dirty = $event" @locked="locked = $event" @back="mobileDetail = false" @saved="load" />
        <PasswordResetPanel v-else-if="selected.startsWith('password-reset:')" :request-id="selected.slice(15)" readonly @back="mobileDetail = false" />
        <IdentityRecords v-else-if="selected.startsWith('identity-change:')" :request-id="selected.slice(16)" embedded mode="changes" @locked="locked = $event" @dirty="dirty = $event" @back="mobileDetail = false" />
        <div v-else class="pw-empty iw-welcome">选择一条记录查看结果与依据</div>
      </div>
    </template>
    <IamLeaveGuard ref="leaveGuard" :dirty="dirty" :busy="locked" />
  </section>
</template>
