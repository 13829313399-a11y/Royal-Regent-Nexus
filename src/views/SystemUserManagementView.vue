<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  ArrowLeft,
  Building2,
  BriefcaseBusiness,
  ClipboardCheck,
  Check,
  CheckCircle2,
  CircleAlert,
  Clock3,
  Factory,
  KeyRound,
  LifeBuoy,
  LoaderCircle,
  Mail,
  Phone,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  UserCheck,
  UserCog,
  UserPlus,
  UserRoundX,
  Users,
  XCircle,
} from '@lucide/vue'
import { useRoute } from 'vue-router'
import {
  systemApi,
  type PasswordResetRequestDetail,
  type PasswordResetStatus,
  type RegistrationProfileRequest,
  type RegistrationRequestResponse,
  type RoleResponse,
  type UserResponse,
} from '@/api/system'
import UserAvatar from '@/components/common/UserAvatar.vue'
import { factoryContexts } from '@/data/enterpriseMock'
import { identityApi, type Organization } from '@/api/identity'
import { getPositionSuggestions } from '@/data/positionCatalog'
import {
  registrationDepartmentLabel,
  registrationDepartments,
} from '@/data/registrationDepartments'
import { formatBusinessDateTime, parseBusinessTimestamp } from '@/lib/dateTime'
import { getApiErrorMessage } from '@/lib/http'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const authStore = useAuthStore()
const activeTab = ref<'pending' | 'password-reset' | 'users'>('pending')
const requests = ref<RegistrationRequestResponse[]>([])
const users = ref<UserResponse[]>([])
const systemPositions = ref<RoleResponse[]>([])
const passwordResetRequests = ref<PasswordResetRequestDetail[]>([])
const passwordResetStatus = ref<PasswordResetStatus>('pending')
const selectedPasswordResetId = ref('')
const passwordResetReviewTarget = ref<PasswordResetRequestDetail | null>(null)
const passwordResetReviewMode = ref<'approve' | 'reject' | 'reissue' | ''>('')
const passwordResetReviewComment = ref('')
const passwordResetIdentityVerified = ref(false)
const selectedSystemPositions = ref<Record<string, string>>({})
const approvalProfiles = ref<Record<string, RegistrationProfileRequest>>({})
const approvalComments = ref<Record<string, string>>({})
const rejectComments = ref<Record<string, string>>({})
const userSearch = ref('')
const userStatusFilter = ref<'all' | 'active' | 'suspended' | 'retired'>('all')
const selectedRequestId = ref('')
const isLoading = ref(false)
const actionKey = ref('')
const errorMessage = ref('')
const successMessage = ref('')

const canManageUsers = computed(() => authStore.can('system:user_manage'))
const currentAccountName = computed(() => authStore.currentUser?.display_name?.trim() || authStore.currentUser?.username || '当前账号')
const currentAccountCode = computed(() => authStore.currentUser?.username || '已登录')
const organizations = ref<Organization[]>([])
const factoryOptions = computed(() => organizations.value.filter(o => o.kind !== 'group' && o.status === 'active').map(o => ({ id: o.id, shortName: o.name })))
const approvalDepartments = computed(() => organizations.value.find(o => o.id === selectedProfile.value?.factory_id)?.departments ?? [])
async function loadOrganizations() {
  try { organizations.value = (await identityApi.catalog()).organizations } catch (e) { errorMessage.value = getApiErrorMessage(e) }
}
onMounted(loadOrganizations)
const activeUsers = computed(() => users.value.filter((user) => user.status === 'active'))
const pendingUsers = computed(() => users.value.filter((user) => user.status === 'pending'))
const selectedPasswordResetRequest = computed(() =>
  passwordResetRequests.value.find((request) => request.id === selectedPasswordResetId.value)
  ?? passwordResetRequests.value[0]
  ?? null,
)
const selectedRequest = computed(() =>
  requests.value.find((request) => request.id === selectedRequestId.value) ?? requests.value[0] ?? null,
)
const selectedProfile = computed(() => selectedRequest.value ? approvalProfile(selectedRequest.value) : null)
const selectedPositionSuggestions = computed(() => getPositionSuggestions(selectedProfile.value?.department ?? ''))
const allSystemPositions = computed(() => systemPositions.value
  .filter((role) => role.is_system_position)
  .sort((left, right) => left.position_sort_order - right.position_sort_order || left.name.localeCompare(right.name, 'zh-CN')),
)
const groupedSystemPositions = computed(() => {
  const groups = new Map<string, RoleResponse[]>()
  for (const role of allSystemPositions.value) {
    const department = role.position_department || 'other'
    const positions = groups.get(department)
    if (positions) positions.push(role)
    else groups.set(department, [role])
  }
  const orderedGroups = registrationDepartments
    .map((department) => ({
      department: department.id,
      name: department.name,
      positions: groups.get(department.id) ?? [],
    }))
    .filter((group) => group.positions.length)
  const knownDepartments = new Set<string>(registrationDepartments.map((department) => department.id))
  const extraGroups = [...groups.entries()]
    .filter(([department]) => !knownDepartments.has(department))
    .map(([department, positions]) => ({
      department,
      name: departmentLabel(department),
      positions,
    }))
  return [...orderedGroups, ...extraGroups]
})
const selectedApprovalSystemPosition = computed(() => {
  if (!selectedRequest.value) return null
  const selectedRoleId = getSelectedSystemPositionId(selectedRequest.value)
  return systemPositions.value.find((role) => role.id === selectedRoleId) ?? null
})
const recommendedApprovalSystemPosition = computed(() => {
  if (!selectedRequest.value) return null
  const recommendedRoleId = selectedRequest.value.recommended_role_ids
    .find((roleId) => allSystemPositions.value.some((role) => role.id === roleId))
  return allSystemPositions.value.find((role) => role.id === recommendedRoleId) ?? null
})
const filteredUsers = computed(() => {
  const keyword = userSearch.value.trim().toLowerCase()
  return users.value.filter((user) => {
    const statusMatched = userStatusFilter.value === 'all' || user.status === userStatusFilter.value
    if (!statusMatched) return false
    if (!keyword) return true
    return [
      user.username,
      user.display_name,
      user.phone,
      user.email,
      userPosition(user),
      userSystemPositionName(user),
      userPrimaryDepartment(user),
    ].some((value) => value.toLowerCase().includes(keyword))
  })
})

const pendingFootText = computed(() => {
  const earliestSubmission = requests.value.reduce<{ value: string; timestamp: number } | null>((earliest, request) => {
    const timestamp = parseBusinessTimestamp(request.submitted_at)
    if (timestamp === null || (earliest && earliest.timestamp <= timestamp)) return earliest
    return { value: request.submitted_at, timestamp }
  }, null)
  if (!earliestSubmission) return requests.value.length ? '请及时处理新的账号申请' : '暂无待处理申请'
  return `最早提交于 ${formatBusinessDateTime(earliestSubmission.value, { includeSeconds: true })}`
})

function factoryLabel(factoryId: string) {
  return factoryContexts.find((factory) => factory.id === factoryId)?.shortName ?? factoryId
}

function departmentLabel(departmentId: string) {
  return registrationDepartmentLabel(departmentId)
}

const userStatusPresentations: Record<string, { label: string; toneClass: string }> = {
  pending: { label: '待审批', toneClass: 'pill-amber' },
  approved: { label: '已通过', toneClass: 'pill-blue' },
  rejected: { label: '已拒绝', toneClass: 'pill-red' },
  active: { label: '正常', toneClass: 'pill-green' },
  suspended: { label: '已停用', toneClass: 'pill-slate' },
  retired: { label: '已离职', toneClass: 'pill-slate' },
}

function userStatusPresentation(status: string) {
  return userStatusPresentations[status] ?? { label: '未知状态', toneClass: 'pill-slate' }
}

function avatarText(name: string | null | undefined, username: string) {
  const label = (name || username || '').trim()
  if (!label) return '用'
  if (/^[A-Za-z0-9_]+$/.test(label)) return label.slice(0, 2).toUpperCase()
  return label.slice(0, 1)
}

function resolveUserAvatarUrl(value: string | undefined) {
  const avatarUrl = value?.trim()
  if (!avatarUrl || /^https?:\/\//i.test(avatarUrl)) return avatarUrl ?? ''
  const apiBaseUrl = import.meta.env?.VITE_API_BASE_URL
  if (!apiBaseUrl || !/^https?:\/\//i.test(apiBaseUrl)) return avatarUrl
  try {
    return new URL(avatarUrl, apiBaseUrl).toString()
  } catch {
    return avatarUrl
  }
}

function contactLabel(request: RegistrationRequestResponse) {
  return request.phone || request.email || '未填写'
}

const passwordResetStatusOptions: Array<{ value: PasswordResetStatus; label: string }> = [
  { value: 'pending', label: '待审核' },
  { value: 'approved', label: '已批准待改密' },
  { value: 'completed', label: '已完成' },
  { value: 'rejected', label: '已驳回' },
  { value: 'expired', label: '已过期' },
  { value: 'legacy_invalid', label: '旧版申请' },
]

function passwordResetStatusLabel(status: PasswordResetStatus) {
  return passwordResetStatusOptions.find((option) => option.value === status)?.label ?? status
}

function passwordResetStatusTone(status: PasswordResetStatus) {
  return {
    pending: 'pill-amber',
    approved: 'pill-blue',
    completed: 'pill-green',
    rejected: 'pill-red',
    expired: 'pill-slate',
    legacy_invalid: 'pill-slate',
  }[status]
}

function approvalProfile(request: RegistrationRequestResponse) {
  const existing = approvalProfiles.value[request.id]
  if (existing) return existing
  const profile: RegistrationProfileRequest = {
    display_name: request.display_name,
    phone: request.phone,
    email: request.email,
    factory_id: request.org_unit_id || request.factory_id,
    business_factory_ids: [],
    department: request.department,
    position: request.position,
  }
  approvalProfiles.value = { ...approvalProfiles.value, [request.id]: profile }
  return profile
}

function getSelectedSystemPositionId(request: RegistrationRequestResponse) {
  const available = allSystemPositions.value
  const current = selectedSystemPositions.value[request.id]
  if (current && available.some((role) => role.id === current)) return current
  return ''
}

function setSelectedSystemPosition(requestId: string, roleId: string) {
  selectedSystemPositions.value = { ...selectedSystemPositions.value, [requestId]: roleId }
}

function handleProfileDepartmentChange(request: RegistrationRequestResponse) {
  selectedSystemPositions.value = { ...selectedSystemPositions.value, [request.id]: '' }
}

function userPrimaryFactory(user: UserResponse) {
  return user.primary_factory_id || user.roles[0]?.factory_id || ''
}

function userPrimaryDepartment(user: UserResponse) {
  return user.primary_department || user.roles[0]?.department || ''
}

function userPosition(user: UserResponse) {
  return user.position?.trim() || '未填写'
}

function userSystemPositionName(user: UserResponse) {
  return user.system_position_role_name?.trim() || '未分配'
}

function selectRequest(requestId: string) {
  selectedRequestId.value = requestId
}

function ensureSelectedRequest() {
  if (!requests.value.length) {
    selectedRequestId.value = ''
    return
  }
  const requestedId = typeof route.query.request_id === 'string' ? route.query.request_id : ''
  if (requestedId && requests.value.some((request) => request.id === requestedId)) {
    selectedRequestId.value = requestedId
    return
  }
  if (!requests.value.some((request) => request.id === selectedRequestId.value)) {
    selectedRequestId.value = requests.value[0].id
  }
}

function ensureUserManagementPermission() {
  if (canManageUsers.value) return true
  errorMessage.value = '当前账号没有账号管理权限，无法执行该操作。'
  successMessage.value = ''
  return false
}

async function loadData() {
  if (!canManageUsers.value) {
    requests.value = []
    users.value = []
    systemPositions.value = []
    passwordResetRequests.value = []
    selectedRequestId.value = ''
    isLoading.value = false
    actionKey.value = ''
    errorMessage.value = ''
    successMessage.value = ''
    return
  }
  isLoading.value = true
  errorMessage.value = ''
  try {
    const [pendingRequests, loadedUsers, loadedPositions, loadedPasswordResetRequests] = await Promise.all([
      systemApi.listRegistrationRequests('pending'),
      systemApi.listUsers(''),
      systemApi.listSystemPositions(),
      systemApi.listPasswordResetRequests(passwordResetStatus.value),
    ])
    requests.value = pendingRequests
    for (const request of pendingRequests) approvalProfile(request)
    users.value = loadedUsers
    systemPositions.value = loadedPositions
    passwordResetRequests.value = loadedPasswordResetRequests
    const requestedResetId = typeof route.query.request_id === 'string' ? route.query.request_id : ''
    if (requestedResetId && loadedPasswordResetRequests.some((item) => item.id === requestedResetId)) {
      selectedPasswordResetId.value = requestedResetId
    } else if (!loadedPasswordResetRequests.some((item) => item.id === selectedPasswordResetId.value)) {
      selectedPasswordResetId.value = loadedPasswordResetRequests[0]?.id ?? ''
    }
    ensureSelectedRequest()
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    isLoading.value = false
  }
}

async function approveRequest(request: RegistrationRequestResponse) {
  if (!ensureUserManagementPermission()) return
  const source = approvalProfile(request)
  const profile: RegistrationProfileRequest = {
    display_name: source.display_name.trim(),
    phone: source.phone.trim(),
    email: source.email.trim(),
    factory_id: organizations.value.find(o => o.id === source.factory_id)?.factory_id ?? source.factory_id,
    org_unit_id: source.factory_id,
    business_factory_ids: source.business_factory_ids ?? [],
    department: source.department,
    position: source.position.trim(),
  }
  if (!profile.display_name) {
    errorMessage.value = '请输入姓名'
    return
  }
  if (!profile.phone && !profile.email) {
    errorMessage.value = '手机或邮箱至少填写一项'
    return
  }
  if (!profile.org_unit_id || !profile.department) {
    errorMessage.value = '请选择厂区和部门'
    return
  }
  if (!profile.position) {
    errorMessage.value = '请输入确认职位'
    return
  }
  if (profile.position.length > 128) {
    errorMessage.value = '职位不能超过 128 个字符'
    return
  }
  const systemPositionRoleId = getSelectedSystemPositionId(request)
  const selectedPosition = systemPositions.value.find((role) => role.id === systemPositionRoleId)
  if (!selectedPosition?.is_system_position) {
    errorMessage.value = '请选择一个内置权限职位'
    return
  }

  actionKey.value = `approve:${request.id}`
  errorMessage.value = ''
  successMessage.value = ''
  try {
    await systemApi.approveRegistrationRequest(request.id, {
      system_position_role_id: systemPositionRoleId,
      profile,
      review_comment: approvalComments.value[request.id] ?? '',
    })
    successMessage.value = `已通过 ${profile.display_name} 的账号申请`
    await loadData()
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    actionKey.value = ''
  }
}

async function rejectRequest(request: RegistrationRequestResponse) {
  if (!ensureUserManagementPermission()) return
  const comment = (rejectComments.value[request.id] || approvalComments.value[request.id] || '').trim()
  if (!comment) {
    errorMessage.value = '拒绝申请时需要填写原因'
    return
  }
  actionKey.value = `reject:${request.id}`
  errorMessage.value = ''
  successMessage.value = ''
  try {
    await systemApi.rejectRegistrationRequest(request.id, { review_comment: comment })
    successMessage.value = `已拒绝 ${request.display_name} 的账号申请`
    await loadData()
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    actionKey.value = ''
  }
}

async function updateStatus(user: UserResponse, status: 'active' | 'suspended') {
  if (!ensureUserManagementPermission()) return
  actionKey.value = `status:${user.id}:${status}`
  errorMessage.value = ''
  successMessage.value = ''
  try {
    await systemApi.updateUserStatus(user.id, { status })
    successMessage.value = `${user.display_name || user.username} 已${status === 'suspended' ? '停用' : '恢复'}`
    await loadData()
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    actionKey.value = ''
  }
}

async function changePasswordResetStatus(status: PasswordResetStatus) {
  passwordResetStatus.value = status
  selectedPasswordResetId.value = ''
  await loadData()
}

function openPasswordResetReview(
  resetRequest: PasswordResetRequestDetail,
  mode: 'approve' | 'reject' | 'reissue',
) {
  passwordResetReviewTarget.value = resetRequest
  passwordResetReviewMode.value = mode
  passwordResetReviewComment.value = ''
  passwordResetIdentityVerified.value = false
  errorMessage.value = ''
}

function closePasswordResetReview() {
  if (actionKey.value.startsWith('password-reset:')) return
  passwordResetReviewTarget.value = null
  passwordResetReviewMode.value = ''
  passwordResetReviewComment.value = ''
  passwordResetIdentityVerified.value = false
}

async function submitPasswordResetReview() {
  if (!ensureUserManagementPermission() || !passwordResetReviewTarget.value || !passwordResetReviewMode.value) return
  const target = passwordResetReviewTarget.value
  const mode = passwordResetReviewMode.value
  const comment = passwordResetReviewComment.value.trim()
  if (mode === 'reject' && !comment) {
    errorMessage.value = '驳回申请时必须填写原因'
    return
  }
  if (mode !== 'reject' && !passwordResetIdentityVerified.value) {
    errorMessage.value = '批准或重新开放前，必须确认已完成申请人身份核验'
    return
  }
  const reviewComment = comment || '已确认完成员工身份核验'
  actionKey.value = `password-reset:${mode}:${target.id}`
  errorMessage.value = ''
  successMessage.value = ''
  try {
    if (mode === 'reject') {
      await systemApi.rejectPasswordResetRequest(target.id, { review_comment: reviewComment })
      successMessage.value = `已驳回密码重置申请 ${target.id}`
    } else {
      const response = mode === 'approve'
        ? await systemApi.approvePasswordResetRequest(target.id, {
          review_comment: reviewComment,
          identity_verified: true,
        })
        : await systemApi.reissuePasswordResetRequest(target.id, {
          review_comment: reviewComment,
          identity_verified: true,
        })
      successMessage.value = response.message
    }
    passwordResetReviewTarget.value = null
    passwordResetReviewMode.value = ''
    passwordResetReviewComment.value = ''
    passwordResetIdentityVerified.value = false
    await loadData()
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    actionKey.value = ''
  }
}

async function initializeData() {
  if (route.query.tab === 'password-reset') activeTab.value = 'password-reset'
  else if (route.query.tab === 'users') activeTab.value = 'users'
  else if (route.query.request_id) activeTab.value = 'pending'
  const requestedResetId = activeTab.value === 'password-reset' && typeof route.query.request_id === 'string'
    ? route.query.request_id
    : ''
  if (requestedResetId) {
    try {
      const detail = await systemApi.getPasswordResetRequest(requestedResetId)
      passwordResetStatus.value = detail.status
      selectedPasswordResetId.value = detail.id
    } catch {
      // The normal load below will surface permission and availability errors consistently.
    }
  }
  await loadData()
}

onMounted(() => {
  void initializeData()
})
</script>

<template>
  <main class="permission-approval-page">
    <div class="wrap">
      <header
        class="topbar"
        data-portal-region="users-header"
      >
        <div class="topbar-left">
          <RouterLink class="home-exit-link" to="/">
            <ArrowLeft class="size-4" aria-hidden="true" />
            返回首页
          </RouterLink>
          <div class="brand">
            <span class="logo">
              <ShieldCheck class="size-6" aria-hidden="true" />
            </span>
            <div>
              <h1>账号 / 权限职位审批</h1>
              <p>Royal Regent Nexus · 集团账号开通制</p>
            </div>
          </div>
        </div>
        <div class="topbar-actions">
          <nav class="view-tabs" aria-label="账号管理视图">
            <button type="button" :class="{ active: activeTab === 'pending' }" :disabled="!canManageUsers" @click="activeTab = 'pending'">
              待审批
              <span>{{ requests.length }}</span>
            </button>
            <button type="button" :class="{ active: activeTab === 'password-reset' }" :disabled="!canManageUsers" @click="activeTab = 'password-reset'">
              密码重置
              <span>{{ passwordResetRequests.length }}</span>
            </button>
            <button type="button" :class="{ active: activeTab === 'users' }" :disabled="!canManageUsers" @click="activeTab = 'users'">
              用户列表
            </button>
          </nav>
          <RouterLink
            class="ghost-link iam-console-entry"
            to="/system/iam/roles"
          >
            <SlidersHorizontal class="size-4" aria-hidden="true" />
            内置职位权限
          </RouterLink>
          <button type="button" class="ghost-link" :disabled="!canManageUsers || isLoading" @click="loadData">
            <RefreshCw class="size-4" :class="{ 'animate-spin': isLoading }" aria-hidden="true" />
            刷新
          </button>
          <div class="admin">
            <div class="t">{{ currentAccountName }}<small>{{ currentAccountCode }} · {{ canManageUsers ? '账号管理' : '只读访问' }}</small></div>
            <span class="av">{{ avatarText(currentAccountName, currentAccountCode) }}</span>
          </div>
        </div>
      </header>

      <section v-if="!canManageUsers" class="protected-access-notice" data-testid="system-users-protected-notice" role="status">
        <span class="protected-access-icon"><ShieldCheck class="size-5" aria-hidden="true" /></span>
        <div>
          <strong>页面可访问 · 敏感账号资料受保护</strong>
          <p>当前账号没有账号管理权限。申请、用户、审批及密码重置明细不会在此模式下读取或展示，也不能执行任何账号变更。</p>
        </div>
      </section>

      <div v-if="canManageUsers" class="stats rrn-portal-region" data-portal-region="users-stats">
        <article class="stat stat-pending">
          <div class="row">
            <span class="ic amber"><Clock3 class="size-5" aria-hidden="true" /></span>
            <span class="delta up">{{ requests.length ? '待处理' : '清空' }}</span>
          </div>
          <div class="n">{{ requests.length }}</div>
          <div class="lb">待审批申请</div>
        </article>
        <article class="stat stat-active">
          <div class="row">
            <span class="ic teal"><CheckCircle2 class="size-5" aria-hidden="true" /></span>
            <span class="delta up">已开通</span>
          </div>
          <div class="n">{{ activeUsers.length }}</div>
          <div class="lb">在用账号</div>
        </article>
        <article class="stat stat-users">
          <div class="row">
            <span class="ic blue"><Users class="size-5" aria-hidden="true" /></span>
            <span class="delta mut">6 厂区</span>
          </div>
          <div class="n">{{ users.length }}</div>
          <div class="lb">账号总数</div>
        </article>
        <article class="stat stat-reset">
          <div class="row">
            <span class="ic slate"><KeyRound class="size-5" aria-hidden="true" /></span>
            <span class="delta mut">待核验</span>
          </div>
          <div class="n">{{ passwordResetRequests.length }}</div>
          <div class="lb">密码重置</div>
        </article>
      </div>

      <div v-if="errorMessage" class="message message-error">
        <CircleAlert class="size-4 shrink-0" aria-hidden="true" />
        <span>{{ errorMessage }}</span>
      </div>
      <div v-if="successMessage" class="message message-success">
        <CheckCircle2 class="size-4 shrink-0" aria-hidden="true" />
        <span>{{ successMessage }}</span>
      </div>

    <section v-if="canManageUsers && activeTab === 'pending'" class="grid approval-workspace">
      <div v-if="isLoading" class="empty-card">正在加载账号申请...</div>
      <div v-else-if="!requests.length" class="empty-card">当前没有待审批账号。</div>
      <template v-else>
        <aside class="panel queue-panel">
          <div class="panel-head">
            <div class="panel-heading-group">
              <span class="panel-heading-icon"><ClipboardCheck class="size-4" aria-hidden="true" /></span>
              <div class="panel-heading-copy">
                <h2>待审批队列</h2>
                <p>{{ pendingFootText }}</p>
              </div>
            </div>
            <span class="cnt">{{ requests.length }} 待处理</span>
          </div>
          <div class="queue">
            <button
              v-for="request in requests"
              :key="request.id"
              type="button"
              class="q-item"
              :class="{ active: selectedRequest?.id === request.id }"
              @click="selectRequest(request.id)"
            >
              <span class="av">{{ avatarText(request.display_name, request.username) }}</span>
              <span class="info">
                <span class="nm">
                  <span class="badge-dot" aria-hidden="true"></span>
                  <b>{{ request.display_name }}</b>
                  <span class="uid">{{ request.username }}</span>
                </span>
                <span class="meta">{{ factoryLabel(request.factory_id) }} · {{ departmentLabel(request.department) }}</span>
                <span class="pos">申请职位：{{ request.position }}</span>
              </span>
              <span class="time">{{ formatBusinessDateTime(request.submitted_at, { includeSeconds: true }) }}</span>
            </button>
          </div>
        </aside>

        <article v-if="selectedRequest" class="panel detail">
          <div class="applicant applicant-hero">
            <span class="av">{{ avatarText(selectedRequest.display_name, selectedRequest.username) }}</span>
            <div class="h">
              <div><b>{{ selectedRequest.display_name }}</b><span class="uid">{{ selectedRequest.username }}</span></div>
              <div class="tags">
                <span class="tag"><Factory class="size-3.5" aria-hidden="true" />{{ factoryLabel(selectedRequest.factory_id) }}</span>
                <span class="tag"><Building2 class="size-3.5" aria-hidden="true" />{{ departmentLabel(selectedRequest.department) }}</span>
                <span class="tag"><BriefcaseBusiness class="size-3.5" aria-hidden="true" />申请职位：{{ selectedRequest.position }}</span>
                <span class="tag"><Phone v-if="selectedRequest.phone" class="size-3.5" aria-hidden="true" /><Mail v-else class="size-3.5" aria-hidden="true" />{{ contactLabel(selectedRequest) }}</span>
              </div>
            </div>
          </div>

          <section class="section position-review-section approval-surface-section">
            <div class="sec-title">
              <span class="st-ic"><BriefcaseBusiness class="size-4" aria-hidden="true" /></span>
              <div class="sec-title-copy">
                <h3>注册资料核验</h3>
                <span class="hint">资料填错可直接修正；账号 / 工号保持唯一防篡改</span>
              </div>
            </div>
            <div class="registration-review-grid">
              <label class="position-confirm-field">
                <span class="field-label"><span>姓名</span><small>员工真实姓名</small></span>
                <input v-model="approvalProfile(selectedRequest).display_name" aria-label="确认姓名" autocomplete="name" type="text">
              </label>
              <label class="position-confirm-field immutable-field">
                <span class="field-label"><span>账号 / 工号</span><small>只读防篡改</small></span>
                <input :value="selectedRequest.username" aria-label="账号或工号" disabled type="text">
              </label>
              <label class="position-confirm-field">
                <span class="field-label"><span>电话号码</span><small>手机或座机</small></span>
                <input v-model="approvalProfile(selectedRequest).phone" aria-label="确认电话" autocomplete="tel" type="tel">
              </label>
              <label class="position-confirm-field">
                <span class="field-label"><span>企业邮箱</span><small>业务通知接收</small></span>
                <input v-model="approvalProfile(selectedRequest).email" aria-label="确认邮箱" autocomplete="email" type="email">
              </label>
              <label class="position-confirm-field">
                <span class="field-label"><span>所属厂区</span><small>主生产基地</small></span>
                <select v-model="approvalProfile(selectedRequest).factory_id" aria-label="确认厂区" @change="approvalProfile(selectedRequest).department = approvalDepartments[0]?.code ?? ''">
                  <option v-for="factory in factoryOptions" :key="factory.id" :value="factory.id">{{ factory.shortName }}</option>
                </select>
              </label>
              <label class="position-confirm-field">
                <span class="field-label"><span>所属部门</span><small>业务归属</small></span>
                <select v-model="approvalProfile(selectedRequest).department" aria-label="确认部门" @change="handleProfileDepartmentChange(selectedRequest)">
                  <option v-for="department in approvalDepartments" :key="department.code" :value="department.code">{{ department.name }}</option>
                </select>
              </label>
              <label class="position-confirm-field registration-position-field">
                <span class="field-label"><span>真实职位（可修改）</span><small>用于名片与通讯录展示</small></span>
                <input v-model="approvalProfile(selectedRequest).position" aria-label="确认职位" autocomplete="organization-title" list="approval-position-suggestions" maxlength="128" placeholder="请核对或修正员工填写的真实职位" type="text">
                <datalist id="approval-position-suggestions">
                  <option v-for="item in selectedPositionSuggestions" :key="item" :value="item"></option>
                </datalist>
                <span v-if="selectedPositionSuggestions.length" class="position-suggestion-chips" aria-label="真实职位建议">
                  <span v-for="item in selectedPositionSuggestions.slice(0, 4)" :key="item">+ {{ item }}</span>
                </span>
              </label>
            </div>
            <fieldset v-if="selectedProfile?.factory_id === 'group-management'" class="position-confirm-field">
              <legend>业务范围（必须明确选择）</legend>
              <label v-for="factory in organizations.filter(o => o.kind === 'factory' && o.status === 'active')" :key="factory.id">
                <input v-model="approvalProfile(selectedRequest).business_factory_ids" type="checkbox" :value="factory.id" />{{ factory.name }}
              </label>
            </fieldset>
            <p class="position-role-note">
              真实职位只用于个人资料展示；下方内置权限职位才决定系统可用功能。
            </p>
          </section>

          <section class="section approval-surface-section permission-position-section">
            <div class="sec-title">
              <span class="st-ic permission-icon"><ShieldCheck class="size-4" aria-hidden="true" /></span>
              <div class="sec-title-copy">
                <h3>内置权限职位授权</h3>
                <span class="hint">核心安全机制：由系统内置职位决定具体业务模块操作权限</span>
              </div>
            </div>
            <p class="system-position-department-label">
              员工资料部门：<strong>{{ departmentLabel(approvalProfile(selectedRequest).department) }}</strong>；可从全部内置职位中选择权限职位
            </p>
            <div
              v-if="recommendedApprovalSystemPosition && !selectedApprovalSystemPosition"
              class="recommendation-banner"
              data-testid="registration-position-recommendation"
            >
              <span class="recommendation-icon"><Sparkles class="size-4" aria-hidden="true" /></span>
              <span class="recommendation-copy">
                <strong>系统推荐：{{ recommendedApprovalSystemPosition.position_department_name }} · {{ recommendedApprovalSystemPosition.name }}</strong>
                <span>推荐仅用于提示，不会自动选中或授权；请管理员核对后主动选择。</span>
              </span>
              <span class="recommendation-state">需人工确认</span>
            </div>
            <template v-if="allSystemPositions.length">
              <label class="system-position-picker">
                <span class="picker-label"><span>选择内置权限职位</span><small>单选机制 · 统一下发</small></span>
                <select
                  :value="getSelectedSystemPositionId(selectedRequest)"
                  aria-label="选择内置权限职位"
                  @change="setSelectedSystemPosition(selectedRequest.id, ($event.target as HTMLSelectElement).value)"
                >
                  <option value="" disabled>请选择内置权限职位</option>
                  <optgroup v-for="group in groupedSystemPositions" :key="group.department" :label="group.name">
                    <option v-for="role in group.positions" :key="role.id" :value="role.id">
                      {{ role.name }} · {{ role.permission_count ? `${role.permission_count} 项权限` : '权限待配置' }}{{ selectedRequest.recommended_role_ids.includes(role.id) ? ' · 推荐' : '' }}
                    </option>
                  </optgroup>
                </select>
              </label>
              <div
                v-if="selectedApprovalSystemPosition"
                class="selected-system-position-summary"
                data-testid="selected-system-position-summary"
                aria-live="polite"
                aria-atomic="true"
              >
                <span class="selected-system-position-check"><Check class="size-3.5" aria-hidden="true" /></span>
                <div class="selected-system-position-copy">
                  <div class="selected-system-position-title">
                    <strong>{{ departmentLabel(selectedApprovalSystemPosition.position_department) }} · {{ selectedApprovalSystemPosition.name }}</strong>
                    <span v-if="selectedRequest.recommended_role_ids.includes(selectedApprovalSystemPosition.id)">推荐</span>
                  </div>
                  <p :title="selectedApprovalSystemPosition.description || selectedApprovalSystemPosition.code">
                    {{ selectedApprovalSystemPosition.description || selectedApprovalSystemPosition.code }}
                  </p>
                </div>
                <b class="selected-system-position-count">{{ selectedApprovalSystemPosition.permission_count ? `${selectedApprovalSystemPosition.permission_count} 项权限` : '权限待配置' }}</b>
              </div>
            </template>
            <div v-else class="empty-system-positions">
              当前还没有可分配的内置权限职位，请先到“内置职位权限”完成配置。
            </div>
          </section>

          <div class="actions action-dock">
            <label class="action-note-wrap">
              <span>审批备注</span>
              <input
                v-model="approvalComments[selectedRequest.id]"
                class="note-in"
                placeholder="可选，例如：资料已与 HR 核对一致"
                type="text"
              >
            </label>
            <button type="button" class="btn btn-reject" :disabled="Boolean(actionKey)" @click="rejectRequest(selectedRequest)">
              <XCircle class="size-4" aria-hidden="true" />
              驳回申请
            </button>
            <button type="button" class="btn btn-approve" :disabled="Boolean(actionKey)" @click="approveRequest(selectedRequest)">
              <LoaderCircle v-if="actionKey === `approve:${selectedRequest.id}`" class="size-4 animate-spin" aria-hidden="true" />
              <Check v-else class="size-4" aria-hidden="true" />
              <span>{{ actionKey === `approve:${selectedRequest.id}` ? '正在开通...' : '通过并开通账号' }}</span>
            </button>
          </div>
        </article>
      </template>
    </section>

    <section v-else-if="canManageUsers && activeTab === 'password-reset'" class="panel">
      <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div class="seg">
          <button
            v-for="option in passwordResetStatusOptions"
            :key="option.value"
            type="button"
            :class="{ on: passwordResetStatus === option.value }"
            :disabled="isLoading"
            @click="changePasswordResetStatus(option.value)"
          >
            {{ option.label }}
          </button>
        </div>
        <button type="button" class="btn btn-sm" :disabled="isLoading" @click="loadData">
          <RefreshCw class="size-3.5" :class="{ 'animate-spin': isLoading }" aria-hidden="true" />
          刷新申请
        </button>
      </div>
      <div v-if="isLoading" class="empty-card">正在加载密码重置申请...</div>
      <div v-else-if="!passwordResetRequests.length" class="empty-card">当前筛选条件下没有密码重置申请。</div>
      <div v-else class="request-grid">
        <article
          v-for="resetRequest in passwordResetRequests"
          :key="resetRequest.id"
          class="request-card"
          :class="{ 'ring-2 ring-teal-600/30': selectedPasswordResetRequest?.id === resetRequest.id }"
          @click="selectedPasswordResetId = resetRequest.id"
        >
          <div class="request-top">
            <span class="request-avatar">{{ avatarText(resetRequest.display_name, resetRequest.username) }}</span>
            <div class="request-person">
              <h2>{{ resetRequest.display_name || resetRequest.username }}</h2>
              <p>{{ resetRequest.id }}</p>
            </div>
            <span class="pill" :class="passwordResetStatusTone(resetRequest.status)">
              <span></span>{{ passwordResetStatusLabel(resetRequest.status) }}
            </span>
          </div>

          <div class="request-meta">
            <div>
              <KeyRound class="size-4" aria-hidden="true" />
              <span>填写账号</span>
              <b>{{ resetRequest.username || '-' }}</b>
            </div>
            <div>
              <Phone class="size-4" aria-hidden="true" />
              <span>填写联系</span>
              <b>{{ resetRequest.contact || '-' }}</b>
            </div>
            <div class="meta-wide">
              <Clock3 class="size-4" aria-hidden="true" />
              <span>提交</span>
              <b>{{ formatBusinessDateTime(resetRequest.submitted_at, { includeSeconds: true }) }}</b>
            </div>
            <div class="meta-wide">
              <LifeBuoy class="size-4" aria-hidden="true" />
              <span>说明</span>
              <b>{{ resetRequest.note || '未填写补充说明' }}</b>
            </div>
          </div>

          <div v-if="resetRequest.status === 'legacy_invalid'" class="recommend-box">
            <CircleAlert class="size-4 shrink-0 text-amber-700" aria-hidden="true" />
            <b>该申请来自旧版流程，不能批准或重新开放。请申请人在原浏览器重新提交密码重置申请。</b>
          </div>
          <div v-else-if="resetRequest.matched_user" class="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-3 text-[12px] text-slate-600">
            <div class="flex items-center gap-2 font-bold text-slate-800">
              <UserCheck class="size-4 text-teal-700" aria-hidden="true" />
              系统员工资料
            </div>
            <div class="mt-2 grid gap-1 sm:grid-cols-2">
              <span>姓名：<b>{{ resetRequest.matched_user.display_name || '-' }}</b></span>
              <span>账号：<b>{{ resetRequest.matched_user.username }}</b></span>
              <span>厂区：<b>{{ factoryLabel(resetRequest.matched_user.factory_id) || '-' }}</b></span>
              <span>部门：<b>{{ departmentLabel(resetRequest.matched_user.department) || '-' }}</b></span>
              <span>电话：<b>{{ resetRequest.matched_user.phone || '-' }}</b></span>
              <span>邮箱：<b>{{ resetRequest.matched_user.email || '-' }}</b></span>
            </div>
            <div class="mt-2 flex flex-wrap gap-2">
              <span class="pill" :class="resetRequest.match_checks.display_name ? 'pill-green' : 'pill-amber'">姓名{{ resetRequest.match_checks.display_name ? '一致' : '需核验' }}</span>
              <span class="pill" :class="resetRequest.match_checks.contact ? 'pill-green' : 'pill-amber'">联系方式{{ resetRequest.match_checks.contact ? '一致' : '需核验' }}</span>
              <span class="pill" :class="resetRequest.match_checks.scope ? 'pill-green' : 'pill-amber'">厂区部门{{ resetRequest.match_checks.scope ? '一致' : '需核验' }}</span>
            </div>
          </div>
          <div v-else class="recommend-box">
            <CircleAlert class="size-4 shrink-0 text-amber-700" aria-hidden="true" />
            <b>未匹配系统账号，不能批准。请人工核验后驳回，禁止通过前端猜测或关联账号。</b>
          </div>

          <div class="request-actions">
            <button
              v-if="resetRequest.status === 'pending' && resetRequest.matched_user"
              type="button"
              class="btn btn-primary"
              :disabled="Boolean(actionKey)"
              @click.stop="openPasswordResetReview(resetRequest, 'approve')"
            >
              <KeyRound class="size-4" aria-hidden="true" />
              批准并开放自助改密
            </button>
            <button
              v-if="resetRequest.status === 'pending'"
              type="button"
              class="btn btn-danger"
              :disabled="Boolean(actionKey)"
              @click.stop="openPasswordResetReview(resetRequest, 'reject')"
            >
              <XCircle class="size-4" aria-hidden="true" />
              驳回
            </button>
            <button
              v-if="resetRequest.status === 'expired' && resetRequest.matched_user"
              type="button"
              class="btn btn-primary"
              :disabled="Boolean(actionKey)"
              @click.stop="openPasswordResetReview(resetRequest, 'reissue')"
            >
              <RefreshCw class="size-4" aria-hidden="true" />
              重新开放 4 小时
            </button>
          </div>
        </article>
      </div>
    </section>

    <section v-else-if="canManageUsers" class="panel users-panel">
      <div class="table-tools">
        <label class="search-box">
          <Search class="size-4" aria-hidden="true" />
          <input v-model="userSearch" aria-label="搜索用户" placeholder="搜索姓名、工号、联系方式、个人职位或权限职位..." type="search">
        </label>
        <div class="seg">
          <button type="button" :class="{ on: userStatusFilter === 'all' }" @click="userStatusFilter = 'all'">全部</button>
          <button type="button" :class="{ on: userStatusFilter === 'active' }" @click="userStatusFilter = 'active'">正常</button>
          <button type="button" :class="{ on: userStatusFilter === 'suspended' }" @click="userStatusFilter = 'suspended'">停用</button>
          <button type="button" :class="{ on: userStatusFilter === 'retired' }" @click="userStatusFilter = 'retired'">已离职</button>
        </div>
      </div>

      <div class="table-wrap">
        <table class="user-table">
          <thead>
            <tr>
              <th>用户</th>
              <th>联系方式</th>
              <th>厂区 / 部门</th>
              <th>个人职位</th>
              <th>权限职位</th>
              <th>状态</th>
              <th>最后登录</th>
              <th class="ops-head">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!filteredUsers.length">
              <td colspan="8" class="empty-row">没有匹配的账号。</td>
            </tr>
            <tr v-for="user in filteredUsers" v-else :key="user.id">
              <td>
                <div class="user-cell">
                  <UserAvatar
                    class="user-avatar"
                    :src="resolveUserAvatarUrl(user.avatar_url)"
                    :name="user.display_name || user.username"
                    :alt="`${user.display_name || user.username}的头像`"
                    shape="rounded"
                  />
                  <div class="user-identity">
                    <strong>{{ user.display_name || user.username }}</strong>
                    <span>{{ user.username }}</span>
                  </div>
                </div>
              </td>
              <td>
                <div class="contact-cell">
                  <span v-if="user.phone"><Phone class="size-3.5" aria-hidden="true" />{{ user.phone }}</span>
                  <span v-if="user.email"><Mail class="size-3.5" aria-hidden="true" />{{ user.email }}</span>
                  <span v-if="!user.phone && !user.email" class="muted small">未填写</span>
                </div>
              </td>
              <td class="muted">
                {{ userPrimaryFactory(user) ? factoryLabel(userPrimaryFactory(user)) : '待确认' }} · {{ userPrimaryDepartment(user) ? departmentLabel(userPrimaryDepartment(user)) : '待确认' }}
              </td>
              <td><span class="employee-position-text">{{ userPosition(user) }}</span></td>
              <td>
                <div class="role-tags">
                  <span v-if="user.system_position_role_id" class="pill pill-teal"><span></span>{{ userSystemPositionName(user) }}</span>
                  <span v-else class="tag">未分配</span>
                </div>
              </td>
              <td>
                <span class="pill" :class="userStatusPresentation(user.status).toneClass">
                  <span></span>{{ userStatusPresentation(user.status).label }}
                </span>
              </td>
              <td class="muted">{{ formatBusinessDateTime(user.last_login_at, { includeSeconds: true }) }}</td>
              <td>
                <div class="row-ops">
                  <RouterLink
                    v-if="authStore.can('system:access_manage') && (user.status === 'active' || user.status === 'suspended')"
                    class="btn btn-sm iam-access-link"
                    :to="`/system/users/${encodeURIComponent(user.id)}/access`"
                  >
                    <SlidersHorizontal class="size-3.5" aria-hidden="true" />
                    调整权限职位
                  </RouterLink>
                  <button
                    v-if="user.status === 'active'"
                    type="button"
                    class="btn btn-danger btn-sm"
                    :disabled="Boolean(actionKey)"
                    @click="updateStatus(user, 'suspended')"
                  >
                    <UserRoundX class="size-3.5" aria-hidden="true" />
                    停用
                  </button>
                  <button
                    v-else-if="user.status === 'suspended'"
                    type="button"
                    class="btn btn-primary btn-sm"
                    :disabled="Boolean(actionKey)"
                    @click="updateStatus(user, 'active')"
                  >
                    <ShieldCheck class="size-3.5" aria-hidden="true" />
                    恢复
                  </button>
                  <span v-else class="muted small">无操作</span>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
        <div class="table-foot">
          <span>共 {{ users.length }} 个账号 · 当前显示 {{ filteredUsers.length }} 个 · 待审批账号 {{ pendingUsers.length }} 个</span>
          <span class="table-foot-badge"><UserCog class="size-3.5" aria-hidden="true" /> 内置职位授权</span>
        </div>
      </div>
    </section>

    <div
      v-if="passwordResetReviewTarget"
      class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/55 px-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="password-reset-review-title"
      @click.self="closePasswordResetReview"
    >
      <section class="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-5 shadow-2xl">
        <div class="flex items-start gap-3">
          <span class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-teal-50 text-teal-700">
            <ClipboardCheck class="size-5" aria-hidden="true" />
          </span>
          <div class="min-w-0 flex-1">
            <h2 id="password-reset-review-title" class="text-base font-bold text-slate-950">
              {{ passwordResetReviewMode === 'reject' ? '驳回密码重置申请' : passwordResetReviewMode === 'reissue' ? '重新开放改密时限' : '批准并开放自助改密' }}
            </h2>
            <p class="mt-1 text-xs leading-5 text-slate-500">申请 {{ passwordResetReviewTarget.id }} · {{ passwordResetReviewTarget.display_name || passwordResetReviewTarget.username }}</p>
          </div>
        </div>
        <div v-if="passwordResetReviewMode === 'reissue'" class="mt-4 rounded-xl border border-amber-100 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800">
          将仅把原设备自助改密时限重新开放 4 小时，不会生成密码、修改用户密码或撤销现有会话。
        </div>
        <div v-else-if="passwordResetReviewMode === 'approve'" class="mt-4 rounded-xl border border-teal-100 bg-teal-50 px-3 py-2 text-xs leading-5 text-teal-900">
          审核通过后，申请人只能在提交申请的原浏览器中设置新密码。系统不会生成或显示临时密码。
        </div>
        <label class="mt-4 block">
          <span class="mb-1.5 block text-xs font-bold text-slate-700">{{ passwordResetReviewMode === 'reject' ? '驳回原因' : '审核 / 核验说明' }}</span>
          <textarea v-model="passwordResetReviewComment" class="min-h-24 w-full resize-none rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm outline-none focus:border-teal-700 focus:bg-white focus:ring-[3px] focus:ring-teal-700/15" :placeholder="passwordResetReviewMode === 'reject' ? '请说明资料无法核验的原因' : '例如：已电话核验员工身份'"></textarea>
        </label>
        <label v-if="passwordResetReviewMode !== 'reject'" class="mt-3 flex cursor-pointer items-start gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-xs leading-5 text-slate-700">
          <input v-model="passwordResetIdentityVerified" class="mt-0.5 size-4" type="checkbox">
          <span>我已通过内部资料或本人确认，核验申请人与账号本人一致。</span>
        </label>
        <div class="mt-5 flex justify-end gap-2">
          <button type="button" class="btn" :disabled="Boolean(actionKey)" @click="closePasswordResetReview">取消</button>
          <button type="button" class="btn" :class="passwordResetReviewMode === 'reject' ? 'btn-danger' : 'btn-primary'" :disabled="Boolean(actionKey) || (passwordResetReviewMode !== 'reject' && !passwordResetIdentityVerified)" @click="submitPasswordResetReview">
            <LoaderCircle v-if="actionKey.startsWith('password-reset:')" class="size-4 animate-spin" aria-hidden="true" />
            <CheckCircle2 v-else class="size-4" aria-hidden="true" />
            确认{{ passwordResetReviewMode === 'reject' ? '驳回' : passwordResetReviewMode === 'reissue' ? '重新开放' : '批准' }}
          </button>
        </div>
      </section>
    </div>

    </div>
  </main>
</template>

<style scoped>
.access-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.system-page-shell {
  min-height: 100vh;
  background: #f1f5f9;
  padding: 24px clamp(16px, 3vw, 42px);
}

.access-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
}

.eyebrow-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.eyebrow-mark {
  display: grid;
  width: 40px;
  height: 40px;
  place-items: center;
  border: 1px solid #99f6e4;
  border-radius: 12px;
  background: #f0fdfa;
  color: #0f766e;
}

.eyebrow {
  color: #64748b;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.22em;
  text-transform: uppercase;
}

.access-head h1 {
  margin: 12px 0 0;
  color: #020617;
  font-size: 30px;
  font-weight: 650;
  letter-spacing: -0.02em;
}

.access-head p {
  margin: 8px 0 0;
  color: #475569;
  font-size: 13px;
}

.head-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.stat-card {
  position: relative;
  overflow: hidden;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  background: white;
  padding: 18px 20px;
  box-shadow: 0 14px 35px rgb(15 23 42 / 5%);
}

.stat-card::before {
  position: absolute;
  inset: 0 auto 0 0;
  width: 4px;
  content: "";
}

.stat-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: #475569;
  font-size: 13px;
  font-weight: 700;
}

.stat-icon {
  display: grid;
  width: 36px;
  height: 36px;
  place-items: center;
  border-radius: 10px;
}

.stat-card strong {
  display: block;
  margin-top: 12px;
  color: #020617;
  font-size: 34px;
  font-weight: 800;
  letter-spacing: -0.02em;
  line-height: 1;
}

.stat-card p {
  margin: 8px 0 0;
  color: #64748b;
  font-size: 12px;
}

.stat-amber::before {
  background: #f59e0b;
}

.stat-amber .stat-icon {
  background: #fffbeb;
  color: #b45309;
}

.stat-green::before {
  background: #10b981;
}

.stat-green .stat-icon {
  background: #ecfdf5;
  color: #047857;
}

.stat-slate::before {
  background: #94a3b8;
}

.stat-slate .stat-icon {
  background: #f8fafc;
  color: #475569;
}

.stat-blue::before {
  background: #2563eb;
}

.stat-blue .stat-icon {
  background: #eff6ff;
  color: #1d4ed8;
}

.message {
  display: flex;
  align-items: center;
  gap: 8px;
  border-radius: 10px;
  padding: 12px 14px;
  font-size: 13px;
  font-weight: 700;
}

.message-error {
  border: 1px solid #fecaca;
  background: #fef2f2;
  color: #b91c1c;
}

.message-success {
  border: 1px solid #a7f3d0;
  background: #ecfdf5;
  color: #047857;
}

.protected-access-notice {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  border: 1px solid #cbd5e1;
  border-radius: 14px;
  background: #fff;
  padding: 18px 20px;
  color: #334155;
  box-shadow: 0 1px 2px rgb(15 23 42 / 4%);
}

.protected-access-icon {
  display: grid;
  width: 38px;
  height: 38px;
  flex: none;
  place-items: center;
  border-radius: 11px;
  background: #f0fdfa;
  color: #0f766e;
}

.protected-access-notice strong {
  display: block;
  color: #0f172a;
  font-size: 14px;
}

.protected-access-notice p {
  margin: 5px 0 0;
  color: #64748b;
  font-size: 13px;
  line-height: 1.7;
}

.tabs {
  display: inline-flex;
  width: fit-content;
  gap: 4px;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  background: #f8fafc;
  padding: 4px;
}

.tab {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  border: 0;
  border-radius: 10px;
  background: transparent;
  color: #475569;
  font-size: 13px;
  font-weight: 700;
  padding: 9px 18px;
  transition: background 0.15s ease, color 0.15s ease, box-shadow 0.15s ease;
}

.tab.active {
  background: #0f766e;
  color: white;
  box-shadow: 0 6px 16px rgb(13 118 110 / 28%);
}

.tab-count {
  display: inline-grid;
  min-width: 20px;
  height: 20px;
  place-items: center;
  border-radius: 999px;
  background: #fffbeb;
  color: #b45309;
  font-size: 11px;
  font-weight: 800;
  padding: 0 6px;
}

.tab.active .tab-count {
  background: rgb(255 255 255 / 22%);
  color: white;
}

.panel {
  margin-top: -2px;
}

.approval-workspace {
  margin-top: -2px;
}

.approval-grid {
  display: grid;
  grid-template-columns: 380px minmax(0, 1fr);
  align-items: start;
  gap: 18px;
}

.approval-queue,
.approval-detail {
  overflow: hidden;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  background: white;
  box-shadow: 0 1px 2px rgb(2 6 23 / 4%), 0 12px 32px rgb(2 6 23 / 4%);
}

.approval-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #f1f5f9;
  padding: 15px 18px;
}

.approval-panel-head h2 {
  margin: 0;
  color: #0f172a;
  font-size: 14px;
  font-weight: 800;
}

.approval-panel-head span {
  border-radius: 999px;
  background: #f0fdfa;
  color: #0f766e;
  font-size: 11.5px;
  font-weight: 700;
  padding: 3px 9px;
}

.queue-list {
  max-height: 640px;
  overflow-y: auto;
}

.queue-item {
  display: flex;
  width: 100%;
  gap: 12px;
  border: 0;
  border-bottom: 1px solid #f1f5f9;
  border-left: 3px solid transparent;
  background: white;
  cursor: pointer;
  padding: 14px 18px;
  text-align: left;
  transition: background 0.15s ease, border-color 0.15s ease;
}

.queue-item:hover {
  background: #f8fafc;
}

.queue-item.active {
  border-left-color: #0f766e;
  background: #f0fdfa;
}

.queue-avatar {
  display: grid;
  width: 40px;
  height: 40px;
  flex: none;
  place-items: center;
  border-radius: 11px;
  background: linear-gradient(135deg, #0f766e, #0d9488);
  color: white;
  font-size: 14px;
  font-weight: 800;
}

.queue-info {
  min-width: 0;
  flex: 1;
}

.queue-name,
.queue-meta,
.queue-position,
.queue-time {
  display: block;
}

.queue-name {
  display: flex;
  align-items: center;
  gap: 7px;
}

.queue-name b {
  color: #0f172a;
  font-size: 13.5px;
  font-weight: 800;
}

.queue-name small {
  color: #94a3b8;
  font-size: 11.5px;
}

.queue-dot {
  width: 7px;
  height: 7px;
  flex: none;
  border-radius: 999px;
  background: #f59e0b;
}

.queue-meta {
  overflow: hidden;
  margin-top: 4px;
  color: #64748b;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.queue-position {
  display: inline-flex;
  align-items: center;
  margin-top: 6px;
  border: 1px solid #ccfbf1;
  border-radius: 7px;
  background: #f0fdfa;
  color: #115e59;
  font-size: 11.5px;
  font-weight: 700;
  padding: 2px 8px;
}

.queue-time {
  flex: none;
  color: #94a3b8;
  font-size: 11px;
  line-height: 1.5;
  text-align: right;
}

.applicant-block {
  display: flex;
  gap: 14px;
  border-bottom: 1px solid #f1f5f9;
  background: linear-gradient(180deg, #f8fafc, white);
  padding: 20px;
}

.applicant-avatar {
  display: grid;
  width: 56px;
  height: 56px;
  flex: none;
  place-items: center;
  border-radius: 14px;
  background: linear-gradient(135deg, #0f766e, #0d9488);
  color: white;
  font-size: 20px;
  font-weight: 800;
  box-shadow: 0 8px 20px rgb(15 118 110 / 25%);
}

.applicant-main {
  min-width: 0;
}

.applicant-main h2 {
  margin: 0;
  color: #020617;
  font-size: 17px;
  font-weight: 800;
}

.applicant-main h2 span {
  margin-left: 8px;
  color: #94a3b8;
  font-size: 12.5px;
  font-weight: 500;
}

.applicant-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin-top: 9px;
}

.applicant-tags span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border: 1px solid #e2e8f0;
  border-radius: 7px;
  background: white;
  color: #475569;
  font-size: 11.5px;
  font-weight: 600;
  padding: 3px 9px;
}

.applicant-tags svg {
  color: #94a3b8;
}

.approval-section {
  border-bottom: 1px solid #f1f5f9;
  padding: 18px 20px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 13px;
}

.section-title > span {
  display: grid;
  width: 26px;
  height: 26px;
  place-items: center;
  border-radius: 8px;
  background: #f0fdfa;
  color: #0f766e;
}

.section-title h3 {
  margin: 0;
  color: #0f172a;
  font-size: 13px;
  font-weight: 800;
}

.section-title small {
  color: #94a3b8;
  font-size: 11.5px;
}

.role-card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
  gap: 10px;
}

.approval-role-card {
  position: relative;
  min-height: 82px;
  border: 1.5px solid #e2e8f0;
  border-radius: 12px;
  background: white;
  cursor: pointer;
  padding: 12px 13px;
  text-align: left;
  transition: border-color 0.15s ease, background 0.15s ease, box-shadow 0.15s ease;
}

.approval-role-card:hover {
  border-color: #99f6e4;
}

.approval-role-card.selected {
  border-color: #0f766e;
  background: #f0fdfa;
  box-shadow: 0 0 0 3px rgb(15 118 110 / 15%);
}

.approval-role-card b {
  display: block;
  color: #0f172a;
  font-size: 13px;
  font-weight: 800;
}

.approval-role-card small {
  display: block;
  margin-top: 4px;
  color: #64748b;
  font-size: 11.5px;
  line-height: 1.5;
}

.role-reco {
  position: absolute;
  top: -8px;
  right: 10px;
  border-radius: 999px;
  background: #0f766e;
  color: white;
  font-size: 10px;
  font-weight: 800;
  padding: 2px 8px;
  box-shadow: 0 3px 8px rgb(15 118 110 / 30%);
}

.role-check {
  position: absolute;
  top: 10px;
  right: 10px;
  display: none;
  color: #0f766e;
}

.approval-role-card.selected .role-check {
  display: block;
}

.perm-groups {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 22px;
}

.perm-group {
  min-width: 0;
}

.perm-group h4 {
  margin: 0 0 8px;
  color: #94a3b8;
  font-size: 11.5px;
  font-weight: 800;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.perm {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
  padding: 6px 0;
}

.cbx {
  display: grid;
  width: 18px;
  height: 18px;
  flex: none;
  place-items: center;
  border: 1.5px solid #cbd5e1;
  border-radius: 5px;
  color: white;
  transition: background 0.15s ease, border-color 0.15s ease;
}

.perm.on .cbx {
  border-color: #0f766e;
  background: #0f766e;
}

.pt {
  min-width: 0;
  color: #475569;
  font-size: 12.5px;
  font-weight: 600;
}

.pc {
  margin-left: auto;
  overflow: hidden;
  color: #94a3b8;
  font-family: "Cascadia Code", Consolas, monospace;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.perm.locked {
  opacity: 0.58;
}

.perm.locked .pc {
  color: #64748b;
}

.scope-block {
  margin-bottom: 14px;
}

.scope-block:last-child {
  margin-bottom: 0;
}

.scope-block p {
  margin: 0 0 8px;
  color: #475569;
  font-size: 12px;
  font-weight: 700;
}

.scope-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.scope-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1.5px solid #e2e8f0;
  border-radius: 999px;
  background: white;
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
  padding: 5px 13px;
  transition: border-color 0.15s ease, background 0.15s ease, color 0.15s ease;
}

.scope-chip.active {
  border-color: #0f766e;
  background: #f0fdfa;
  color: #115e59;
}

.scope-chip.all {
  border-style: dashed;
}

.scope-chip span {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: #cbd5e1;
}

.scope-chip.active span {
  background: #0f766e;
}

.approval-note-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.approval-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  border-top: 1px solid #f1f5f9;
  background: #f8fafc;
  padding: 16px 20px;
}

.request-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 14px;
}

.request-card {
  display: flex;
  flex-direction: column;
  gap: 13px;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  background: white;
  padding: 18px;
  box-shadow: 0 16px 38px rgb(15 23 42 / 6%);
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}

.request-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 24px 60px rgb(15 23 42 / 14%);
}

.request-top {
  display: flex;
  align-items: center;
  gap: 12px;
}

.request-avatar,
.user-avatar {
  display: grid;
  flex: none;
  place-items: center;
  background: #0f766e;
  color: white;
  font-weight: 800;
}

.request-avatar {
  width: 42px;
  height: 42px;
  border-radius: 12px;
  font-size: 16px;
}

.request-person {
  min-width: 0;
  flex: 1;
}

.request-person h2 {
  margin: 0;
  color: #020617;
  font-size: 15px;
  font-weight: 800;
}

.request-person p {
  margin: 2px 0 0;
  color: #64748b;
  font-family: "Cascadia Code", Consolas, monospace;
  font-size: 12px;
}

.request-meta {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 14px;
  border-block: 1px dashed #e2e8f0;
  padding: 12px 0;
}

.request-meta div {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
  color: #334155;
  font-size: 12.5px;
}

.request-meta svg {
  flex: none;
  color: #94a3b8;
}

.request-meta span {
  color: #64748b;
}

.request-meta b {
  min-width: 0;
  overflow: hidden;
  color: #334155;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.meta-wide {
  grid-column: 1 / -1;
}

.recommend-box {
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid #99f6e4;
  border-radius: 10px;
  background: #f0fdfa;
  color: #0f766e;
  font-size: 12.5px;
  padding: 9px 12px;
}

.recommend-box b {
  font-weight: 800;
}

.review-controls {
  display: grid;
  gap: 8px;
}

.review-controls label > span {
  display: block;
  margin-bottom: 6px;
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
}

.field {
  width: 100%;
  height: 40px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fafc;
  color: #020617;
  font: inherit;
  font-size: 13px;
  outline: none;
  padding: 0 10px;
  transition: border-color 0.15s ease, background 0.15s ease, box-shadow 0.15s ease;
}

.field:focus {
  border-color: #0f766e;
  background: white;
  box-shadow: 0 0 0 3px rgb(15 118 110 / 12%);
}

.request-actions {
  display: flex;
  gap: 9px;
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: white;
  color: #475569;
  font-size: 13px;
  font-weight: 700;
  padding: 9px 16px;
  transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease, transform 0.1s ease;
}

.btn:hover {
  border-color: #cbd5e1;
  background: #f8fafc;
}

.btn:active {
  transform: scale(0.99);
}

.btn:disabled {
  cursor: wait;
  opacity: 0.65;
  transform: none;
}

.btn-primary {
  flex: 1;
  border-color: #0f766e;
  background: #0f766e;
  color: white;
}

.btn-primary:hover {
  border-color: #115e59;
  background: #115e59;
}

.btn-danger {
  flex: 1;
  border-color: #cbd5e1;
  color: #b91c1c;
}

.btn-danger:hover {
  border-color: #fecaca;
  background: #fef2f2;
}

.btn-sm {
  flex: none;
  height: 32px;
  border-radius: 8px;
  font-size: 12px;
  padding: 0 10px;
}

.pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  width: fit-content;
  border: 1px solid transparent;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 800;
  line-height: 1.4;
  padding: 3px 10px;
  white-space: nowrap;
}

.pill > span {
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: currentColor;
}

.pill-amber {
  border-color: #fde68a;
  background: #fffbeb;
  color: #b45309;
}

.pill-green {
  border-color: #a7f3d0;
  background: #ecfdf5;
  color: #047857;
}

.pill-slate {
  border-color: #e2e8f0;
  background: #f8fafc;
  color: #475569;
}

.pill-blue {
  border-color: #bfdbfe;
  background: #eff6ff;
  color: #1e40af;
}

.pill-violet {
  border-color: #ddd6fe;
  background: #f5f3ff;
  color: #6d28d9;
}

.pill-teal {
  border-color: #99f6e4;
  background: #f0fdfa;
  color: #0f766e;
}

.pill-red {
  border-color: #fecaca;
  background: #fef2f2;
  color: #b91c1c;
}

.empty-card {
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  background: white;
  color: #64748b;
  font-size: 13px;
  padding: 42px 20px;
  text-align: center;
}

.users-panel {
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  background: white;
  box-shadow: 0 14px 35px rgb(15 23 42 / 5%);
  overflow: hidden;
}

.table-tools {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid #f1f5f9;
  padding: 14px;
}

.search-box {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 260px;
  height: 38px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: white;
  color: #94a3b8;
  padding: 0 13px;
}

.search-box input {
  min-width: 0;
  flex: 1;
  border: 0;
  background: transparent;
  color: #020617;
  font: inherit;
  font-size: 13px;
  outline: none;
}

.search-box input::placeholder {
  color: #94a3b8;
}

.seg {
  display: inline-flex;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #f8fafc;
  padding: 3px;
}

.seg button {
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: #475569;
  font-size: 12.5px;
  font-weight: 700;
  padding: 6px 14px;
}

.seg button.on {
  background: white;
  color: #020617;
  box-shadow: 0 10px 24px rgb(15 23 42 / 6%);
}

.table-wrap {
  overflow-x: auto;
}

.user-table {
  min-width: 1120px;
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.user-table th {
  border-bottom: 1px solid #e2e8f0;
  background: #f8fafc;
  color: #64748b;
  font-size: 12px;
  font-weight: 800;
  padding: 10px 12px;
  text-align: left;
  white-space: nowrap;
}

.user-table td {
  border-bottom: 1px solid #e2e8f0;
  color: #334155;
  padding: 12px;
  vertical-align: middle;
}

.user-table tbody tr:hover {
  background: #f8fafc;
}

.user-table tbody tr:last-child td {
  border-bottom: 0;
}

.ops-head {
  text-align: right;
}

.user-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}

.user-avatar {
  width: 34px;
  height: 34px;
  border-radius: 9px;
  font-size: 12px;
}

.user-identity strong {
  display: block;
  color: #020617;
  font-size: 13px;
}

.user-identity span {
  display: block;
  color: #64748b;
  font-family: "Cascadia Code", Consolas, monospace;
  font-size: 11px;
}

.contact-cell {
  display: grid;
  gap: 5px;
  color: #475569;
  font-size: 12px;
}

.contact-cell span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.contact-cell svg {
  flex: none;
  color: #0f766e;
}

.role-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.tag {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  background: #f1f5f9;
  color: #64748b;
  font-size: 11px;
  font-weight: 700;
  padding: 3px 8px;
}

.muted {
  color: #64748b;
}

.small {
  font-size: 12px;
}

.row-ops {
  display: flex;
  gap: 6px;
  justify-content: flex-end;
}

.iam-access-link {
  border-color: #a7f3d0;
  background: #ecfdf5;
  color: #047857;
  text-decoration: none;
}

.iam-access-link:hover {
  border-color: #6ee7b7;
  background: #d1fae5;
}

.empty-row {
  color: #64748b;
  padding: 34px 12px !important;
  text-align: center;
}

.table-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-top: 1px solid #e2e8f0;
  color: #64748b;
  font-size: 12px;
  padding: 12px 14px;
}

.table-foot-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border-radius: 999px;
  background: #f0fdfa;
  color: #0f766e;
  font-weight: 800;
  padding: 4px 9px;
}

@media (max-width: 900px) {
  .access-head {
    align-items: stretch;
    flex-direction: column;
  }

  .head-actions {
    justify-content: flex-start;
  }

  .stats-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .perm-groups {
    grid-template-columns: 1fr;
  }

  .request-grid {
    grid-template-columns: 1fr;
  }

  .request-meta {
    grid-template-columns: 1fr;
  }

  .search-box {
    width: 100%;
    min-width: 0;
  }

  .table-foot {
    align-items: flex-start;
    flex-direction: column;
  }
}

.permission-approval-page {
  --teal: #0f766e;
  --teal-hover: #0d9488;
  --teal-50: #f0fdfa;
  --teal-100: #ccfbf1;
  --teal-200: #99f6e4;
  --teal-700: #0f766e;
  --teal-800: #115e59;
  --ink: #020617;
  --slate-950: #020617;
  --slate-900: #0f172a;
  --slate-800: #1e293b;
  --slate-700: #334155;
  --slate-600: #475569;
  --slate-500: #64748b;
  --slate-400: #94a3b8;
  --slate-300: #cbd5e1;
  --slate-200: #e2e8f0;
  --slate-100: #f1f5f9;
  --slate-50: #f8fafc;
  --ring: rgb(15 118 110 / 15%);
  --radius-lg: 16px;
  --radius-md: 12px;
  --radius-sm: 10px;

  min-height: 100vh;
  background:
    radial-gradient(circle at top left, rgb(14 165 233 / 6%), transparent 32%),
    linear-gradient(180deg, #f8fafc, #eef4f8);
  color: var(--ink);
  font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI", system-ui, sans-serif;
  -webkit-font-smoothing: antialiased;
}

.permission-approval-page svg {
  display: block;
}

.wrap {
  max-width: 1240px;
  margin: 0 auto;
  padding: 26px 24px 48px;
}

.topbar {
  position: sticky;
  top: 0;
  z-index: 30;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin: 0 -24px 22px;
  border-bottom: 1px solid rgb(226 232 240 / 86%);
  background: rgb(248 250 252 / 92%);
  box-shadow: 0 8px 22px rgb(15 23 42 / 3%);
  padding: 12px 24px;
  backdrop-filter: blur(14px);
}

.topbar-left {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 14px;
}

.home-exit-link {
  display: inline-flex;
  min-height: 38px;
  flex: none;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: 1px solid var(--slate-200);
  border-radius: 10px;
  background: white;
  color: var(--slate-700);
  box-shadow: 0 2px 8px rgb(2 6 23 / 4%);
  cursor: pointer;
  font-size: 12.5px;
  font-weight: 800;
  padding: 0 12px;
  text-decoration: none;
  transition: border-color 0.15s, background 0.15s, color 0.15s, transform 0.15s;
}

.home-exit-link:hover {
  border-color: var(--teal-200);
  background: var(--teal-50);
  color: var(--teal-800);
  transform: translateY(-1px);
}

.home-exit-link:focus-visible,
.view-tabs button:focus-visible,
.ghost-link:focus-visible {
  outline: 3px solid var(--ring);
  outline-offset: 2px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.brand .logo {
  display: grid;
  width: 46px;
  height: 46px;
  place-items: center;
  border-radius: 12px;
  background: var(--slate-950);
  color: white;
  box-shadow: 0 8px 20px rgb(2 6 23 / 24%);
}

.brand h1 {
  margin: 0;
  color: var(--slate-950);
  font-size: 17px;
  font-weight: 800;
  letter-spacing: -0.01em;
}

.brand p {
  margin: 2px 0 0;
  color: var(--slate-500);
  font-size: 12px;
}

.topbar-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-left: auto;
  justify-content: flex-end;
}

.admin {
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid var(--slate-200);
  border-radius: 999px;
  background: white;
  padding: 5px 6px 5px 14px;
  box-shadow: 0 2px 8px rgb(2 6 23 / 4%);
}

.admin .t {
  color: var(--slate-700);
  font-size: 12.5px;
  font-weight: 700;
}

.admin .t small {
  display: block;
  color: var(--slate-400);
  font-size: 11px;
  font-weight: 500;
}

.admin .av {
  display: grid;
  width: 34px;
  height: 34px;
  place-items: center;
  border-radius: 999px;
  background: var(--teal);
  color: white;
  font-size: 13px;
  font-weight: 800;
}

.view-tabs {
  display: inline-flex;
  gap: 4px;
  border: 1px solid var(--slate-200);
  border-radius: 999px;
  background: white;
  padding: 4px;
  box-shadow: 0 2px 8px rgb(2 6 23 / 4%);
}

.view-tabs button,
.ghost-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 34px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: var(--slate-600);
  cursor: pointer;
  font: inherit;
  font-size: 12px;
  font-weight: 800;
  padding: 0 12px;
  text-decoration: none;
  transition: background 0.15s, color 0.15s;
}

.view-tabs button.active {
  background: var(--teal);
  color: white;
}

.view-tabs span {
  display: inline-grid;
  min-width: 18px;
  height: 18px;
  place-items: center;
  border-radius: 999px;
  background: rgb(255 255 255 / 20%);
  color: currentColor;
  font-size: 10px;
}

.ghost-link {
  border: 1px solid var(--slate-200);
  background: white;
  box-shadow: 0 2px 8px rgb(2 6 23 / 4%);
}

.ghost-link:hover,
.view-tabs button:hover {
  background: var(--slate-50);
  color: var(--slate-900);
}

.stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
  margin-bottom: 22px;
}

.stat {
  border: 1px solid var(--slate-200);
  border-radius: var(--radius-md);
  background: white;
  padding: 16px 18px;
  box-shadow: 0 1px 2px rgb(2 6 23 / 4%), 0 8px 24px rgb(2 6 23 / 3%);
}

.stat .row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.stat .ic {
  display: grid;
  width: 36px;
  height: 36px;
  place-items: center;
  border-radius: 10px;
}

.stat .ic.amber {
  background: #fffbeb;
  color: #b45309;
}

.stat .ic.teal {
  background: var(--teal-50);
  color: var(--teal-700);
}

.stat .ic.blue {
  background: #eff6ff;
  color: #1d4ed8;
}

.stat .ic.slate {
  background: var(--slate-100);
  color: var(--slate-600);
}

.stat .n {
  margin-top: 12px;
  color: var(--slate-950);
  font-size: 26px;
  font-weight: 800;
  line-height: 1;
}

.stat .lb {
  margin-top: 5px;
  color: var(--slate-500);
  font-size: 12px;
}

.stat .delta {
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  padding: 2px 7px;
}

.delta.up {
  background: #ecfdf5;
  color: #047857;
}

.delta.mut {
  background: var(--slate-100);
  color: var(--slate-500);
}

.grid {
  display: grid;
  grid-template-columns: 380px 1fr;
  align-items: start;
  gap: 18px;
}

.grid > .empty-card {
  grid-column: 1 / -1;
}

.panel {
  overflow: hidden;
  border: 1px solid var(--slate-200);
  border-radius: var(--radius-lg);
  background: white;
  box-shadow: 0 1px 2px rgb(2 6 23 / 4%), 0 12px 32px rgb(2 6 23 / 4%);
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--slate-100);
  padding: 15px 18px;
}

.panel-head h2 {
  margin: 0;
  color: var(--slate-900);
  font-size: 14px;
  font-weight: 800;
}

.panel-heading-copy p {
  margin: 3px 0 0;
  color: var(--slate-500);
  font-size: 11px;
}

.panel-head .cnt {
  border-radius: 999px;
  background: var(--teal-50);
  color: var(--teal-700);
  font-size: 11.5px;
  font-weight: 700;
  padding: 3px 9px;
}

.queue {
  max-height: 640px;
  overflow-y: auto;
}

.q-item {
  display: flex;
  width: 100%;
  gap: 12px;
  border: 0;
  border-bottom: 1px solid var(--slate-100);
  border-left: 3px solid transparent;
  background: white;
  cursor: pointer;
  padding: 14px 18px;
  text-align: left;
  transition: background 0.15s, border-color 0.15s;
}

.q-item:hover {
  background: var(--slate-50);
}

.q-item.active {
  border-left-color: var(--teal);
  background: var(--teal-50);
}

.q-item .av {
  display: grid;
  width: 40px;
  height: 40px;
  flex: none;
  place-items: center;
  border-radius: 11px;
  background: linear-gradient(135deg, #0f766e, #0d9488);
  color: white;
  font-size: 14px;
  font-weight: 800;
}

.q-item .info {
  min-width: 0;
  flex: 1;
}

.q-item .nm {
  display: flex;
  align-items: center;
  gap: 7px;
}

.q-item .nm b {
  color: var(--slate-900);
  font-size: 13.5px;
  font-weight: 800;
}

.q-item .nm .uid {
  color: var(--slate-400);
  font-size: 11.5px;
}

.q-item .meta {
  overflow: hidden;
  margin-top: 4px;
  color: var(--slate-500);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.q-item .pos {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin-top: 6px;
  border: 1px solid var(--teal-100);
  border-radius: 7px;
  background: var(--teal-50);
  color: var(--teal-800);
  font-size: 11.5px;
  font-weight: 700;
  padding: 2px 8px;
}

.q-item .time {
  flex: none;
  color: var(--slate-400);
  font-size: 11px;
  line-height: 1.5;
  text-align: right;
}

.badge-dot {
  width: 7px;
  height: 7px;
  flex: none;
  border-radius: 999px;
  background: #f59e0b;
}

.detail {
  min-width: 0;
}

.applicant {
  display: flex;
  gap: 14px;
  border-bottom: 1px solid var(--slate-100);
  background: linear-gradient(180deg, #f8fafc, white);
  padding: 20px;
}

.applicant .av {
  display: grid;
  width: 56px;
  height: 56px;
  flex: none;
  place-items: center;
  border-radius: 14px;
  background: linear-gradient(135deg, #0f766e, #0d9488);
  color: white;
  font-size: 20px;
  font-weight: 800;
  box-shadow: 0 8px 20px rgb(15 118 110 / 25%);
}

.applicant .h {
  min-width: 0;
}

.applicant .h b {
  color: var(--slate-950);
  font-size: 17px;
  font-weight: 800;
}

.applicant .h .uid {
  margin-left: 8px;
  color: var(--slate-400);
  font-size: 12.5px;
}

.applicant .tags {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin-top: 9px;
}

.tag {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border: 1px solid var(--slate-200);
  border-radius: 7px;
  background: white;
  color: var(--slate-600);
  font-size: 11.5px;
  font-weight: 600;
  padding: 3px 9px;
}

.tag svg {
  width: 13px;
  height: 13px;
  color: var(--slate-400);
}

.section {
  border-bottom: 1px solid var(--slate-100);
  padding: 18px 20px;
}

.section:last-child {
  border-bottom: none;
}

.sec-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 13px;
}

.sec-title .st-ic {
  display: grid;
  width: 26px;
  height: 26px;
  place-items: center;
  border-radius: 8px;
  background: var(--teal-50);
  color: var(--teal-700);
}

.sec-title h3 {
  margin: 0;
  color: var(--slate-900);
  font-size: 13px;
  font-weight: 800;
}

.sec-title .hint {
  color: var(--slate-400);
  font-size: 11.5px;
  font-weight: 500;
}

.position-review-grid {
  display: grid;
  grid-template-columns: minmax(0, 0.8fr) minmax(0, 1.2fr);
  gap: 12px;
}

.registration-review-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.registration-position-field {
  grid-column: 1 / -1;
}

.position-original,
.position-confirm-field {
  display: grid;
  gap: 7px;
  min-width: 0;
}

.position-original {
  align-content: center;
  border: 1px solid var(--slate-200);
  border-radius: var(--radius-sm);
  background: var(--slate-50);
  padding: 10px 12px;
}

.position-original span,
.position-confirm-field > span {
  color: var(--slate-500);
  font-size: 11.5px;
  font-weight: 700;
}

.position-original strong {
  overflow-wrap: anywhere;
  color: var(--slate-900);
  font-size: 13px;
}

.position-confirm-field input,
.position-confirm-field select {
  width: 100%;
  height: 42px;
  box-sizing: border-box;
  border: 1px solid var(--slate-200);
  border-radius: var(--radius-sm);
  background: white;
  color: var(--slate-900);
  font: inherit;
  font-size: 13px;
  outline: none;
  padding: 0 12px;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.position-confirm-field input:disabled {
  color: var(--slate-500);
  background: var(--slate-100);
  cursor: not-allowed;
}

.position-confirm-field input:focus,
.position-confirm-field select:focus {
  border-color: var(--teal);
  box-shadow: 0 0 0 3px var(--ring);
}

.position-role-note {
  margin: 10px 0 0;
  color: var(--slate-500);
  font-size: 11.5px;
  line-height: 1.6;
}

.system-position-department-label {
  margin: 0 0 10px;
  color: var(--slate-500);
  font-size: 12px;
}

.system-position-department-label strong {
  color: var(--slate-900);
}

.empty-system-positions {
  padding: 18px;
  border: 1px dashed var(--slate-300);
  border-radius: 12px;
  color: var(--slate-500);
  background: var(--slate-50);
  font-size: 12.5px;
  text-align: center;
}

.employee-position-text {
  color: var(--slate-700);
  font-size: 12.5px;
  font-weight: 700;
}

.system-position-picker {
  display: grid;
  gap: 6px;
  color: var(--slate-700);
  font-size: 12px;
  font-weight: 800;
}

.system-position-picker select {
  width: 100%;
  height: 42px;
  border: 1px solid var(--slate-300);
  border-radius: 10px;
  background: white;
  color: var(--slate-900);
  font: inherit;
  font-weight: 700;
  padding: 0 38px 0 12px;
  outline: none;
}

.system-position-picker select:focus {
  border-color: var(--teal);
  box-shadow: 0 0 0 3px var(--ring);
}

.selected-system-position-summary {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
  border: 1px solid var(--teal-200);
  border-radius: 12px;
  background: var(--teal-50);
  padding: 10px 12px;
}

.selected-system-position-check {
  display: grid;
  width: 24px;
  height: 24px;
  place-items: center;
  border-radius: 999px;
  background: var(--teal);
  color: white;
}

.selected-system-position-copy {
  min-width: 0;
}

.selected-system-position-title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 7px;
  color: var(--slate-900);
  font-size: 12.5px;
}

.selected-system-position-title span {
  border-radius: 999px;
  background: var(--teal);
  color: white;
  font-size: 9.5px;
  font-weight: 800;
  padding: 2px 7px;
}

.selected-system-position-copy p {
  margin: 2px 0 0;
  color: var(--slate-500);
  font-size: 11px;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.selected-system-position-count {
  color: var(--teal-dark);
  font-size: 11px;
  white-space: nowrap;
}

.engineer-bundle-note {
  display: grid;
  gap: 4px;
  margin-top: 12px;
  border: 1px solid #99f6e4;
  border-radius: 10px;
  background: #f0fdfa;
  color: #115e59;
  padding: 11px 13px;
  font-size: 11.5px;
}

.engineer-bundle-note strong {
  font-size: 12.5px;
}

.engineer-bundle-note small {
  margin-top: 2px;
  color: #64748b;
}

.perm-groups {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 22px;
}

.perm-group h4 {
  margin: 0 0 8px;
  color: var(--slate-400);
  font-size: 11.5px;
  font-weight: 800;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.perm {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 6px 0;
}

.cbx {
  display: grid;
  width: 18px;
  height: 18px;
  flex: none;
  place-items: center;
  border: 1.5px solid var(--slate-300);
  border-radius: 5px;
  color: white;
  transition: background 0.15s, border-color 0.15s;
}

.perm.on .cbx {
  border-color: var(--teal);
  background: var(--teal);
}

.perm .pt {
  color: var(--slate-700);
  font-size: 12.5px;
}

.perm .pc {
  margin-left: auto;
  color: var(--slate-400);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
}

.perm.locked {
  cursor: not-allowed;
  opacity: 0.55;
}

.scope-block {
  margin-bottom: 14px;
}

.scope-block:last-child {
  margin-bottom: 0;
}

.scope-lbl {
  margin-bottom: 8px;
  color: var(--slate-600);
  font-size: 12px;
  font-weight: 700;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1.5px solid var(--slate-200);
  border-radius: 999px;
  background: white;
  color: var(--slate-600);
  font-size: 12px;
  font-weight: 600;
  padding: 5px 13px;
  transition: border-color 0.15s, background 0.15s, color 0.15s;
}

.chip.on {
  border-color: var(--teal);
  background: var(--teal-50);
  color: var(--teal-800);
}

.chip .cd {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: var(--slate-300);
}

.chip.on .cd {
  background: var(--teal);
}

.chip.all {
  border-style: dashed;
}

.actions {
  display: flex;
  align-items: center;
  gap: 12px;
  border-top: 1px solid var(--slate-100);
  background: var(--slate-50);
  padding: 16px 20px;
}

.note-in {
  flex: 1;
  height: 40px;
  border: 1px solid var(--slate-200);
  border-radius: var(--radius-sm);
  background: white;
  color: var(--slate-800);
  font-family: inherit;
  font-size: 13px;
  outline: none;
  padding: 0 13px;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.note-in:focus {
  border-color: var(--teal);
  box-shadow: 0 0 0 3px var(--ring);
}

.note-in::placeholder {
  color: var(--slate-400);
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  height: 40px;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-family: inherit;
  font-size: 13px;
  font-weight: 700;
  padding: 0 18px;
  transition: background 0.15s, border-color 0.15s, color 0.15s, transform 0.1s;
}

.btn svg {
  width: 16px;
  height: 16px;
}

.btn-reject,
.btn-danger {
  border-color: var(--slate-200);
  background: white;
  color: var(--slate-600);
}

.btn-reject:hover,
.btn-danger:hover {
  border-color: #fecaca;
  background: #fef2f2;
  color: #b91c1c;
}

.btn-approve,
.btn-primary {
  border-color: var(--teal);
  background: var(--teal);
  color: white;
  box-shadow: 0 6px 16px rgb(15 118 110 / 26%);
}

.btn-approve:hover,
.btn-primary:hover {
  border-color: var(--teal-hover);
  background: var(--teal-hover);
}

.btn-sm {
  height: 32px;
  border-radius: 8px;
  font-size: 12px;
  padding: 0 10px;
  box-shadow: none;
}

.btn:disabled,
.ghost-link:disabled {
  cursor: wait;
  opacity: 0.65;
}

.message {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
  border-radius: 10px;
  padding: 12px 14px;
  font-size: 13px;
  font-weight: 700;
}

.message-error {
  border: 1px solid #fecaca;
  background: #fef2f2;
  color: #b91c1c;
}

.message-success {
  border: 1px solid #a7f3d0;
  background: #ecfdf5;
  color: #047857;
}

@media (max-width: 1080px) {
  .grid {
    grid-template-columns: 1fr;
  }

  .stats {
    grid-template-columns: repeat(2, 1fr);
  }

  .perm-groups {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .wrap {
    padding: 18px 14px 32px;
  }

  .topbar {
    align-items: flex-start;
    gap: 10px;
    margin: 0 -14px 18px;
    padding: 10px 14px;
  }

  .topbar-left {
    width: 100%;
    gap: 10px;
  }

  .topbar-actions {
    width: 100%;
    margin-left: 0;
    justify-content: flex-start;
  }

  .view-tabs {
    max-width: 100%;
    overflow-x: auto;
  }

  .stats {
    grid-template-columns: 1fr;
  }

  .selected-system-position-summary {
    grid-template-columns: auto minmax(0, 1fr);
  }

  .selected-system-position-count {
    grid-column: 2;
  }

  .position-review-grid {
    grid-template-columns: 1fr;
  }

  .registration-review-grid {
    grid-template-columns: 1fr;
  }

  .registration-position-field {
    grid-column: auto;
  }

  .actions {
    align-items: stretch;
    flex-direction: column;
  }

  .note-in,
  .actions .btn {
    width: 100%;
  }
}

/* Gemini reference redesign: presentation-only overrides. */
.permission-approval-page {
  --primary-deep: oklch(0.42 0.12 185);
  --primary-brand: oklch(0.48 0.12 182);
  --primary-bright: oklch(0.56 0.14 180);
  --primary-soft: oklch(0.95 0.025 182);
  --canvas: #f4f8f9;
  --surface: #ffffff;
  --surface-subtle: #f8fafb;
  --surface-hover: #f1f5f7;
  --border-soft: #e2e8eb;
  --border-strong: #cbd5e1;
  --shadow-panel: 0 16px 38px -22px rgb(15 23 42 / 26%), 0 2px 8px rgb(15 23 42 / 4%);
  --shadow-float: 0 22px 50px -28px rgb(15 23 42 / 34%), 0 8px 20px rgb(15 23 42 / 5%);

  background:
    radial-gradient(circle at 0 0, oklch(0.94 0.025 184 / 58%), transparent 34%),
    radial-gradient(circle at 100% 0, oklch(0.95 0.018 220 / 62%), transparent 32%),
    linear-gradient(180deg, #f7fafb 0%, var(--canvas) 44%, #f0f7f7 100%);
}

.wrap {
  max-width: 1540px;
  padding: 24px 32px 64px;
}

.topbar {
  top: 16px;
  flex-wrap: nowrap;
  gap: 14px;
  margin: 0 0 28px;
  border: 1px solid rgb(255 255 255 / 92%);
  border-radius: 24px;
  background: rgb(255 255 255 / 88%);
  box-shadow: 0 12px 34px -20px rgb(15 23 42 / 28%), 0 2px 8px rgb(15 23 42 / 4%);
  padding: 14px 18px;
  backdrop-filter: blur(18px) saturate(145%);
}

.topbar-left {
  gap: 16px;
}

.home-exit-link {
  min-height: 42px;
  border-radius: 999px;
  background: var(--surface-subtle);
  box-shadow: none;
  padding: 0 16px;
}

.home-exit-link:hover {
  border-color: color-mix(in oklch, var(--primary-brand), white 72%);
  background: white;
  color: var(--primary-deep);
  box-shadow: 0 8px 18px -13px rgb(15 118 110 / 55%);
  transform: translateX(-2px);
}

.brand {
  gap: 14px;
  border-left: 1px solid var(--border-soft);
  padding-left: 16px;
}

.brand .logo {
  width: 44px;
  height: 44px;
  border-radius: 13px;
  background: linear-gradient(145deg, var(--primary-bright), var(--primary-deep));
  box-shadow: 0 10px 22px -11px rgb(0 101 89 / 72%), inset 0 1px 0 rgb(255 255 255 / 28%);
}

.brand h1 {
  font-size: 18px;
  letter-spacing: -0.02em;
}

.brand p {
  margin-top: 3px;
  color: #64748b;
  font-size: 12px;
}

.topbar-actions {
  flex-wrap: nowrap;
  gap: 8px;
}

.view-tabs {
  position: relative;
  isolation: isolate;
  display: grid;
  min-width: 340px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0;
  border-color: #edf1f3;
  background: #edf2f4;
  box-shadow: inset 0 1px 2px rgb(15 23 42 / 5%);
}

.view-tabs::before {
  position: absolute;
  z-index: -1;
  top: 4px;
  bottom: 4px;
  left: 4px;
  width: calc((100% - 8px) / 3);
  border: 1px solid rgb(226 232 240 / 82%);
  border-radius: 999px;
  background: white;
  box-shadow: 0 5px 14px -8px rgb(15 23 42 / 38%), 0 1px 3px rgb(15 23 42 / 8%);
  content: "";
  transition: transform 320ms cubic-bezier(0.16, 1, 0.3, 1);
}

.view-tabs:has(button:nth-child(2).active)::before {
  transform: translateX(100%);
}

.view-tabs:has(button:nth-child(3).active)::before {
  transform: translateX(200%);
}

.view-tabs button {
  z-index: 1;
  min-width: 0;
  min-height: 36px;
  border-radius: 999px;
  color: #64748b;
  padding: 0 13px;
  white-space: nowrap;
}

.view-tabs button.active {
  background: transparent;
  color: var(--primary-deep);
}

.view-tabs button:hover {
  background: transparent;
  color: #0f172a;
}

.view-tabs span {
  background: #dfe7e9;
  color: #64748b;
  transition: background 180ms ease, color 180ms ease;
}

.view-tabs button.active span {
  background: var(--primary-soft);
  color: var(--primary-deep);
}

.ghost-link {
  min-height: 38px;
  border-color: var(--border-soft);
  background: rgb(255 255 255 / 78%);
  box-shadow: none;
  padding: 0 13px;
}

.ghost-link:hover {
  border-color: color-mix(in oklch, var(--primary-brand), white 70%);
  background: var(--primary-soft);
  color: var(--primary-deep);
}

.admin {
  border-color: var(--border-soft);
  box-shadow: none;
}

.admin .av {
  background: linear-gradient(145deg, var(--primary-bright), var(--primary-deep));
  box-shadow: inset 0 1px 0 rgb(255 255 255 / 28%);
}

.stats {
  gap: 20px;
  margin-bottom: 28px;
}

.stat {
  position: relative;
  overflow: hidden;
  min-height: 152px;
  border-color: rgb(218 227 230 / 88%);
  border-radius: 18px;
  background: linear-gradient(145deg, rgb(255 255 255 / 98%), rgb(250 253 253 / 94%));
  box-shadow: var(--shadow-panel);
  padding: 24px 26px;
  transition: border-color 220ms ease, box-shadow 220ms ease, transform 220ms cubic-bezier(0.16, 1, 0.3, 1);
}

.stat::after {
  position: absolute;
  width: 118px;
  height: 118px;
  right: -38px;
  bottom: -54px;
  border-radius: 999px;
  background: var(--stat-glow, rgb(148 163 184 / 10%));
  content: "";
  filter: blur(2px);
}

.stat:hover {
  border-color: color-mix(in oklch, var(--stat-accent, var(--primary-brand)), white 72%);
  box-shadow: var(--shadow-float);
  transform: translateY(-3px);
}

.stat-pending {
  --stat-accent: #f59e0b;
  --stat-glow: rgb(245 158 11 / 11%);
}

.stat-active {
  --stat-accent: #10b981;
  --stat-glow: rgb(16 185 129 / 11%);
}

.stat-users {
  --stat-accent: #3b82f6;
  --stat-glow: rgb(59 130 246 / 10%);
}

.stat-reset {
  --stat-accent: #64748b;
  --stat-glow: rgb(100 116 139 / 10%);
}

.stat .ic {
  width: 44px;
  height: 44px;
  border-radius: 13px;
}

.stat .n {
  position: relative;
  z-index: 1;
  margin-top: 19px;
  font-size: 34px;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.035em;
}

.stat .lb {
  position: relative;
  z-index: 1;
  margin-top: -22px;
  color: #52606d;
  font-size: 13px;
  font-weight: 700;
  text-align: right;
}

.stat .delta {
  border: 1px solid currentColor;
  background: color-mix(in srgb, currentColor 7%, white);
  padding: 3px 8px;
}

.grid {
  grid-template-columns: 470px minmax(0, 1fr);
  gap: 24px;
}

.panel {
  border-color: rgb(218 227 230 / 92%);
  border-radius: 20px;
  box-shadow: var(--shadow-panel);
}

.queue-panel {
  position: sticky;
  top: 116px;
}

.panel-head {
  min-height: 88px;
  border-bottom-color: #e8eef0;
  background: linear-gradient(180deg, #fff, #fbfcfd);
  padding: 18px 20px;
}

.panel-heading-group {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 10px;
}

.panel-heading-icon {
  display: grid;
  width: 34px;
  height: 34px;
  flex: none;
  place-items: center;
  border-radius: 10px;
  background: var(--primary-soft);
  color: var(--primary-deep);
}

.panel-head h2 {
  font-size: 16px;
}

.panel-heading-copy p {
  margin-top: 4px;
  font-size: 11.5px;
  font-variant-numeric: tabular-nums;
}

.panel-head .cnt {
  flex: none;
  border: 1px solid #fde68a;
  background: #fffbeb;
  color: #b45309;
  padding: 4px 10px;
}

.queue {
  max-height: 688px;
  background: #fbfcfd;
  padding: 12px;
}

.q-item {
  position: relative;
  overflow: hidden;
  align-items: flex-start;
  margin-bottom: 10px;
  border: 1px solid var(--border-soft);
  border-left: 1px solid var(--border-soft);
  border-radius: 15px;
  background: white;
  padding: 15px 16px;
  transition: border-color 200ms ease, background 200ms ease, box-shadow 200ms ease, transform 220ms cubic-bezier(0.16, 1, 0.3, 1);
}

.q-item:last-child {
  margin-bottom: 0;
}

.q-item::before {
  position: absolute;
  inset: 10px auto 10px 0;
  width: 4px;
  border-radius: 0 999px 999px 0;
  background: linear-gradient(180deg, var(--primary-bright), var(--primary-deep));
  content: "";
  opacity: 0;
  transform: scaleY(0.5);
  transition: opacity 180ms ease, transform 220ms ease;
}

.q-item:hover {
  border-color: #cbd5e1;
  background: white;
  box-shadow: 0 10px 24px -18px rgb(15 23 42 / 50%);
  transform: translateX(3px);
}

.q-item.active {
  border-color: var(--primary-brand);
  background: linear-gradient(100deg, var(--primary-soft), white 66%);
  box-shadow: 0 12px 28px -20px rgb(0 101 89 / 60%), 0 0 0 1px rgb(15 118 110 / 8%);
  transform: translateX(3px);
}

.q-item.active::before {
  opacity: 1;
  transform: scaleY(1);
}

.q-item .av {
  width: 44px;
  height: 44px;
  border-radius: 13px;
  background: linear-gradient(145deg, var(--primary-bright), var(--primary-deep));
  box-shadow: 0 8px 18px -11px rgb(0 101 89 / 76%);
}

.q-item .nm b {
  font-size: 14px;
}

.q-item .pos {
  border-color: color-mix(in oklch, var(--primary-brand), white 78%);
  background: var(--primary-soft);
  padding: 3px 9px;
}

.q-item .time {
  font-variant-numeric: tabular-nums;
}

.badge-dot {
  box-shadow: 0 0 0 4px rgb(245 158 11 / 12%);
  animation: approval-pulse 2.4s ease-in-out infinite;
}

.detail {
  overflow: visible;
  background: rgb(255 255 255 / 92%);
}

.applicant-hero {
  position: relative;
  overflow: hidden;
  align-items: center;
  margin: 24px;
  border: 1px solid color-mix(in oklch, var(--primary-brand), white 80%);
  border-radius: 20px;
  background:
    radial-gradient(circle at 92% 18%, rgb(13 148 136 / 9%), transparent 34%),
    linear-gradient(135deg, var(--primary-soft), #f8fafc 58%, white);
  box-shadow: inset 0 1px 0 rgb(255 255 255 / 80%);
  padding: 24px;
}

.applicant-hero::after {
  position: absolute;
  width: 180px;
  height: 180px;
  right: -86px;
  bottom: -120px;
  border: 28px solid rgb(15 118 110 / 5%);
  border-radius: 999px;
  content: "";
  pointer-events: none;
}

.applicant .av {
  width: 68px;
  height: 68px;
  border-radius: 18px;
  background: linear-gradient(145deg, var(--primary-bright), var(--primary-deep));
  box-shadow: 0 16px 28px -14px rgb(0 101 89 / 72%), inset 0 1px 0 rgb(255 255 255 / 30%);
  font-size: 24px;
}

.applicant .h b {
  font-size: 21px;
  letter-spacing: -0.025em;
}

.applicant .h .uid {
  display: inline-flex;
  border: 1px solid color-mix(in oklch, var(--primary-brand), white 72%);
  border-radius: 999px;
  background: rgb(255 255 255 / 82%);
  color: var(--primary-deep);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 11.5px;
  font-weight: 700;
  padding: 3px 9px;
  vertical-align: 2px;
}

.applicant .tags {
  margin-top: 12px;
}

.applicant .tag {
  border-radius: 999px;
  background: rgb(255 255 255 / 84%);
  box-shadow: 0 2px 5px rgb(15 23 42 / 3%);
  padding: 5px 10px;
}

.applicant .tag svg {
  color: var(--primary-brand);
}

.approval-surface-section {
  margin: 0 24px 20px;
  border: 1px solid var(--border-soft);
  border-radius: 18px;
  background: white;
  box-shadow: 0 8px 24px -22px rgb(15 23 42 / 42%);
  padding: 0;
}

.approval-surface-section .sec-title {
  margin: 0;
  border-bottom: 1px solid #edf1f3;
  padding: 17px 18px;
}

.sec-title .st-ic {
  width: 34px;
  height: 34px;
  flex: none;
  border-radius: 10px;
}

.sec-title-copy {
  display: flex;
  min-width: 0;
  flex: 1;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.sec-title h3 {
  font-size: 15px;
}

.sec-title .hint {
  max-width: 58%;
  color: #64748b;
  line-height: 1.5;
  text-align: right;
}

.registration-review-grid {
  gap: 16px 18px;
  padding: 20px 18px 8px;
}

.position-confirm-field {
  gap: 8px;
}

.field-label,
.picker-label {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
}

.field-label > span,
.picker-label > span {
  color: #334155;
  font-size: 12.5px;
  font-weight: 800;
}

.field-label small,
.picker-label small {
  color: #94a3b8;
  font-size: 10.5px;
  font-weight: 600;
}

.position-confirm-field input,
.position-confirm-field select,
.system-position-picker select {
  height: 46px;
  border-color: #dbe3e6;
  border-radius: 12px;
  background: #fafcfd;
  padding-inline: 14px;
  transition: border-color 180ms ease, background 180ms ease, box-shadow 180ms ease, transform 180ms ease;
}

.position-confirm-field input:hover,
.position-confirm-field select:hover,
.system-position-picker select:hover {
  border-color: #cbd5e1;
  background: white;
}

.position-confirm-field input:focus,
.position-confirm-field select:focus,
.system-position-picker select:focus,
.note-in:focus {
  border-color: var(--primary-brand);
  background: white;
  box-shadow: 0 0 0 4px rgb(15 118 110 / 13%);
}

.immutable-field input:disabled {
  border-style: dashed;
  border-color: #cbd5e1;
  background: #f1f5f9;
  color: #64748b;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

.position-suggestion-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
}

.position-suggestion-chips > span {
  border: 1px solid #e2e8f0;
  border-radius: 999px;
  background: #f8fafc;
  color: #64748b;
  font-size: 10.5px;
  font-weight: 700;
  padding: 4px 9px;
}

.approval-surface-section > .position-role-note {
  margin: 8px 18px 18px;
  border-left: 3px solid color-mix(in oklch, var(--primary-brand), white 48%);
  border-radius: 0 8px 8px 0;
  background: #f8fafc;
  padding: 8px 10px;
}

.permission-position-section {
  padding-bottom: 18px;
}

.permission-position-section .system-position-department-label,
.permission-position-section .recommendation-banner,
.permission-position-section .system-position-picker,
.permission-position-section .selected-system-position-summary,
.permission-position-section .empty-system-positions {
  margin-right: 18px;
  margin-left: 18px;
}

.permission-position-section .system-position-department-label {
  margin-top: 16px;
  margin-bottom: 12px;
}

.recommendation-banner {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 11px;
  margin-top: 0;
  margin-bottom: 14px;
  border: 1px solid #bfdbfe;
  border-radius: 14px;
  background: linear-gradient(105deg, #eff6ff, #f8fbff 72%);
  color: #1e40af;
  padding: 12px 14px;
}

.recommendation-icon {
  display: grid;
  width: 30px;
  height: 30px;
  place-items: center;
  border-radius: 9px;
  background: white;
  color: #2563eb;
  box-shadow: 0 4px 12px -8px rgb(37 99 235 / 60%);
}

.recommendation-copy {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.recommendation-copy strong {
  overflow: hidden;
  color: #1d4ed8;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.recommendation-copy > span {
  color: #64748b;
  font-size: 10.5px;
  line-height: 1.5;
}

.recommendation-state {
  border: 1px solid #bfdbfe;
  border-radius: 999px;
  background: white;
  color: #1d4ed8;
  font-size: 10px;
  font-weight: 800;
  padding: 4px 8px;
  white-space: nowrap;
}

.system-position-picker {
  gap: 8px;
}

.selected-system-position-summary {
  margin-top: 12px;
  border-color: color-mix(in oklch, var(--primary-brand), white 70%);
  border-radius: 14px;
  background: linear-gradient(105deg, var(--primary-soft), #fbfefd);
  padding: 13px 14px;
}

.selected-system-position-check {
  width: 30px;
  height: 30px;
  background: linear-gradient(145deg, var(--primary-bright), var(--primary-deep));
  box-shadow: 0 8px 16px -11px rgb(0 101 89 / 80%);
}

.selected-system-position-title {
  font-size: 13px;
}

.selected-system-position-copy p {
  margin-top: 4px;
  font-size: 11.5px;
  line-height: 1.55;
}

.selected-system-position-count {
  border-radius: 999px;
  background: white;
  color: var(--primary-deep);
  padding: 5px 9px;
}

.action-dock {
  position: sticky;
  z-index: 10;
  bottom: 12px;
  gap: 10px;
  margin: 0 12px 12px;
  border: 1px solid rgb(226 232 235 / 88%);
  border-radius: 16px;
  background: rgb(255 255 255 / 90%);
  box-shadow: 0 18px 42px -24px rgb(15 23 42 / 52%), 0 4px 14px rgb(15 23 42 / 6%);
  padding: 12px;
  backdrop-filter: blur(16px) saturate(140%);
}

.action-note-wrap {
  display: grid;
  min-width: 220px;
  flex: 1;
  gap: 5px;
}

.action-note-wrap > span {
  color: #64748b;
  font-size: 10.5px;
  font-weight: 800;
}

.note-in {
  width: 100%;
  height: 42px;
  border-color: #dbe3e6;
  border-radius: 11px;
  background: #fafcfd;
}

.action-dock .btn {
  position: relative;
  overflow: hidden;
  height: 44px;
  align-self: end;
  border-radius: 12px;
  padding: 0 18px;
  transition: border-color 180ms ease, background 180ms ease, box-shadow 180ms ease, color 180ms ease, transform 120ms ease;
}

.btn-reject {
  border-color: #fecdd3;
  color: #be123c;
}

.btn-reject:hover {
  border-color: #fda4af;
  background: #fff1f2;
  box-shadow: 0 8px 18px -13px rgb(225 29 72 / 55%);
}

.btn-approve {
  min-width: 174px;
  border-color: transparent;
  background: linear-gradient(135deg, var(--primary-bright), var(--primary-deep));
  box-shadow: 0 9px 20px -12px rgb(0 101 89 / 85%), inset 0 1px 0 rgb(255 255 255 / 25%);
}

.btn-approve::before {
  position: absolute;
  inset: 0 auto 0 -70%;
  width: 52%;
  background: linear-gradient(90deg, transparent, rgb(255 255 255 / 28%), transparent);
  content: "";
  pointer-events: none;
  transform: skewX(-18deg);
  transition: left 760ms ease;
}

.btn-approve:hover {
  border-color: transparent;
  background: linear-gradient(135deg, oklch(0.57 0.15 180), oklch(0.4 0.12 185));
  box-shadow: 0 13px 26px -14px rgb(0 101 89 / 90%), inset 0 1px 0 rgb(255 255 255 / 28%);
  transform: translateY(-1px);
}

.btn-approve:hover::before {
  left: 125%;
}

.action-dock .btn:active {
  transform: scale(0.98);
}

.request-card,
.users-panel {
  border-color: rgb(218 227 230 / 92%);
  border-radius: 18px;
  box-shadow: var(--shadow-panel);
}

.message {
  border-radius: 14px;
  box-shadow: 0 8px 22px -18px rgb(15 23 42 / 45%);
}

@keyframes approval-pulse {
  0%,
  100% {
    box-shadow: 0 0 0 3px rgb(245 158 11 / 10%);
  }

  50% {
    box-shadow: 0 0 0 6px rgb(245 158 11 / 4%);
  }
}

@media (max-width: 1200px) {
  .topbar {
    flex-wrap: wrap;
  }

  .topbar-actions {
    width: 100%;
    justify-content: flex-start;
  }

  .admin {
    margin-left: auto;
  }

  .queue-panel {
    top: 170px;
  }
}

@media (max-width: 1120px) {
  .grid {
    grid-template-columns: 1fr;
  }

  .queue-panel {
    position: static;
  }

  .queue {
    display: grid;
    max-height: none;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
  }

  .q-item {
    margin-bottom: 0;
  }
}

@media (max-width: 820px) {
  .wrap {
    padding: 16px 14px 40px;
  }

  .topbar {
    top: 8px;
    margin-bottom: 20px;
    padding: 12px;
  }

  .topbar-actions {
    display: grid;
    grid-template-columns: 1fr auto;
  }

  .view-tabs {
    width: 100%;
    min-width: 0;
    grid-column: 1 / -1;
  }

  .iam-console-entry {
    justify-self: start;
  }

  .admin {
    justify-self: end;
    margin-left: 0;
  }

  .stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
  }

  .stat {
    min-height: 132px;
    padding: 18px;
  }

  .stat .n {
    margin-top: 15px;
    font-size: 30px;
  }

  .queue {
    grid-template-columns: 1fr;
  }

  .applicant-hero,
  .approval-surface-section {
    margin-right: 14px;
    margin-left: 14px;
  }

  .applicant-hero {
    margin-top: 14px;
    padding: 18px;
  }

  .sec-title-copy {
    display: grid;
    justify-content: stretch;
  }

  .sec-title .hint {
    max-width: none;
    text-align: left;
  }

  .registration-review-grid {
    grid-template-columns: 1fr;
  }

  .registration-position-field {
    grid-column: auto;
  }

  .action-dock {
    position: static;
    align-items: stretch;
    flex-direction: column;
  }

  .action-dock .btn,
  .action-note-wrap {
    width: 100%;
  }
}

@media (max-width: 560px) {
  .home-exit-link {
    width: 42px;
    padding: 0;
    font-size: 0;
  }

  .brand {
    min-width: 0;
    padding-left: 10px;
  }

  .brand .logo {
    width: 40px;
    height: 40px;
  }

  .brand h1 {
    overflow: hidden;
    font-size: 15px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .brand p,
  .admin .t {
    display: none;
  }

  .ghost-link {
    padding: 0 10px;
  }

  .stats {
    grid-template-columns: 1fr;
  }

  .stat {
    min-height: 122px;
  }

  .panel-head {
    align-items: flex-start;
  }

  .q-item .time {
    display: none;
  }

  .applicant-hero {
    align-items: flex-start;
    padding: 16px;
  }

  .applicant .av {
    width: 52px;
    height: 52px;
    border-radius: 14px;
    font-size: 19px;
  }

  .applicant .h b {
    font-size: 18px;
  }

  .recommendation-banner,
  .selected-system-position-summary {
    grid-template-columns: auto minmax(0, 1fr);
  }

  .recommendation-state,
  .selected-system-position-count {
    grid-column: 2;
    justify-self: start;
  }
}

@media (prefers-reduced-motion: reduce) {
  .permission-approval-page *,
  .permission-approval-page *::before,
  .permission-approval-page *::after {
    scroll-behavior: auto !important;
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
</style>
