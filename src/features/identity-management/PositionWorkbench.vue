<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { isNavigationFailure, NavigationFailureType, onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { ArrowRight, BriefcaseBusiness, ChevronLeft, ChevronRight, ClipboardList, KeyRound, ListChecks, Search, RefreshCw, ShieldCheck, SlidersHorizontal, UserRoundPlus, UsersRound } from '@lucide/vue'
import { identityApi, type OrganizationCatalog, type OrgDepartmentCount, type Person } from '@/api/identity'
import { iamApi, type RoleSummary } from '@/api/iam'
import { positionReviewsApi, type ReviewResult } from '@/api/positionReviews'
import type { StudioResult } from '@/api/accessStudio'
import { iamWorkspaceApi } from '@/api/iamWorkspace'
import { Button } from '@/components/ui/button'
import IamLeaveGuard from '@/components/iam/workspace/IamLeaveGuard.vue'
import { personStatusPresentation } from '@/components/iam/workspace/iam-status'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage } from '@/lib/http'
import { formatBusinessDateTime } from '@/lib/dateTime'
import PositionReviewPane from './PositionReviewPane.vue'
import PersonContext from './workspace/PersonContext.vue'
import PasswordResetPanel from './workspace/PasswordResetPanel.vue'
import IdentityRecords from './IdentityRecords.vue'
import { departmentName, lastLoginLabel } from './positionLabels'
import { taskLabels, taskStateLabels, taskStatusText, workspaceCapabilities, personOrg, type WorkspaceTask, type SourceCoverage, type PersonPanel } from './workspace/contracts'
import { iamStudioEnabled } from '@/components/iam/workspace/iam-navigation'
import StudioPeople from './studio/StudioPeople.vue'
import StudioPerson from './studio/StudioPerson.vue'
import type { TaskKind } from './workspace/contracts'
import './studio/workspace.css'
import './position-workbench.css'
import './workspace/workspace.css'
import './workspace/permission-studio.css'
import './studio/inbox.css'
const route = useRoute(), router = useRouter(), auth = useAuthStore()
const catalog = ref<OrganizationCatalog>(), tasks = ref<WorkspaceTask[]>([]), people = ref<Person[]>([]), coverage = ref<SourceCoverage[]>([])
const directoryCatalog = ref<OrganizationCatalog>(), catalogError = ref(''), directoryError = ref('')
const orgCounts = ref<OrgDepartmentCount[]>()
const personMode = ref(String(route.query.identity_mode || '')), personStatus = ref(String(route.query.status || '')), roleFilter = ref(String(route.query.role_id || ''))
const roles = ref<RoleSummary[]>([]), roleError = ref(''), roleLoading = ref(false)
const q = ref(''), loading = ref(false), error = ref(''), notice = ref(''), locked = ref(false), dirty = ref(false)
const total = ref<number | null>(0), actionable = ref<number | null>(0), partial = ref(false)
const caps = computed(() => workspaceCapabilities(p => auth.can(p)))
const view = computed(() => route.query.view === 'people' || route.query.person || route.query.tab === 'people' ? 'people' : 'todo')
const selected = computed(() => typeof (route.query.task || route.query.item) === 'string' ? String(route.query.task || route.query.item) : '')
const personId = computed(() => typeof route.query.person === 'string' ? route.query.person : '')
const panel = computed(() => (['profile', 'exceptions', 'account', 'advanced', 'manage'].includes(String(route.query.panel)) ? route.query.panel : 'profile') as PersonPanel)
const tab = computed(() => ['packages', 'effective', 'timeline'].includes(String(route.query.tab)) ? String(route.query.tab) : 'packages')
const department = ref(String(route.query.department || '')), packageFilter = ref(String(route.query.has_packages || ''))
const counts = ref<Partial<Record<TaskKind, number | null>>>({})
const buckets = [
  { key: 'registration', name: '新员工注册待开通', help: '核验资料 · 配包开通', icon: UserRoundPlus },
  { key: 'position', name: '岗位与权限调整', help: '对照现职 · 审核变更', icon: BriefcaseBusiness },
  { key: 'password-reset', name: '密码找回核验', help: '核实身份 · 开放本人改密', icon: KeyRound },
  { key: 'identity-change', name: '任职变更与复核', help: '核对任职 · 办理审批', icon: ShieldCheck },
] as const
const inbox = computed(() => iamStudioEnabled && view.value === 'todo')
const inboxFiltersOpen = ref(false)
const page = computed(() => Math.max(1, Math.min(100000, Number(route.query.page) || 1)))
const org = ref(String(route.query.org || '')), kind = ref(String(route.query.kind || '')), state = ref(String(route.query.state || 'open'))
const rows = ref<HTMLElement>(), searchInput = ref<HTMLInputElement>(), mobileDetail = ref(!!selected.value || !!personId.value)
const leave = ref<InstanceType<typeof IamLeaveGuard>>()
let generation = 0
const viewer = computed(() => `${auth.currentUser?.id ?? ''}:${auth.authorizationVersion}:${auth.currentUser?.identity?.employment_epoch ?? ''}:${auth.currentUser?.identity?.effective_context_key ?? ''}`)
const orgName = (id: string) => catalog.value?.organizations.find(o => o.id === id)?.name || id || '未登记'
const routeError = computed(() => route.query.route_error ? '链接包含无效或冲突的办理目标，请从列表重新选择。' : '')
const taskKind = computed(() => selected.value.split(':')[0] || '')
const filtersActive = computed(() => !!(q.value.trim() || org.value || department.value || packageFilter.value || personMode.value || personStatus.value || roleFilter.value || (view.value === 'todo' && (kind.value || state.value !== 'open'))))
const hasVisibleRecords = computed(() => view.value === 'people' ? people.value.length > 0 : tasks.value.length > 0)
async function load() {
  const current = ++generation, identity = viewer.value
  loading.value = true; error.value = ''; tasks.value = []; people.value = []; orgCounts.value = undefined; total.value = null; actionable.value = null; counts.value = {}; coverage.value = []; partial.value = false
  try {
    if (routeError.value) return
    if (!catalog.value) {
      try {
        const data = caps.value.people ? await identityApi.catalog() : await positionReviewsApi.catalog()
        if (current !== generation || identity !== viewer.value) return
        catalog.value = data; catalogError.value = ''
      } catch (e) {
        if (current !== generation || identity !== viewer.value) return
        if (!iamStudioEnabled) throw e
        catalogError.value = getApiErrorMessage(e)
      }
    }
    if (view.value === 'people') {
      coverage.value = []
      if (!caps.value.people) return
      if (iamStudioEnabled && !directoryCatalog.value) {
        try {
          const data = await identityApi.personnelCatalog()
          if (current !== generation || identity !== viewer.value) return
          directoryCatalog.value = data; directoryError.value = ''
        } catch (e) {
          if (current !== generation || identity !== viewer.value) return
          directoryError.value = getApiErrorMessage(e)
        }
      }
      const data = await identityApi.people({ ...(iamStudioEnabled ? {include: 'access_summary', include_org_counts: 'true', department: department.value, has_packages: packageFilter.value, identity_mode: personMode.value, status: personStatus.value, role_id: roleFilter.value} : {}), q: q.value, org_unit_id: org.value, page: page.value, page_size: 30 })
      if (current !== generation || identity !== viewer.value) return
      people.value = data.items; total.value = data.total
      orgCounts.value = data.org_counts
    } else {
      if (!caps.value.people && !caps.value.exceptions) return
      const data = await iamWorkspaceApi.tasks({ ...(iamStudioEnabled ? { include_bucket_counts: 'true' } : {}), q: q.value, org_unit_id: org.value, kind: kind.value, state: state.value === 'all' ? '' : state.value, page: page.value, page_size: 30 })
      if (current !== generation || identity !== viewer.value) return
      counts.value = data.bucket_counts || {}; tasks.value = data.items; total.value = data.visible_total; actionable.value = data.actionable_total; coverage.value = data.coverage; partial.value = data.partial
      if (inbox.value && !selected.value && data.items[0] && window.matchMedia?.('(min-width: 901px)').matches) {
        await choose(data.items[0].key, false)
      }
    }
  } catch (e) {
    if (current !== generation || identity !== viewer.value) return
    error.value = getApiErrorMessage(e); tasks.value = []; people.value = []; coverage.value = []
  } finally { if (current === generation) loading.value = false }
}
function started(task: string, reused: boolean) {
  notice.value = reused ? '已打开此人的现有岗位待办。' : '岗位待办已创建。离开编辑不会撤销这条待办。'
  void choose(task)
}
async function choose(task: string, openOnMobile = true) {
  if (locked.value) return
  const ok = await router.replace({ query: { ...route.query, view: iamStudioEnabled ? 'inbox' : 'todo', tab: undefined, task, person: undefined, panel: undefined, item: undefined, request_id: undefined, route_error: undefined } })
  if (!ok || isNavigationFailure(ok, NavigationFailureType.duplicated)) mobileDetail.value = openOnMobile
}
async function selectPerson(person: Person, targetPanel: PersonPanel = 'profile') {
  if (locked.value) return
  const ok = await router.replace({ query: { ...route.query, view: 'people', person: person.id, panel: targetPanel, tab: undefined, task: undefined, item: undefined } })
  if (!ok) mobileDetail.value = true
}
async function closePerson() {
  if (locked.value) return
  const res = await router.replace({query: {...route.query, person: undefined, panel: undefined, tab: undefined}})
  if (!res) mobileDetail.value = false
}
async function readRoleFilter(event: Event) {
  if (!(event.target as HTMLDetailsElement).open || !caps.value.catalog || !caps.value.exceptions || roles.value.length || roleLoading.value) return
  const actor = viewer.value
  roleLoading.value = true; roleError.value = ''
  try {
    const items = await iamApi.listRoles()
    if (viewer.value === actor) roles.value = items
  } catch (e) { if (viewer.value === actor) roleError.value = getApiErrorMessage(e) }
  finally { if (viewer.value === actor) roleLoading.value = false }
}
function filterOrg(id: string, dept: string) {
  org.value = id; department.value = dept; void filter()
}
function bucket(key: TaskKind) { kind.value = kind.value === key ? '' : key; void filter() }
async function changeView(value: string) {
  if (locked.value) return
  await router.replace({ query: { view: value, org: org.value || undefined } }); mobileDetail.value = false
}
async function filter(nextPage = 1) {
  if (locked.value) return
  const previousGeneration = generation
  const result = await router.replace({ query: { ...route.query, page: nextPage > 1 ? String(nextPage) : undefined,
    ...(inbox.value ? { task: undefined, item: undefined } : {}),
    role_id: view.value === 'people' ? roleFilter.value || undefined : undefined,
    identity_mode: view.value === 'people' ? personMode.value || undefined : undefined, status: view.value === 'people' ? personStatus.value || undefined : undefined,
    department: view.value === 'people' ? department.value || undefined : undefined, has_packages: view.value === 'people' ? packageFilter.value || undefined : undefined,
    org: org.value || undefined, kind: view.value === 'todo' ? kind.value || undefined : undefined, state: view.value === 'todo' ? state.value : undefined } })
  if (previousGeneration === generation && (!result || isNavigationFailure(result, NavigationFailureType.duplicated))) await load()
  if (inbox.value && isNavigationFailure(result, NavigationFailureType.aborted)) kind.value = String(route.query.kind || '')
  return result
}
async function resetFilters() {
  if (locked.value || loading.value) return
  const previous = { q: q.value, org: org.value, kind: kind.value, state: state.value, department: department.value, packages: packageFilter.value, mode: personMode.value, role: roleFilter.value, status: personStatus.value }
  const previousPath = route.fullPath, previousViewer = viewer.value
  q.value = ''; org.value = ''; kind.value = ''; state.value = 'open'; department.value = ''; packageFilter.value = ''; personMode.value = ''; personStatus.value = ''; roleFilter.value = ''
  const result = await filter()
  if (isNavigationFailure(result, NavigationFailureType.aborted) && route.fullPath === previousPath && viewer.value === previousViewer) {
    q.value = previous.q; org.value = previous.org; kind.value = previous.kind; state.value = previous.state; department.value = previous.department; packageFilter.value = previous.packages; personMode.value = previous.mode; roleFilter.value = previous.role; personStatus.value = previous.status
  }
}
async function openFirstRecord() {
  if (locked.value || loading.value) return
  if (view.value === 'people') {
    const person = people.value[0]
    if (person) await selectPerson(person)
  } else {
    const task = tasks.value[0]
    if (task) await choose(task.key)
  }
}
async function back() {
  if (locked.value) return
  mobileDetail.value = false; await nextTick(); rows.value?.querySelector<HTMLElement>('[aria-pressed="true"]')?.focus()
}
async function next() {
  await load()
  const item = tasks.value.find(i => i.key !== selected.value && i.state === 'actionable')
  if (item) await choose(item.key)
  else { await router.replace({ query: { ...route.query, task: undefined } }); mobileDetail.value = false }
}
async function completed(message: string) {
  dirty.value = false
  const handled = selected.value, path = route.fullPath, actor = viewer.value
  if (!inbox.value || !handled) { await load(); return }
  notice.value = message
  await load()
  const stillHere = () => route.fullPath === path && selected.value === handled && viewer.value === actor && !locked.value && !dirty.value
  await nextTick()
  if (!stillHere() || error.value) return
  let nextItem = tasks.value.find(item => item.key !== handled && item.state === 'actionable')
  if (!nextItem && (page.value > 1 || (total.value ?? 0) > tasks.value.length) && ['open', 'actionable', 'all', ''].includes(state.value)) {
    try {
      const result = await iamWorkspaceApi.tasks({q: q.value, org_unit_id: org.value, kind: kind.value,
        state: 'actionable', page: 1, page_size: 2})
      if (!stillHere()) return
      nextItem = result.items.find(item => item.key !== handled)
    } catch (e) {
      if (stillHere()) error.value = '下一项暂不可用。' + getApiErrorMessage(e)
      return
    }
  }
  if (nextItem) await choose(nextItem.key)
  else if (!partial.value) notice.value += ' 当前筛选下没有下一项可办理事项。'
}
function reviewCompleted(receipt: ReviewResult | StudioResult) {
  if (receipt?.status !== 'committed' || ('item_key' in receipt && receipt.item_key !== selected.value)) return
  return completed(receipt.message || '办理结果已保存。')
}
async function permitLeave() { const allowed = !locked.value && ((await leave.value?.permitLeave()) ?? !dirty.value); if (allowed) dirty.value = false; return allowed }
onBeforeRouteLeave(permitLeave)
onBeforeRouteUpdate((to, from) => {
  if (iamStudioEnabled && from.query.person && from.query.person === to.query.person && from.query.panel === to.query.panel && from.query.tab === to.query.tab) return !locked.value
  return permitLeave()
})
watch(personId, async (current, previous) => {
  if (!iamStudioEnabled || current || !previous) return
  await nextTick()
  const opener = Array.from(document.querySelectorAll<HTMLButtonElement>('[data-iam-person]')).find(b => b.dataset.iamPerson === previous)
  const target = opener || searchInput.value
  target?.focus({preventScroll:true})
})
const beforeUnload = (event: BeforeUnloadEvent) => { if (locked.value || dirty.value) { event.preventDefault(); event.returnValue = '' } }
const shortcut = (event: KeyboardEvent) => {
  if (event.key === '/' && !event.ctrlKey && !event.metaKey && !event.altKey && !locked.value &&
      !(event.target instanceof HTMLElement && event.target.closest('input,textarea,select,[contenteditable="true"],[role="dialog"]'))) {
    event.preventDefault()
    if (inbox.value) inboxFiltersOpen.value = true
    void nextTick(() => searchInput.value?.focus())
  }
}
watch([view, page, () => route.query.org, () => route.query.kind, () => route.query.state, () => route.query.department, () => route.query.has_packages, () => route.query.identity_mode, () => route.query.role_id, () => route.query.status], () => {
  personMode.value = String(route.query.identity_mode || ''); roleFilter.value = String(route.query.role_id || ''); personStatus.value = String(route.query.status || '')
  department.value = String(route.query.department || ''); packageFilter.value = String(route.query.has_packages || '')
  org.value = String(route.query.org || ''); kind.value = String(route.query.kind || ''); state.value = String(route.query.state || 'open'); void load()
})
watch(viewer, () => { ++generation; tasks.value = []; people.value = []; coverage.value = []; catalog.value = undefined; directoryCatalog.value = undefined; directoryError.value = ''; catalogError.value = ''; roleError.value = ''; roleLoading.value = false; roles.value = []; total.value = null; actionable.value = null; q.value = ''; error.value = ''; void load() }, { flush: 'sync' })
onMounted(() => { window.addEventListener('beforeunload', beforeUnload); window.addEventListener('keydown', shortcut); void load() })
onBeforeUnmount(() => { ++generation; window.removeEventListener('beforeunload', beforeUnload); window.removeEventListener('keydown', shortcut) })
</script>
<template>
  <section class="pw-root iw-root iw-permission-page" :class="{ 'iam2-workbench': iamStudioEnabled, 'iam2-inbox': inbox, 'iw-mobile-detail': mobileDetail && (selected || personId) }" data-yl-help="identity-management.overview">
    <header v-if="iamStudioEnabled" class="iw-page-heading iam2-heading">
      <div class="iw-heading-copy"><h1>{{ view === 'people' ? '人员全景' : '办理大厅' }}</h1><p>{{ view === 'people' ? '按组织查看人员、任职与有效权限' : '查看待办事项，核验申请资料与权限影响。' }}</p></div>
      <Button v-if="inbox" variant="outline" type="button" :disabled="locked" aria-controls="iam-inbox-filters" :aria-expanded="inboxFiltersOpen" @click="inboxFiltersOpen = !inboxFiltersOpen"><SlidersHorizontal :size="15" />{{ filtersActive ? '筛选中' : '筛选事项' }}</Button>
    </header>
    <header v-else class="iw-page-heading">
      <div class="iw-heading-copy">
        <h1>人员与权限</h1>
        <p>按管理范围办理，岗位与实际权限放在同一屏</p>
      </div>
      <nav class="iw-view-switch" aria-label="人员与权限视图">
        <button :aria-pressed="view === 'todo'" :disabled="locked" @click="changeView('todo')"><ClipboardList :size="17" aria-hidden="true" />待办处理</button>
        <button :aria-pressed="view === 'people'" :disabled="locked" @click="changeView('people')"><UsersRound :size="17" aria-hidden="true" />全部人员</button>
      </nav>
    </header>
    <nav v-if="inbox" class="iam2-queues" aria-label="事项队列">
      <button v-for="b in buckets" :key="b.key" :data-kind="b.key" :disabled="locked || coverage.some(c => c.kind === b.key && c.state === 'not_authorized')" :aria-pressed="kind === b.key" @click="bucket(b.key)">
        <span class="iam2-track-copy"><span class="iam2-track-title"><component :is="b.icon" :size="16" aria-hidden="true" />{{ b.name }}</span><small>{{ b.help }}</small></span>
        <strong :class="{ 'iam2-track-unavailable': !loading && counts[b.key] == null }">{{ loading ? '…' : counts[b.key] != null ? counts[b.key] : coverage.some(c => c.kind === b.key && c.state === 'not_authorized') ? '无查看权限' : '暂不可用' }}</strong>
      </button>
    </nav>
    <form v-if="view === 'todo' || (!iamStudioEnabled && caps.people)" v-show="!inbox || inboxFiltersOpen" id="iam-inbox-filters" class="iw-toolbar" @submit.prevent="filter()">
      <label class="pw-search iw-studio-search">
        <Search :size="18" aria-hidden="true" />
        <input ref="searchInput" v-model="q" type="search" aria-label="搜索姓名或账号" placeholder="搜索姓名或账号" :disabled="locked">
        <kbd aria-hidden="true" title="按 / 聚焦搜索">/</kbd>
      </label>
      <select v-if="!iamStudioEnabled || view !== 'people'" v-model="org" aria-label="组织筛选" :disabled="locked" @change="filter()">
        <option value="">全部组织</option>
        <option v-for="o in catalog?.organizations.filter(o => o.kind !== 'group' && o.status === 'active')" :key="o.id" :value="o.id">{{ o.name }}</option>
      </select>
      <template v-if="view === 'todo'">
        <select v-if="!iamStudioEnabled" v-model="kind" aria-label="任务类型" :disabled="locked" @change="filter()">
          <option value="">全部类型</option>
          <option v-for="(label, key) in taskLabels" :key="key" :value="key">{{ label }}</option>
        </select>
        <select v-model="state" aria-label="办理状态" :disabled="locked" @change="filter()">
          <option value="open">未结束</option>
          <option v-for="(label, key) in taskStateLabels" :key="key" :value="key">{{ label }}</option>
          <option value="all">全部状态</option>
        </select>
      </template>
      <div class="iw-toolbar-actions">
        <Button class="iw-query-button" type="submit" :disabled="locked || loading">查询</Button>
        <Button variant="outline" type="button" :disabled="locked || loading || !filtersActive" @click="resetFilters">重置</Button>
        <Button class="iw-refresh" variant="outline" type="button" aria-label="刷新列表" title="刷新列表" :disabled="locked || loading" @click="load"><RefreshCw :size="17" :class="{ 'iw-is-loading': loading }" aria-hidden="true" /></Button>
      </div>
    </form>
    <p v-if="routeError || error" class="pw-error" role="alert">{{ routeError || error }}<Button v-if="!routeError" variant="outline" @click="load">重试</Button><RouterLink v-else to="/system/users?view=todo">返回待办列表</RouterLink></p>
    <p v-if="catalogError" class="pw-notice" role="status">组织目录暂不可用 · {{ catalogError }} <Button variant="outline" @click="load">重试</Button></p>
    <p v-if="notice" class="pw-notice" role="status">{{ notice }}</p>
    <div v-if="coverage.some(c => c.state === 'unavailable' || c.state === 'disabled')" class="iw-coverage" role="status"><span v-for="source in coverage.filter(c => c.state === 'unavailable' || c.state === 'disabled')" :key="source.kind">{{ taskLabels[source.kind] }}：{{ source.message || (source.state === 'disabled' ? '尚未启用' : '暂不可读取') }}</span></div>
    <template v-if="iamStudioEnabled && view === 'people'">
      <p v-if="directoryError" class="pw-notice" role="status">组织树暂不可用 · {{ directoryError }}</p>
      <StudioPeople v-if="caps.people" :catalog="directoryCatalog" :org-counts="orgCounts" :org="org" :department="department" :people="people" :page="page" :total="total" :loading="loading" :failed="!!error || !!routeError" :locked="locked" :editable="!!(catalog?.studio_writes_enabled && catalog?.writes_enabled && caps.exceptions)" :viewer-id="auth.currentUser?.id" @filter="filterOrg" @select="selectPerson" @manage="p => selectPerson(p, 'manage')" @task="choose" @page="filter">
        <template #filters>
          <form class="iw-toolbar iam2-person-filters" @submit.prevent="filter()">
            <label class="pw-search iw-studio-search"><Search :size="16" aria-hidden="true" /><input ref="searchInput" v-model="q" type="search" aria-label="搜索姓名或账号" placeholder="搜索姓名或账号" :disabled="locked"><kbd aria-hidden="true">/</kbd></label>
            <select v-model="packageFilter" aria-label="权限包筛选" :disabled="locked" @change="filter()"><option value="">全部权限包状态</option><option value="yes">有有效包</option><option value="no">无有效包</option></select>
            <details class="iam2-filters" @toggle="readRoleFilter"><summary>更多筛选</summary><div>
              <label>任职类型<select v-model="personMode" :disabled="locked" @change="filter()"><option value="">全部</option><option value="legacy">历史来源待核实</option><option value="v2">正式任职</option></select></label>
              <label>人员状态<select v-model="personStatus" :disabled="locked" @change="filter()"><option value="">全部</option><option value="active">在用</option><option value="suspended">已停用</option><option value="left">已离职</option></select></label>
              <label v-if="caps.catalog && caps.exceptions">权限包<select v-model="roleFilter" :disabled="locked || roleLoading" @change="filter()"><option value="">全部</option><option v-for="r in roles" :key="r.id" :value="r.id">{{ r.name }} · {{ r.position_department_name || r.code }}</option></select></label>
              <p v-if="roleError" role="status">权限包选项暂不可用 · {{ roleError }}</p>
            </div></details>
            <div class="iw-toolbar-actions"><Button class="iw-query-button" type="submit" :disabled="locked || loading">查询</Button><Button variant="ghost" type="button" :disabled="locked || loading || !filtersActive" @click="resetFilters">重置</Button><Button class="iw-refresh" variant="outline" type="button" aria-label="刷新列表" title="刷新列表" :disabled="locked || loading" @click="load"><RefreshCw :size="16" aria-hidden="true" /></Button></div>
          </form>
        </template>
      </StudioPeople>
      <p v-else-if="!personId" class="pw-notice">人员目录受保护。可从已授权的个人例外链接进入。</p>
      <StudioPerson v-if="personId && !routeError" :person-id="personId" :panel="panel" :tab="tab" :catalog="catalog" @close="closePerson" @tab="router.replace({query:{...route.query, tab: $event, panel:'profile'}})" @panel="router.replace({query:{...route.query, panel:$event}})" @task="started" @saved="load" @locked="locked = $event" @dirty="dirty = $event" />
    </template>
    <div v-else class="iw-workspace" :class="{ 'has-detail': mobileDetail && (selected || personId), 'iw-no-list': view === 'people' && !caps.people }">
      <aside ref="rows" class="iw-list" aria-label="办理队列">
        <header v-if="inbox" class="iam2-queue-heading">
          <strong><ListChecks :size="18" aria-hidden="true" />待办队列</strong>
          <span class="iam2-actionable">{{ loading ? '读取中…' : actionable === null ? '统计暂不可用' : actionable + ' 条可处理' }}</span>
        </header>
        <header v-else>
          <strong>{{ view === 'people' ? '人员目录' : '待办队列' }}<span v-if="total !== null" class="iw-list-count" :class="{ 'is-people': view === 'people' }">{{ total }}</span></strong>
          <small>{{ view === 'people' ? '点击人员只读查看' : actionable === null ? '统计暂不可用' : `当前筛选可处理 ${actionable} 条` }}</small>
        </header>
        <div v-if="!inbox" class="iw-table-head"><span>人员 / 组织</span><span>{{ view === 'people' ? '当前岗位' : '申报变化' }}</span><span>{{ view === 'people' ? '状态 / 最近登录' : '类型 / 提交' }}</span></div>
        <div class="iw-list-scroll">
          <div v-if="loading" class="iw-list-loading" role="status">
            <p class="pw-empty">正在读取…</p>
            <div v-for="row in 5" :key="row" class="iw-skeleton-row" aria-hidden="true"><i /><span><b /><b /></span><b /></div>
          </div>
          <template v-else-if="view === 'people'">
            <button v-for="person in people" :key="person.id" class="iw-row iw-person-row" :aria-pressed="personId === person.id" :disabled="locked" @click="selectPerson(person)">
              <span class="iw-row-person">
                <span class="iw-row-avatar" aria-hidden="true">{{ person.display_name.slice(0, 1) }}</span>
                <span><strong :title="person.display_name">{{ person.display_name }}</strong><small :title="`${orgName(personOrg(person))} · ${departmentName(person.primary_department)}`">{{ orgName(personOrg(person)) }} · {{ departmentName(person.primary_department) }}</small></span>
              </span>
              <span><strong :title="person.position">{{ person.position || '岗位待确认' }}</strong><small :title="person.username">{{ person.username }}</small></span>
              <span><small class="pw-badge iw-status" :data-tone="personStatusPresentation(person.status).tone">{{ personStatusPresentation(person.status).label }}</small><small class="iw-last-login" :title="`最近登录（北京时间）：${lastLoginLabel(person.last_login_at, true)}`">{{ lastLoginLabel(person.last_login_at) }}</small></span>
            </button>
          </template>
          <template v-else-if="inbox">
            <button v-for="task in tasks" :key="task.key" class="iam2-task-card" :data-kind="task.kind" :aria-pressed="selected === task.key" :disabled="locked" @click="choose(task.key)">
              <span class="iam2-task-title"><span><strong>{{ task.subject.display_name }}</strong> <small>@{{ task.subject.username }}</small></span><span class="iam2-kind-pill">{{ taskLabels[task.kind] }}</span></span>
              <span class="iam2-task-change">{{ task.kind === 'position' && task.current_position ? task.current_position + ' → ' : '' }}{{ task.proposed_position || taskLabels[task.kind] }}</span>
              <span v-if="task.blocked_reasons.length || task.state !== 'actionable'" class="iam2-task-status">{{ task.blocked_reasons[0] || taskStatusText(task) }}</span>
              <span class="iam2-task-foot"><span>{{ orgName(task.org_unit_id) }} · {{ departmentName(task.department) }}</span><time :datetime="task.created_at">{{ formatBusinessDateTime(task.created_at) }}</time></span>
            </button>
          </template>
          <template v-else>
            <button v-for="task in tasks" :key="task.key" class="iw-row" :data-kind="task.kind" :aria-pressed="selected === task.key" :disabled="locked" @click="choose(task.key)">
              <span class="iw-row-person">
                <span class="iw-row-avatar" aria-hidden="true">{{ task.subject.display_name.slice(0, 1) }}</span>
                <span><strong :title="task.subject.display_name">{{ task.subject.display_name }}</strong><small :title="`${orgName(task.org_unit_id)} · ${departmentName(task.department)}`">{{ orgName(task.org_unit_id) }} · {{ departmentName(task.department) }}</small></span>
              </span>
              <span><strong :title="task.proposed_position">{{ task.proposed_position || taskLabels[task.kind] }}</strong><small class="iw-task-state" :data-state="task.state" :title="task.blocked_reasons.join('；')">{{ task.blocked_reasons[0] || taskStatusText(task) }}</small></span>
              <span><small class="pw-badge iw-kind-badge" :data-kind="task.kind">{{ taskLabels[task.kind] }}</small><small :title="formatBusinessDateTime(task.created_at)">{{ formatBusinessDateTime(task.created_at) }}</small></span>
            </button>
          </template>
          <div v-if="!loading && !error && !(view === 'people' ? people.length : tasks.length)" class="pw-empty iw-empty-list"><UsersRound :size="32" aria-hidden="true" /><h2>{{ view === 'people' && !caps.people ? '人员列表受保护' : partial ? '部分来源暂不可读取' : '当前筛选没有记录' }}</h2><p>调整筛选条件，或从已有链接打开获授权的详情。</p></div>
        </div>
        <footer class="iw-pagination">
          <span>{{ total === null ? '当前已读取 ' + tasks.length + ' 条' : total + ' 条' }} · 第 {{ page }} 页</span>
          <div><Button variant="ghost" :disabled="page <= 1 || locked || loading" @click="filter(page - 1)"><ChevronLeft :size="15" aria-hidden="true" />上一页</Button><Button variant="ghost" :disabled="locked || loading || (total !== null ? page * 30 >= total : tasks.length < 30)" @click="filter(page + 1)">下一页<ChevronRight :size="15" aria-hidden="true" /></Button></div>
        </footer>
      </aside>
      <PersonContext v-if="personId && !routeError" :person-id="personId" :panel="panel" :catalog="catalog" @panel="router.replace({ query: { ...route.query, panel: $event } })" @task="started" @back="back" @saved="load" @locked="locked = $event" />
      <PositionReviewPane v-else-if="selected && ['position','registration'].includes(taskKind) && !routeError" :item-key="selected" :catalog="catalog" :studio="iamStudioEnabled" compact @saved="reviewCompleted" @next="next" @back="back" @locked="locked = $event" @dirty="dirty = $event" />
      <PasswordResetPanel v-else-if="taskKind === 'password-reset' && !routeError" :request-id="selected.slice(selected.indexOf(':') + 1)" @saved="completed('密码找回处理结果已保存。')" @refreshed="load" @back="back" @locked="locked = $event" />
      <IdentityRecords v-else-if="taskKind === 'identity-change' && !routeError" embedded :request-id="selected.slice(selected.indexOf(':') + 1)" :catalog="catalog" mode="changes" @saved="completed" @locked="locked = $event" @dirty="dirty = $event" @back="back" />
      <div v-else class="pw-empty iw-welcome">
        <span class="iw-welcome-icon" aria-hidden="true"><ShieldCheck :size="42" /></span>
        <h2>{{ iamStudioEnabled ? '选择事项开始核对' : '选择人员，核对岗位与权限' }}</h2>
        <p>{{ iamStudioEnabled ? '请从左侧队列选择申请，查看原始资料与可办理操作。' : '查看人员只读；需要调整时明确发起办理。' }}</p>
        <ol v-if="!iamStudioEnabled" class="iw-welcome-steps" aria-label="办理流程"><li><span>1</span>选择人员</li><li><span>2</span>核对岗位与方案</li><li><span>3</span>预览后确认</li></ol>
        <Button v-if="hasVisibleRecords" :disabled="locked || loading" @click="openFirstRecord">{{ view === 'people' ? '查看首位人员' : '查看首条待办' }}<ArrowRight :size="16" aria-hidden="true" /></Button>
      </div>
    </div>
    <IamLeaveGuard ref="leave" :dirty="dirty" :busy="locked" />
  </section>
</template>
