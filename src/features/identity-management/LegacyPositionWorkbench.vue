<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { Search, RefreshCw, ChevronRight, UsersRound, ShieldCheck } from '@lucide/vue'
import { identityApi, type OrganizationCatalog, type Person, type PersonIdentity } from '@/api/identity'
import { positionReviewsApi as api, positionStatus, type BuiltinPackage, type WorkItem } from '@/api/positionReviews'
import { Button } from '@/components/ui/button'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage } from '@/lib/http'
import { formatBusinessDateTime } from '@/lib/dateTime'
import PositionReviewPane from './PositionReviewPane.vue'
import './position-workbench.css'
import { permissionName } from './positionLabels'
const route = useRoute(), router = useRouter(), auth = useAuthStore()
const personDetail = ref<PersonIdentity>()
let personGeneration = 0
const catalog = ref<OrganizationCatalog>(), items = ref<WorkItem[]>([]), people = ref<Person[]>([]), packages = ref<BuiltinPackage[]>([])
const q = ref(''), org = ref(''), kind = ref(''), page = ref(1), total = ref(0), actionable = ref(0), loading = ref(false), error = ref(''), locked = ref(false)
const tab = computed(() => route.query.person ? 'people' : ['people', 'packages', 'history'].includes(String(route.query.tab)) ? String(route.query.tab) : 'pending')
const selected = computed(() => typeof route.query.item === 'string' && /^(position|registration):[^/]+$/.test(route.query.item) ? route.query.item : '')
const rows = ref<HTMLElement>(), mobileDetail = ref(!!selected.value), routingAttention = ref(false)
let generation = 0
const viewer = computed(() => `${auth.currentUser?.id ?? ''}:${auth.authorizationVersion}:${auth.currentUser?.identity?.employment_epoch ?? ''}:${auth.currentUser?.identity?.effective_context_key ?? ''}`)
const orgName = (id: string) => catalog.value?.organizations.find(o => o.id === id)?.name || id
async function load() {
  const current = ++generation, identity = viewer.value
  loading.value = true; error.value = ''
  try {
    if (!catalog.value) catalog.value = await api.catalog()
    if (tab.value === 'people') {
      const data = await identityApi.people({ q: q.value, org_unit_id: org.value, page: page.value })
      if (current !== generation || identity !== viewer.value) return
      people.value = data.items; total.value = data.total
    } else if (tab.value === 'packages') {
      const data = await api.packages()
      if (current !== generation || identity !== viewer.value) return
      packages.value = data.items
    } else {
      const data = await api.queue({ q: q.value, org_unit_id: org.value, kind: kind.value, page: page.value, status: tab.value === 'history' ? 'history' : 'pending' })
      if (current !== generation || identity !== viewer.value) return
      items.value = data.items; total.value = data.total; actionable.value = data.actionable_total; routingAttention.value = data.routing_attention
      if (!selected.value && items.value[0] && window.innerWidth >= 1100) await choose(items.value[0].item_key, false)
    }
  } catch (e) {
    if (current !== generation || identity !== viewer.value) return
    error.value = getApiErrorMessage(e)
    if ([401, 403].includes((e as { response?: { status?: number } }).response?.status ?? 0)) { items.value = []; people.value = []; packages.value = []; total.value = 0 }
  } finally { if (current === generation) loading.value = false }
}
async function choose(key: string, mobile = true) {
  if (locked.value) return
  mobileDetail.value = mobile
  await router.replace({ query: { ...route.query, item: key, person: undefined, request_id: undefined } })
}
async function changeTab(value: string) {
  if (locked.value) return
  page.value = 1; mobileDetail.value = false
  await router.replace({ query: { tab: value } })
}
async function adjust(person: Person) {
  if (locked.value) return
  error.value = ''
  try {
    const result = await api.adjust(person.id, { org_unit_id: person.primary_org_unit_id || person.primary_factory_id,
      department_code: person.primary_department, position: person.position || '待核对岗位' })
    await choose(result.item_key)
  } catch (e) { error.value = getApiErrorMessage(e) }
}
async function readPerson(id: string) {
  const current = ++personGeneration, actor = viewer.value
  personDetail.value = undefined
  try { const detail = await identityApi.person(id); if (current === personGeneration && actor === viewer.value) personDetail.value = detail }
  catch (e) { if (current === personGeneration && actor === viewer.value) error.value = getApiErrorMessage(e) }
}
async function selectPerson(person: Person) {
  if (locked.value) return
  mobileDetail.value = true
  await router.replace({ query: { tab: 'people', person: person.id } })
}
async function back() {
  mobileDetail.value = false; await nextTick()
  rows.value?.querySelector<HTMLElement>('[aria-current="true"]')?.focus()
}
async function next() { await load(); const item = items.value.find(i => i.item_key !== selected.value); if (item) await choose(item.item_key); else await router.replace({ query: { ...route.query, item: undefined } }) }
async function start() {
  if (typeof route.query.request_id === 'string') await choose(`registration:${route.query.request_id}`)
  await load()
}
watch(() => route.query.person, id => { if (typeof id === 'string') void readPerson(id); else { ++personGeneration; personDetail.value = undefined } }, { immediate: true })
watch(tab, () => { void load() })
watch(viewer, () => { ++generation; ++personGeneration; personDetail.value = undefined; items.value = []; people.value = []; packages.value = []; catalog.value = undefined; total.value = 0; actionable.value = 0; if (!locked.value) void router.replace({ query: { tab: tab.value } }); void load() })
const beforeUnload = (event: BeforeUnloadEvent) => { if (locked.value) { event.preventDefault(); event.returnValue = '' } }
onBeforeRouteLeave(() => !locked.value)
onBeforeRouteUpdate(to => !locked.value || to.fullPath === route.fullPath)
onMounted(() => { window.addEventListener('beforeunload', beforeUnload); void start() })
onBeforeUnmount(() => { ++generation; window.removeEventListener('beforeunload', beforeUnload) })
</script>
<template>
  <section class="pw-root">
    <header class="pw-heading"><div><h1>人员与权限</h1><p>岗位变化看得清，权限分配一次办好。</p></div><details class="pw-more"><summary>更多管理<ChevronRight :size="16" /></summary><nav><RouterLink to="/system/users/advanced">任职、预约与工作交接</RouterLink><RouterLink to="/system/iam/requests">原任职变更单</RouterLink><RouterLink to="/system/iam/roles">完整角色与系统管理</RouterLink><RouterLink to="/system/iam/audit">完整授权审计</RouterLink><RouterLink to="/system/users/registration?tab=password-reset">密码重置与旧账号入口</RouterLink></nav></details></header>
    <nav class="pw-tabs" aria-label="人员与权限视图"><button v-for="t in [{ id: 'pending', label: '待分配' }, { id: 'people', label: '全部人员' }, { id: 'packages', label: '内置权限' }, { id: 'history', label: '办理记录' }]" :key="t.id" :aria-current="tab === t.id ? 'page' : undefined" :disabled="locked" @click="changeTab(t.id)">{{ t.label }}<span v-if="t.id === 'pending' && actionable">{{ actionable }}</span></button></nav>
    <form v-if="tab !== 'packages'" class="pw-toolbar" @submit.prevent="page = 1; load()"><label class="pw-search"><Search :size="16" /><span class="sr-only">搜索姓名或账号</span><input v-model="q" type="search" placeholder="搜索姓名或账号" :disabled="locked"></label><label><span class="sr-only">组织筛选</span><select v-model="org" :disabled="locked" @change="page = 1; load()"><option value="">全部组织</option><option v-for="o in catalog?.organizations.filter(o => o.kind !== 'group' && o.status === 'active')" :key="o.id" :value="o.id">{{ o.name }}</option></select></label><label v-if="tab !== 'people'"><span class="sr-only">任务类型</span><select v-model="kind" :disabled="locked" @change="page = 1; load()"><option value="">全部任务</option><option value="registration">新员工注册</option><option value="position">岗位更新</option></select></label><Button type="submit" variant="outline" :disabled="locked || loading">搜索</Button><Button variant="ghost" :disabled="locked || loading" aria-label="刷新待办" @click="load"><RefreshCw :size="17" /></Button><small><ShieldCheck :size="15" />仅显示管理范围内的人员</small></form>
    <p v-if="error" class="pw-error" role="alert">{{ error }}<Button variant="outline" @click="load">重试</Button></p>
    <p v-if="routingAttention" class="pw-notice" role="status">部分申请的通知尚未找到具备完整办理范围的管理员。申请仍在队列中，请核实管理范围和转授权。</p>
    <div v-if="tab === 'packages'" class="pw-catalog"><article v-for="p in packages" :key="p.role_id"><h2>{{ p.name }}</h2><p>{{ p.description }}</p><details><summary>{{ p.capability_summary.length }} 项能力</summary><ul><li v-for="c in p.capability_summary" :key="c">{{ permissionName(c) }}</li></ul></details><small>选择办理对象后核对可分配范围</small></article></div>
    <div v-else class="pw-workspace" :class="{ 'has-detail': mobileDetail && (selected || personDetail) }">
      <aside ref="rows" class="pw-queue" aria-label="办理队列"><div class="pw-queue-heading"><span>{{ tab === 'people' ? '全部人员' : tab === 'history' ? '办理记录' : '待办队列' }} · {{ total }}</span><small>{{ tab === 'pending' ? '较早提交优先' : '' }}</small></div><p v-if="loading" class="pw-empty" role="status">正在读取…</p><template v-else-if="tab === 'people'"><button v-for="person in people" :key="person.id" class="pw-queue-row" :disabled="locked" :aria-current="selected && items.find(i => i.item_key === selected)?.user.id === person.id ? 'true' : undefined" @click="selectPerson(person)"><div class="pw-inline"><span class="pw-avatar">{{ person.display_name.slice(0, 1) }}</span><div><strong>{{ person.display_name }}</strong><small>{{ person.username }}</small></div><ChevronRight :size="16" /></div><p>{{ person.position || '岗位待核对' }}</p><small>{{ orgName(person.primary_org_unit_id || person.primary_factory_id) }}</small></button></template><template v-else><button v-for="item in items" :key="item.item_key" class="pw-queue-row" :aria-current="selected === item.item_key ? 'true' : undefined" :disabled="locked" @click="choose(item.item_key)"><div class="pw-inline"><span class="pw-avatar">{{ item.user.display_name.slice(0, 1) }}</span><div><strong>{{ item.user.display_name }}</strong><small>{{ item.user.username }}</small></div><ChevronRight :size="16" /></div><p>{{ item.before?.position || '申请开通' }} → {{ item.declaration.position }}</p><div class="pw-inline"><span class="pw-badge" :class="{ 'is-registration': item.kind === 'registration' }">{{ item.kind === 'registration' ? '新员工注册' : item.origin === 'admin' ? '管理员核对' : '岗位更新' }}</span><small>{{ positionStatus[item.status] }}</small></div><small>{{ orgName(item.declaration.org_unit_id) }} · {{ formatBusinessDateTime(item.created_at) }}</small></button></template><div v-if="!loading && !total" class="pw-empty"><UsersRound :size="30" /><h2>{{ q || org || kind ? '没有匹配的人员' : '当前没有待办' }}</h2><p>{{ q || org || kind ? '试试调整搜索词和筛选条件。' : '新注册和员工岗位更新会出现在这里。' }}</p></div><footer v-if="total > 30" class="pw-pagination"><Button variant="ghost" :disabled="page <= 1 || locked" @click="page--; load()">上一页</Button><span>{{ page }} / {{ Math.ceil(total / 30) }}</span><Button variant="ghost" :disabled="page * 30 >= total || locked" @click="page++; load()">下一页</Button></footer></aside>
      <section v-if="personDetail && !selected" class="pw-pane"><h2>{{ personDetail.display_name }}</h2><p>{{ personDetail.position }} · 只读资料</p><Button @click="adjust({ ...personDetail, username: '', primary_org_unit_id: personDetail.primary_assignment?.org_unit_id || personDetail.primary_factory_id })">发起岗位 / 权限调整</Button></section><PositionReviewPane v-else-if="selected" :item-key="selected" :catalog="catalog" @saved="load" @next="next" @back="back" @locked="locked = $event" /><div v-else class="pw-empty pw-welcome"><ShieldCheck :size="40" /><h2>核对岗位，确认权限</h2><p>从左侧选择一位人员，岗位对照、权限方案和影响将在同一处展开。</p></div>
    </div>
  </section>
</template>
