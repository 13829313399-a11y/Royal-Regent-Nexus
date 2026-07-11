<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  ArrowLeft,
  Building2,
  BriefcaseBusiness,
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
  Sparkles,
  UserCheck,
  UserCog,
  UserPlus,
  UserRoundX,
  Users,
  XCircle,
} from '@lucide/vue'
import {
  systemApi,
  type RegistrationRequestResponse,
  type RoleResponse,
  type SystemNotificationResponse,
  type UserResponse,
} from '@/api/system'
import UserAvatar from '@/components/common/UserAvatar.vue'
import { departmentMap, departments, factoryContexts } from '@/data/enterpriseMock'
import { getApiErrorMessage } from '@/lib/http'
import { useRoute } from 'vue-router'

const route = useRoute()
const activeTab = ref<'pending' | 'password-reset' | 'users'>('pending')
const requests = ref<RegistrationRequestResponse[]>([])
const users = ref<UserResponse[]>([])
const roles = ref<RoleResponse[]>([])
const systemNotifications = ref<SystemNotificationResponse[]>([])
const selectedRoles = ref<Record<string, string>>({})
const approvalComments = ref<Record<string, string>>({})
const rejectComments = ref<Record<string, string>>({})
const userSearch = ref('')
const userStatusFilter = ref<'all' | 'active' | 'suspended'>('all')
const selectedRequestId = ref('')
const isLoading = ref(false)
const actionKey = ref('')
const errorMessage = ref('')
const successMessage = ref('')

type PermissionDefinition = {
  label: string
  code: string
  matchCode?: string
  locked?: boolean
}

type PermissionGroupDefinition = {
  title: string
  permissions: PermissionDefinition[]
}

const allFactoryScopeLabel = '全部厂区 ( * )'

const permissionGroupDefinitions: PermissionGroupDefinition[] = [
  {
    title: '工程 / 啤办',
    permissions: [
      { label: '查看啤办单据', code: 'molding_sample:read' },
      { label: '新建啤办申请', code: 'molding_sample:create' },
      { label: '编辑草稿', code: 'molding_sample:edit_draft' },
      { label: '删除草稿', code: 'molding_sample:delete_draft' },
      { label: '主管审核', code: 'molding_sample:supervisor_review' },
      { label: '经理终审', code: 'molding_sample:manager_review' },
      { label: '改价维护', code: 'molding_sample:price_update' },
      { label: '敏感审计查看', code: 'molding_sample:audit_read' },
    ],
  },
  {
    title: '生产 / 仓管',
    permissions: [
      { label: '生产任务查看', code: 'molding_sample:production_read' },
      { label: '开始生产', code: 'molding_sample:production_start' },
      { label: '生产回填', code: 'molding_sample:production_fillback' },
      { label: '生产完成', code: 'molding_sample:production_complete' },
      { label: '领料申请', code: 'molding_sample:warehouse_requisition' },
      { label: '库存发料', code: 'molding_sample:inventory_issue' },
    ],
  },
  {
    title: 'QA / 箱唛',
    permissions: [
      { label: '查看箱唛', code: 'carton_mark:read' },
      { label: '维护箱唛模板', code: 'carton_mark:template_upload' },
      { label: '上传实拍', code: 'carton_mark:photo_upload' },
      { label: '箱唛复核', code: 'carton_mark:review' },
    ],
  },
  {
    title: '报价 / 排产',
    permissions: [
      { label: '查看报价中心', code: 'customer_price:read' },
      { label: '导入内部报价', code: 'customer_price:import_internal_quote' },
      { label: '导出客户报价', code: 'customer_price:export_customer_quote' },
      { label: '报价差异比较', code: 'customer_price:compare' },
      { label: '查看内部报价', code: 'internal_pricing:read' },
      { label: '创建内部报价', code: 'internal_pricing:create' },
      { label: '查看注塑排产', code: 'injection_schedule:read' },
      { label: '导入排产计划', code: 'injection_schedule:import' },
    ],
  },
  {
    title: '协同 / 通用',
    permissions: [
      { label: '接收模块通知', code: 'molding_sample:notification_read' },
      { label: '账号 / 权限管理', code: 'admin.manage', matchCode: 'system:user_manage', locked: true },
      { label: '角色权限维护', code: 'system:role_manage', locked: true },
    ],
  },
]

const rolePermissionPresets: Record<string, string[]> = {
  engineer: [
    'molding_sample:read',
    'molding_sample:create',
    'molding_sample:edit_draft',
    'molding_sample:delete_draft',
    'molding_sample:notification_read',
  ],
  engineering_supervisor: [
    'molding_sample:read',
    'molding_sample:supervisor_review',
    'molding_sample:notification_read',
  ],
  manager: [
    'molding_sample:read',
    'molding_sample:edit_draft',
    'molding_sample:delete_draft',
    'molding_sample:manager_review',
    'molding_sample:price_update',
    'molding_sample:audit_read',
    'molding_sample:notification_read',
  ],
  carton_warehouse_keeper: [
    'carton_mark:read',
    'carton_mark:template_upload',
  ],
  qa_inspector: [
    'carton_mark:read',
    'carton_mark:photo_upload',
    'carton_mark:review',
  ],
  molding_clerk: [
    'molding_sample:read',
    'molding_sample:production_read',
    'molding_sample:production_start',
    'molding_sample:production_fillback',
    'molding_sample:production_complete',
    'molding_sample:notification_read',
    'injection_schedule:read',
    'injection_schedule:import',
  ],
  sales_customer_owner: [
    'customer_price:read',
    'customer_price:import_internal_quote',
    'customer_price:export_customer_quote',
    'customer_price:compare',
    'internal_pricing:read',
    'internal_pricing:create',
  ],
  sales_customer_supervisor: [
    'customer_price:read',
    'customer_price:import_internal_quote',
    'customer_price:export_customer_quote',
    'customer_price:compare',
    'internal_pricing:read',
    'internal_pricing:create',
  ],
  admin: permissionGroupDefinitions.flatMap((group) =>
    group.permissions.map((permission) => permission.matchCode ?? permission.code),
  ),
}

const activeUsers = computed(() => users.value.filter((user) => user.status === 'active'))
const pendingUsers = computed(() => users.value.filter((user) => user.status === 'pending'))
const suspendedUsers = computed(() => users.value.filter((user) => user.status === 'suspended'))
const passwordResetRequests = computed(() =>
  systemNotifications.value.filter((notification) => notification.type === 'password_reset' && notification.status !== 'handled'),
)
const selectedRequest = computed(() =>
  requests.value.find((request) => request.id === selectedRequestId.value) ?? requests.value[0] ?? null,
)
const factoryScopesForSelectedRequest = computed(() => {
  const request = selectedRequest.value
  return factoryContexts
    .filter((factory) => factory.id !== 'group')
    .map((factory) => ({
      id: factory.id,
      label: factory.shortName,
      active: factory.id === request?.factory_id,
    }))
})
const departmentScopesForSelectedRequest = computed(() => {
  const request = selectedRequest.value
  return departments
    .filter((department) => department.id !== 'overview')
    .map((department) => ({
      id: department.id,
      label: department.name,
      active: department.id === request?.department,
    }))
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
      user.roles.map((role) => role.role_name).join(' '),
      user.roles.map((role) => role.department).join(' '),
    ].some((value) => value.toLowerCase().includes(keyword))
  })
})

const pendingFootText = computed(() => {
  const first = requests.value[0]
  if (!first?.submitted_at) return requests.value.length ? '请及时处理新的账号申请' : '暂无待处理申请'
  return `最早提交于 ${formatDateTime(first.submitted_at)}`
})

function factoryLabel(factoryId: string) {
  return factoryContexts.find((factory) => factory.id === factoryId)?.shortName ?? factoryId
}

function departmentLabel(departmentId: string) {
  return departmentMap[departmentId as keyof typeof departmentMap]?.name ?? departmentId
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    pending: '待审批',
    approved: '已通过',
    rejected: '已拒绝',
    active: '正常',
    suspended: '已停用',
  }
  return labels[status] ?? status
}

function roleName(roleId: string) {
  return roles.value.find((role) => role.id === roleId)?.name ?? roleId
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return '-'
  return value.replace('T', ' ').slice(0, 16)
}

function avatarText(name: string | null | undefined, username: string) {
  const label = (name || username || '').trim()
  if (!label) return '用'
  if (/^[A-Za-z0-9_]+$/.test(label)) return label.slice(0, 2).toUpperCase()
  return label.slice(0, 1)
}

function resolveUserAvatarUrl(value: string | undefined) {
  const avatarUrl = value?.trim()
  if (!avatarUrl || /^https?:\/\//i.test(avatarUrl)) {
    return avatarUrl ?? ''
  }

  const apiBaseUrl = import.meta.env?.VITE_API_BASE_URL
  if (!apiBaseUrl || !/^https?:\/\//i.test(apiBaseUrl)) {
    return avatarUrl
  }

  try {
    return new URL(avatarUrl, apiBaseUrl).toString()
  } catch {
    return avatarUrl
  }
}

function contactLabel(request: RegistrationRequestResponse) {
  return request.phone || request.email || '未填写'
}

function payloadText(notification: SystemNotificationResponse, key: string) {
  const value = notification.payload[key]
  return typeof value === 'string' ? value : ''
}

function resetRequestUser(notification: SystemNotificationResponse) {
  const userId = payloadText(notification, 'matched_user_id')
  return users.value.find((user) => user.id === userId) ?? null
}

function roleToneClass(name: string) {
  if (/管理员|经理|主管/.test(name)) return 'pill-violet'
  if (/QA|检验|品质/.test(name)) return 'pill-blue'
  if (/仓|PMC|排产/.test(name)) return 'pill-amber'
  return 'pill-teal'
}

function statusToneClass(status: string) {
  if (status === 'active') return 'pill-green'
  if (status === 'suspended') return 'pill-slate'
  if (status === 'pending') return 'pill-amber'
  if (status === 'rejected') return 'pill-red'
  return 'pill-blue'
}

function inferPermissionCodesForRole(role: RoleResponse | undefined, request: RegistrationRequestResponse) {
  const roleText = `${role?.name ?? ''} ${role?.code ?? ''} ${request.position} ${request.department}`
  if (/管理员|admin/i.test(roleText)) return rolePermissionPresets.admin
  if (/QA|检验|品质/i.test(roleText)) return rolePermissionPresets.qa_inspector
  if (/仓|PMC|物料|carton/i.test(roleText)) return rolePermissionPresets.carton_warehouse_keeper
  if (/生产|啤机|排产/i.test(roleText)) return rolePermissionPresets.molding_clerk
  if (/车间业务主管|业务主管/i.test(roleText)) return rolePermissionPresets.sales_customer_supervisor
  if (/业务|报价|客户|sales/i.test(roleText)) return rolePermissionPresets.sales_customer_owner
  if (/主管|supervisor/i.test(roleText)) return rolePermissionPresets.engineering_supervisor
  if (/经理|manager/i.test(roleText)) return rolePermissionPresets.manager
  return rolePermissionPresets.engineer
}

function permissionGroupsForSelectedRole(request: RegistrationRequestResponse) {
  const selectedRoleId = getSelectedRoleId(request)
  const role = roles.value.find((candidate) => candidate.id === selectedRoleId)
  const roleKey = role?.code || role?.id || selectedRoleId
  const permissionCodes = new Set(rolePermissionPresets[roleKey] ?? inferPermissionCodesForRole(role, request))

  return permissionGroupDefinitions
    .map((group) => ({
      title: group.title,
      permissions: group.permissions.map((permission) => ({
        ...permission,
        enabled: permissionCodes.has(permission.matchCode ?? permission.code),
      })),
    }))
    .filter((group) => group.permissions.some((permission) => permission.enabled || permission.locked))
}

function getSelectedRoleId(request: RegistrationRequestResponse) {
  if (!selectedRoles.value[request.id]) {
    selectedRoles.value[request.id] = request.recommended_role_ids[0] ?? roles.value[0]?.id ?? ''
  }

  return selectedRoles.value[request.id]
}

function setSelectedRoleId(requestId: string, roleId: string) {
  selectedRoles.value = { ...selectedRoles.value, [requestId]: roleId }
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

async function loadData() {
  isLoading.value = true
  errorMessage.value = ''
  try {
    const [pendingRequests, loadedUsers, loadedRoles, loadedNotifications] = await Promise.all([
      systemApi.listRegistrationRequests('pending'),
      systemApi.listUsers(''),
      systemApi.listRoles(),
      systemApi.listNotifications(),
    ])
    requests.value = pendingRequests
    users.value = loadedUsers
    roles.value = loadedRoles
    systemNotifications.value = loadedNotifications
    ensureSelectedRequest()
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    isLoading.value = false
  }
}

async function approveRequest(request: RegistrationRequestResponse) {
  const roleId = getSelectedRoleId(request)
  if (!roleId) {
    errorMessage.value = '请先选择授权角色'
    return
  }

  const role_assignments = [
    {
      role_id: roleId,
      factory_id: request.factory_id,
      department: request.department,
    },
  ]

  actionKey.value = `approve:${request.id}`
  errorMessage.value = ''
  successMessage.value = ''
  try {
    await systemApi.approveRegistrationRequest(request.id, {
      role_assignments,
      review_comment: approvalComments.value[request.id] ?? '',
    })
    successMessage.value = `已通过 ${request.display_name} 的账号申请`
    await loadData()
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    actionKey.value = ''
  }
}

async function rejectRequest(request: RegistrationRequestResponse) {
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

async function resetPasswordFromNotification(notification: SystemNotificationResponse) {
  const user = resetRequestUser(notification)
  if (!user) {
    errorMessage.value = '未匹配到系统账号，请人工核验后再处理'
    return
  }

  actionKey.value = `reset-password:${notification.id}`
  errorMessage.value = ''
  successMessage.value = ''
  try {
    await systemApi.resetUserPassword(user.id, {
      temporary_password: '123456',
      notification_id: notification.id,
    })
    successMessage.value = `${user.display_name || user.username} 已重置为临时密码 123456`
    await loadData()
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    actionKey.value = ''
  }
}

async function markPasswordResetHandled(notification: SystemNotificationResponse) {
  actionKey.value = `reset-handled:${notification.id}`
  errorMessage.value = ''
  successMessage.value = ''
  try {
    await systemApi.updateNotification(notification.id, { status: 'handled' })
    successMessage.value = `已标记 ${payloadText(notification, 'username') || notification.title} 的密码重置申请为已处理`
    await loadData()
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    actionKey.value = ''
  }
}

onMounted(() => {
  if (route.query.tab === 'password-reset') {
    activeTab.value = 'password-reset'
  } else if (route.query.request_id) {
    activeTab.value = 'pending'
  }
  void loadData()
})
</script>

<template>
  <main class="permission-approval-page">
    <div class="wrap">
      <header class="topbar">
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
              <h1>权限 / 角色审批</h1>
              <p>Royal Regent Nexus · 集团账号开通制</p>
            </div>
          </div>
        </div>
        <div class="topbar-actions">
          <nav class="view-tabs" aria-label="账号管理视图">
            <button type="button" :class="{ active: activeTab === 'pending' }" @click="activeTab = 'pending'">
              待审批
              <span>{{ requests.length }}</span>
            </button>
            <button type="button" :class="{ active: activeTab === 'password-reset' }" @click="activeTab = 'password-reset'">
              密码重置
              <span>{{ passwordResetRequests.length }}</span>
            </button>
            <button type="button" :class="{ active: activeTab === 'users' }" @click="activeTab = 'users'">
              用户列表
            </button>
          </nav>
          <button type="button" class="ghost-link" :disabled="isLoading" @click="loadData">
            <RefreshCw class="size-4" :class="{ 'animate-spin': isLoading }" aria-hidden="true" />
            刷新
          </button>
          <div class="admin">
            <div class="t">系统管理员<small>集团数字化中心 · 超级管理员</small></div>
            <span class="av">管</span>
          </div>
        </div>
      </header>

      <div class="stats">
        <article class="stat">
          <div class="row">
            <span class="ic amber"><Clock3 class="size-5" aria-hidden="true" /></span>
            <span class="delta up">{{ requests.length ? '待处理' : '清空' }}</span>
          </div>
          <div class="n">{{ requests.length }}</div>
          <div class="lb">待审批申请</div>
        </article>
        <article class="stat">
          <div class="row">
            <span class="ic teal"><CheckCircle2 class="size-5" aria-hidden="true" /></span>
            <span class="delta up">已开通</span>
          </div>
          <div class="n">{{ activeUsers.length }}</div>
          <div class="lb">在用账号</div>
        </article>
        <article class="stat">
          <div class="row">
            <span class="ic blue"><Users class="size-5" aria-hidden="true" /></span>
            <span class="delta mut">6 厂区</span>
          </div>
          <div class="n">{{ users.length }}</div>
          <div class="lb">账号总数</div>
        </article>
        <article class="stat">
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

    <section v-if="activeTab === 'pending'" class="grid approval-workspace">
      <div v-if="isLoading" class="empty-card">正在加载账号申请...</div>
      <div v-else-if="!requests.length" class="empty-card">当前没有待审批账号。</div>
      <template v-else>
        <aside class="panel">
          <div class="panel-head">
            <h2>待审批账号</h2>
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
              <span class="time">{{ formatDateTime(request.submitted_at) }}</span>
            </button>
          </div>
        </aside>

        <article v-if="selectedRequest" class="panel detail">
          <div class="applicant">
            <span class="av">{{ avatarText(selectedRequest.display_name, selectedRequest.username) }}</span>
            <div class="h">
              <div><b>{{ selectedRequest.display_name }}</b><span class="uid">{{ selectedRequest.username }}</span></div>
              <div class="tags">
                <span class="tag"><Factory class="size-3.5" aria-hidden="true" />{{ factoryLabel(selectedRequest.factory_id) }}</span>
                <span class="tag"><Building2 class="size-3.5" aria-hidden="true" />{{ departmentLabel(selectedRequest.department) }}</span>
                <span class="tag"><BriefcaseBusiness class="size-3.5" aria-hidden="true" />{{ selectedRequest.position }}</span>
                <span class="tag"><Phone v-if="selectedRequest.phone" class="size-3.5" aria-hidden="true" /><Mail v-else class="size-3.5" aria-hidden="true" />{{ contactLabel(selectedRequest) }}</span>
              </div>
            </div>
          </div>

          <section class="section">
            <div class="sec-title">
              <span class="st-ic"><Users class="size-4" aria-hidden="true" /></span>
              <h3>系统角色</h3>
              <span class="hint">根据申请职位「{{ selectedRequest.position }}」智能推荐</span>
            </div>
            <div class="roles">
              <button
                v-for="role in roles"
                :key="role.id"
                type="button"
                class="role"
                :class="{ sel: getSelectedRoleId(selectedRequest) === role.id }"
                @click="setSelectedRoleId(selectedRequest.id, role.id)"
              >
                <span v-if="selectedRequest.recommended_role_ids.includes(role.id)" class="reco">推荐</span>
                <span class="check"><Check class="size-3" aria-hidden="true" /></span>
                <div class="rname">{{ role.name }}</div>
                <div class="rdesc">{{ role.description || role.code }}</div>
              </button>
            </div>
          </section>

          <section class="section">
            <div class="sec-title">
              <span class="st-ic"><KeyRound class="size-4" aria-hidden="true" /></span>
              <h3>权限清单</h3>
              <span class="hint">角色默认已勾选，高危权限锁定</span>
            </div>
            <div class="perm-groups">
              <div v-for="group in permissionGroupsForSelectedRole(selectedRequest)" :key="group.title" class="perm-group">
                <h4>{{ group.title }}</h4>
                <label
                  v-for="permission in group.permissions"
                  :key="permission.code"
                  :class="[permission.locked ? 'perm locked' : 'perm', { on: permission.enabled }]"
                >
                  <span class="cbx">
                    <Check v-if="permission.enabled" class="size-3" aria-hidden="true" />
                  </span>
                  <span class="pt">{{ permission.label }}</span>
                  <span class="pc">{{ permission.code }}</span>
                </label>
              </div>
            </div>
          </section>

          <section class="section">
            <div class="sec-title">
              <span class="st-ic"><ShieldCheck class="size-4" aria-hidden="true" /></span>
              <h3>数据范围</h3>
              <span class="hint">限定该账号可访问的厂区与部门</span>
            </div>
            <div class="scope-block">
              <div class="scope-lbl">厂区范围 (factory_scopes)</div>
              <div class="chips">
                <span
                  v-for="factory in factoryScopesForSelectedRequest"
                  :key="factory.id"
                  class="chip"
                  :class="{ on: factory.active }"
                >
                  <span class="cd"></span>{{ factory.label }}
                </span>
                <span class="chip all"><span class="cd"></span>{{ allFactoryScopeLabel }}</span>
              </div>
            </div>
            <div class="scope-block">
              <div class="scope-lbl">部门范围 (department_scopes)</div>
              <div class="chips">
                <span
                  v-for="department in departmentScopesForSelectedRequest"
                  :key="department.id"
                  class="chip"
                  :class="{ on: department.active }"
                >
                  <span class="cd"></span>{{ department.label }}
                </span>
              </div>
            </div>
          </section>

          <div class="actions">
            <input
              v-model="approvalComments[selectedRequest.id]"
              class="note-in"
              placeholder="审批备注（可选，驳回时建议填写原因）"
              type="text"
            >
            <button type="button" class="btn btn-reject" :disabled="Boolean(actionKey)" @click="rejectRequest(selectedRequest)">
              <XCircle class="size-4" aria-hidden="true" />
              驳回
            </button>
            <button type="button" class="btn btn-approve" :disabled="Boolean(actionKey)" @click="approveRequest(selectedRequest)">
              <LoaderCircle v-if="actionKey === `approve:${selectedRequest.id}`" class="size-4 animate-spin" aria-hidden="true" />
              <Check v-else class="size-4" aria-hidden="true" />
              通过并开通
            </button>
          </div>
        </article>
      </template>
    </section>

    <section v-else-if="activeTab === 'password-reset'" class="panel">
      <div v-if="isLoading" class="empty-card">正在加载密码重置申请...</div>
      <div v-else-if="!passwordResetRequests.length" class="empty-card">当前没有待处理密码重置申请。</div>
      <div v-else class="request-grid">
        <article v-for="notification in passwordResetRequests" :key="notification.id" class="request-card">
          <div class="request-top">
            <span class="request-avatar">{{ avatarText(payloadText(notification, 'display_name'), payloadText(notification, 'username')) }}</span>
            <div class="request-person">
              <h2>{{ payloadText(notification, 'display_name') || payloadText(notification, 'username') }}</h2>
              <p>{{ payloadText(notification, 'username') }}</p>
            </div>
            <span class="pill" :class="notification.status === 'read' ? 'pill-blue' : 'pill-amber'">
              <span></span>{{ notification.status === 'read' ? '已读' : '未读' }}
            </span>
          </div>

          <div class="request-meta">
            <div>
              <KeyRound class="size-4" aria-hidden="true" />
              <span>账号</span>
              <b>{{ payloadText(notification, 'username') || '-' }}</b>
            </div>
            <div>
              <Phone class="size-4" aria-hidden="true" />
              <span>联系</span>
              <b>{{ payloadText(notification, 'contact') || '-' }}</b>
            </div>
            <div class="meta-wide">
              <Clock3 class="size-4" aria-hidden="true" />
              <span>提交</span>
              <b>{{ formatDateTime(notification.created_at) }}</b>
            </div>
            <div class="meta-wide">
              <LifeBuoy class="size-4" aria-hidden="true" />
              <span>说明</span>
              <b>{{ payloadText(notification, 'note') || notification.message }}</b>
            </div>
          </div>

          <div class="recommend-box">
            <Sparkles class="size-4 shrink-0" aria-hidden="true" />
            <span>处理方式：</span>
            <b v-if="resetRequestUser(notification)">重置为临时密码 123456，并要求用户重新登录</b>
            <b v-else>未匹配系统账号，请人工核验后标记处理</b>
          </div>

          <div class="request-actions">
            <button
              v-if="resetRequestUser(notification)"
              type="button"
              class="btn btn-primary"
              :disabled="Boolean(actionKey)"
              @click="resetPasswordFromNotification(notification)"
            >
              <LoaderCircle v-if="actionKey === `reset-password:${notification.id}`" class="size-4 animate-spin" aria-hidden="true" />
              <KeyRound v-else class="size-4" aria-hidden="true" />
              重置为临时密码
            </button>
            <button
              type="button"
              class="btn"
              :class="resetRequestUser(notification) ? '' : 'btn-primary'"
              :disabled="Boolean(actionKey)"
              @click="markPasswordResetHandled(notification)"
            >
              <LoaderCircle v-if="actionKey === `reset-handled:${notification.id}`" class="size-4 animate-spin" aria-hidden="true" />
              <CheckCircle2 v-else class="size-4" aria-hidden="true" />
              标记已处理
            </button>
          </div>
        </article>
      </div>
    </section>

    <section v-else class="panel users-panel">
      <div class="table-tools">
        <label class="search-box">
          <Search class="size-4" aria-hidden="true" />
          <input v-model="userSearch" placeholder="搜索姓名、工号、联系方式、角色..." type="search">
        </label>
        <div class="seg">
          <button type="button" :class="{ on: userStatusFilter === 'all' }" @click="userStatusFilter = 'all'">全部</button>
          <button type="button" :class="{ on: userStatusFilter === 'active' }" @click="userStatusFilter = 'active'">正常</button>
          <button type="button" :class="{ on: userStatusFilter === 'suspended' }" @click="userStatusFilter = 'suspended'">停用</button>
        </div>
      </div>

      <div class="table-wrap">
        <table class="user-table">
          <thead>
            <tr>
              <th>用户</th>
              <th>联系方式</th>
              <th>厂区 / 部门</th>
              <th>角色</th>
              <th>状态</th>
              <th>最后登录</th>
              <th class="ops-head">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!filteredUsers.length">
              <td colspan="7" class="empty-row">没有匹配的账号。</td>
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
                  <div>
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
                {{ user.roles.map((role) => `${factoryLabel(role.factory_id)} · ${departmentLabel(role.department)}`).join('、') || '-' }}
              </td>
              <td>
                <div class="role-tags">
                  <span
                    v-for="role in user.roles"
                    :key="role.id"
                    class="pill"
                    :class="roleToneClass(role.role_name)"
                  >
                    <span></span>{{ role.role_name }}
                  </span>
                  <span v-if="!user.roles.length" class="tag">未授权</span>
                </div>
              </td>
              <td>
                <span class="pill" :class="statusToneClass(user.status)">
                  <span></span>{{ statusLabel(user.status) }}
                </span>
              </td>
              <td class="muted">{{ formatDateTime(user.last_login_at) }}</td>
              <td>
                <div class="row-ops">
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
          <span class="table-foot-badge"><UserCog class="size-3.5" aria-hidden="true" /> RBAC 授权</span>
        </div>
      </div>
    </section>
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

.user-cell strong {
  display: block;
  color: #020617;
  font-size: 13px;
}

.user-cell span {
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
  justify-content: flex-end;
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

.roles {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}

.role {
  position: relative;
  min-height: auto;
  border: 1.5px solid var(--slate-200);
  border-radius: var(--radius-md);
  background: white;
  cursor: pointer;
  padding: 12px 13px;
  text-align: left;
  transition: border-color 0.15s, background 0.15s, box-shadow 0.15s;
}

.role:hover {
  border-color: var(--teal-200);
}

.role.sel {
  border-color: var(--teal);
  background: var(--teal-50);
  box-shadow: 0 0 0 3px var(--ring);
}

.role .rname {
  color: var(--slate-900);
  font-size: 13px;
  font-weight: 800;
}

.role .rdesc {
  margin-top: 4px;
  color: var(--slate-500);
  font-size: 11.5px;
  line-height: 1.5;
}

.role .reco {
  position: absolute;
  top: -8px;
  right: 10px;
  border-radius: 999px;
  background: var(--teal);
  color: white;
  font-size: 10px;
  font-weight: 800;
  padding: 2px 8px;
  box-shadow: 0 3px 8px rgb(15 118 110 / 30%);
}

.role .check {
  position: absolute;
  top: 10px;
  right: 10px;
  display: none;
  width: 18px;
  height: 18px;
  place-items: center;
  border-radius: 999px;
  background: var(--teal);
  color: white;
}

.role.sel .check {
  display: grid;
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

  .roles {
    grid-template-columns: 1fr 1fr;
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

  .stats,
  .roles {
    grid-template-columns: 1fr;
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
</style>
