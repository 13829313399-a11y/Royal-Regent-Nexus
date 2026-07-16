<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { AlertTriangle, ArrowLeft, ArrowRight, CheckCircle2, LoaderCircle, RefreshCw, Save, ShieldCheck, X } from '@lucide/vue'
import { useRoute } from 'vue-router'
import {
  iamApi,
  type PermissionCatalogItem,
  type RoleAccessResponse,
  type RoleSummary,
  type UserAccessResponse,
  type UserSystemPositionPreviewResponse,
} from '@/api/iam'
import IamIdentitySummary from '@/components/iam/IamIdentitySummary.vue'
import IamNavigation from '@/components/iam/IamNavigation.vue'
import {
  isBuiltInPositionPermissionVisible,
  permissionDisplayLabel,
} from '@/components/iam/permissionCatalogLabels'
import { registrationDepartments } from '@/data/registrationDepartments'
import { getApiErrorMessage } from '@/lib/http'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const authStore = useAuthStore()

const access = ref<UserAccessResponse | null>(null)
const systemPositions = ref<RoleSummary[]>([])
const permissions = ref<PermissionCatalogItem[]>([])
const selectedSystemPositionRoleId = ref('')
const selectedPositionAccess = ref<RoleAccessResponse | null>(null)
const reason = ref('')
const preview = ref<UserSystemPositionPreviewResponse | null>(null)
const confirmedHighRisk = ref(false)
const isLoading = ref(false)
const isLoadingPosition = ref(false)
const isPreviewing = ref(false)
const isCommitting = ref(false)
const errorMessage = ref('')
const successMessage = ref('')

const userId = computed(() => String(route.params.userId ?? ''))
const userFactory = computed(() => access.value?.profile?.primary_factory_id ?? '')
const userDepartment = computed(() => access.value?.profile?.primary_department ?? '')
const hasPrimaryOrganization = computed(() => Boolean(userFactory.value && userDepartment.value))
const assignableSystemPositions = computed(() => hasPrimaryOrganization.value
  ? systemPositions.value.filter((position) => position.position_department === userDepartment.value)
  : [],
)
const selectedSystemPosition = computed(() =>
  systemPositions.value.find((position) => position.id === selectedSystemPositionRoleId.value) ?? null,
)
const hasPositionChange = computed(() =>
  Boolean(selectedSystemPositionRoleId.value)
  && selectedSystemPositionRoleId.value !== (access.value?.system_position_role_id ?? ''),
)
const hasHistoricalAuthorization = computed(() =>
  Boolean((access.value?.cleanup_role_count ?? 0) || (access.value?.cleanup_override_count ?? 0)),
)
const hasSystemPositionAction = computed(() => hasPrimaryOrganization.value
  && (hasPositionChange.value || hasHistoricalAuthorization.value))
const groupedSystemPositions = computed(() => {
  const sorted = [...assignableSystemPositions.value]
    .filter((position) => position.is_system_position)
    .sort((left, right) => {
      const leftDepartment = registrationDepartments.findIndex((item) => item.id === left.position_department)
      const rightDepartment = registrationDepartments.findIndex((item) => item.id === right.position_department)
      const departmentOrder = (leftDepartment < 0 ? 999 : leftDepartment) - (rightDepartment < 0 ? 999 : rightDepartment)
      return departmentOrder || left.position_sort_order - right.position_sort_order || left.name.localeCompare(right.name, 'zh-CN')
    })
  const groups = new Map<string, { department: string; name: string; positions: RoleSummary[] }>()
  for (const position of sorted) {
    const department = position.position_department || 'other'
    const group = groups.get(department)
    if (group) group.positions.push(position)
    else groups.set(department, {
      department,
      name: position.position_department_name || department,
      positions: [position],
    })
  }
  return [...groups.values()]
})
const groupedInheritedPermissions = computed(() => {
  const enabledCodes = new Set(selectedPositionAccess.value?.permission_codes ?? [])
  const groups = new Map<string, { moduleCode: string; moduleName: string; items: PermissionCatalogItem[] }>()
  permissions.value
    .filter((permission) => permission.status === 'active'
      && enabledCodes.has(permission.code)
      && isBuiltInPositionPermissionVisible(permission.code))
    .sort((left, right) => left.sort_order - right.sort_order || left.code.localeCompare(right.code))
    .forEach((permission) => {
      const group = groups.get(permission.module_code)
      if (group) group.items.push(permission)
      else groups.set(permission.module_code, {
        moduleCode: permission.module_code,
        moduleName: permission.module_name,
        items: [permission],
      })
    })
  return [...groups.values()]
})
const visibleInheritedPermissionCount = computed(() => groupedInheritedPermissions.value
  .reduce((total, group) => total + group.items.length, 0))
const permissionLabels = computed(() => new Map(
  permissions.value.map((permission) => [permission.code, permissionDisplayLabel(permission)]),
))

function initialSystemPosition(userAccess: UserAccessResponse, positions: RoleSummary[]) {
  if (!userAccess.profile?.primary_factory_id || !userAccess.profile.primary_department) return ''
  const candidates = positions.filter((position) =>
    position.position_department === userAccess.profile?.primary_department,
  )
  const existing = candidates.find((position) => position.id === userAccess.system_position_role_id)
  if (existing) return existing.id
  const recommended = candidates.find((position) => position.id === userAccess.recommended_system_position_role_id)
  if (recommended) return recommended.id
  return ''
}

async function loadSelectedPositionAccess() {
  preview.value = null
  successMessage.value = ''
  selectedPositionAccess.value = null
  if (!selectedSystemPositionRoleId.value) return
  isLoadingPosition.value = true
  try {
    selectedPositionAccess.value = await iamApi.getRoleAccess(selectedSystemPositionRoleId.value)
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    isLoadingPosition.value = false
  }
}

async function loadData() {
  isLoading.value = true
  errorMessage.value = ''
  try {
    const [userAccess, positions, catalog] = await Promise.all([
      iamApi.getUserAccess(userId.value),
      iamApi.listSystemPositions(),
      iamApi.listPermissions('active'),
    ])
    access.value = userAccess
    systemPositions.value = positions.filter((position) => position.is_system_position)
    permissions.value = catalog
    selectedSystemPositionRoleId.value = initialSystemPosition(userAccess, systemPositions.value)
    reason.value = ''
    preview.value = null
    await loadSelectedPositionAccess()
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
    if ((error as { response?: { status?: number } })?.response?.status === 403) {
      await authStore.refreshSession()
    }
  } finally {
    isLoading.value = false
  }
}

function discardChange() {
  selectedSystemPositionRoleId.value = access.value
    ? initialSystemPosition(access.value, systemPositions.value)
    : ''
  reason.value = ''
  preview.value = null
  errorMessage.value = ''
  void loadSelectedPositionAccess()
}

async function previewChange() {
  if (!hasSystemPositionAction.value) {
    errorMessage.value = '当前权限职位和历史授权都不需要调整。'
    return
  }
  if (!reason.value.trim()) {
    errorMessage.value = '调整权限职位必须填写原因。'
    return
  }
  isPreviewing.value = true
  errorMessage.value = ''
  successMessage.value = ''
  try {
    preview.value = await iamApi.previewUserSystemPosition(userId.value, {
      base_revision: access.value?.authorization_version ?? 0,
      system_position_role_id: selectedSystemPositionRoleId.value,
      reason: reason.value.trim(),
    })
    confirmedHighRisk.value = false
  } catch (error) {
    const status = (error as { response?: { status?: number } })?.response?.status
    errorMessage.value = status === 409 ? '授权版本已变化，页面已刷新，请重新选择。' : getApiErrorMessage(error)
    if (status === 409) await loadData()
    if (status === 403) await authStore.refreshSession()
  } finally {
    isPreviewing.value = false
  }
}

async function commitChange() {
  if (!preview.value) return
  isCommitting.value = true
  errorMessage.value = ''
  try {
    const result = await iamApi.commitUserSystemPosition(
      userId.value,
      preview.value.preview_token,
      confirmedHighRisk.value,
    )
    preview.value = null
    await loadData()
    await authStore.refreshSession()
    successMessage.value = '权限职位已更换并立即生效。'
  } catch (error) {
    const status = (error as { response?: { status?: number } })?.response?.status
    errorMessage.value = status === 409 ? '预览已失效或授权版本已变化，请重新预览。' : getApiErrorMessage(error)
    preview.value = null
    if (status === 409) await loadData()
    if (status === 403) await authStore.refreshSession()
  } finally {
    isCommitting.value = false
  }
}

function diffStateLabel(value: 'allow' | 'deny' | 'none') {
  return value === 'allow' ? '拥有' : value === 'deny' ? '禁止' : '无'
}

onMounted(() => void loadData())
</script>

<template>
  <main class="min-h-screen min-w-0 max-w-full overflow-x-clip bg-slate-100 text-slate-950">
    <IamNavigation title="调整权限职位" subtitle="员工只绑定一个内置权限职位；具体权限统一在内置职位权限中维护。" />

    <div class="mx-auto grid w-full min-w-0 max-w-[1480px] gap-5 px-4 py-5 sm:px-5 sm:py-6 xl:px-8">
      <RouterLink class="inline-flex w-fit items-center gap-2 text-sm font-bold text-slate-600 hover:text-emerald-800" to="/system/users?tab=users">
        <ArrowLeft class="size-4" aria-hidden="true" />返回用户列表
      </RouterLink>

      <div v-if="errorMessage" role="alert" class="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
        <AlertTriangle class="mt-0.5 size-4 shrink-0" aria-hidden="true" />{{ errorMessage }}
      </div>
      <div v-if="successMessage" role="status" class="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm font-semibold text-emerald-800">{{ successMessage }}</div>

      <div v-if="isLoading" class="grid min-h-72 place-items-center rounded-2xl border border-slate-200 bg-white">
        <div class="text-center text-slate-500"><LoaderCircle class="mx-auto mb-3 size-7 animate-spin text-emerald-700" /><p>正在读取用户权限职位…</p></div>
      </div>

      <template v-else-if="access">
        <IamIdentitySummary :access="access" />

        <section class="grid min-w-0 gap-5 xl:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
          <article class="min-w-0 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div class="mb-4 flex items-start justify-between gap-3">
              <div>
                <h2 class="flex items-center gap-2 font-bold"><ShieldCheck class="size-4 text-emerald-700" />内置权限职位</h2>
                <p class="mt-1 text-sm text-slate-500">更换职位后，原有底层角色和个人特殊权限会统一清理。</p>
              </div>
              <span class="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-bold text-emerald-700">单一职位</span>
            </div>

            <div class="rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm">
              <span class="text-xs font-semibold text-slate-500">当前权限职位</span>
              <strong class="mt-1 block text-slate-950">{{ access.system_position_role_name || '尚未分配' }}</strong>
            </div>

            <div v-if="!hasPrimaryOrganization" data-testid="missing-primary-department" class="mt-4 flex gap-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm leading-6 text-amber-900">
              <AlertTriangle class="mt-0.5 size-5 shrink-0" aria-hidden="true" />
              <div>
                <b>尚未确认主组织资料</b>
                <p>请先在账号审批或用户资料中补全厂区和部门，再分配内置权限职位。</p>
              </div>
            </div>

            <label v-else class="mt-4 grid gap-1.5 text-sm font-semibold text-slate-700">
              选择新的内置权限职位
              <select v-model="selectedSystemPositionRoleId" aria-label="选择新的内置权限职位" class="h-11 w-full min-w-0 rounded-xl border border-slate-200 bg-white px-3 outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100" @change="loadSelectedPositionAccess">
                <option value="" disabled>请选择内置权限职位</option>
                <optgroup v-for="group in groupedSystemPositions" :key="group.department" :label="group.name">
                  <option v-for="position in group.positions" :key="position.id" :value="position.id">
                    {{ position.name }}（{{ position.permission_count }} 项权限）
                  </option>
                </optgroup>
              </select>
              <span class="text-xs font-normal text-slate-400">只显示员工主部门可分配的内置职位。</span>
            </label>

            <div v-if="selectedSystemPosition" class="mt-3 rounded-xl border border-emerald-100 bg-emerald-50/60 p-3 text-sm text-emerald-950">
              <b>{{ selectedSystemPosition.position_department_name }} · {{ selectedSystemPosition.name }}</b>
              <p class="mt-1 leading-6 text-emerald-800">{{ selectedSystemPosition.description || '该职位的权限由管理员统一维护。' }}</p>
            </div>

            <div v-if="hasHistoricalAuthorization" class="mt-4 flex gap-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm leading-6 text-amber-900">
              <AlertTriangle class="mt-0.5 size-5 shrink-0" aria-hidden="true" />
              <div>
                <b>检测到历史授权</b>
                <p>当前生效 {{ access.legacy_role_count }} 条旧角色、{{ access.active_override_count }} 条个人特殊权限；本次共将清理 {{ access.cleanup_role_count }} 条普通角色和 {{ access.cleanup_override_count }} 条个人权限（包括尚未生效或已到期的残留授权）。</p>
              </div>
            </div>
          </article>

          <article class="min-w-0 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
            <header class="border-b border-slate-200 px-5 py-4">
              <div class="flex flex-wrap items-start justify-between gap-3">
                <div><h2 class="font-bold">将继承的权限</h2><p class="mt-1 text-sm text-slate-500">这里只展示内置职位结果，不能逐项修改。</p></div>
                <span class="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-bold text-slate-600">{{ visibleInheritedPermissionCount }} 项</span>
              </div>
            </header>
            <div v-if="isLoadingPosition" class="grid min-h-48 place-items-center"><LoaderCircle class="size-6 animate-spin text-emerald-700" /></div>
            <div v-else-if="groupedInheritedPermissions.length" class="divide-y divide-slate-100">
              <section v-for="group in groupedInheritedPermissions" :key="group.moduleCode" class="p-5">
                <div class="mb-3"><h3 class="font-bold text-slate-900">{{ group.moduleName }}</h3><code class="text-xs text-slate-400">{{ group.moduleCode }}</code></div>
                <ul class="grid gap-2 sm:grid-cols-2">
                  <li v-for="permission in group.items" :key="permission.code" class="flex min-w-0 items-start gap-2 rounded-xl bg-slate-50 p-3">
                    <CheckCircle2 class="mt-0.5 size-4 shrink-0 text-emerald-600" aria-hidden="true" />
                    <span class="min-w-0"><b class="block text-sm">{{ permissionDisplayLabel(permission) }}</b><code class="block break-all text-xs text-slate-400">{{ permission.code }}</code></span>
                  </li>
                </ul>
              </section>
            </div>
            <p v-else class="p-8 text-center text-sm text-slate-500">该内置职位尚未配置权限，当前将保持默认拒绝。</p>
          </article>
        </section>

        <section v-if="hasPrimaryOrganization" data-testid="system-position-action-panel" class="min-w-0 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <div class="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
            <label class="grid gap-1.5 text-sm font-semibold text-slate-700">
              调整原因 <span class="text-xs font-normal text-slate-400">必填，将进入审计记录</span>
              <input v-model="reason" type="text" maxlength="300" placeholder="例如：员工岗位职责调整为工程主管" class="h-11 w-full min-w-0 rounded-xl border border-slate-200 px-3 outline-none transition focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100">
            </label>
            <div class="grid grid-cols-1 gap-2 sm:flex">
              <button type="button" class="inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 text-sm font-bold text-slate-700 hover:bg-slate-50 disabled:opacity-50" :disabled="isPreviewing" @click="discardChange">
                <RefreshCw class="size-4" />取消修改
              </button>
              <button type="button" class="inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-emerald-700 px-5 text-sm font-bold text-white hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-50" :disabled="!hasSystemPositionAction || isPreviewing || !reason.trim()" @click="previewChange">
                <LoaderCircle v-if="isPreviewing" class="size-4 animate-spin" /><Save v-else class="size-4" />{{ hasPositionChange ? '预览职位调整' : '预览历史授权清理' }}
              </button>
            </div>
          </div>
        </section>
      </template>
    </div>

    <div v-if="preview" class="fixed inset-0 z-50 grid place-items-center bg-slate-950/45 p-4" @click.self="preview = null">
      <section class="max-h-[90vh] w-full max-w-3xl overflow-hidden rounded-2xl bg-white shadow-2xl" role="dialog" aria-modal="true" aria-labelledby="system-position-preview-title">
        <header class="flex items-start justify-between gap-4 border-b border-slate-200 px-5 py-4">
          <div><h2 id="system-position-preview-title" class="text-lg font-bold">确认权限职位调整</h2><p class="mt-1 text-sm text-slate-500">系统会以一次事务完成旧授权清理和新职位绑定。</p></div>
          <button type="button" aria-label="关闭权限职位调整预览" class="rounded-lg p-2 text-slate-400 hover:bg-slate-100" :disabled="isCommitting" @click="preview = null"><X class="size-5" /></button>
        </header>
        <div class="max-h-[62vh] overflow-y-auto p-5">
          <div class="flex flex-col items-stretch gap-3 rounded-xl bg-slate-50 p-4 sm:flex-row sm:items-center">
            <span class="flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"><small class="block text-slate-400">调整前</small><b>{{ preview.before_role_names.join('、') || '未分配内置职位' }}</b></span>
            <ArrowRight class="mx-auto size-5 shrink-0 text-slate-400 sm:mx-0" />
            <span class="flex-1 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900"><small class="block text-emerald-600">调整后</small><b>{{ preview.after_role_name }}</b></span>
          </div>
          <div class="mt-4 grid gap-3 sm:grid-cols-2">
            <div class="rounded-xl border border-slate-200 p-3 text-sm"><span class="text-slate-500">清理历史角色</span><b class="mt-1 block text-lg">{{ preview.removed_role_count }} 条</b></div>
            <div class="rounded-xl border border-slate-200 p-3 text-sm"><span class="text-slate-500">清理个人特殊权限</span><b class="mt-1 block text-lg">{{ preview.removed_override_count }} 条</b></div>
          </div>
          <div v-if="preview.diffs.length" class="mt-4 overflow-hidden rounded-xl border border-slate-200">
            <div v-for="diff in preview.diffs" :key="`${diff.permission_code}:${diff.factory_id}:${diff.department}`" class="flex flex-col gap-2 border-b border-slate-100 p-3 text-sm last:border-b-0 sm:flex-row sm:items-center sm:justify-between">
              <span class="min-w-0"><b class="block">{{ permissionLabels.get(diff.permission_code) || diff.permission_code }}</b><code class="block break-all text-xs text-slate-400">{{ diff.permission_code }}</code></span>
              <span class="shrink-0 font-bold" :class="diff.after === 'allow' ? 'text-emerald-700' : 'text-rose-700'">{{ diffStateLabel(diff.before) }} → {{ diffStateLabel(diff.after) }}</span>
            </div>
          </div>
          <label v-if="preview.high_risk" class="mt-4 flex gap-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"><input v-model="confirmedHighRisk" type="checkbox" class="mt-0.5 size-4 accent-amber-600"><span>我已核对高风险权限和历史授权清理范围。</span></label>
        </div>
        <footer class="flex justify-end gap-2 border-t border-slate-200 bg-slate-50 p-4"><button type="button" class="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-bold" :disabled="isCommitting" @click="preview = null">返回修改</button><button type="button" class="inline-flex items-center gap-2 rounded-xl bg-emerald-700 px-4 py-2 text-sm font-bold text-white disabled:opacity-50" :disabled="isCommitting || (preview.high_risk && !confirmedHighRisk)" @click="commitChange"><LoaderCircle v-if="isCommitting" class="size-4 animate-spin" /><CheckCircle2 v-else class="size-4" />确认并立即生效</button></footer>
      </section>
    </div>
  </main>
</template>
