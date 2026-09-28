<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
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
import { TabsRoot, TabsList, TabsTrigger, TabsContent } from 'reka-ui'
import IamLeaveGuard from '@/components/iam/workspace/IamLeaveGuard.vue'
import IamDialogSurface from '@/components/iam/workspace/IamDialogSurface.vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
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
const router = useRouter()
let loadGeneration = 0
let routeGeneration = 0
const requestedUnavailable = ref('')
const resetReviewOpen = ref(false)
const resetSurface = ref<InstanceType<typeof IamDialogSurface>>()
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
const approvalBaselines = ref<Record<string, string>>({})
const leaveGuard = ref<InstanceType<typeof IamLeaveGuard>>()
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
const currentAccountName = computed(
  () =>
    authStore.currentUser?.display_name?.trim() || authStore.currentUser?.username || '当前账号',
)
const currentAccountCode = computed(() => authStore.currentUser?.username || '已登录')
const organizations = ref<Organization[]>([])
const factoryOptions = computed(() =>
  organizations.value
    .filter((o) => o.kind !== 'group' && o.status === 'active')
    .map((o) => ({ id: o.id, shortName: o.name })),
)
const approvalDepartments = computed(
  () =>
    organizations.value.find((o) => o.id === selectedProfile.value?.factory_id)?.departments ?? [],
)
async function loadOrganizations() {
  if (!canManageUsers.value) return
  const generation = routeGeneration
  try {
    const result = await identityApi.catalog()
    if (generation === routeGeneration) organizations.value = result.organizations
  } catch (e) {
    if (generation === routeGeneration) errorMessage.value = getApiErrorMessage(e)
  }
}
const activeUsers = computed(() => users.value.filter((user) => user.status === 'active'))
const pendingUsers = computed(() => users.value.filter((user) => user.status === 'pending'))
const selectedPasswordResetRequest = computed(
  () =>
    passwordResetRequests.value.find((request) => request.id === selectedPasswordResetId.value) ??
    null,
)
const selectedRequest = computed(
  () => requests.value.find((request) => request.id === selectedRequestId.value) ?? null,
)
const selectedProfile = computed(() =>
  selectedRequest.value ? approvalProfile(selectedRequest.value) : null,
)
const selectedPositionSuggestions = computed(() =>
  getPositionSuggestions(selectedProfile.value?.department ?? ''),
)
const allSystemPositions = computed(() =>
  systemPositions.value
    .filter((role) => role.is_system_position)
    .sort(
      (left, right) =>
        left.position_sort_order - right.position_sort_order ||
        left.name.localeCompare(right.name, 'zh-CN'),
    ),
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
  const knownDepartments = new Set<string>(
    registrationDepartments.map((department) => department.id),
  )
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
  const recommendedRoleId = selectedRequest.value.recommended_role_ids.find((roleId) =>
    allSystemPositions.value.some((role) => role.id === roleId),
  )
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
  const earliestSubmission = requests.value.reduce<{ value: string; timestamp: number } | null>(
    (earliest, request) => {
      const timestamp = parseBusinessTimestamp(request.submitted_at)
      if (timestamp === null || (earliest && earliest.timestamp <= timestamp)) return earliest
      return { value: request.submitted_at, timestamp }
    },
    null,
  )
  if (!earliestSubmission)
    return requests.value.length ? '请及时处理新的账号申请' : '暂无待处理申请'
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
  approvalBaselines.value[request.id] = JSON.stringify(profile)
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

async function selectPasswordRequest(id: string) {
  if (id === selectedPasswordResetId.value || actionKey.value) return
  if (route.query.request_id) {
    await router.replace({ query: { ...route.query, request_id: id } })
  } else if (await permitRouteLeave()) selectedPasswordResetId.value = id
}
async function selectRequest(requestId: string) {
  if (requestId === selectedRequestId.value || actionKey.value) return
  if (route.query.request_id) {
    await router.replace({ query: { ...route.query, request_id: requestId } })
  } else if (await permitRouteLeave()) selectedRequestId.value = requestId
}

function ensureSelectedRequest() {
  if (!requests.value.length) {
    selectedRequestId.value = ''
    return
  }
  const requestedId = typeof route.query.request_id === 'string' ? route.query.request_id : ''
  if (requestedId && activeTab.value === 'pending') {
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
  const generation = ++loadGeneration
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
    const [pendingRequests, loadedUsers, loadedPositions, loadedPasswordResetRequests] =
      await Promise.all([
        systemApi.listRegistrationRequests('pending'),
        systemApi.listUsers(''),
        systemApi.listSystemPositions(),
        systemApi.listPasswordResetRequests(passwordResetStatus.value),
      ])
    if (generation !== loadGeneration) return
    requests.value = pendingRequests
    for (const request of pendingRequests) approvalProfile(request)
    users.value = loadedUsers
    systemPositions.value = loadedPositions
    passwordResetRequests.value = loadedPasswordResetRequests
    const requestedResetId =
      typeof route.query.request_id === 'string' ? route.query.request_id : ''
    if (requestedResetId && activeTab.value === 'password-reset') {
      selectedPasswordResetId.value = requestedResetId
    } else if (
      !loadedPasswordResetRequests.some((item) => item.id === selectedPasswordResetId.value)
    ) {
      selectedPasswordResetId.value = loadedPasswordResetRequests[0]?.id ?? ''
    }
    ensureSelectedRequest()
    const requested =
      activeTab.value === 'password-reset'
        ? selectedPasswordResetRequest.value
        : selectedRequest.value
    requestedUnavailable.value =
      requestedResetId && !requested ? '指定申请不存在或不在当前可见范围，请从列表另选申请。' : ''
  } catch (error) {
    if (generation !== loadGeneration) return
    errorMessage.value = getApiErrorMessage(error)
    if ((error as { response?: { status?: number } }).response?.status === 403) {
      requests.value = []
      users.value = []
      passwordResetRequests.value = []
      systemPositions.value = []
      selectedRequestId.value = ''
      selectedPasswordResetId.value = ''
      resetReviewOpen.value = false
      clearPasswordReview()
    }
  } finally {
    if (generation === loadGeneration) isLoading.value = false
  }
}

async function approveRequest(request: RegistrationRequestResponse) {
  if (actionKey.value) return
  const generation = routeGeneration
  if (!ensureUserManagementPermission()) return
  const source = approvalProfile(request)
  const profile: RegistrationProfileRequest = {
    display_name: source.display_name.trim(),
    phone: source.phone.trim(),
    email: source.email.trim(),
    factory_id:
      organizations.value.find((o) => o.id === source.factory_id)?.factory_id ?? source.factory_id,
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
    if (generation !== routeGeneration) return
    successMessage.value = `已通过 ${profile.display_name} 的账号申请`
    await loadData()
  } catch (error) {
    if (generation !== routeGeneration) return
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    if (generation === routeGeneration) actionKey.value = ''
  }
}

async function rejectRequest(request: RegistrationRequestResponse) {
  if (actionKey.value) return
  const generation = routeGeneration
  if (!ensureUserManagementPermission()) return
  const comment = (
    rejectComments.value[request.id] ||
    approvalComments.value[request.id] ||
    ''
  ).trim()
  if (!comment) {
    errorMessage.value = '拒绝申请时需要填写原因'
    return
  }
  actionKey.value = `reject:${request.id}`
  errorMessage.value = ''
  successMessage.value = ''
  try {
    await systemApi.rejectRegistrationRequest(request.id, { review_comment: comment })
    if (generation !== routeGeneration) return
    successMessage.value = `已拒绝 ${request.display_name} 的账号申请`
    await loadData()
  } catch (error) {
    if (generation !== routeGeneration) return
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    if (generation === routeGeneration) actionKey.value = ''
  }
}

async function updateStatus(user: UserResponse, status: 'active' | 'suspended') {
  if (actionKey.value) return
  const generation = routeGeneration
  if (!ensureUserManagementPermission()) return
  actionKey.value = `status:${user.id}:${status}`
  errorMessage.value = ''
  successMessage.value = ''
  try {
    await systemApi.updateUserStatus(user.id, { status })
    if (generation !== routeGeneration) return
    successMessage.value = `${user.display_name || user.username} 已${status === 'suspended' ? '停用' : '恢复'}`
    await loadData()
  } catch (error) {
    if (generation !== routeGeneration) return
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    if (generation === routeGeneration) actionKey.value = ''
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
  resetReviewOpen.value = true
  passwordResetReviewTarget.value = resetRequest
  passwordResetReviewMode.value = mode
  passwordResetReviewComment.value = ''
  passwordResetIdentityVerified.value = false
  errorMessage.value = ''
}

function closePasswordResetReview() {
  void resetSurface.value?.requestClose()
}
function clearPasswordReview() {
  passwordResetReviewTarget.value = null
  passwordResetReviewMode.value = ''
  passwordResetReviewComment.value = ''
  passwordResetIdentityVerified.value = false
}

async function submitPasswordResetReview() {
  if (actionKey.value) return
  const generation = routeGeneration
  if (
    !ensureUserManagementPermission() ||
    !passwordResetReviewTarget.value ||
    !passwordResetReviewMode.value
  )
    return
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
      if (generation !== routeGeneration) return
      successMessage.value = `已驳回密码重置申请 ${target.id}`
    } else {
      const response =
        mode === 'approve'
          ? await systemApi.approvePasswordResetRequest(target.id, {
              review_comment: reviewComment,
              identity_verified: true,
            })
          : await systemApi.reissuePasswordResetRequest(target.id, {
              review_comment: reviewComment,
              identity_verified: true,
            })
      if (generation !== routeGeneration) return
      successMessage.value = response.message
    }
    resetReviewOpen.value = false
    passwordResetReviewTarget.value = null
    passwordResetReviewMode.value = ''
    passwordResetReviewComment.value = ''
    passwordResetIdentityVerified.value = false
    await loadData()
  } catch (error) {
    if (generation !== routeGeneration) return
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    if (generation === routeGeneration) actionKey.value = ''
  }
}

async function initializeData() {
  const generation = ++routeGeneration
  ++loadGeneration
  actionKey.value = ''
  resetReviewOpen.value = false
  clearPasswordReview()
  requestedUnavailable.value = ''
  if (!canManageUsers.value) {
    await loadData()
    return
  }
  activeTab.value =
    route.query.tab === 'password-reset'
      ? 'password-reset'
      : route.query.tab === 'users'
        ? 'users'
        : 'pending'
  const requestedResetId =
    activeTab.value === 'password-reset' && typeof route.query.request_id === 'string'
      ? route.query.request_id
      : ''
  if (requestedResetId) {
    selectedPasswordResetId.value = requestedResetId
    try {
      const detail = await systemApi.getPasswordResetRequest(requestedResetId)
      if (generation !== routeGeneration) return
      passwordResetStatus.value = detail.status
    } catch {
      if (generation !== routeGeneration) return
      requestedUnavailable.value = '指定申请不存在或不可见。'
    }
  }
  await Promise.all([loadOrganizations(), loadData()])
}
function changeTab(value: string | number) {
  const query = { ...route.query, tab: String(value) }
  delete (query as Record<string, unknown>).request_id
  void router.replace({ query })
}
const registrationDirty = computed(() =>
  requests.value.some(
    (request) =>
      JSON.stringify(approvalProfiles.value[request.id]) !== approvalBaselines.value[request.id] ||
      selectedSystemPositions.value[request.id] ||
      approvalComments.value[request.id] ||
      rejectComments.value[request.id],
  ),
)
async function permitRouteLeave() {
  if (resetReviewOpen.value) return await resetSurface.value?.permitLeave()
  if (actionKey.value) {
    errorMessage.value = '办理请求正在处理中，请等待结果后离开。'
    return false
  }
  const allow = (await leaveGuard.value?.permitLeave()) ?? true
  if (allow && registrationDirty.value) {
    approvalProfiles.value = {}
    approvalBaselines.value = {}
    selectedSystemPositions.value = {}
    approvalComments.value = {}
    rejectComments.value = {}
  }
  return allow
}
onBeforeRouteLeave(permitRouteLeave)
onBeforeRouteUpdate(permitRouteLeave)
watch(
  () => route.fullPath,
  () => {
    void initializeData()
  },
  { immediate: true },
)
onBeforeUnmount(() => {
  ++loadGeneration
  ++routeGeneration
})
</script>

<template>
  <section class="iamx-account-page permission-approval-page">
    <div class="wrap">
      <TabsRoot :model-value="activeTab" @update:model-value="changeTab"
        ><header class="iamx-section-head">
          <div>
            <h2>账号办理</h2>
            <p>审核注册资料，处理密码找回与账号状态</p>
          </div>
          <button
            type="button"
            class="btn"
            :disabled="!canManageUsers || isLoading"
            @click="loadData"
          >
            <RefreshCw :size="16" />刷新
          </button>
        </header>
        <TabsList class="iamx-tabs" aria-label="账号管理视图"
          ><TabsTrigger value="pending" :disabled="!canManageUsers">注册审核</TabsTrigger
          ><TabsTrigger value="password-reset" :disabled="!canManageUsers">密码找回</TabsTrigger
          ><TabsTrigger value="users" :disabled="!canManageUsers"
            >兼容账号列表</TabsTrigger
          ></TabsList
        >
        <section
          v-if="!canManageUsers"
          class="protected-access-notice"
          data-testid="system-users-protected-notice"
          role="status"
        >
          <span class="protected-access-icon"
            ><ShieldCheck class="size-5" aria-hidden="true"
          /></span>
          <div>
            <strong>页面可访问 · 敏感账号资料受保护</strong>
            <p>
              当前账号没有账号管理权限。申请、用户、审批及密码重置明细不会在此模式下读取或展示，也不能执行任何账号变更。
            </p>
          </div>
        </section>

        <div v-if="errorMessage" role="alert" class="message message-error">
          <CircleAlert class="size-4 shrink-0" aria-hidden="true" />
          <span>{{ errorMessage }}</span>
        </div>
        <div v-if="successMessage" role="status" class="message message-success">
          <CheckCircle2 class="size-4 shrink-0" aria-hidden="true" />
          <span>{{ successMessage }}</span>
        </div>

        <p v-if="requestedUnavailable" role="alert" class="iamx-notice">
          {{ requestedUnavailable }}
        </p>
        <TabsContent value="pending"
          ><section
            v-if="canManageUsers && activeTab === 'pending'"
            class="approval-workspace"
            :class="{ 'has-selection': selectedRequest }"
          >
            <div v-if="isLoading" class="empty-card">正在加载账号申请...</div>
            <div v-else-if="!requests.length" class="empty-card">当前没有待审批账号。</div>
            <template v-else>
              <aside class="panel queue-panel">
                <div class="panel-head">
                  <div class="panel-heading-group">
                    <span class="panel-heading-icon"
                      ><ClipboardCheck class="size-4" aria-hidden="true"
                    /></span>
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
                      <span class="meta"
                        >{{ factoryLabel(request.factory_id) }} ·
                        {{ departmentLabel(request.department) }}</span
                      >
                      <span class="pos">申请职位：{{ request.position }}</span>
                    </span>
                    <span class="time">{{
                      formatBusinessDateTime(request.submitted_at, { includeSeconds: true })
                    }}</span>
                  </button>
                </div>
              </aside>

              <article v-if="selectedRequest" class="panel detail">
                <button class="btn iamx-back-to-queue" @click="selectedRequestId = ''">
                  返回申请列表
                </button>
                <div class="applicant applicant-hero">
                  <span class="av">{{
                    avatarText(selectedRequest.display_name, selectedRequest.username)
                  }}</span>
                  <div class="h">
                    <div>
                      <b>{{ selectedRequest.display_name }}</b
                      ><span class="uid">{{ selectedRequest.username }}</span>
                    </div>
                    <div class="tags">
                      <span class="tag"
                        ><Factory class="size-3.5" aria-hidden="true" />{{
                          factoryLabel(selectedRequest.factory_id)
                        }}</span
                      >
                      <span class="tag"
                        ><Building2 class="size-3.5" aria-hidden="true" />{{
                          departmentLabel(selectedRequest.department)
                        }}</span
                      >
                      <span class="tag"
                        ><BriefcaseBusiness class="size-3.5" aria-hidden="true" />申请职位：{{
                          selectedRequest.position
                        }}</span
                      >
                      <span class="tag"
                        ><Phone
                          v-if="selectedRequest.phone"
                          class="size-3.5"
                          aria-hidden="true"
                        /><Mail v-else class="size-3.5" aria-hidden="true" />{{
                          contactLabel(selectedRequest)
                        }}</span
                      >
                    </div>
                  </div>
                </div>

                <section class="section position-review-section approval-surface-section">
                  <div class="sec-title">
                    <span class="st-ic"
                      ><BriefcaseBusiness class="size-4" aria-hidden="true"
                    /></span>
                    <div class="sec-title-copy">
                      <h3>注册资料核验</h3>
                      <span class="hint">资料填错可直接修正；账号 / 工号保持唯一防篡改</span>
                    </div>
                  </div>
                  <div class="registration-review-grid">
                    <label class="position-confirm-field">
                      <span class="field-label"><span>姓名</span><small>员工真实姓名</small></span>
                      <input
                        v-model="approvalProfile(selectedRequest).display_name"
                        aria-label="确认姓名"
                        autocomplete="name"
                        type="text"
                      />
                    </label>
                    <label class="position-confirm-field immutable-field">
                      <span class="field-label"
                        ><span>账号 / 工号</span><small>只读防篡改</small></span
                      >
                      <input
                        :value="selectedRequest.username"
                        aria-label="账号或工号"
                        disabled
                        type="text"
                      />
                    </label>
                    <label class="position-confirm-field">
                      <span class="field-label"
                        ><span>电话号码</span><small>手机或座机</small></span
                      >
                      <input
                        v-model="approvalProfile(selectedRequest).phone"
                        aria-label="确认电话"
                        autocomplete="tel"
                        type="tel"
                      />
                    </label>
                    <label class="position-confirm-field">
                      <span class="field-label"
                        ><span>企业邮箱</span><small>业务通知接收</small></span
                      >
                      <input
                        v-model="approvalProfile(selectedRequest).email"
                        aria-label="确认邮箱"
                        autocomplete="email"
                        type="email"
                      />
                    </label>
                    <label class="position-confirm-field">
                      <span class="field-label"
                        ><span>所属厂区</span><small>主生产基地</small></span
                      >
                      <select
                        v-model="approvalProfile(selectedRequest).factory_id"
                        aria-label="确认厂区"
                        @change="
                          approvalProfile(selectedRequest).department =
                            approvalDepartments[0]?.code ?? ''
                        "
                      >
                        <option
                          v-for="factory in factoryOptions"
                          :key="factory.id"
                          :value="factory.id"
                        >
                          {{ factory.shortName }}
                        </option>
                      </select>
                    </label>
                    <label class="position-confirm-field">
                      <span class="field-label"><span>所属部门</span><small>业务归属</small></span>
                      <select
                        v-model="approvalProfile(selectedRequest).department"
                        aria-label="确认部门"
                        @change="handleProfileDepartmentChange(selectedRequest)"
                      >
                        <option
                          v-for="department in approvalDepartments"
                          :key="department.code"
                          :value="department.code"
                        >
                          {{ department.name }}
                        </option>
                      </select>
                    </label>
                    <label class="position-confirm-field registration-position-field">
                      <span class="field-label"
                        ><span>真实职位（可修改）</span><small>用于名片与通讯录展示</small></span
                      >
                      <input
                        v-model="approvalProfile(selectedRequest).position"
                        aria-label="确认职位"
                        autocomplete="organization-title"
                        list="approval-position-suggestions"
                        maxlength="128"
                        placeholder="请核对或修正员工填写的真实职位"
                        type="text"
                      />
                      <datalist id="approval-position-suggestions">
                        <option
                          v-for="item in selectedPositionSuggestions"
                          :key="item"
                          :value="item"
                        ></option>
                      </datalist>
                      <span
                        v-if="selectedPositionSuggestions.length"
                        class="position-suggestion-chips"
                        aria-label="真实职位建议"
                      >
                        <span v-for="item in selectedPositionSuggestions.slice(0, 4)" :key="item"
                          >+ {{ item }}</span
                        >
                      </span>
                    </label>
                  </div>
                  <fieldset
                    v-if="selectedProfile?.factory_id === 'group-management'"
                    class="position-confirm-field"
                  >
                    <legend>业务范围（必须明确选择）</legend>
                    <label
                      v-for="factory in organizations.filter(
                        (o) => o.kind === 'factory' && o.status === 'active',
                      )"
                      :key="factory.id"
                    >
                      <input
                        v-model="approvalProfile(selectedRequest).business_factory_ids"
                        type="checkbox"
                        :value="factory.id"
                      />{{ factory.name }}
                    </label>
                  </fieldset>
                  <p class="position-role-note">
                    真实职位只用于个人资料展示；下方内置权限职位才决定系统可用功能。
                  </p>
                </section>

                <section class="section approval-surface-section permission-position-section">
                  <div class="sec-title">
                    <span class="st-ic permission-icon"
                      ><ShieldCheck class="size-4" aria-hidden="true"
                    /></span>
                    <div class="sec-title-copy">
                      <h3>内置权限职位授权</h3>
                      <span class="hint">核心安全机制：由系统内置职位决定具体业务模块操作权限</span>
                    </div>
                  </div>
                  <p class="system-position-department-label">
                    员工资料部门：<strong>{{
                      departmentLabel(approvalProfile(selectedRequest).department)
                    }}</strong
                    >；可从全部内置职位中选择权限职位
                  </p>
                  <div
                    v-if="recommendedApprovalSystemPosition && !selectedApprovalSystemPosition"
                    class="recommendation-banner"
                    data-testid="registration-position-recommendation"
                  >
                    <span class="recommendation-icon"
                      ><Sparkles class="size-4" aria-hidden="true"
                    /></span>
                    <span class="recommendation-copy">
                      <strong
                        >系统推荐：{{
                          recommendedApprovalSystemPosition.position_department_name
                        }}
                        · {{ recommendedApprovalSystemPosition.name }}</strong
                      >
                      <span>推荐仅用于提示，不会自动选中或授权；请管理员核对后主动选择。</span>
                    </span>
                    <span class="recommendation-state">需人工确认</span>
                  </div>
                  <template v-if="allSystemPositions.length">
                    <label class="system-position-picker">
                      <span class="picker-label"
                        ><span>选择内置权限职位</span><small>单选机制 · 统一下发</small></span
                      >
                      <select
                        :value="getSelectedSystemPositionId(selectedRequest)"
                        aria-label="选择内置权限职位"
                        @change="
                          setSelectedSystemPosition(
                            selectedRequest.id,
                            ($event.target as HTMLSelectElement).value,
                          )
                        "
                      >
                        <option value="" disabled>请选择内置权限职位</option>
                        <optgroup
                          v-for="group in groupedSystemPositions"
                          :key="group.department"
                          :label="group.name"
                        >
                          <option v-for="role in group.positions" :key="role.id" :value="role.id">
                            {{ role.name }} ·
                            {{
                              role.permission_count
                                ? `${role.permission_count} 项权限`
                                : '权限待配置'
                            }}{{
                              selectedRequest.recommended_role_ids.includes(role.id)
                                ? ' · 推荐'
                                : ''
                            }}
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
                      <span class="selected-system-position-check"
                        ><Check class="size-3.5" aria-hidden="true"
                      /></span>
                      <div class="selected-system-position-copy">
                        <div class="selected-system-position-title">
                          <strong
                            >{{
                              departmentLabel(selectedApprovalSystemPosition.position_department)
                            }}
                            · {{ selectedApprovalSystemPosition.name }}</strong
                          >
                          <span
                            v-if="
                              selectedRequest.recommended_role_ids.includes(
                                selectedApprovalSystemPosition.id,
                              )
                            "
                            >推荐</span
                          >
                        </div>
                        <p
                          :title="
                            selectedApprovalSystemPosition.description ||
                            selectedApprovalSystemPosition.code
                          "
                        >
                          {{
                            selectedApprovalSystemPosition.description ||
                            selectedApprovalSystemPosition.code
                          }}
                        </p>
                      </div>
                      <b class="selected-system-position-count">{{
                        selectedApprovalSystemPosition.permission_count
                          ? `${selectedApprovalSystemPosition.permission_count} 项权限`
                          : '权限待配置'
                      }}</b>
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
                    />
                  </label>
                  <button
                    type="button"
                    class="btn btn-reject"
                    :disabled="Boolean(actionKey)"
                    @click="rejectRequest(selectedRequest)"
                  >
                    <XCircle class="size-4" aria-hidden="true" />
                    驳回申请
                  </button>
                  <button
                    type="button"
                    class="btn btn-approve"
                    :disabled="Boolean(actionKey)"
                    @click="approveRequest(selectedRequest)"
                  >
                    <LoaderCircle
                      v-if="actionKey === `approve:${selectedRequest.id}`"
                      class="size-4 animate-spin"
                      aria-hidden="true"
                    />
                    <Check v-else class="size-4" aria-hidden="true" />
                    <span>{{
                      actionKey === `approve:${selectedRequest.id}`
                        ? '正在开通...'
                        : '通过并开通账号'
                    }}</span>
                  </button>
                </div>
              </article>
            </template>
          </section> </TabsContent
        ><TabsContent value="password-reset"
          ><section v-if="canManageUsers && activeTab === 'password-reset'" class="panel">
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
                <RefreshCw
                  class="size-3.5"
                  :class="{ 'animate-spin': isLoading }"
                  aria-hidden="true"
                />
                刷新申请
              </button>
            </div>
            <div v-if="isLoading" class="empty-card">正在加载密码重置申请...</div>
            <div v-else-if="!passwordResetRequests.length" class="empty-card">
              当前筛选条件下没有密码重置申请。
            </div>
            <div
              v-else
              class="iamx-queue-layout"
              :class="{ 'has-selection': selectedPasswordResetRequest }"
            >
              <aside class="iamx-queue" aria-label="密码找回申请列表">
                <button
                  v-for="item in passwordResetRequests"
                  :key="item.id"
                  class="iamx-queue-item"
                  :aria-pressed="selectedPasswordResetRequest?.id === item.id"
                  @click="selectPasswordRequest(item.id)"
                >
                  <strong>{{ item.display_name || item.username }}</strong>
                  <p>{{ item.username }}</p>
                  <small
                    >{{ passwordResetStatusLabel(item.status) }} ·
                    {{ formatBusinessDateTime(item.submitted_at) }}</small
                  >
                </button>
              </aside>
              <div class="iamx-record-detail">
                <button
                  v-if="selectedPasswordResetRequest"
                  class="btn iamx-back-to-queue"
                  @click="selectedPasswordResetId = ''"
                >
                  返回申请列表
                </button>
                <p v-if="!selectedPasswordResetRequest" class="iamx-empty">请选择一条可见申请。</p>
                <article
                  v-for="resetRequest in selectedPasswordResetRequest
                    ? [selectedPasswordResetRequest]
                    : []"
                  :key="resetRequest.id"
                  class="request-card"
                  :class="{
                    'ring-2 ring-teal-600/30': selectedPasswordResetRequest?.id === resetRequest.id,
                  }"
                  @click="selectedPasswordResetId = resetRequest.id"
                >
                  <div class="request-top">
                    <span class="request-avatar">{{
                      avatarText(resetRequest.display_name, resetRequest.username)
                    }}</span>
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
                      <b>{{
                        formatBusinessDateTime(resetRequest.submitted_at, { includeSeconds: true })
                      }}</b>
                    </div>
                    <div class="meta-wide">
                      <LifeBuoy class="size-4" aria-hidden="true" />
                      <span>说明</span>
                      <b>{{ resetRequest.note || '未填写补充说明' }}</b>
                    </div>
                  </div>

                  <div v-if="resetRequest.status === 'legacy_invalid'" class="recommend-box">
                    <CircleAlert class="size-4 shrink-0 text-amber-700" aria-hidden="true" />
                    <b
                      >该申请来自旧版流程，不能批准或重新开放。请申请人在原浏览器重新提交密码重置申请。</b
                    >
                  </div>
                  <div
                    v-else-if="resetRequest.matched_user"
                    class="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-3 text-[12px] text-slate-600"
                  >
                    <div class="flex items-center gap-2 font-bold text-slate-800">
                      <UserCheck class="size-4 text-teal-700" aria-hidden="true" />
                      系统员工资料
                    </div>
                    <div class="mt-2 grid gap-1 sm:grid-cols-2">
                      <span
                        >姓名：<b>{{ resetRequest.matched_user.display_name || '-' }}</b></span
                      >
                      <span
                        >账号：<b>{{ resetRequest.matched_user.username }}</b></span
                      >
                      <span
                        >厂区：<b>{{
                          factoryLabel(resetRequest.matched_user.factory_id) || '-'
                        }}</b></span
                      >
                      <span
                        >部门：<b>{{
                          departmentLabel(resetRequest.matched_user.department) || '-'
                        }}</b></span
                      >
                      <span
                        >电话：<b>{{ resetRequest.matched_user.phone || '-' }}</b></span
                      >
                      <span
                        >邮箱：<b>{{ resetRequest.matched_user.email || '-' }}</b></span
                      >
                    </div>
                    <div class="mt-2 flex flex-wrap gap-2">
                      <span
                        class="pill"
                        :class="
                          resetRequest.match_checks.display_name ? 'pill-green' : 'pill-amber'
                        "
                        >姓名{{ resetRequest.match_checks.display_name ? '一致' : '需核验' }}</span
                      >
                      <span
                        class="pill"
                        :class="resetRequest.match_checks.contact ? 'pill-green' : 'pill-amber'"
                        >联系方式{{ resetRequest.match_checks.contact ? '一致' : '需核验' }}</span
                      >
                      <span
                        class="pill"
                        :class="resetRequest.match_checks.scope ? 'pill-green' : 'pill-amber'"
                        >厂区部门{{ resetRequest.match_checks.scope ? '一致' : '需核验' }}</span
                      >
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
            </div>
          </section> </TabsContent
        ><TabsContent value="users"
          ><section v-if="canManageUsers" class="panel users-panel">
            <div class="table-tools">
              <label class="search-box">
                <Search class="size-4" aria-hidden="true" />
                <input
                  v-model="userSearch"
                  aria-label="搜索用户"
                  placeholder="搜索姓名、工号、联系方式、个人职位或权限职位..."
                  type="search"
                />
              </label>
              <div class="seg">
                <button
                  type="button"
                  :class="{ on: userStatusFilter === 'all' }"
                  @click="userStatusFilter = 'all'"
                >
                  全部
                </button>
                <button
                  type="button"
                  :class="{ on: userStatusFilter === 'active' }"
                  @click="userStatusFilter = 'active'"
                >
                  正常
                </button>
                <button
                  type="button"
                  :class="{ on: userStatusFilter === 'suspended' }"
                  @click="userStatusFilter = 'suspended'"
                >
                  停用
                </button>
                <button
                  type="button"
                  :class="{ on: userStatusFilter === 'retired' }"
                  @click="userStatusFilter = 'retired'"
                >
                  已离职
                </button>
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
                        <span v-if="user.phone"
                          ><Phone class="size-3.5" aria-hidden="true" />{{ user.phone }}</span
                        >
                        <span v-if="user.email"
                          ><Mail class="size-3.5" aria-hidden="true" />{{ user.email }}</span
                        >
                        <span v-if="!user.phone && !user.email" class="muted small">未填写</span>
                      </div>
                    </td>
                    <td class="muted">
                      {{
                        userPrimaryFactory(user) ? factoryLabel(userPrimaryFactory(user)) : '待确认'
                      }}
                      ·
                      {{
                        userPrimaryDepartment(user)
                          ? departmentLabel(userPrimaryDepartment(user))
                          : '待确认'
                      }}
                    </td>
                    <td>
                      <span class="employee-position-text">{{ userPosition(user) }}</span>
                    </td>
                    <td>
                      <div class="role-tags">
                        <span v-if="user.system_position_role_id" class="pill pill-teal"
                          ><span></span>{{ userSystemPositionName(user) }}</span
                        >
                        <span v-else class="tag">未分配</span>
                      </div>
                    </td>
                    <td>
                      <span class="pill" :class="userStatusPresentation(user.status).toneClass">
                        <span></span>{{ userStatusPresentation(user.status).label }}
                      </span>
                    </td>
                    <td class="muted">
                      {{ formatBusinessDateTime(user.last_login_at, { includeSeconds: true }) }}
                    </td>
                    <td>
                      <div class="row-ops">
                        <RouterLink
                          v-if="
                            authStore.can('system:access_manage') &&
                            (user.status === 'active' || user.status === 'suspended')
                          "
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
                <span
                  >共 {{ users.length }} 个账号 · 当前显示 {{ filteredUsers.length }} 个 ·
                  待审批账号 {{ pendingUsers.length }} 个</span
                >
                <span class="table-foot-badge"
                  ><UserCog class="size-3.5" aria-hidden="true" /> 内置职位授权</span
                >
              </div>
            </div>
          </section>
        </TabsContent></TabsRoot
      >
      <IamDialogSurface
        ref="resetSurface"
        v-model:open="resetReviewOpen"
        :title="
          passwordResetReviewMode === 'reject'
            ? '驳回密码重置申请'
            : passwordResetReviewMode === 'reissue'
              ? '重新开放改密时限'
              : '批准并开放自助改密'
        "
        :description="
          passwordResetReviewTarget
            ? `申请 ${passwordResetReviewTarget.id} · ${passwordResetReviewTarget.display_name || passwordResetReviewTarget.username}`
            : ''
        "
        :busy="Boolean(actionKey)"
        :dirty="Boolean(passwordResetReviewComment || passwordResetIdentityVerified)"
        @closed="clearPasswordReview"
        ><template v-if="passwordResetReviewTarget">
          <div
            v-if="passwordResetReviewMode === 'reissue'"
            class="mt-4 rounded-xl border border-amber-100 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800"
          >
            将仅把原设备自助改密时限重新开放 4 小时，不会生成密码、修改用户密码或撤销现有会话。
          </div>
          <div
            v-else-if="passwordResetReviewMode === 'approve'"
            class="mt-4 rounded-xl border border-teal-100 bg-teal-50 px-3 py-2 text-xs leading-5 text-teal-900"
          >
            审核通过后，申请人只能在提交申请的原浏览器中设置新密码。系统不会生成或显示临时密码。
          </div>
          <label class="mt-4 block">
            <span class="mb-1.5 block text-xs font-bold text-slate-700">{{
              passwordResetReviewMode === 'reject' ? '驳回原因' : '审核 / 核验说明'
            }}</span>
            <textarea
              v-model="passwordResetReviewComment"
              class="min-h-24 w-full resize-none rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm outline-none focus:border-teal-700 focus:bg-white focus:ring-[3px] focus:ring-teal-700/15"
              :placeholder="
                passwordResetReviewMode === 'reject'
                  ? '请说明资料无法核验的原因'
                  : '例如：已电话核验员工身份'
              "
            ></textarea>
          </label>
          <label
            v-if="passwordResetReviewMode !== 'reject'"
            class="mt-3 flex cursor-pointer items-start gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-xs leading-5 text-slate-700"
          >
            <input v-model="passwordResetIdentityVerified" class="mt-0.5 size-4" type="checkbox" />
            <span>我已通过内部资料或本人确认，核验申请人与账号本人一致。</span>
          </label>
          <div class="mt-5 flex justify-end gap-2">
            <button
              type="button"
              class="btn"
              :disabled="Boolean(actionKey)"
              @click="closePasswordResetReview"
            >
              取消
            </button>
            <button
              type="button"
              class="btn"
              :class="passwordResetReviewMode === 'reject' ? 'btn-danger' : 'btn-primary'"
              :disabled="
                Boolean(actionKey) ||
                (passwordResetReviewMode !== 'reject' && !passwordResetIdentityVerified)
              "
              @click="submitPasswordResetReview"
            >
              <LoaderCircle
                v-if="actionKey.startsWith('password-reset:')"
                class="size-4 animate-spin"
                aria-hidden="true"
              />
              <CheckCircle2 v-else class="size-4" aria-hidden="true" />
              确认{{
                passwordResetReviewMode === 'reject'
                  ? '驳回'
                  : passwordResetReviewMode === 'reissue'
                    ? '重新开放'
                    : '批准'
              }}
            </button>
          </div>
        </template></IamDialogSurface
      >
    </div>
    <IamLeaveGuard ref="leaveGuard" :dirty="registrationDirty" :busy="Boolean(actionKey)" />
  </section>
</template>

<style scoped src="./iam-account.css"></style>
