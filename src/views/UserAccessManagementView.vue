<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  LoaderCircle,
  LockKeyhole,
  RefreshCw,
  Save,
  ShieldCheck,
  X,
} from '@lucide/vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute } from 'vue-router'
import {
  iamApi,
  type PermissionCatalogItem,
  type RoleAccessResponse,
  type RoleSummary,
  type UserAccessResponse,
  type UserAccessPreviewResponse,
  type UserSystemPositionPreviewResponse,
} from '@/api/iam'
import { TabsRoot, TabsList, TabsTrigger, TabsContent } from 'reka-ui'
import IamLeaveGuard from '@/components/iam/workspace/IamLeaveGuard.vue'
import IamDialogSurface from '@/components/iam/workspace/IamDialogSurface.vue'
import {
  knownIdentityMode,
  rememberIdentityMode,
} from '@/components/iam/workspace/identity-ui-context'
import IamIdentitySummary from '@/components/iam/IamIdentitySummary.vue'
import IamNavigation from '@/components/iam/IamNavigation.vue'
import {
  permissionAccessKindLabel,
  permissionDisplayLabel,
  permissionEffectiveScopeLabel,
  permissionRiskLabel,
  permissionStatusLabel,
  roleScopeModeDescription,
  roleScopeModeLabel,
} from '@/components/iam/permissionCatalogLabels'
import { registrationDepartments } from '@/data/registrationDepartments'
import { getApiErrorMessage } from '@/lib/http'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const authStore = useAuthStore()
const activeSection = ref('exceptions')
const identityMode = computed(() =>
  knownIdentityMode(authStore.currentUser?.id || '', userId.value),
)
const previewOpen = ref(false)
const selfReviewOpen = ref(false)
const supplierOpen = ref(false)
let routeGeneration = 0
let loadGeneration = 0
let supplierGeneration = 0
let selfReviewGeneration = 0

type DisplayPermission = PermissionCatalogItem & { catalog_missing?: boolean }
type SelfReviewOverrideEffect = 'allow' | 'inherit'

const SELF_REVIEW_PERMISSION_CODE = 'internal_quote:self_review'

const access = ref<UserAccessResponse | null>(null)
const systemPositions = ref<RoleSummary[]>([])
const permissions = ref<PermissionCatalogItem[]>([])
const selectedSystemPositionRoleId = ref('')
const selectedPositionAccess = ref<RoleAccessResponse | null>(null)
const preview = ref<UserSystemPositionPreviewResponse | null>(null)
const selfReviewPreview = ref<UserAccessPreviewResponse | null>(null)
const selfReviewDesiredEffect = ref<SelfReviewOverrideEffect>('allow')
const confirmedHighRisk = ref(false)
const selfReviewConfirmedHighRisk = ref(false)
const supplierPermissionCodes = [
  'carton_supplier:read',
  'carton_supplier:edit',
  'carton_supplier:approve',
] as const
type SupplierPermissionCode = (typeof supplierPermissionCodes)[number]
const supplierDraft = reactive<Record<SupplierPermissionCode, boolean>>({
  'carton_supplier:read': false,
  'carton_supplier:edit': false,
  'carton_supplier:approve': false,
})
const supplierPreview = ref<UserAccessPreviewResponse | null>(null)
const supplierReason = ref('')
const supplierConfirmedHighRisk = ref(false)
const isPreviewingSupplier = ref(false)
const isCommittingSupplier = ref(false)
const isLoading = ref(false)
const isLoadingPosition = ref(false)
const isPreviewing = ref(false)
const isCommitting = ref(false)
const isPreviewingSelfReview = ref(false)
const isCommittingSelfReview = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
let selectedPositionAccessRequestSequence = 0
let previewRequestSequence = 0

const canManageAccess = computed(() => authStore.can('system:access_manage'))
const canManageSupplier = computed(
  () =>
    canManageAccess.value &&
    (authStore.grants ?? []).some(
      (grant) =>
        (grant.role_code === 'admin' || grant.role_id === 'admin') &&
        grant.factory_id === '*' &&
        ['*', 'system'].includes(grant.department),
    ),
)
const supplierCatalogReady = computed(() =>
  supplierPermissionCodes.every((code) =>
    permissions.value.some(
      (permission) => permission.code === code && permission.status === 'active',
    ),
  ),
)
const supplierCurrent = computed(
  () =>
    Object.fromEntries(
      supplierPermissionCodes.map((code) => [
        code,
        access.value?.overrides.some(
          (item) =>
            item.permission_code === code &&
            item.factory_id === '*' &&
            item.department === '*' &&
            item.state === 'active' &&
            item.effect === 'allow',
        ) ?? false,
      ]),
    ) as Record<SupplierPermissionCode, boolean>,
)
const userId = computed(() => String(route.params.userId ?? ''))
const userFactory = computed(() => access.value?.profile?.primary_factory_id ?? '')
const userDepartment = computed(() => access.value?.profile?.primary_department ?? '')
const hasPrimaryOrganization = computed(() => Boolean(userFactory.value && userDepartment.value))
const isSalesBusinessUser = computed(() => userDepartment.value === 'sales-business')
const selfReviewCatalogItem = computed(
  () =>
    permissions.value.find((permission) => permission.code === SELF_REVIEW_PERMISSION_CODE) ?? null,
)
const selfReviewEffectiveAccess = computed(
  () =>
    access.value?.effective_access.find(
      (entry) =>
        entry.permission_code === SELF_REVIEW_PERMISSION_CODE &&
        entry.factory_id === userFactory.value &&
        entry.department === 'sales-business',
    ) ?? null,
)
const selfReviewAllowed = computed(() => Boolean(selfReviewEffectiveAccess.value?.allowed))
const selfReviewDirectlyAllowed = computed(
  () => selfReviewAllowed.value && selfReviewEffectiveAccess.value?.source_type === 'user_override',
)
const selfReviewInherited = computed(
  () => selfReviewAllowed.value && selfReviewEffectiveAccess.value?.source_type !== 'user_override',
)
const selfReviewStatusText = computed(() => {
  if (selfReviewInherited.value) return '权限职位默认具备'
  if (selfReviewDirectlyAllowed.value) return '管理员已单独授予'
  return '当前未授权'
})
const assignableSystemPositions = computed(() =>
  hasPrimaryOrganization.value ? systemPositions.value : [],
)
const selectedSystemPosition = computed(
  () =>
    systemPositions.value.find((position) => position.id === selectedSystemPositionRoleId.value) ??
    null,
)
const recommendedSystemPosition = computed(
  () =>
    systemPositions.value.find(
      (position) => position.id === access.value?.recommended_system_position_role_id,
    ) ?? null,
)
const isSelectedGeneralManager = computed(
  () => selectedPositionAccess.value?.id === 'position_general_manager',
)
const hasPositionChange = computed(
  () =>
    Boolean(selectedSystemPositionRoleId.value) &&
    selectedSystemPositionRoleId.value !== (access.value?.system_position_role_id ?? ''),
)
const hasHistoricalAuthorization = computed(() =>
  Boolean((access.value?.cleanup_role_count ?? 0) || (access.value?.cleanup_override_count ?? 0)),
)
const hasVerifiedSelectedPositionAccess = computed(
  () =>
    !isLoadingPosition.value &&
    Boolean(selectedSystemPositionRoleId.value) &&
    selectedPositionAccess.value?.id === selectedSystemPositionRoleId.value,
)
const hasSystemPositionAction = computed(
  () =>
    identityMode.value !== 'v2' &&
    canManageAccess.value &&
    hasPrimaryOrganization.value &&
    Boolean(selectedSystemPositionRoleId.value) &&
    hasVerifiedSelectedPositionAccess.value &&
    (hasPositionChange.value || hasHistoricalAuthorization.value),
)
const groupedSystemPositions = computed(() => {
  const sorted = [...assignableSystemPositions.value]
    .filter((position) => position.is_system_position)
    .sort((left, right) => {
      const leftDepartment = registrationDepartments.findIndex(
        (item) => item.id === left.position_department,
      )
      const rightDepartment = registrationDepartments.findIndex(
        (item) => item.id === right.position_department,
      )
      const departmentOrder =
        (leftDepartment < 0 ? 999 : leftDepartment) - (rightDepartment < 0 ? 999 : rightDepartment)
      return (
        departmentOrder ||
        left.position_sort_order - right.position_sort_order ||
        left.name.localeCompare(right.name, 'zh-CN')
      )
    })
  const groups = new Map<string, { department: string; name: string; positions: RoleSummary[] }>()
  for (const position of sorted) {
    const department = position.position_department || 'other'
    const group = groups.get(department)
    if (group) group.positions.push(position)
    else
      groups.set(department, {
        department,
        name: position.position_department_name || department,
        positions: [position],
      })
  }
  return [...groups.values()]
})
const inheritedPermissionItems = computed<DisplayPermission[]>(() => {
  const enabledCodes = new Set(selectedPositionAccess.value?.permission_codes ?? [])
  const catalog = new Map(permissions.value.map((permission) => [permission.code, permission]))
  return [...enabledCodes]
    .map<DisplayPermission>(
      (code, index) =>
        catalog.get(code) ?? {
          code,
          name: code,
          description: '职位定义引用了权限目录中不存在的代码，请检查系统同步状态。',
          module_code: 'catalog_error',
          module_name: '权限目录异常',
          action: code.split(':').at(-1) ?? code,
          access_kind: 'operate',
          risk_level: 'high',
          scope_type: 'factory_department',
          status: 'inactive',
          sort_order: Number.MAX_SAFE_INTEGER - index,
          applicable_departments: [],
          requires_global_factory: false,
          scope_guidance: '权限目录缺失',
          catalog_missing: true,
        },
    )
    .sort(
      (left, right) => left.sort_order - right.sort_order || left.code.localeCompare(right.code),
    )
})
const groupedInheritedPermissions = computed(() => {
  const groups = new Map<
    string,
    { moduleCode: string; moduleName: string; items: DisplayPermission[] }
  >()
  inheritedPermissionItems.value.forEach((permission) => {
    const group = groups.get(permission.module_code)
    if (group) group.items.push(permission)
    else
      groups.set(permission.module_code, {
        moduleCode: permission.module_code,
        moduleName: permission.module_name,
        items: [permission],
      })
  })
  return [...groups.values()]
})
const visibleInheritedPermissionCount = computed(() =>
  groupedInheritedPermissions.value.reduce((total, group) => total + group.items.length, 0),
)
const selectedPositionScopeSummary = computed(() =>
  isSelectedGeneralManager.value
    ? '跨厂操作 · 全业务部门'
    : roleScopeModeLabel(selectedPositionAccess.value?.scope_mode),
)
const permissionLabels = computed(
  () =>
    new Map(
      permissions.value.map((permission) => [permission.code, permissionDisplayLabel(permission)]),
    ),
)
const previewBeforePositionLabel = computed(
  () =>
    preview.value?.before_role_ids
      .map((roleId, index) =>
        systemPositionDisplayName(roleId, preview.value?.before_role_names[index] ?? roleId),
      )
      .join('、') || '未分配内置职位',
)
const previewAfterPositionLabel = computed(() =>
  preview.value
    ? systemPositionDisplayName(preview.value.after_role_id, preview.value.after_role_name)
    : '',
)

function systemPositionDisplayName(roleId: string, fallback: string) {
  const position = systemPositions.value.find((item) => item.id === roleId)
  return position ? `${position.position_department_name} · ${position.name}` : fallback
}

function initialSystemPosition(userAccess: UserAccessResponse, positions: RoleSummary[]) {
  if (!userAccess.profile?.primary_factory_id || !userAccess.profile.primary_department) return ''
  const existing = positions.find((position) => position.id === userAccess.system_position_role_id)
  if (existing) return existing.id
  return ''
}

function isRecommendedPosition(roleId: string) {
  return roleId === access.value?.recommended_system_position_role_id
}

function roleSourceLabel(source?: string) {
  return source === 'code' ? '代码固定' : '数据库配置'
}

function clearProtectedAccess() {
  ++selectedPositionAccessRequestSequence
  ++previewRequestSequence
  ++supplierGeneration
  ++selfReviewGeneration
  access.value = null
  selectedPositionAccess.value = null
  selectedSystemPositionRoleId.value = ''
  permissions.value = []
  systemPositions.value = []
  previewOpen.value = false
  selfReviewOpen.value = false
  supplierOpen.value = false
  preview.value = null
  selfReviewPreview.value = null
  supplierPreview.value = null
}
function ensureAccessManagementPermission() {
  if (canManageAccess.value) return true
  errorMessage.value = '当前账号没有权限职位调整权限，无法执行该操作。'
  successMessage.value = ''
  preview.value = null
  selfReviewPreview.value = null
  supplierPreview.value = null
  return false
}

async function loadSelectedPositionAccess() {
  if (!ensureAccessManagementPermission()) return
  const requestSequence = ++selectedPositionAccessRequestSequence
  const roleId = selectedSystemPositionRoleId.value
  previewRequestSequence += 1
  isPreviewing.value = false
  preview.value = null
  successMessage.value = ''
  selectedPositionAccess.value = null
  if (!roleId) {
    isLoadingPosition.value = false
    return
  }
  isLoadingPosition.value = true
  try {
    const result = await iamApi.getRoleAccess(roleId)
    if (
      requestSequence !== selectedPositionAccessRequestSequence ||
      roleId !== selectedSystemPositionRoleId.value
    )
      return
    selectedPositionAccess.value = result
  } catch (error) {
    if (requestSequence === selectedPositionAccessRequestSequence) {
      errorMessage.value = getApiErrorMessage(error)
    }
  } finally {
    if (requestSequence === selectedPositionAccessRequestSequence) {
      isLoadingPosition.value = false
    }
  }
}

async function loadData() {
  const targetGeneration = routeGeneration
  const loadingGeneration = ++loadGeneration
  const viewerId = authStore.currentUser?.id || ''
  if (!canManageAccess.value) {
    access.value = null
    systemPositions.value = []
    permissions.value = []
    selectedSystemPositionRoleId.value = ''
    selectedPositionAccess.value = null
    preview.value = null
    selfReviewPreview.value = null
    supplierPreview.value = null
    isLoading.value = false
    isLoadingPosition.value = false
    isPreviewing.value = false
    isCommitting.value = false
    isPreviewingSelfReview.value = false
    isCommittingSelfReview.value = false
    errorMessage.value = ''
    successMessage.value = ''
    return
  }
  isLoading.value = true
  errorMessage.value = ''
  try {
    const [userAccess, positions, catalog] = await Promise.all([
      iamApi.getUserAccess(userId.value),
      iamApi.listSystemPositions(),
      iamApi.listPermissions('all'),
    ])
    if (
      targetGeneration !== routeGeneration ||
      loadingGeneration !== loadGeneration ||
      viewerId !== (authStore.currentUser?.id || '')
    ) return
    access.value = userAccess
    if (userAccess.identity_mode === 'legacy' || userAccess.identity_mode === 'v2') {
      rememberIdentityMode(viewerId, userId.value, userAccess.identity_mode)
    }
    for (const code of supplierPermissionCodes)
      supplierDraft[code] = userAccess.overrides.some(
        (item) =>
          item.permission_code === code &&
          item.factory_id === '*' &&
          item.department === '*' &&
          item.state === 'active' &&
          item.effect === 'allow',
      )
    systemPositions.value = positions.filter((position) => position.is_system_position)
    permissions.value = catalog
    selectedSystemPositionRoleId.value = initialSystemPosition(userAccess, systemPositions.value)
    preview.value = null
    selfReviewPreview.value = null
    supplierPreview.value = null
    await loadSelectedPositionAccess()
  } catch (error) {
    if (targetGeneration !== routeGeneration || loadingGeneration !== loadGeneration) return
    errorMessage.value = getApiErrorMessage(error)
    if ((error as { response?: { status?: number } })?.response?.status === 403) {
      clearProtectedAccess()
      await authStore.refreshSession()
    }
  } finally {
    if (targetGeneration === routeGeneration && loadingGeneration === loadGeneration)
      isLoading.value = false
  }
}

function discardChange() {
  if (!ensureAccessManagementPermission()) return
  selectedSystemPositionRoleId.value = access.value
    ? initialSystemPosition(access.value, systemPositions.value)
    : ''
  preview.value = null
  errorMessage.value = ''
  void loadSelectedPositionAccess()
}

async function previewChange() {
  const targetGeneration = routeGeneration
  if (!ensureAccessManagementPermission()) return
  if (!selectedSystemPositionRoleId.value) {
    errorMessage.value = '请先主动选择一个内置权限职位。'
    return
  }
  if (!hasVerifiedSelectedPositionAccess.value) {
    errorMessage.value = '请等待固定权限和数据范围加载完成后再预览。'
    return
  }
  if (!hasSystemPositionAction.value) {
    errorMessage.value = '当前权限职位和历史授权都不需要调整。'
    return
  }
  const roleId = selectedSystemPositionRoleId.value
  const requestSequence = ++previewRequestSequence
  isPreviewing.value = true
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const result = await iamApi.previewUserSystemPosition(userId.value, {
      base_revision: access.value?.authorization_version ?? 0,
      system_position_role_id: roleId,
    })
    if (requestSequence !== previewRequestSequence || roleId !== selectedSystemPositionRoleId.value)
      return
    preview.value = result
    confirmedHighRisk.value = false
  } catch (error) {
    if (requestSequence !== previewRequestSequence) return
    const status = (error as { response?: { status?: number } })?.response?.status
    if (
      JSON.stringify((error as { response?: { data?: unknown } }).response?.data ?? '').includes(
        'IDENTITY_CHANGE_REQUIRED',
      )
    ) {
      rememberIdentityMode(authStore.currentUser?.id || '', userId.value, 'v2')
      errorMessage.value = '此人员已使用正式任职，请返回人员中心，通过“办理变更”调整职位。'
      return
    }
    errorMessage.value =
      status === 409 ? '授权版本已变化，页面已刷新，请重新选择。' : getApiErrorMessage(error)
    if (status === 409) {
      const message = errorMessage.value
      await loadData()
      if (targetGeneration === routeGeneration) errorMessage.value = message
    }
    if (status === 403) {
      clearProtectedAccess()
      await authStore.refreshSession()
    }
  } finally {
    if (requestSequence === previewRequestSequence) {
      isPreviewing.value = false
    }
  }
}

async function commitChange() {
  if (isCommitting.value) return
  const targetGeneration = routeGeneration
  if (!ensureAccessManagementPermission()) return
  if (!preview.value) return
  isCommitting.value = true
  errorMessage.value = ''
  try {
    const result = await iamApi.commitUserSystemPosition(
      userId.value,
      preview.value.preview_token,
      confirmedHighRisk.value,
    )
    if (targetGeneration !== routeGeneration) return
    previewOpen.value = false
    preview.value = null
    await loadData()
    if (targetGeneration !== routeGeneration) return
    await authStore.refreshSession()
    if (targetGeneration !== routeGeneration) return
    successMessage.value = '权限职位已更换并立即生效。'
  } catch (error) {
    if (targetGeneration !== routeGeneration) return
    const status = (error as { response?: { status?: number } })?.response?.status
    errorMessage.value =
      status === 409 ? '预览已失效或授权版本已变化，请重新预览。' : getApiErrorMessage(error)
    previewOpen.value = false
    preview.value = null
    if (status === 409) {
      const message = errorMessage.value
      await loadData()
      if (targetGeneration === routeGeneration) errorMessage.value = message
    }
    if (status === 403) {
      clearProtectedAccess()
      await authStore.refreshSession()
    }
  } finally {
    if (targetGeneration === routeGeneration) isCommitting.value = false
  }
}

async function previewSelfReviewChange() {
  const targetGeneration = routeGeneration
  const request = ++selfReviewGeneration
  if (!ensureAccessManagementPermission() || !access.value) return
  if (!isSalesBusinessUser.value || !userFactory.value) {
    errorMessage.value = '本人报价自审权限仅适用于已确认厂区的业务部人员。'
    return
  }
  if (!selfReviewCatalogItem.value || selfReviewCatalogItem.value.status !== 'active') {
    errorMessage.value = '本人报价自审权限目录尚未启用，请重启后端完成权限同步。'
    return
  }
  if (selfReviewInherited.value) {
    errorMessage.value = '当前权限职位已默认包含本人报价自审，无需重复授予。'
    return
  }
  const effect: SelfReviewOverrideEffect = selfReviewDirectlyAllowed.value ? 'inherit' : 'allow'
  isPreviewingSelfReview.value = true
  errorMessage.value = ''
  successMessage.value = ''
  selfReviewPreview.value = null
  try {
    const result = await iamApi.previewUserAccess(userId.value, {
      base_revision: access.value.authorization_version,
      reason:
        effect === 'allow' ? '管理员授予内部报价本人自审权限' : '管理员收回内部报价本人自审权限',
      overrides: [
        {
          permission_code: SELF_REVIEW_PERMISSION_CODE,
          effect,
          factory_id: userFactory.value,
          department: 'sales-business',
        },
      ],
    })
    if (targetGeneration !== routeGeneration || request !== selfReviewGeneration) return
    selfReviewPreview.value = result
    selfReviewDesiredEffect.value = effect
    selfReviewConfirmedHighRisk.value = false
  } catch (error) {
    if (targetGeneration !== routeGeneration) return
    const status = (error as { response?: { status?: number } })?.response?.status
    errorMessage.value =
      status === 409 ? '用户授权版本已变化，页面已刷新，请重新操作。' : getApiErrorMessage(error)
    if (status === 409) {
      const message = errorMessage.value
      await loadData()
      if (targetGeneration === routeGeneration) errorMessage.value = message
    }
    if (status === 403) {
      clearProtectedAccess()
      await authStore.refreshSession()
    }
  } finally {
    if (targetGeneration === routeGeneration && request === selfReviewGeneration)
      isPreviewingSelfReview.value = false
  }
}

async function commitSelfReviewChange() {
  if (isCommittingSelfReview.value) return
  const targetGeneration = routeGeneration
  if (!ensureAccessManagementPermission() || !selfReviewPreview.value) return
  isCommittingSelfReview.value = true
  errorMessage.value = ''
  try {
    await iamApi.commitUserAccess(
      userId.value,
      selfReviewPreview.value.preview_token,
      selfReviewConfirmedHighRisk.value,
    )
    if (targetGeneration !== routeGeneration) return
    selfReviewOpen.value = false
    const granted = selfReviewDesiredEffect.value === 'allow'
    selfReviewPreview.value = null
    await loadData()
    if (targetGeneration !== routeGeneration) return
    await authStore.refreshSession()
    if (targetGeneration !== routeGeneration) return
    successMessage.value = granted
      ? '已授予本人报价自审权限，立即生效。'
      : '已收回本人报价自审权限，立即生效。'
  } catch (error) {
    if (targetGeneration !== routeGeneration) return
    const status = (error as { response?: { status?: number } })?.response?.status
    errorMessage.value =
      status === 409 ? '权限预览已失效或授权版本已变化，请重新操作。' : getApiErrorMessage(error)
    selfReviewOpen.value = false
    selfReviewPreview.value = null
    if (status === 409) {
      const message = errorMessage.value
      await loadData()
      if (targetGeneration === routeGeneration) errorMessage.value = message
    }
    if (status === 403) {
      clearProtectedAccess()
      await authStore.refreshSession()
    }
  } finally {
    if (targetGeneration === routeGeneration) isCommittingSelfReview.value = false
  }
}

async function previewSupplierPermissions() {
  const targetGeneration = routeGeneration
  const request = ++supplierGeneration
  if (!canManageSupplier.value || !access.value) return
  if (!supplierCatalogReady.value) {
    errorMessage.value = '供应商协同权限目录尚未启用，请重启后端完成权限同步。'
    return
  }
  if (
    (supplierDraft['carton_supplier:edit'] || supplierDraft['carton_supplier:approve']) &&
    !supplierDraft['carton_supplier:read']
  ) {
    errorMessage.value = '登记送货或确认接单前，必须同时授予查看权限。'
    return
  }
  const overrides = supplierPermissionCodes
    .filter((code) => supplierDraft[code] !== supplierCurrent.value[code])
    .map((code) => ({
      permission_code: code,
      effect: supplierDraft[code] ? ('allow' as const) : ('inherit' as const),
      factory_id: '*',
      department: '*',
    }))
  if (!overrides.length) {
    errorMessage.value = '供应商协同权限没有变化。'
    return
  }
  if (supplierReason.value.trim().length < 4) {
    errorMessage.value = '请填写至少四个字的权限变更原因。'
    return
  }
  isPreviewingSupplier.value = true
  errorMessage.value = ''
  successMessage.value = ''
  supplierPreview.value = null
  try {
    const result = await iamApi.previewUserAccess(userId.value, {
      base_revision: access.value.authorization_version,
      reason: supplierReason.value.trim(),
      overrides,
    })
    if (targetGeneration !== routeGeneration || request !== supplierGeneration) return
    supplierPreview.value = result
    supplierConfirmedHighRisk.value = false
  } catch (error) {
    if (targetGeneration !== routeGeneration || request !== supplierGeneration) return
    errorMessage.value = getApiErrorMessage(error)
    const status = (error as { response?: { status?: number } })?.response?.status
    if (status === 409) {
      const message = errorMessage.value
      await loadData()
      if (targetGeneration === routeGeneration) errorMessage.value = message
    }
    if (status === 403) {
      clearProtectedAccess()
      await authStore.refreshSession()
    }
  } finally {
    if (targetGeneration === routeGeneration && request === supplierGeneration)
      isPreviewingSupplier.value = false
  }
}

async function commitSupplierPermissions() {
  if (isCommittingSupplier.value) return
  const targetGeneration = routeGeneration
  if (!canManageSupplier.value || !supplierPreview.value) return
  isCommittingSupplier.value = true
  errorMessage.value = ''
  try {
    await iamApi.commitUserAccess(
      userId.value,
      supplierPreview.value.preview_token,
      supplierConfirmedHighRisk.value,
    )
    if (targetGeneration !== routeGeneration) return
    supplierOpen.value = false
    supplierPreview.value = null
    supplierReason.value = ''
    await loadData()
    if (targetGeneration !== routeGeneration) return
    await authStore.refreshSession()
    if (targetGeneration !== routeGeneration) return
    successMessage.value = '供应商协同权限已更新。'
  } catch (error) {
    if (targetGeneration !== routeGeneration) return
    errorMessage.value = getApiErrorMessage(error)
    supplierOpen.value = false
    supplierPreview.value = null
    const status = (error as { response?: { status?: number } })?.response?.status
    if (status === 409) {
      const message = errorMessage.value
      await loadData()
      if (targetGeneration === routeGeneration) errorMessage.value = message
    }
    if (status === 403) {
      clearProtectedAccess()
      await authStore.refreshSession()
    }
  } finally {
    if (targetGeneration === routeGeneration) isCommittingSupplier.value = false
  }
}

const leaveGuard = ref<InstanceType<typeof IamLeaveGuard>>()
const authorizationDirty = computed(
  () =>
    hasPositionChange.value ||
    supplierReason.value.trim().length > 0 ||
    supplierPermissionCodes.some((code) => supplierDraft[code] !== supplierCurrent.value[code]) ||
    confirmedHighRisk.value ||
    selfReviewConfirmedHighRisk.value ||
    supplierConfirmedHighRisk.value,
)
const authorizationBusy = computed(
  () => isCommitting.value || isCommittingSelfReview.value || isCommittingSupplier.value,
)
async function permitRouteLeave() {
  if (authorizationBusy.value) {
    errorMessage.value = '办理请求正在处理中，请等待结果后离开。'
    return false
  }
  return (await leaveGuard.value?.permitLeave()) ?? true
}
onBeforeRouteLeave(permitRouteLeave)
onBeforeRouteUpdate(permitRouteLeave)
function diffStateLabel(value: 'allow' | 'deny' | 'none') {
  return value === 'allow' ? '拥有' : value === 'deny' ? '禁止' : '无'
}

watch(preview, (value) => {
  if (value) previewOpen.value = true
})
watch(selfReviewPreview, (value) => {
  if (value) selfReviewOpen.value = true
})
watch(supplierPreview, (value) => {
  if (value) supplierOpen.value = true
})
watch(
  [supplierDraft, supplierReason],
  () => {
    ++supplierGeneration
    supplierPreview.value = null
    supplierOpen.value = false
    supplierConfirmedHighRisk.value = false
    isPreviewingSupplier.value = false
  },
  { deep: true, flush: 'sync' },
)
watch(
  [userId, () => authStore.currentUser?.id || ''],
  () => {
    ++routeGeneration
    ++loadGeneration
    ++selectedPositionAccessRequestSequence
    ++previewRequestSequence
    ++supplierGeneration
    ++selfReviewGeneration
    access.value = null
    selectedPositionAccess.value = null
    selectedSystemPositionRoleId.value = ''
    permissions.value = []
    systemPositions.value = []
    preview.value = null
    selfReviewPreview.value = null
    supplierPreview.value = null
    previewOpen.value = false
    selfReviewOpen.value = false
    supplierOpen.value = false
    confirmedHighRisk.value = false
    selfReviewConfirmedHighRisk.value = false
    supplierConfirmedHighRisk.value = false
    supplierReason.value = ''
    activeSection.value = 'exceptions'
    for (const code of supplierPermissionCodes) supplierDraft[code] = false
    isCommitting.value = false
    isPreviewing.value = false
    isCommittingSelfReview.value = false
    isPreviewingSelfReview.value = false
    isCommittingSupplier.value = false
    isPreviewingSupplier.value = false
    errorMessage.value = ''
    successMessage.value = ''
    void loadData()
  },
  { immediate: true },
)
onBeforeUnmount(() => {
  ++routeGeneration
  ++loadGeneration
  ++selectedPositionAccessRequestSequence
  ++previewRequestSequence
  ++supplierGeneration
  ++selfReviewGeneration
})
</script>

<template>
  <section class="iamx-access-page">
    <IamNavigation
      title="调整权限职位"
      subtitle="实际职位用于人员资料；权限职位由管理员主动选择，并固定继承代码定义的权限和范围。"
    />

    <div class="grid min-w-0 gap-4">
      <RouterLink
        class="inline-flex w-fit items-center gap-2 text-sm font-bold text-slate-600 hover:text-emerald-800"
        :to="`/system/users?person=${userId}`"
      >
        <ArrowLeft class="size-4" aria-hidden="true" />返回人员详情
      </RouterLink>

      <section
        v-if="!canManageAccess"
        data-testid="user-access-protected-notice"
        role="status"
        class="flex items-start gap-3 rounded-2xl border border-slate-300 bg-white p-5 text-sm text-slate-700 shadow-sm"
      >
        <span
          class="grid size-10 shrink-0 place-items-center rounded-xl bg-emerald-50 text-emerald-700"
          ><LockKeyhole class="size-5" aria-hidden="true"
        /></span>
        <div>
          <h2 class="font-bold text-slate-950">页面可访问 · 权限资料受保护</h2>
          <p class="mt-1 leading-6 text-slate-500">
            当前账号没有权限职位调整权限。用户授权明细不会在此模式下读取或展示，职位选择、变更预览及提交操作均不可用。
          </p>
        </div>
      </section>

      <div
        v-if="errorMessage"
        role="alert"
        class="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800"
      >
        <AlertTriangle class="mt-0.5 size-4 shrink-0" aria-hidden="true" />{{ errorMessage }}
        <button class="iamx-link-button" :disabled="isLoading" @click="loadData">
          重新读取资料
        </button>
      </div>
      <div
        v-if="successMessage"
        role="status"
        class="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm font-semibold text-emerald-800"
      >
        {{ successMessage }}
      </div>

      <div
        v-if="isLoading"
        class="grid min-h-72 place-items-center rounded-2xl border border-slate-200 bg-white"
      >
        <div class="text-center text-slate-500">
          <LoaderCircle class="mx-auto mb-3 size-7 animate-spin text-emerald-700" />
          <p>正在读取用户权限职位…</p>
        </div>
      </div>

      <template v-else-if="canManageAccess && access">
        <IamIdentitySummary :access="access" />

        <TabsRoot v-model="activeSection"
          ><TabsList class="iamx-tabs" aria-label="授权设置栏目"
            ><TabsTrigger value="exceptions">个人例外</TabsTrigger
            ><TabsTrigger v-if="canManageSupplier" value="supplier">供应商协作</TabsTrigger
            ><TabsTrigger value="legacy">旧权限兼容</TabsTrigger></TabsList
          ><TabsContent value="exceptions"
            ><p v-if="!isSalesBusinessUser" class="iamx-notice">
              当前个人例外仅支持已确认厂区的业务部人员办理本人报价自审。
            </p>
            <article
              v-if="isSalesBusinessUser"
              data-testid="self-review-permission-card"
              class="min-w-0 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
            >
              <div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                <div class="min-w-0">
                  <div class="flex flex-wrap items-center gap-2">
                    <h2 class="flex items-center gap-2 font-bold text-slate-950">
                      <ShieldCheck class="size-4 text-emerald-700" />个人特殊权限 · 本人报价自审
                    </h2>
                    <span
                      class="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-bold text-amber-700"
                      >高风险权限</span
                    >
                  </div>
                  <p class="mt-2 max-w-4xl text-sm leading-6 text-slate-500">
                    允许该人员审核本人创建、且建单时由本人担任业务审核负责人的内部报价。不会授权其审核别人创建的报价，也不会改变最终放行流程。
                  </p>
                  <p class="mt-2 text-xs leading-5 text-slate-400">
                    业务主管和业务经理的内置权限职位默认包含此权限；普通跟客由管理员按个人授予。更换内置权限职位会按现有规则清理个人特殊权限。
                  </p>
                </div>
                <div class="flex shrink-0 flex-col items-stretch gap-2 sm:items-end">
                  <span
                    class="rounded-full px-3 py-1.5 text-center text-xs font-bold"
                    :class="
                      selfReviewAllowed
                        ? 'bg-emerald-50 text-emerald-700'
                        : 'bg-slate-100 text-slate-600'
                    "
                    >{{ selfReviewStatusText }}</span
                  >
                  <button
                    v-if="!selfReviewInherited"
                    type="button"
                    class="inline-flex h-10 items-center justify-center gap-2 rounded-xl px-4 text-sm font-bold disabled:cursor-not-allowed disabled:opacity-50"
                    :class="
                      selfReviewDirectlyAllowed
                        ? 'border border-rose-200 bg-white text-rose-700 hover:bg-rose-50'
                        : 'bg-emerald-700 text-white hover:bg-emerald-800'
                    "
                    :disabled="
                      !canManageAccess ||
                      isPreviewingSelfReview ||
                      isCommittingSelfReview ||
                      selfReviewCatalogItem?.status !== 'active'
                    "
                    @click="previewSelfReviewChange"
                  >
                    <LoaderCircle v-if="isPreviewingSelfReview" class="size-4 animate-spin" />
                    <ShieldCheck v-else class="size-4" />
                    {{ selfReviewDirectlyAllowed ? '预览收回权限' : '预览授予权限' }}
                  </button>
                  <span v-else class="text-xs font-semibold text-emerald-700"
                    >随当前业务主管/经理职位自动生效</span
                  >
                </div>
              </div>
            </article> </TabsContent
          ><TabsContent value="supplier">
            <article
              v-if="canManageSupplier"
              data-testid="supplier-permission-card"
              class="min-w-0 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
            >
              <h2 class="font-bold text-slate-950">纸箱供应商协同权限</h2>
              <p class="mt-2 text-sm text-slate-600">
                可与华康 B
                质检等内部职位并存。查看范围自动限于东康已下单的服务厂区；仓库收货继续由内部权限控制。
              </p>
              <p class="mt-1 text-xs text-slate-500">
                权限授予全部厂区 /
                全部部门，具体订单仍按供应商和已发行采购单过滤。编辑用于登记送货；审批用于确认接单与承诺交期。
              </p>
              <div class="mt-4 grid gap-2 sm:grid-cols-3">
                <label
                  v-for="code in supplierPermissionCodes"
                  :key="code"
                  class="flex items-center gap-2 rounded-xl border border-slate-200 p-3 text-sm font-semibold"
                >
                  <input
                    v-model="supplierDraft[code]"
                    type="checkbox"
                    :aria-label="permissionLabels.get(code) || code"
                    :disabled="
                      !supplierCatalogReady || isPreviewingSupplier || isCommittingSupplier
                    "
                    @change="supplierPreview = null"
                  />
                  {{ permissionLabels.get(code) || code }}
                </label>
              </div>
              <label class="mt-4 block text-sm font-semibold"
                >开通/收回原因
                <input
                  v-model="supplierReason"
                  aria-label="供应商权限变更原因"
                  class="mt-1 block h-10 w-full rounded-lg border border-slate-200 px-3"
                  :disabled="isPreviewingSupplier || isCommittingSupplier"
                  @input="supplierPreview = null"
                />
              </label>
              <div class="mt-3 flex justify-end">
                <button
                  type="button"
                  class="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-bold text-white disabled:opacity-50"
                  :disabled="!supplierCatalogReady || isPreviewingSupplier || isCommittingSupplier"
                  @click="previewSupplierPermissions"
                >
                  {{ isPreviewingSupplier ? '正在预览…' : '预览供应商权限变更' }}
                </button>
              </div>
              <IamDialogSurface
                v-model:open="supplierOpen"
                title="确认供应商权限变更"
                :busy="isCommittingSupplier"
                @closed="supplierPreview = null"
                ><div v-if="supplierPreview">
                  <h3 class="font-bold">确认本次权限变更</h3>
                  <p v-for="diff in supplierPreview.diffs" :key="diff.permission_code" class="mt-1">
                    {{ permissionLabels.get(diff.permission_code) || diff.permission_code }}：{{
                      diffStateLabel(diff.before)
                    }}
                    → {{ diffStateLabel(diff.after) }}
                  </p>
                  <label v-if="supplierPreview.high_risk" class="mt-3 flex items-center gap-2"
                    ><input
                      v-model="supplierConfirmedHighRisk"
                      type="checkbox"
                      aria-label="确认供应商高风险权限"
                    />已核对跨厂区审批权限</label
                  >
                  <div class="mt-3 flex justify-end gap-2">
                    <button
                      type="button"
                      class="rounded-lg border bg-white px-3 py-2"
                      :disabled="isCommittingSupplier"
                      @click="supplierOpen = false"
                    >
                      取消</button
                    ><button
                      type="button"
                      class="rounded-lg bg-emerald-700 px-4 py-2 font-bold text-white disabled:opacity-50"
                      :disabled="
                        isCommittingSupplier ||
                        (supplierPreview.high_risk && !supplierConfirmedHighRisk)
                      "
                      @click="commitSupplierPermissions"
                    >
                      {{ isCommittingSupplier ? '正在保存…' : '确认保存权限' }}
                    </button>
                  </div>
                </div>
              </IamDialogSurface>
            </article> </TabsContent
          ><TabsContent value="legacy"
            ><p v-if="identityMode === 'unknown'" class="iamx-notice">
              尚未核实此人员的任职模式。旧权限办理是否可用由服务器核验；需要调整正式任职时请返回人员中心。
            </p>
            <p v-if="identityMode === 'v2'" class="iamx-notice">
              该人员已使用正式任职，请在人员中心通过“办理变更”调整职位与权限包。
            </p>
            <div v-else>
              <section class="grid min-w-0 gap-5 xl:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
                <article class="min-w-0 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                  <div class="mb-4 flex items-start justify-between gap-3">
                    <div>
                      <h2 class="flex items-center gap-2 font-bold">
                        <ShieldCheck class="size-4 text-emerald-700" />内置权限职位
                      </h2>
                      <p class="mt-1 text-sm text-slate-500">
                        更换职位后，原有底层角色和其他个人特殊权限会清理；供应商协同权限独立保留。
                      </p>
                    </div>
                    <span
                      class="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-bold text-emerald-700"
                      >单一职位</span
                    >
                  </div>

                  <div class="rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm">
                    <span class="text-xs font-semibold text-slate-500">权限职位</span>
                    <strong class="mt-1 block text-slate-950">{{
                      access.system_position_role_name || '尚未分配'
                    }}</strong>
                  </div>

                  <div
                    v-if="recommendedSystemPosition && !access.system_position_role_id"
                    data-testid="recommended-position-hint"
                    class="mt-3 rounded-xl border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900"
                  >
                    <b
                      >推荐：{{ recommendedSystemPosition.position_department_name }} ·
                      {{ recommendedSystemPosition.name }}</b
                    >
                    <p class="mt-1 leading-5 text-blue-700">
                      推荐仅用于提示，不会自动选中或授权；请管理员核对后主动选择。
                    </p>
                  </div>

                  <div
                    v-if="!hasPrimaryOrganization"
                    data-testid="missing-primary-department"
                    class="mt-4 flex gap-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm leading-6 text-amber-900"
                  >
                    <AlertTriangle class="mt-0.5 size-5 shrink-0" aria-hidden="true" />
                    <div>
                      <b>尚未确认主组织资料</b>
                      <p>请先在账号审批或用户资料中补全厂区和部门，再分配内置权限职位。</p>
                    </div>
                  </div>

                  <label v-else class="mt-4 grid gap-1.5 text-sm font-semibold text-slate-700">
                    选择新的内置权限职位
                    <select
                      v-model="selectedSystemPositionRoleId"
                      aria-label="选择新的内置权限职位"
                      class="h-11 w-full min-w-0 rounded-xl border border-slate-200 bg-white px-3 outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-500"
                      :disabled="!canManageAccess || isPreviewing || isCommitting"
                      @change="loadSelectedPositionAccess"
                    >
                      <option value="" disabled>请选择内置权限职位</option>
                      <optgroup
                        v-for="group in groupedSystemPositions"
                        :key="group.department"
                        :label="group.name"
                      >
                        <option
                          v-for="position in group.positions"
                          :key="position.id"
                          :value="position.id"
                        >
                          {{ position.name }}（{{ position.permission_count }} 项权限）{{
                            isRecommendedPosition(position.id) ? ' · 推荐' : ''
                          }}
                        </option>
                      </optgroup>
                    </select>
                    <span class="text-xs font-normal text-slate-400"
                      >显示全部内置职位，并按权限部门分组。</span
                    >
                  </label>

                  <div
                    v-if="selectedSystemPosition"
                    class="mt-3 rounded-xl border border-emerald-100 bg-emerald-50/60 p-3 text-sm text-emerald-950"
                  >
                    <div class="flex flex-wrap items-center gap-2">
                      <b
                        >{{ selectedSystemPosition.position_department_name }} ·
                        {{ selectedSystemPosition.name }}</b
                      >
                      <span
                        v-if="isRecommendedPosition(selectedSystemPosition.id)"
                        class="rounded-full bg-blue-100 px-2 py-0.5 text-[11px] font-bold text-blue-700"
                        >推荐</span
                      >
                    </div>
                    <p class="mt-1 leading-6 text-emerald-800">
                      {{ selectedSystemPosition.description || '该职位的权限由系统代码固定维护。' }}
                    </p>
                    <dl
                      v-if="selectedPositionAccess"
                      data-testid="selected-position-fixed-metadata"
                      class="mt-3 grid gap-2 sm:grid-cols-2"
                    >
                      <div class="rounded-lg bg-white/75 p-2.5">
                        <dt class="text-xs text-emerald-700">权限来源</dt>
                        <dd class="mt-0.5 font-bold">
                          {{ roleSourceLabel(selectedPositionAccess.source) }}
                        </dd>
                      </div>
                      <div class="rounded-lg bg-white/75 p-2.5">
                        <dt class="text-xs text-emerald-700">固定数据范围</dt>
                        <dd class="mt-0.5 font-bold">{{ selectedPositionScopeSummary }}</dd>
                      </div>
                      <div class="rounded-lg bg-white/75 p-2.5">
                        <dt class="text-xs text-emerald-700">定义版本</dt>
                        <dd class="mt-0.5 font-mono text-xs font-bold">
                          {{ selectedPositionAccess.definition_version || '待同步' }}
                        </dd>
                      </div>
                      <div class="min-w-0 rounded-lg bg-white/75 p-2.5">
                        <dt class="text-xs text-emerald-700">定义哈希</dt>
                        <dd class="mt-0.5 break-all font-mono text-[11px] font-bold">
                          {{ selectedPositionAccess.definition_hash || '待同步' }}
                        </dd>
                      </div>
                    </dl>
                    <p
                      v-if="selectedPositionAccess"
                      class="mt-2 inline-flex items-start gap-1.5 text-xs leading-5 text-emerald-800"
                    >
                      <LockKeyhole class="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />{{
                        roleScopeModeDescription(selectedPositionAccess.scope_mode)
                      }}
                    </p>
                    <p
                      v-if="isSelectedGeneralManager"
                      data-testid="selected-general-manager-boundary"
                      class="mt-2 rounded-lg border border-blue-200 bg-blue-50 p-2.5 text-xs font-semibold leading-5 text-blue-800"
                    >
                      跨厂操作 · 全业务部门；不包含账号与权限管理。
                    </p>
                  </div>

                  <div
                    v-if="hasHistoricalAuthorization"
                    class="mt-4 flex gap-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm leading-6 text-amber-900"
                  >
                    <AlertTriangle class="mt-0.5 size-5 shrink-0" aria-hidden="true" />
                    <div>
                      <b>检测到历史授权</b>
                      <p>
                        当前生效 {{ access.legacy_role_count }} 条旧角色、{{
                          access.active_override_count
                        }}
                        条个人特殊权限；本次共将清理 {{ access.cleanup_role_count }} 条普通角色和
                        {{ access.cleanup_override_count }}
                        条个人权限（包括尚未生效或已到期的残留授权）。
                      </p>
                    </div>
                  </div>

                  <div
                    v-if="canManageAccess && hasPrimaryOrganization"
                    data-testid="system-position-action-panel"
                    class="mt-4 flex flex-col gap-2 border-t border-slate-100 pt-4 sm:flex-row sm:justify-end"
                  >
                    <button
                      type="button"
                      class="inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 text-sm font-bold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                      :disabled="!canManageAccess || isPreviewing"
                      @click="discardChange"
                    >
                      <RefreshCw class="size-4" />取消修改
                    </button>
                    <button
                      type="button"
                      class="inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-emerald-700 px-5 text-sm font-bold text-white hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-50"
                      :disabled="!canManageAccess || !hasSystemPositionAction || isPreviewing"
                      @click="previewChange"
                    >
                      <LoaderCircle v-if="isPreviewing" class="size-4 animate-spin" /><Save
                        v-else
                        class="size-4"
                      />{{ hasPositionChange ? '预览职位调整' : '预览历史授权清理' }}
                    </button>
                  </div>
                </article>

                <article
                  class="min-w-0 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"
                >
                  <header class="border-b border-slate-200 px-5 py-4">
                    <div class="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <h2 class="font-bold">将继承的完整权限</h2>
                        <p class="mt-1 text-sm text-slate-500">
                          权限和数据范围由代码固定，管理员只能查看，不能逐项修改。
                        </p>
                      </div>
                      <span
                        class="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-bold text-slate-600"
                        >{{ visibleInheritedPermissionCount }} 项</span
                      >
                    </div>
                  </header>
                  <div v-if="isLoadingPosition" class="grid min-h-48 place-items-center">
                    <LoaderCircle class="size-6 animate-spin text-emerald-700" />
                  </div>
                  <div
                    v-else-if="groupedInheritedPermissions.length"
                    class="divide-y divide-slate-100"
                  >
                    <section
                      v-for="group in groupedInheritedPermissions"
                      :key="group.moduleCode"
                      class="p-5"
                    >
                      <div class="mb-3">
                        <h3 class="font-bold text-slate-900">{{ group.moduleName }}</h3>
                        <code class="text-xs text-slate-400">{{ group.moduleCode }}</code>
                      </div>
                      <ul class="grid gap-2 sm:grid-cols-2">
                        <li
                          v-for="permission in group.items"
                          :key="permission.code"
                          class="flex min-w-0 items-start gap-2 rounded-xl border p-3"
                          :class="
                            permission.catalog_missing
                              ? 'border-rose-200 bg-rose-50'
                              : 'border-slate-100 bg-slate-50'
                          "
                        >
                          <CheckCircle2
                            class="mt-0.5 size-4 shrink-0 text-emerald-600"
                            aria-hidden="true"
                          />
                          <span class="min-w-0 flex-1">
                            <span class="flex items-start justify-between gap-2"
                              ><span class="min-w-0"
                                ><b class="block text-sm">{{
                                  permissionDisplayLabel(permission)
                                }}</b
                                ><code class="block break-all text-xs text-slate-400">{{
                                  permission.code
                                }}</code></span
                              ><span
                                class="shrink-0 rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-bold text-emerald-800"
                                >已包含</span
                              ></span
                            >
                            <span class="mt-2 flex flex-wrap gap-1.5">
                              <span
                                class="rounded-full bg-white px-2 py-0.5 text-[11px] font-bold text-slate-600"
                                >{{ permissionAccessKindLabel(permission.access_kind) }}</span
                              >
                              <span
                                class="rounded-full bg-blue-50 px-2 py-0.5 text-[11px] font-bold text-blue-700"
                                >{{
                                  permissionEffectiveScopeLabel(
                                    permission,
                                    selectedPositionAccess?.scope_mode,
                                  )
                                }}</span
                              >
                              <span
                                class="rounded-full px-2 py-0.5 text-[11px] font-bold"
                                :class="
                                  permission.risk_level === 'high'
                                    ? 'bg-amber-50 text-amber-700'
                                    : 'bg-white text-slate-600'
                                "
                                >{{ permissionRiskLabel(permission.risk_level) }}</span
                              >
                              <span
                                class="rounded-full px-2 py-0.5 text-[11px] font-bold"
                                :class="
                                  permission.status === 'inactive'
                                    ? 'bg-rose-50 text-rose-700'
                                    : 'bg-emerald-50 text-emerald-700'
                                "
                                >{{ permissionStatusLabel(permission.status) }}</span
                              >
                            </span>
                            <span class="mt-1.5 block text-xs leading-5 text-slate-500">{{
                              permission.description || '暂无说明。'
                            }}</span>
                            <span
                              v-if="permission.catalog_missing"
                              class="mt-1 block text-xs font-semibold text-rose-700"
                              >权限目录缺失，当前定义异常。</span
                            >
                          </span>
                        </li>
                      </ul>
                    </section>
                  </div>
                  <p
                    v-else-if="!selectedPositionAccess"
                    class="p-8 text-center text-sm text-slate-500"
                  >
                    请先主动选择一个内置权限职位，再核对固定权限和数据范围。
                  </p>
                  <p v-else class="p-8 text-center text-sm text-slate-500">
                    该内置职位固定为空权限，当前保持默认拒绝。
                  </p>
                </article>
              </section>
            </div></TabsContent
          ></TabsRoot
        >
      </template>
    </div>

    <IamDialogSurface
      v-model:open="previewOpen"
      title="确认权限职位调整"
      :busy="isCommitting"
      @closed="preview = null"
      ><template v-if="canManageAccess && preview">
        <div class="max-h-[62vh] overflow-y-auto p-5">
          <div
            class="flex flex-col items-stretch gap-3 rounded-xl bg-slate-50 p-4 sm:flex-row sm:items-center"
          >
            <span class="flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
              ><small class="block text-slate-400">调整前</small
              ><b>{{ previewBeforePositionLabel }}</b></span
            >
            <ArrowRight class="mx-auto size-5 shrink-0 text-slate-400 sm:mx-0" />
            <span
              class="flex-1 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900"
              ><small class="block text-emerald-600">调整后</small
              ><b>{{ previewAfterPositionLabel }}</b></span
            >
          </div>
          <div class="mt-4 grid gap-3 sm:grid-cols-2">
            <div class="rounded-xl border border-slate-200 p-3 text-sm">
              <span class="text-slate-500">清理历史角色</span
              ><b class="mt-1 block text-lg">{{ preview.removed_role_count }} 条</b>
            </div>
            <div class="rounded-xl border border-slate-200 p-3 text-sm">
              <span class="text-slate-500">清理个人特殊权限</span
              ><b class="mt-1 block text-lg">{{ preview.removed_override_count }} 条</b>
            </div>
          </div>
          <div
            v-if="preview.diffs.length"
            class="mt-4 overflow-hidden rounded-xl border border-slate-200"
          >
            <div
              v-for="diff in preview.diffs"
              :key="`${diff.permission_code}:${diff.factory_id}:${diff.department}`"
              class="flex flex-col gap-2 border-b border-slate-100 p-3 text-sm last:border-b-0 sm:flex-row sm:items-center sm:justify-between"
            >
              <span class="min-w-0"
                ><b class="block">{{
                  permissionLabels.get(diff.permission_code) || diff.permission_code
                }}</b
                ><code class="block break-all text-xs text-slate-400">{{
                  diff.permission_code
                }}</code></span
              >
              <span
                class="shrink-0 font-bold"
                :class="diff.after === 'allow' ? 'text-emerald-700' : 'text-rose-700'"
                >{{ diffStateLabel(diff.before) }} → {{ diffStateLabel(diff.after) }}</span
              >
            </div>
          </div>
          <label
            v-if="preview.high_risk"
            class="mt-4 flex gap-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"
            ><input
              v-model="confirmedHighRisk"
              type="checkbox"
              class="mt-0.5 size-4 accent-amber-600"
              :disabled="!canManageAccess"
            /><span>我已核对高风险权限和历史授权清理范围。</span></label
          >
        </div>
        <footer class="flex justify-end gap-2 border-t border-slate-200 bg-slate-50 p-4">
          <button
            type="button"
            class="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-bold"
            :disabled="!canManageAccess || isCommitting"
            @click="previewOpen = false"
          >
            返回修改</button
          ><button
            type="button"
            class="inline-flex items-center gap-2 rounded-xl bg-emerald-700 px-4 py-2 text-sm font-bold text-white disabled:opacity-50"
            :disabled="
              !canManageAccess || isCommitting || (preview.high_risk && !confirmedHighRisk)
            "
            @click="commitChange"
          >
            <LoaderCircle v-if="isCommitting" class="size-4 animate-spin" /><CheckCircle2
              v-else
              class="size-4"
            />确认并立即生效
          </button>
        </footer>
      </template></IamDialogSurface
    >

    <IamDialogSurface
      v-model:open="selfReviewOpen"
      title="确认本人报价自审权限"
      :busy="isCommittingSelfReview"
      @closed="selfReviewPreview = null"
      ><template v-if="canManageAccess && selfReviewPreview">
        <div class="p-5">
          <div class="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm">
            <b class="block text-slate-950">本人创建报价可自审</b>
            <code class="mt-1 block text-xs text-slate-400">{{ SELF_REVIEW_PERMISSION_CODE }}</code>
            <p class="mt-3 leading-6 text-slate-600">
              {{
                selfReviewDesiredEffect === 'allow'
                  ? '授予后，该人员可审核本人创建且由本人负责的报价。'
                  : '收回后，该人员重新执行提交人与审核人分离规则。'
              }}
            </p>
          </div>
          <label
            v-if="selfReviewPreview.high_risk"
            class="mt-4 flex gap-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"
          >
            <input
              v-model="selfReviewConfirmedHighRisk"
              type="checkbox"
              class="mt-0.5 size-4 accent-amber-600"
              :disabled="isCommittingSelfReview"
            />
            <span
              >我已核对：该权限仅限本人创建且由本人负责的报价，但会允许同一账号提交并审核分段。</span
            >
          </label>
        </div>
        <footer class="flex justify-end gap-2 border-t border-slate-200 bg-slate-50 p-4">
          <button
            type="button"
            class="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-bold"
            :disabled="isCommittingSelfReview"
            @click="selfReviewOpen = false"
          >
            取消
          </button>
          <button
            type="button"
            class="inline-flex items-center gap-2 rounded-xl bg-emerald-700 px-4 py-2 text-sm font-bold text-white disabled:opacity-50"
            :disabled="
              isCommittingSelfReview ||
              (selfReviewPreview.high_risk && !selfReviewConfirmedHighRisk)
            "
            @click="commitSelfReviewChange"
          >
            <LoaderCircle v-if="isCommittingSelfReview" class="size-4 animate-spin" /><CheckCircle2
              v-else
              class="size-4"
            />确认并立即生效
          </button>
        </footer>
      </template></IamDialogSurface
    >
    <IamLeaveGuard ref="leaveGuard" :dirty="authorizationDirty" :busy="authorizationBusy" />
  </section>
</template>
