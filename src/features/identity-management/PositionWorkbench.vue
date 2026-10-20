<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { isNavigationFailure, NavigationFailureType, onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { ArrowRight, ChevronLeft, ChevronRight, ClipboardList, Search, RefreshCw, UsersRound, ShieldCheck } from '@lucide/vue'
import { identityApi, type OrganizationCatalog, type Person } from '@/api/identity'
import { positionReviewsApi } from '@/api/positionReviews'
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
import './position-workbench.css'
import './workspace/workspace.css'
import './workspace/permission-studio.css'
const route = useRoute(), router = useRouter(), auth = useAuthStore()
const catalog = ref<OrganizationCatalog>(), tasks = ref<WorkspaceTask[]>([]), people = ref<Person[]>([]), coverage = ref<SourceCoverage[]>([])
const q = ref(''), loading = ref(false), error = ref(''), notice = ref(''), locked = ref(false), dirty = ref(false)
const total = ref<number | null>(0), actionable = ref<number | null>(0), partial = ref(false)
const caps = computed(() => workspaceCapabilities(p => auth.can(p)))
const view = computed(() => route.query.view === 'people' || route.query.person || route.query.tab === 'people' ? 'people' : 'todo')
const selected = computed(() => typeof (route.query.task || route.query.item) === 'string' ? String(route.query.task || route.query.item) : '')
const personId = computed(() => typeof route.query.person === 'string' ? route.query.person : '')
const panel = computed(() => (['profile', 'exceptions', 'account', 'advanced', 'manage'].includes(String(route.query.panel)) ? route.query.panel : 'profile') as PersonPanel)
const page = computed(() => Math.max(1, Math.min(100000, Number(route.query.page) || 1)))
const org = ref(String(route.query.org || '')), kind = ref(String(route.query.kind || '')), state = ref(String(route.query.state || 'open'))
const rows = ref<HTMLElement>(), searchInput = ref<HTMLInputElement>(), mobileDetail = ref(!!selected.value || !!personId.value)
const leave = ref<InstanceType<typeof IamLeaveGuard>>()
let generation = 0
const viewer = computed(() => `${auth.currentUser?.id ?? ''}:${auth.authorizationVersion}:${auth.currentUser?.identity?.employment_epoch ?? ''}:${auth.currentUser?.identity?.effective_context_key ?? ''}`)
const orgName = (id: string) => catalog.value?.organizations.find(o => o.id === id)?.name || id || '未登记'
const routeError = computed(() => route.query.route_error ? '链接包含无效或冲突的办理目标，请从列表重新选择。' : '')
const taskKind = computed(() => selected.value.split(':')[0] || '')
const filtersActive = computed(() => !!(q.value.trim() || org.value || (view.value === 'todo' && (kind.value || state.value !== 'open'))))
const hasVisibleRecords = computed(() => view.value === 'people' ? people.value.length > 0 : tasks.value.length > 0)
async function load() {
  const current = ++generation, identity = viewer.value
  loading.value = true; error.value = ''; tasks.value = []; people.value = []; total.value = null; actionable.value = null
  try {
    if (routeError.value) return
    if (!catalog.value) {
      const data = caps.value.people ? await identityApi.catalog() : await positionReviewsApi.catalog()
      if (current !== generation || identity !== viewer.value) return
      catalog.value = data
    }
    if (view.value === 'people') {
      coverage.value = []
      if (!caps.value.people) return
      const data = await identityApi.people({ q: q.value, org_unit_id: org.value, page: page.value, page_size: 30 })
      if (current !== generation || identity !== viewer.value) return
      people.value = data.items; total.value = data.total
    } else {
      if (!caps.value.people && !caps.value.exceptions) return
      const data = await iamWorkspaceApi.tasks({ q: q.value, org_unit_id: org.value, kind: kind.value, state: state.value === 'all' ? '' : state.value, page: page.value, page_size: 30 })
      if (current !== generation || identity !== viewer.value) return
      tasks.value = data.items; total.value = data.visible_total; actionable.value = data.actionable_total; coverage.value = data.coverage; partial.value = data.partial
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
async function choose(task: string) {
  if (locked.value) return
  const ok = await router.replace({ query: { ...route.query, view: 'todo', task, person: undefined, panel: undefined, item: undefined, request_id: undefined, route_error: undefined } })
  if (!ok) mobileDetail.value = true
}
async function selectPerson(person: Person) {
  if (locked.value) return
  const ok = await router.replace({ query: { ...route.query, view: 'people', person: person.id, panel: 'profile', task: undefined, item: undefined } })
  if (!ok) mobileDetail.value = true
}
async function changeView(value: string) {
  if (locked.value) return
  await router.replace({ query: { view: value, org: org.value || undefined } }); mobileDetail.value = false
}
async function filter(nextPage = 1) {
  if (locked.value) return
  const result = await router.replace({ query: { ...route.query, page: nextPage > 1 ? String(nextPage) : undefined,
    org: org.value || undefined, kind: view.value === 'todo' ? kind.value || undefined : undefined, state: view.value === 'todo' ? state.value : undefined } })
  if (!result || isNavigationFailure(result, NavigationFailureType.duplicated)) await load()
  return result
}
async function resetFilters() {
  if (locked.value || loading.value) return
  const previous = { q: q.value, org: org.value, kind: kind.value, state: state.value }
  const previousPath = route.fullPath, previousViewer = viewer.value
  q.value = ''; org.value = ''; kind.value = ''; state.value = 'open'
  const result = await filter()
  if (isNavigationFailure(result, NavigationFailureType.aborted) && route.fullPath === previousPath && viewer.value === previousViewer) {
    q.value = previous.q; org.value = previous.org; kind.value = previous.kind; state.value = previous.state
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
async function permitLeave() { const allowed = !locked.value && ((await leave.value?.permitLeave()) ?? !dirty.value); if (allowed) dirty.value = false; return allowed }
onBeforeRouteLeave(permitLeave); onBeforeRouteUpdate(permitLeave)
const beforeUnload = (event: BeforeUnloadEvent) => { if (locked.value || dirty.value) { event.preventDefault(); event.returnValue = '' } }
const shortcut = (event: KeyboardEvent) => {
  if (event.key === '/' && !event.ctrlKey && !event.metaKey && !event.altKey && !locked.value &&
      !(event.target instanceof HTMLElement && event.target.closest('input,textarea,select,[contenteditable="true"],[role="dialog"]'))) {
    event.preventDefault(); searchInput.value?.focus()
  }
}
watch([view, page, () => route.query.org, () => route.query.kind, () => route.query.state], () => {
  org.value = String(route.query.org || ''); kind.value = String(route.query.kind || ''); state.value = String(route.query.state || 'open'); void load()
})
watch(viewer, () => { ++generation; tasks.value = []; people.value = []; coverage.value = []; catalog.value = undefined; total.value = null; actionable.value = null; q.value = ''; error.value = ''; void load() }, { flush: 'sync' })
onMounted(() => { window.addEventListener('beforeunload', beforeUnload); window.addEventListener('keydown', shortcut); void load() })
onBeforeUnmount(() => { ++generation; window.removeEventListener('beforeunload', beforeUnload); window.removeEventListener('keydown', shortcut) })
</script>
<template>
  <section class="pw-root iw-root iw-permission-page" :class="{ 'iw-mobile-detail': mobileDetail && (selected || personId) }" data-yl-help="identity-management.overview">
    <header class="iw-page-heading">
      <div class="iw-heading-copy">
        <h1>人员与权限</h1>
        <p>按管理范围办理，岗位与实际权限放在同一屏</p>
      </div>
      <nav class="iw-view-switch" aria-label="人员与权限视图">
        <button :aria-pressed="view === 'todo'" :disabled="locked" @click="changeView('todo')"><ClipboardList :size="17" aria-hidden="true" />待办处理</button>
        <button :aria-pressed="view === 'people'" :disabled="locked" @click="changeView('people')"><UsersRound :size="17" aria-hidden="true" />全部人员</button>
      </nav>
    </header>
    <form v-if="view === 'todo' || caps.people" class="iw-toolbar" @submit.prevent="filter()">
      <label class="pw-search iw-studio-search">
        <Search :size="18" aria-hidden="true" />
        <input ref="searchInput" v-model="q" type="search" aria-label="搜索姓名或账号" placeholder="搜索姓名或账号" :disabled="locked">
        <kbd aria-hidden="true" title="按 / 聚焦搜索">/</kbd>
      </label>
      <select v-model="org" aria-label="组织筛选" :disabled="locked" @change="filter()">
        <option value="">全部组织</option>
        <option v-for="o in catalog?.organizations.filter(o => o.kind !== 'group' && o.status === 'active')" :key="o.id" :value="o.id">{{ o.name }}</option>
      </select>
      <template v-if="view === 'todo'">
        <select v-model="kind" aria-label="任务类型" :disabled="locked" @change="filter()">
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
    <p v-if="notice" class="pw-notice" role="status">{{ notice }}</p>
    <div v-if="coverage.some(c => c.state === 'unavailable' || c.state === 'disabled')" class="iw-coverage" role="status"><span v-for="source in coverage.filter(c => c.state === 'unavailable' || c.state === 'disabled')" :key="source.kind">{{ taskLabels[source.kind] }}：{{ source.message || (source.state === 'disabled' ? '尚未启用' : '暂不可读取') }}</span></div>
    <div class="iw-workspace" :class="{ 'has-detail': mobileDetail && (selected || personId), 'iw-no-list': view === 'people' && !caps.people }">
      <aside ref="rows" class="iw-list" aria-label="办理队列">
        <header>
          <strong>{{ view === 'people' ? '人员目录' : '待办队列' }}<span v-if="total !== null" class="iw-list-count" :class="{ 'is-people': view === 'people' }">{{ total }}</span></strong>
          <small>{{ view === 'people' ? '点击人员只读查看' : actionable === null ? '统计暂不可用' : `当前筛选可处理 ${actionable} 条` }}</small>
        </header>
        <div class="iw-table-head"><span>人员 / 组织</span><span>{{ view === 'people' ? '当前岗位' : '申报变化' }}</span><span>{{ view === 'people' ? '状态 / 最近登录' : '类型 / 提交' }}</span></div>
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
      <PositionReviewPane v-else-if="selected && ['position','registration'].includes(taskKind) && !routeError" :item-key="selected" :catalog="catalog" compact @saved="dirty = false; load()" @next="next" @back="back" @locked="locked = $event" @dirty="dirty = $event" />
      <PasswordResetPanel v-else-if="taskKind === 'password-reset' && !routeError" :request-id="selected.slice(selected.indexOf(':') + 1)" @saved="load" @back="back" @locked="locked = $event" />
      <IdentityRecords v-else-if="taskKind === 'identity-change' && !routeError" embedded :request-id="selected.slice(selected.indexOf(':') + 1)" :catalog="catalog" mode="changes" @locked="locked = $event" @dirty="dirty = $event" @back="back" />
      <div v-else class="pw-empty iw-welcome">
        <span class="iw-welcome-icon" aria-hidden="true"><ShieldCheck :size="42" /></span>
        <h2>选择人员，核对岗位与权限</h2>
        <p>查看人员只读；需要调整时明确发起办理。</p>
        <ol class="iw-welcome-steps" aria-label="办理流程"><li><span>1</span>选择人员</li><li><span>2</span>核对岗位与方案</li><li><span>3</span>预览后确认</li></ol>
        <Button v-if="hasVisibleRecords" :disabled="locked || loading" @click="openFirstRecord">{{ view === 'people' ? '查看首位人员' : '查看首条待办' }}<ArrowRight :size="16" aria-hidden="true" /></Button>
      </div>
    </div>
    <IamLeaveGuard ref="leave" :dirty="dirty" :busy="locked" />
  </section>
</template>
