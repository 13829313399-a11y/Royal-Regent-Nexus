<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  CheckCircle2,
  CircleAlert,
  LoaderCircle,
  RefreshCw,
  ShieldCheck,
  UserCheck,
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
const isLoading = ref(false)
const actionKey = ref('')
const errorMessage = ref('')
const successMessage = ref('')

const activeUsers = computed(() => users.value.filter((user) => user.status === 'active'))
const pendingUsers = computed(() => users.value.filter((user) => user.status === 'pending'))
const suspendedUsers = computed(() => users.value.filter((user) => user.status === 'suspended'))

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
  <section class="space-y-5">
    <header class="flex flex-col gap-4 rounded-lg border border-slate-200 bg-white px-5 py-4 shadow-sm lg:flex-row lg:items-center lg:justify-between">
      <div>
        <p class="text-xs font-bold uppercase tracking-wide text-teal-700">System Access</p>
        <h1 class="mt-1 text-2xl font-black text-slate-950">账号与权限管理</h1>
        <p class="mt-1 text-sm text-slate-500">处理账号申请、授权角色、停用或恢复账号。</p>
      </div>
      <button
        type="button"
        class="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-slate-200 px-4 text-sm font-bold text-slate-600 transition hover:bg-slate-50 disabled:cursor-wait disabled:opacity-60"
        :disabled="isLoading"
        @click="loadData"
      >
        <RefreshCw class="size-4" :class="{ 'animate-spin': isLoading }" aria-hidden="true" />
        刷新
      </button>
    </header>

    <div class="grid gap-3 sm:grid-cols-3">
      <div class="rounded-lg border border-slate-200 bg-white p-4">
        <p class="text-xs font-semibold text-slate-500">待审批</p>
        <p class="mt-2 text-2xl font-black text-slate-950">{{ requests.length }}</p>
      </div>
      <div class="rounded-lg border border-slate-200 bg-white p-4">
        <p class="text-xs font-semibold text-slate-500">正常账号</p>
        <p class="mt-2 text-2xl font-black text-slate-950">{{ activeUsers.length }}</p>
      </div>
      <div class="rounded-lg border border-slate-200 bg-white p-4">
        <p class="text-xs font-semibold text-slate-500">停用账号</p>
        <p class="mt-2 text-2xl font-black text-slate-950">{{ suspendedUsers.length }}</p>
      </div>
    </div>

    <div v-if="errorMessage" class="flex items-center gap-2 rounded-lg border border-red-100 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">
      <CircleAlert class="size-4 shrink-0" aria-hidden="true" />
      <span>{{ errorMessage }}</span>
    </div>
    <div v-if="successMessage" class="rounded-lg border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm font-semibold text-emerald-700">
      {{ successMessage }}
    </div>

    <nav class="inline-flex rounded-lg border border-slate-200 bg-white p-1">
      <button
        type="button"
        class="inline-flex h-9 items-center gap-2 rounded-md px-4 text-sm font-bold transition"
        :class="activeTab === 'pending' ? 'bg-teal-700 text-white' : 'text-slate-600 hover:bg-slate-50'"
        @click="activeTab = 'pending'"
      >
        <UserCheck class="size-4" aria-hidden="true" />
        待审批
      </button>
      <button
        type="button"
        class="inline-flex h-9 items-center gap-2 rounded-md px-4 text-sm font-bold transition"
        :class="activeTab === 'users' ? 'bg-teal-700 text-white' : 'text-slate-600 hover:bg-slate-50'"
        @click="activeTab = 'users'"
      >
        <Users class="size-4" aria-hidden="true" />
        用户列表
      </button>
    </nav>

    <section v-if="activeTab === 'pending'" class="space-y-3">
      <div v-if="isLoading" class="rounded-lg border border-slate-200 bg-white px-5 py-10 text-center text-sm text-slate-500">
        正在加载账号申请...
      </div>
      <div v-else-if="!requests.length" class="rounded-lg border border-slate-200 bg-white px-5 py-10 text-center text-sm text-slate-500">
        当前没有待审批账号。
      </div>
      <article
        v-for="request in requests"
        v-else
        :key="request.id"
        class="rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
      >
        <div class="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-2">
              <h2 class="text-lg font-black text-slate-950">{{ request.display_name }}</h2>
              <span class="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-bold text-amber-700">{{ statusLabel(request.status) }}</span>
              <span class="font-mono text-xs text-slate-400">{{ request.username }}</span>
            </div>
            <div class="mt-3 grid gap-2 text-sm text-slate-600 sm:grid-cols-2 lg:grid-cols-4">
              <span>{{ factoryLabel(request.factory_id) }}</span>
              <span>{{ departmentLabel(request.department) }}</span>
              <span>{{ request.position }}</span>
              <span>{{ request.submitted_at }}</span>
            </div>
            <p class="mt-2 text-sm text-slate-500">
              联系方式：{{ request.phone || '未填手机' }} / {{ request.email || '未填邮箱' }}
            </p>
          </div>

          <div class="grid w-full gap-2 xl:w-[520px]">
            <label class="block">
              <span class="mb-1 block text-xs font-semibold text-slate-500">推荐 / 授权角色</span>
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
            <input
              v-model="approvalComments[request.id]"
              class="field"
              placeholder="通过备注，可选"
              type="text"
            >
            <input
              v-model="rejectComments[request.id]"
              class="field"
              placeholder="拒绝原因"
              type="text"
            >
            <div class="grid grid-cols-2 gap-2">
              <button
                type="button"
                class="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-teal-700 text-sm font-bold text-white transition hover:bg-teal-800 disabled:cursor-wait disabled:bg-slate-300"
                :disabled="Boolean(actionKey)"
                @click="approveRequest(request)"
              >
                <LoaderCircle v-if="actionKey === `approve:${request.id}`" class="size-4 animate-spin" aria-hidden="true" />
                <CheckCircle2 v-else class="size-4" aria-hidden="true" />
                通过
              </button>
              <button
                type="button"
                class="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-red-200 text-sm font-bold text-red-700 transition hover:bg-red-50 disabled:cursor-wait disabled:opacity-60"
                :disabled="Boolean(actionKey)"
                @click="rejectRequest(request)"
              >
                <XCircle class="size-4" aria-hidden="true" />
                拒绝
              </button>
            </div>
          </div>
        </div>
      </article>
    </section>

    <section v-else class="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
      <div class="border-b border-slate-100 px-4 py-3">
        <h2 class="font-black text-slate-950">用户列表</h2>
        <p class="mt-1 text-sm text-slate-500">待审批账号 {{ pendingUsers.length }} 个；停用账号可在这里恢复。</p>
      </div>
      <div class="overflow-x-auto">
        <table class="min-w-full text-left text-sm">
          <thead class="bg-slate-50 text-xs font-bold uppercase tracking-wide text-slate-500">
            <tr>
              <th class="px-4 py-3">账号</th>
              <th class="px-4 py-3">状态</th>
              <th class="px-4 py-3">角色</th>
              <th class="px-4 py-3">范围</th>
              <th class="px-4 py-3">最后登录</th>
              <th class="px-4 py-3 text-right">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            <tr v-for="user in users" :key="user.id">
              <td class="px-4 py-3">
                <div class="font-bold text-slate-950">{{ user.display_name || user.username }}</div>
                <div class="font-mono text-xs text-slate-400">{{ user.username }}</div>
              </td>
              <td class="px-4 py-3">
                <span class="rounded-full px-2 py-0.5 text-xs font-bold" :class="user.status === 'active' ? 'bg-emerald-100 text-emerald-700' : user.status === 'suspended' ? 'bg-red-100 text-red-700' : 'bg-slate-100 text-slate-600'">
                  {{ statusLabel(user.status) }}
                </span>
              </td>
              <td class="px-4 py-3 text-slate-600">
                {{ user.roles.map((role) => role.role_name).join('、') || '-' }}
              </td>
              <td class="px-4 py-3 text-slate-600">
                {{ user.roles.map((role) => `${factoryLabel(role.factory_id)} / ${departmentLabel(role.department)}`).join('、') || '-' }}
              </td>
              <td class="px-4 py-3 text-slate-500">{{ user.last_login_at || '-' }}</td>
              <td class="px-4 py-3 text-right">
                <button
                  v-if="user.status === 'active'"
                  type="button"
                  class="inline-flex h-8 items-center gap-1 rounded-md border border-red-200 px-3 text-xs font-bold text-red-700 transition hover:bg-red-50 disabled:cursor-wait disabled:opacity-60"
                  :disabled="Boolean(actionKey)"
                  @click="updateStatus(user, 'suspended')"
                >
                  <UserRoundX class="size-3.5" aria-hidden="true" />
                  停用
                </button>
                <button
                  v-else-if="user.status === 'suspended'"
                  type="button"
                  class="inline-flex h-8 items-center gap-1 rounded-md border border-teal-200 px-3 text-xs font-bold text-teal-700 transition hover:bg-teal-50 disabled:cursor-wait disabled:opacity-60"
                  :disabled="Boolean(actionKey)"
                  @click="updateStatus(user, 'active')"
                >
                  <ShieldCheck class="size-3.5" aria-hidden="true" />
                  恢复
                </button>
                <span v-else class="text-xs text-slate-400">无操作</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </section>
</template>

<style scoped>
.field {
  height: 40px;
  width: 100%;
  border-radius: 8px;
  border: 1px solid rgb(226 232 240);
  background: rgb(248 250 252);
  padding: 0 10px;
  font-size: 13px;
  outline: none;
}

.field:focus {
  border-color: rgb(15 118 110);
  background: white;
  box-shadow: 0 0 0 3px rgb(15 118 110 / 12%);
}
</style>
