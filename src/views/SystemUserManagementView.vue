<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  Building2,
  BriefcaseBusiness,
  CheckCircle2,
  CircleAlert,
  Clock3,
  Factory,
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
  type UserResponse,
} from '@/api/system'
import { departmentMap, factoryContexts } from '@/data/enterpriseMock'
import { getApiErrorMessage } from '@/lib/http'

const activeTab = ref<'pending' | 'users'>('pending')
const requests = ref<RegistrationRequestResponse[]>([])
const users = ref<UserResponse[]>([])
const roles = ref<RoleResponse[]>([])
const selectedRoles = ref<Record<string, string>>({})
const approvalComments = ref<Record<string, string>>({})
const rejectComments = ref<Record<string, string>>({})
const userSearch = ref('')
const userStatusFilter = ref<'all' | 'active' | 'suspended'>('all')
const isLoading = ref(false)
const actionKey = ref('')
const errorMessage = ref('')
const successMessage = ref('')

const activeUsers = computed(() => users.value.filter((user) => user.status === 'active'))
const pendingUsers = computed(() => users.value.filter((user) => user.status === 'pending'))
const suspendedUsers = computed(() => users.value.filter((user) => user.status === 'suspended'))
const filteredUsers = computed(() => {
  const keyword = userSearch.value.trim().toLowerCase()
  return users.value.filter((user) => {
    const statusMatched = userStatusFilter.value === 'all' || user.status === userStatusFilter.value
    if (!statusMatched) return false

    if (!keyword) return true
    return [
      user.username,
      user.display_name,
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

function contactLabel(request: RegistrationRequestResponse) {
  return request.phone || request.email || '未填写'
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

function getSelectedRoleId(request: RegistrationRequestResponse) {
  if (!selectedRoles.value[request.id]) {
    selectedRoles.value[request.id] = request.recommended_role_ids[0] ?? roles.value[0]?.id ?? ''
  }

  return selectedRoles.value[request.id]
}

function setSelectedRoleId(requestId: string, roleId: string) {
  selectedRoles.value = { ...selectedRoles.value, [requestId]: roleId }
}

async function loadData() {
  isLoading.value = true
  errorMessage.value = ''
  try {
    const [pendingRequests, loadedUsers, loadedRoles] = await Promise.all([
      systemApi.listRegistrationRequests('pending'),
      systemApi.listUsers(''),
      systemApi.listRoles(),
    ])
    requests.value = pendingRequests
    users.value = loadedUsers
    roles.value = loadedRoles
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
  const comment = rejectComments.value[request.id]?.trim()
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

onMounted(() => {
  void loadData()
})
</script>

<template>
  <section class="access-page">
    <header class="access-head">
      <div>
        <div class="eyebrow-row">
          <span class="eyebrow-mark">
            <ShieldCheck class="size-5" aria-hidden="true" />
          </span>
          <span class="eyebrow">System Access</span>
        </div>
        <h1>账号与权限管理</h1>
        <p>处理账号申请、授权角色、停用或恢复账号 · 集团数字化中心统一管理</p>
      </div>
      <button type="button" class="btn" :disabled="isLoading" @click="loadData">
        <RefreshCw class="size-4" :class="{ 'animate-spin': isLoading }" aria-hidden="true" />
        刷新
      </button>
    </header>

    <div class="stats-grid">
      <article class="stat-card stat-amber">
        <div class="stat-top">
          <span>待审批申请</span>
          <span class="stat-icon"><UserPlus class="size-5" aria-hidden="true" /></span>
        </div>
        <strong>{{ requests.length }}</strong>
        <p>{{ pendingFootText }}</p>
      </article>
      <article class="stat-card stat-green">
        <div class="stat-top">
          <span>正常账号</span>
          <span class="stat-icon"><Users class="size-5" aria-hidden="true" /></span>
        </div>
        <strong>{{ activeUsers.length }}</strong>
        <p>覆盖华康A/B · 华登 · 华兴四厂区</p>
      </article>
      <article class="stat-card stat-slate">
        <div class="stat-top">
          <span>已停用</span>
          <span class="stat-icon"><UserRoundX class="size-5" aria-hidden="true" /></span>
        </div>
        <strong>{{ suspendedUsers.length }}</strong>
        <p>离职或调岗，权限已回收</p>
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

    <nav class="tabs" aria-label="账号管理视图">
      <button type="button" class="tab" :class="{ active: activeTab === 'pending' }" @click="activeTab = 'pending'">
        <UserCheck class="size-4" aria-hidden="true" />
        待审批
        <span class="tab-count">{{ requests.length }}</span>
      </button>
      <button type="button" class="tab" :class="{ active: activeTab === 'users' }" @click="activeTab = 'users'">
        <Users class="size-4" aria-hidden="true" />
        用户列表
      </button>
    </nav>

    <section v-if="activeTab === 'pending'" class="panel">
      <div v-if="isLoading" class="empty-card">正在加载账号申请...</div>
      <div v-else-if="!requests.length" class="empty-card">当前没有待审批账号。</div>
      <div v-else class="request-grid">
        <article v-for="request in requests" :key="request.id" class="request-card">
          <div class="request-top">
            <span class="request-avatar">{{ avatarText(request.display_name, request.username) }}</span>
            <div class="request-person">
              <h2>{{ request.display_name }}</h2>
              <p>{{ request.username }}</p>
            </div>
            <span class="pill pill-amber"><span></span>{{ statusLabel(request.status) }}</span>
          </div>

          <div class="request-meta">
            <div>
              <Factory class="size-4" aria-hidden="true" />
              <span>厂区</span>
              <b>{{ factoryLabel(request.factory_id) }}</b>
            </div>
            <div>
              <Building2 class="size-4" aria-hidden="true" />
              <span>部门</span>
              <b>{{ departmentLabel(request.department) }}</b>
            </div>
            <div>
              <BriefcaseBusiness class="size-4" aria-hidden="true" />
              <span>职位</span>
              <b>{{ request.position }}</b>
            </div>
            <div>
              <Phone v-if="request.phone" class="size-4" aria-hidden="true" />
              <Mail v-else class="size-4" aria-hidden="true" />
              <span>联系</span>
              <b>{{ contactLabel(request) }}</b>
            </div>
            <div class="meta-wide">
              <Clock3 class="size-4" aria-hidden="true" />
              <span>提交</span>
              <b>{{ formatDateTime(request.submitted_at) }}</b>
            </div>
          </div>

          <div class="recommend-box">
            <Sparkles class="size-4 shrink-0" aria-hidden="true" />
            <span>系统推荐角色：</span>
            <b>{{ roleName(request.recommended_role_ids[0] ?? getSelectedRoleId(request)) }}</b>
          </div>

          <div class="review-controls">
            <label>
              <span>推荐 / 授权角色</span>
              <select
                class="field"
                :value="getSelectedRoleId(request)"
                @change="setSelectedRoleId(request.id, ($event.target as HTMLSelectElement).value)"
              >
                <option v-for="role in roles" :key="role.id" :value="role.id">
                  {{ role.name }}{{ request.recommended_role_ids.includes(role.id) ? '（推荐）' : '' }}
                </option>
              </select>
            </label>
            <input v-model="approvalComments[request.id]" class="field" placeholder="通过备注，可选" type="text">
            <input v-model="rejectComments[request.id]" class="field" placeholder="拒绝原因" type="text">
          </div>

          <div class="request-actions">
            <button type="button" class="btn btn-primary" :disabled="Boolean(actionKey)" @click="approveRequest(request)">
              <LoaderCircle v-if="actionKey === `approve:${request.id}`" class="size-4 animate-spin" aria-hidden="true" />
              <CheckCircle2 v-else class="size-4" aria-hidden="true" />
              通过并授权
            </button>
            <button type="button" class="btn btn-danger" :disabled="Boolean(actionKey)" @click="rejectRequest(request)">
              <XCircle class="size-4" aria-hidden="true" />
              驳回
            </button>
          </div>
        </article>
      </div>
    </section>

    <section v-else class="panel users-panel">
      <div class="table-tools">
        <label class="search-box">
          <Search class="size-4" aria-hidden="true" />
          <input v-model="userSearch" placeholder="搜索姓名、工号、角色..." type="search">
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
              <th>厂区 / 部门</th>
              <th>角色</th>
              <th>状态</th>
              <th>最后登录</th>
              <th class="ops-head">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!filteredUsers.length">
              <td colspan="6" class="empty-row">没有匹配的账号。</td>
            </tr>
            <tr v-for="user in filteredUsers" v-else :key="user.id">
              <td>
                <div class="user-cell">
                  <span class="user-avatar">{{ avatarText(user.display_name, user.username) }}</span>
                  <div>
                    <strong>{{ user.display_name || user.username }}</strong>
                    <span>{{ user.username }}</span>
                  </div>
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
  </section>
</template>

<style scoped>
.access-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
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

.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
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
  min-width: 980px;
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

  .stats-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
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
</style>
