<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { ArrowLeft, ArrowUpRight, BriefcaseBusiness, Building2, Clock3, History, Info, KeyRound, LockKeyhole, Mail, Phone, ShieldCheck, SlidersHorizontal, UserRound } from '@lucide/vue'
import { identityApi, type PersonIdentity, type OrganizationCatalog, type ChangeRecord, type ChangePreview } from '@/api/identity'
import { positionReviewsApi } from '@/api/positionReviews'
import { iamWorkspaceApi } from '@/api/iamWorkspace'
import { systemApi } from '@/api/system'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage } from '@/lib/http'
import { parseBusinessTimestamp } from '@/lib/dateTime'
import { Button } from '@/components/ui/button'
import IamDialogSurface from '@/components/iam/workspace/IamDialogSurface.vue'
import { rememberIdentityMode } from '@/components/iam/workspace/identity-ui-context'
import { personStatusPresentation } from '@/components/iam/workspace/iam-status'
import IdentityWizard from '../IdentityWizard.vue'
import AccessExplanation from '../AccessExplanation.vue'
import DelegationEditor from '../DelegationEditor.vue'
import { departmentName, lastLoginLabel } from '../positionLabels'
import { workspaceCapabilities, type PersonPanel } from './contracts'
const AccessPanel = defineAsyncComponent(() => import('@/views/UserAccessManagementView.vue'))
const props = defineProps<{ personId: string; panel: PersonPanel; catalog?: OrganizationCatalog }>()
const emit = defineEmits<{ panel: [PersonPanel]; task: [string, boolean]; back: []; saved: []; locked: [boolean] }>()
const auth = useAuthStore(), person = ref<PersonIdentity>(), loading = ref(false), error = ref(''), notice = ref('')
const caps = computed(() => workspaceCapabilities(p => auth.can(p)))
const viewer = computed(() => `${auth.currentUser?.id}:${auth.authorizationVersion}:${auth.currentUser?.identity?.employment_epoch}:${auth.currentUser?.identity?.effective_context_key}`)
const dialog = ref<InstanceType<typeof IamDialogSurface>>(), dirty = ref(false), busy = ref(false), savedDraft = ref('')
const pendingVerification = ref(false)
const statusDialogOpen = ref(false), statusError = ref(''), statusUncertain = ref(false)
const desiredStatus = ref<'active' | 'suspended'>('suspended')
let pendingStatus: { id: string; desired: 'active' | 'suspended'; owner: string } | undefined
const account = computed(() => `${auth.currentUser?.id}:${auth.currentUser?.identity?.employment_epoch}`)
type PendingChange = { id: string; revision: number; state: string; command?: { record: ChangeRecord; preview: ChangePreview; key: string } }
let pendingChange: (PendingChange & { owner: string }) | undefined
const locked = computed(() => busy.value || pendingVerification.value || statusUncertain.value)
const canChangeStatus = computed(() => caps.value.people && !!person.value &&
  ['active', 'suspended'].includes(person.value.status) && person.value.employment_status !== 'left')
const beforeUnload = (event: BeforeUnloadEvent) => { if (locked.value || dirty.value) { event.preventDefault(); event.returnValue = '' } }
onMounted(() => window.addEventListener('beforeunload', beforeUnload))
onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload))
function rememberPending(value: PendingChange | null) { pendingChange = value ? { ...value, owner: account.value } : undefined }
async function retryPending() {
  const anchor = pendingChange, current = generation
  if (!anchor?.command || anchor.owner !== account.value || busy.value || !caps.value.people || !caps.value.exceptions || !props.catalog?.writes_enabled) return
  busy.value = true
  try {
    const result = await identityApi.commit(anchor.command.record, anchor.command.preview, anchor.command.key)
    if (current !== generation) return
    await saved(result)
  } catch (e) {
    if (current !== generation) return
    error.value = getApiErrorMessage(e)
    const status = (e as { response?: { status?: number } }).response?.status
    if (status && status !== 408 && status < 500) { pendingChange = undefined; pendingVerification.value = false }
  } finally { if (current === generation) busy.value = false }
}
async function verifyPending() {
  if (!pendingChange || busy.value) return
  const anchor = pendingChange, current = generation
  busy.value = true
  try {
    const result = await iamWorkspaceApi.change(anchor.id)
    if (current !== generation) return
    if (result.revision !== anchor.revision || result.state !== anchor.state) {
      pendingChange = undefined; pendingVerification.value = false; notice.value = '已读取原办理单的新状态，请在操作记录查看结果。'
    } else notice.value = '尚未观察到原办理单变化。请稍后重新核查，勿重复提交。'
  } catch (e) { if (current === generation) error.value = getApiErrorMessage(e) }
  finally { if (current === generation) busy.value = false }
}
let generation = 0
const orgName = (id: string) => props.catalog?.organizations.find(o => o.id === id)?.name || id || '未登记'
const accountValue = (value: string | null | undefined) => value == null ? '未记录' : value.trim() || '未填写'
const bindings = computed(() => {
  const value = person.value
  if (!value || value.employment_status === 'left') return []
  const now = parseBusinessTimestamp(value.server_now) ?? Date.now()
  const activeAssignments = new Set(value.active_assignments_summary?.map(a => a.id) || [])
  return value.role_bindings.filter(b => {
    if (b.state !== 'active' || b.assignment_id && !activeAssignments.has(b.assignment_id)) return false
    if (value.identity_mode === 'v2' && !b.assignment_id && b.employment_epoch !== value.employment_epoch) return false
    const start = parseBusinessTimestamp(b.valid_from), end = parseBusinessTimestamp(b.valid_until)
    return (!b.valid_from || start !== null && start <= now) && (!b.valid_until || end !== null && now < end)
  })
})
async function read() {
  const current = ++generation, actor = viewer.value
  person.value = undefined; error.value = ''; notice.value = ''; dirty.value = false; loading.value = false
  if (!caps.value.people || props.panel === 'exceptions') return
  loading.value = true
  try {
    const data = await identityApi.person(props.personId)
    if (current !== generation || actor !== viewer.value) return
    person.value = data; rememberIdentityMode(auth.currentUser?.id || '', data.id, data.identity_mode)
  } catch (e) { if (current === generation && actor === viewer.value) error.value = getApiErrorMessage(e) }
  finally { if (current === generation) loading.value = false }
}
async function start() {
  const target = person.value, current = generation, actor = viewer.value
  if (!target || locked.value || !caps.value.people || !caps.value.exceptions || !props.catalog?.writes_enabled) return
  busy.value = true; error.value = ''
  try {
    const result = await positionReviewsApi.adjust(target.id, {
      org_unit_id: target.primary_assignment?.org_unit_id || target.primary_org_unit_id || target.primary_factory_id,
      department_code: target.primary_department, position: target.position || '待核对岗位',
    })
    if (current !== generation || actor !== viewer.value) return
    notice.value = result.reused ? '已打开现有岗位待办。' : '岗位待办已创建；离开编辑不会撤销这条待办。'
    busy.value = false
    emit('task', result.item_key, result.reused)
  } catch (e) { if (current === generation && actor === viewer.value) error.value = getApiErrorMessage(e) }
  finally { if (current === generation) busy.value = false }
}
async function saved(row?: ChangeRecord) {
  const continueManagement = props.panel === 'manage' && row?.request_type === 'confirm_identity' && row.state === 'applied'
  pendingChange = undefined; pendingVerification.value = false; dirty.value = false; busy.value = false
  if (!continueManagement) emit('panel', 'profile')
  await read()
  notice.value = continueManagement ? '正式任职已确认，请继续填写要调整的职位和权限包。' : row?.state === 'pending_approval' ? '已提交给有权管理员审核，当前权限尚未改变。' : row?.state === 'scheduled' ? '已预约，权限将在指定时间生效。' : '办理已完成。'
  emit('saved')
}
function openStatusDialog() {
  if (locked.value || !canChangeStatus.value) return
  desiredStatus.value = person.value!.status === 'active' ? 'suspended' : 'active'
  statusError.value = ''; statusDialogOpen.value = true
}
async function changeStatus(retry = false) {
  if (busy.value || !caps.value.people) return
  if (retry ? !statusUncertain.value || !pendingStatus || pendingStatus.owner !== account.value || pendingStatus.id !== props.personId
    : locked.value || !statusDialogOpen.value || !canChangeStatus.value) return
  const current = generation, actor = viewer.value
  const intent = retry ? pendingStatus! : { id: person.value!.id, desired: desiredStatus.value, owner: account.value }
  pendingStatus = intent
  busy.value = true; statusError.value = ''
  try {
    await systemApi.updateUserStatus(intent.id, { status: intent.desired })
    if (current !== generation || actor !== viewer.value) return
    pendingStatus = undefined; statusUncertain.value = false; statusDialogOpen.value = false; busy.value = false
    await read()
    if (actor !== viewer.value || props.personId !== intent.id) return
    notice.value = intent.desired === 'suspended' ? '账号已停用，原登录会话已失效。' : '账号已恢复，可重新登录。'
    emit('saved')
  } catch (e) {
    if (current !== generation || actor !== viewer.value) return
    const status = (e as { response?: { status?: number } }).response?.status
    statusUncertain.value = !status || status === 408 || status >= 500
    statusError.value = getApiErrorMessage(e)
    if (!statusDialogOpen.value) error.value = statusError.value
    if (statusUncertain.value) statusDialogOpen.value = false
    else pendingStatus = undefined
    if (status === 401 || status === 403) { person.value = undefined; statusDialogOpen.value = false; error.value = statusError.value }
  } finally { if (current === generation) busy.value = false }
}
async function verifyStatus() {
  if (!pendingStatus || busy.value || !caps.value.people) return
  const current = generation, actor = viewer.value, pending = pendingStatus
  busy.value = true; error.value = ''
  try {
    const data = await identityApi.person(pending.id)
    if (current !== generation || actor !== viewer.value) return
    person.value = data
    if (data.status === pending.desired) {
      pendingStatus = undefined; statusUncertain.value = false
      notice.value = `已核实账号状态：${personStatusPresentation(data.status).label}。`; emit('saved')
    } else notice.value = '尚未观察到目标状态，请稍后再次核查。'
  } catch (e) { if (current === generation && actor === viewer.value) { person.value = undefined; error.value = getApiErrorMessage(e) } }
  finally { if (current === generation) busy.value = false }
}
const permitLeave = async () => locked.value ? false : ['advanced', 'manage'].includes(props.panel) ? (await dialog.value?.permitLeave()) ?? true : true
onBeforeRouteLeave(permitLeave); onBeforeRouteUpdate(permitLeave)
watch(viewer, () => { ++generation; person.value = undefined; busy.value = false; dirty.value = false; savedDraft.value = ''; pendingVerification.value = !!pendingChange && pendingChange.owner === account.value; if (!pendingVerification.value) pendingChange = undefined }, { flush: 'sync' })
watch(viewer, () => { statusDialogOpen.value = false; statusError.value = ''; statusUncertain.value = !!pendingStatus && pendingStatus.owner === account.value; if (!statusUncertain.value) pendingStatus = undefined }, { flush: 'sync' })
watch(() => props.personId, () => { statusDialogOpen.value = false; statusError.value = '' }, { flush: 'sync' })
watch([() => props.personId, viewer], read, { immediate: true, flush: 'sync' })
watch(() => props.panel, panel => { if (panel !== 'exceptions' && !person.value && !loading.value) void read() })
watch(locked, value => emit('locked', value), { flush: 'sync' })
onBeforeUnmount(() => { ++generation })
</script>
<template>
  <section class="iw-person-context" aria-label="人员只读详情">
    <header class="iw-person-heading">
      <Button class="iw-mobile-back" variant="ghost" :disabled="locked" @click="emit('back')"><ArrowLeft :size="16" />返回列表</Button>
      <span class="iw-person-avatar" aria-hidden="true">{{ person?.display_name.slice(0, 1) || '人' }}</span>
      <div><h2>{{ person?.display_name || '人员详情' }}</h2><p>{{ person?.position || (panel === 'exceptions' ? '个人例外与供应商授权' : '岗位与授权资料') }}</p></div>
      <span class="pw-badge iw-readonly-badge"><LockKeyhole :size="13" aria-hidden="true" />只读查看</span>
    </header>
    <nav class="iw-person-tabs" aria-label="人员详情栏目">
      <button v-if="caps.people" :aria-pressed="panel === 'profile'" :disabled="locked" @click="emit('panel', 'profile')"><BriefcaseBusiness :size="16" aria-hidden="true" />岗位与权限</button>
      <button v-if="caps.exceptions" :aria-pressed="panel === 'exceptions'" :disabled="locked" @click="emit('panel', 'exceptions')"><ShieldCheck :size="16" aria-hidden="true" />个人例外</button>
      <button v-if="caps.people" :aria-pressed="panel === 'account'" :disabled="locked" @click="emit('panel', 'account')"><KeyRound :size="16" aria-hidden="true" />账号状态</button>
    </nav>
    <div class="iw-detail-scroll">
      <p v-if="loading" role="status">正在读取人员资料…</p>
      <p v-if="error" class="pw-error" role="alert">{{ error }}<Button variant="outline" @click="read">重新读取</Button></p>
      <p v-if="notice" class="pw-notice" role="status">{{ notice }}</p>
      <div v-if="statusUncertain" class="pw-notice" role="status">账号状态提交结果待确认。可读取最新状态；若请求未成功，可重试同一目标状态。<div class="pw-inline"><Button :disabled="busy || !caps.people" @click="verifyStatus">核查账号状态</Button><Button :disabled="busy || !caps.people" @click="changeStatus(true)">{{ pendingStatus?.desired === 'suspended' ? '重试停用账号' : '重试恢复账号' }}</Button></div></div>
      <div v-if="pendingVerification" class="pw-notice" role="status">访问权限已更新，原办理请求的结果仍待核查。<Button :disabled="busy" @click="verifyPending">核查原办理结果</Button><Button :disabled="busy || !pendingChange?.command || !caps.exceptions || !catalog?.writes_enabled" @click="retryPending">使用原办理内容重试</Button></div>
      <AccessPanel v-if="panel === 'exceptions' && caps.exceptions" :key="`${personId}:${viewer}`" :target-user-id="personId" embedded />
      <p v-else-if="!caps.people" class="pw-notice">人员资料受保护。请使用已授权的个人例外面板。</p>
      <template v-else-if="person">
        <p class="iw-readonly-note"><Info :size="16" aria-hidden="true" /><span>查看、切换人员和刷新不会创建办理单。</span></p>
        <dl class="iw-facts">
          <div><dt><BriefcaseBusiness :size="14" aria-hidden="true" />正式岗位</dt><dd>{{ person.position || '待确认' }}</dd></div>
          <div><dt><Building2 :size="14" aria-hidden="true" />组织 / 部门</dt><dd>{{ orgName(person.primary_assignment?.org_unit_id || person.primary_org_unit_id || person.primary_factory_id) }} · {{ departmentName(person.primary_department) }}</dd></div>
          <div><dt><KeyRound :size="14" aria-hidden="true" />账号状态</dt><dd><span class="iw-status" :data-tone="personStatusPresentation(person.status).tone">{{ personStatusPresentation(person.status).label }}</span></dd></div>
          <div><dt><ShieldCheck :size="14" aria-hidden="true" />任职状态</dt><dd>{{ person.employment_status === 'left' ? '已离职' : person.employment_status === 'frozen' ? '已冻结' : person.identity_mode === 'v2' ? '正式任职已确认' : '历史来源待核实' }}</dd></div>
          <div><dt><UserRound :size="14" aria-hidden="true" />登录账号</dt><dd>{{ accountValue(person.username) }}</dd></div>
          <div><dt><Clock3 :size="14" aria-hidden="true" />最近登录</dt><dd>{{ lastLoginLabel(person.last_login_at, true) }}</dd></div>
          <div><dt><Phone :size="14" aria-hidden="true" />手机号码</dt><dd>{{ accountValue(person.phone) }}</dd></div>
          <div><dt><Mail :size="14" aria-hidden="true" />邮箱</dt><dd>{{ accountValue(person.email) }}</dd></div>
        </dl>
        <p class="pw-subtle">登录时间以最近一次成功登录为准，按北京时间显示。</p>
        <template v-if="panel !== 'account'">
          <div class="iw-detail-section-heading"><h3><ShieldCheck :size="18" aria-hidden="true" />当前授权来源</h3><span>{{ bindings.length }} 个当前来源</span></div>
          <p v-if="!bindings.length" class="pw-subtle">当前没有在用的方案绑定。</p>
          <div v-for="b in bindings" :key="b.id" class="iw-source">
            <span class="iw-source-icon" aria-hidden="true"><ShieldCheck :size="20" /></span>
            <div><strong>{{ b.role_name }}</strong><small>{{ b.assignment_id ? '任职绑定' : '独立来源' }} · {{ b.role_version_id ? '已固定版本' : '保留原解释' }} · {{ departmentName(b.department) }}</small><p>{{ b.factory_ceiling?.map(orgName).join('、') || '保留原批准范围' }}</p></div>
          </div>
          <details v-if="person.assignments.length"><summary>全部任职与历史 · {{ person.assignments.length }}</summary><p v-for="a in person.assignments" :key="a.id">{{ a.official_position_title }} · {{ a.org_name }} · {{ a.state }} · {{ a.valid_from }}{{ a.valid_until ? ` 至 ${a.valid_until}` : '' }}</p></details>
          <AccessExplanation v-if="catalog && caps.exceptions" :key="person.id" :user-id="person.id" :catalog="catalog" :default-factory="person.primary_factory_id" :default-department="person.primary_department" />
          <DelegationEditor v-if="catalog?.can_manage_delegations && person.id !== auth.currentUser?.id" :user-id="person.id" :catalog="catalog" :default-org="person.primary_assignment?.org_unit_id || person.primary_org_unit_id || person.primary_factory_id" :default-department="person.primary_department" />
        </template>
        <div class="pw-inline iw-secondary-actions">
          <Button variant="outline" :disabled="locked || !caps.exceptions || !catalog?.writes_enabled" @click="start"><SlidersHorizontal :size="15" aria-hidden="true" />按内置方案快速调整</Button>
          <Button variant="outline" :disabled="locked || !caps.exceptions || !catalog?.writes_enabled" @click="emit('panel', 'advanced')"><BriefcaseBusiness :size="15" aria-hidden="true" />任职、冻结与离职</Button>
          <RouterLink :to="{ path: '/system/iam/audit', query: { source: 'position', person: person.id } }" class="iamx-link-button"><History :size="15" aria-hidden="true" />查看此人记录</RouterLink>
        </div>
      </template>
    </div>
    <footer v-if="person && panel !== 'exceptions'" class="iw-person-footer">
      <span><LockKeyhole :size="14" aria-hidden="true" />当前为只读资料</span>
      <div class="pw-inline"><Button v-if="canChangeStatus" variant="outline" :disabled="locked" @click="openStatusDialog">{{ person.status === 'active' ? '停用账号' : '恢复账号' }}</Button><Button :disabled="locked || !caps.exceptions || !catalog?.writes_enabled" @click="emit('panel', 'manage')">调整职位与权限<ArrowUpRight :size="17" aria-hidden="true" /></Button></div>
    </footer>
    <IamDialogSurface :open="statusDialogOpen" :title="desiredStatus === 'suspended' ? '确认停用账号' : '确认恢复账号'" :description="`${person?.display_name || ''} · ${person?.username || ''}`" :busy="busy" @update:open="statusDialogOpen = $event">
      <p>{{ desiredStatus === 'suspended' ? '停用后，此账号将无法登录，所有现有登录会话立即失效；人员资料和历史记录保留。' : '恢复后，此账号可重新登录，按当前有效任职与授权获取权限。' }}</p>
      <p v-if="statusError" role="alert" class="pw-error">{{ statusError }}</p>
      <div class="pw-inline"><Button variant="outline" :disabled="busy" @click="statusDialogOpen = false">取消</Button><Button :variant="desiredStatus === 'suspended' ? 'destructive' : 'default'" :disabled="busy" @click="changeStatus()">{{ busy ? '正在处理…' : desiredStatus === 'suspended' ? '确认停用' : '确认恢复' }}</Button></div>
    </IamDialogSurface>
    <IamDialogSurface ref="dialog" :open="['advanced', 'manage'].includes(panel) && !pendingVerification && !!person && !!catalog && caps.exceptions" :title="panel === 'manage' ? '调整职位与权限' : '任职、预约与账号状态'" :description="person?.display_name" drawer :dirty="dirty" :busy="busy" :saved-description="savedDraft" @update:open="emit('panel', 'profile')" @discarded="dirty = false"><IdentityWizard v-if="person && catalog && ['advanced', 'manage'].includes(panel)" :key="`${person.id}:${person.identity_version}:${panel}:${viewer}`" :purpose="panel === 'manage' ? 'position-permissions' : undefined" :person="person" :catalog="catalog" @dirty="dirty = $event" @busy="busy = $event" @draft="savedDraft = $event" @pending="rememberPending" @saved="saved" /></IamDialogSurface>
  </section>
</template>
