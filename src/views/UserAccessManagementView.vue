<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ArrowLeft, CalendarClock, LoaderCircle, RefreshCw, Save, ShieldAlert } from '@lucide/vue'
import { useRoute } from 'vue-router'
import {
  iamApi,
  type EffectiveAccessEntry,
  type ManageableScope,
  type PermissionCatalogItem,
  type PermissionDraftEffect,
  type RoleBinding,
  type RoleBindingDraft,
  type RoleSummary,
  type UserAccessPreviewResponse,
  type UserAccessResponse,
} from '@/api/iam'
import IamAccessPreviewDialog from '@/components/iam/IamAccessPreviewDialog.vue'
import IamIdentitySummary from '@/components/iam/IamIdentitySummary.vue'
import IamNavigation from '@/components/iam/IamNavigation.vue'
import IamPermissionMatrix, { type PermissionMatrixResolution } from '@/components/iam/IamPermissionMatrix.vue'
import IamRoleBindings from '@/components/iam/IamRoleBindings.vue'
import IamScopeSelector from '@/components/iam/IamScopeSelector.vue'
import { departmentMap, departments, factoryContexts } from '@/data/enterpriseMock'
import { getApiErrorMessage } from '@/lib/http'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const authStore = useAuthStore()

const access = ref<UserAccessResponse | null>(null)
const permissions = ref<PermissionCatalogItem[]>([])
const roles = ref<RoleSummary[]>([])
const manageableScopes = ref<ManageableScope[]>([])
const selectedFactoryId = ref('')
const selectedDepartment = ref('')
const draftStates = ref<Record<string, PermissionDraftEffect>>({})
const originalStates = ref<Record<string, PermissionDraftEffect>>({})
const roleBindingDrafts = ref<RoleBindingDraft[]>([])
const reason = ref('')
const validUntil = ref('')
const preview = ref<UserAccessPreviewResponse | null>(null)
const isLoading = ref(false)
const isPreviewing = ref(false)
const isCommitting = ref(false)
const errorMessage = ref('')
const successMessage = ref('')

const userId = computed(() => String(route.params.userId ?? ''))
const activePermissions = computed(() => permissions.value
  .filter((permission) => permission.status === 'active')
  .sort((left, right) => left.sort_order - right.sort_order || left.code.localeCompare(right.code)))

const changedPermissionCodes = computed(() => activePermissions.value
  .map((permission) => permission.code)
  .filter((permissionCode) => draftStates.value[permissionCode] !== originalStates.value[permissionCode]))
const changeCount = computed(() => changedPermissionCodes.value.length + roleBindingDrafts.value.length)

const resolutionByPermission = computed<Record<string, PermissionMatrixResolution | undefined>>(() => {
  const resolutions: Record<string, PermissionMatrixResolution | undefined> = {}
  for (const permission of activePermissions.value) {
    const entries = (access.value?.effective_access ?? []).filter((entry) =>
      entry.permission_code === permission.code
      && scopeMatches(entry, selectedFactoryId.value, selectedDepartment.value),
    )
    const denied = entries.find((entry) => entry.effect === 'deny' || entry.allowed === false)
    const allowed = entries.find((entry) => entry.effect === 'allow' && entry.allowed !== false)
    const resolved = denied ?? allowed
    resolutions[permission.code] = resolved
      ? {
          allowed: resolved.effect === 'allow' && resolved.allowed !== false,
          source_label: sourceLabel(resolved),
        }
      : { allowed: false, source_label: '默认拒绝' }
  }
  return resolutions
})

function scopeMatches(entry: EffectiveAccessEntry, factoryId: string, department: string) {
  return (entry.factory_id === '*' || entry.factory_id === factoryId)
    && (entry.department === '*' || entry.department === department)
}

function sourceLabel(entry: EffectiveAccessEntry) {
  if (entry.source_name) return entry.source_name
  if (entry.source_ids?.length) return `${entry.source_type} · ${entry.source_ids.join('、')}`
  return entry.source_type || (entry.allowed ? '有效授权' : '明确禁止')
}

function factoryLabel(factoryId: string) {
  if (factoryId === '*') return '全部厂区'
  return factoryContexts.find((factory) => factory.id === factoryId)?.shortName ?? factoryId
}

function departmentLabel(departmentId: string) {
  if (departmentId === '*') return '全部部门'
  return departmentMap[departmentId as keyof typeof departmentMap]?.name ?? departmentId
}

function uniqueScopes(scopes: ManageableScope[]) {
  const seen = new Set<string>()
  return scopes.filter((scope) => {
    const key = `${scope.factory_id}:${scope.department}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function buildFallbackScopes(userAccess: UserAccessResponse, superAdmin: boolean) {
  if (superAdmin) {
    const result: ManageableScope[] = [{ factory_id: '*', factory_name: '全部厂区', department: '*', department_name: '全部部门' }]
    for (const factory of factoryContexts.filter((item) => item.id !== 'group')) {
      for (const department of departments.filter((item) => item.id !== 'overview')) {
        result.push({
          factory_id: factory.id,
          factory_name: factory.shortName,
          department: department.id,
          department_name: department.name,
        })
      }
    }
    return result
  }

  return uniqueScopes([
    ...userAccess.role_bindings.map((binding) => ({
      factory_id: binding.factory_id,
      factory_name: factoryLabel(binding.factory_id),
      department: binding.department,
      department_name: departmentLabel(binding.department),
    })),
    ...userAccess.overrides.map((override) => ({
      factory_id: override.factory_id,
      factory_name: factoryLabel(override.factory_id),
      department: override.department,
      department_name: departmentLabel(override.department),
    })),
  ])
}

function resetDraftForScope() {
  const next: Record<string, PermissionDraftEffect> = {}
  for (const permission of activePermissions.value) {
    const currentOverride = access.value?.overrides.find((override) =>
      override.permission_code === permission.code
      && override.factory_id === selectedFactoryId.value
      && override.department === selectedDepartment.value
      && override.state === 'active',
    )
    next[permission.code] = currentOverride?.effect ?? 'inherit'
  }
  draftStates.value = { ...next }
  originalStates.value = { ...next }
  preview.value = null
}

function selectInitialScope() {
  const preferredFactory = access.value?.profile?.primary_factory_id
  const preferredDepartment = access.value?.profile?.primary_department
  const preferred = manageableScopes.value.find((scope) =>
    scope.factory_id === preferredFactory && scope.department === preferredDepartment,
  )
  const first = preferred ?? manageableScopes.value[0]
  selectedFactoryId.value = first?.factory_id ?? ''
  selectedDepartment.value = first?.department ?? ''
}

async function loadData() {
  isLoading.value = true
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const [catalog, scopeResponse, userAccess] = await Promise.all([
      iamApi.listPermissions('active'),
      iamApi.getManageableScopes(),
      iamApi.getUserAccess(userId.value),
    ])
    roles.value = await iamApi.listRoles()
    permissions.value = catalog
    access.value = userAccess
    const fallbackScopes = buildFallbackScopes(userAccess, scopeResponse.is_super_admin)
    manageableScopes.value = uniqueScopes(
      scopeResponse.is_super_admin
        ? [...scopeResponse.scopes, ...fallbackScopes]
        : scopeResponse.scopes.length ? scopeResponse.scopes : fallbackScopes,
    )
    selectInitialScope()
    resetDraftForScope()
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
    if ((error as { response?: { status?: number } })?.response?.status === 403) {
      await authStore.refreshSession()
    }
  } finally {
    isLoading.value = false
  }
}

function updatePermissionState(permissionCode: string, effect: PermissionDraftEffect) {
  draftStates.value = { ...draftStates.value, [permissionCode]: effect }
  preview.value = null
  successMessage.value = ''
}

function addRoleBinding(roleId: string) {
  const duplicate = access.value?.role_bindings.some((binding) =>
    binding.state === 'active'
    && binding.role_id === roleId
    && binding.factory_id === selectedFactoryId.value
    && binding.department === selectedDepartment.value,
  ) || roleBindingDrafts.value.some((draft) =>
    draft.operation === 'add'
    && draft.role_id === roleId
    && draft.factory_id === selectedFactoryId.value
    && draft.department === selectedDepartment.value,
  )
  if (duplicate) {
    errorMessage.value = '该角色已在当前范围生效或已加入草稿。'
    return
  }
  roleBindingDrafts.value = [...roleBindingDrafts.value, {
    operation: 'add',
    role_id: roleId,
    factory_id: selectedFactoryId.value,
    department: selectedDepartment.value,
    valid_until: validUntil.value ? new Date(`${validUntil.value}T23:59:59`).toISOString() : null,
  }]
  preview.value = null
  errorMessage.value = ''
}

function revokeRoleBinding(binding: RoleBinding) {
  if (roleBindingDrafts.value.some((draft) => draft.operation === 'revoke' && draft.binding_id === binding.id)) {
    return
  }
  roleBindingDrafts.value = [...roleBindingDrafts.value, {
    operation: 'revoke',
    binding_id: binding.id,
    role_id: binding.role_id,
    factory_id: binding.factory_id,
    department: binding.department,
  }]
  preview.value = null
}

function undoRoleBindingDraft(index: number) {
  roleBindingDrafts.value = roleBindingDrafts.value.filter((_, draftIndex) => draftIndex !== index)
  preview.value = null
}

function discardDraft() {
  draftStates.value = { ...originalStates.value }
  roleBindingDrafts.value = []
  reason.value = ''
  validUntil.value = ''
  preview.value = null
  errorMessage.value = ''
}

async function previewChanges() {
  const trimmedReason = reason.value.trim()
  if (!changeCount.value) {
    errorMessage.value = '请先调整至少一项权限。'
    return
  }
  if (!trimmedReason) {
    errorMessage.value = '权限变更必须填写原因。'
    return
  }

  isPreviewing.value = true
  errorMessage.value = ''
  try {
    preview.value = await iamApi.previewUserAccess(userId.value, {
      base_revision: access.value?.authorization_version ?? 0,
      reason: trimmedReason,
      role_bindings: roleBindingDrafts.value,
      overrides: changedPermissionCodes.value.map((permissionCode) => ({
        permission_code: permissionCode,
        effect: draftStates.value[permissionCode] ?? 'inherit',
        factory_id: selectedFactoryId.value,
        department: selectedDepartment.value,
        valid_until: draftStates.value[permissionCode] === 'inherit' || !validUntil.value
          ? null
          : new Date(`${validUntil.value}T23:59:59`).toISOString(),
      })),
    })
  } catch (error) {
    const status = (error as { response?: { status?: number } })?.response?.status
    errorMessage.value = status === 409 ? '授权版本已变化，页面已刷新，请重新调整。' : getApiErrorMessage(error)
    if (status === 409) await loadData()
    if (status === 403) await authStore.refreshSession()
  } finally {
    isPreviewing.value = false
  }
}

async function commitChanges(confirmHighRisk: boolean) {
  if (!preview.value) return
  isCommitting.value = true
  errorMessage.value = ''
  try {
    const result = await iamApi.commitUserAccess(userId.value, preview.value.preview_token, confirmHighRisk)
    const message = result.status === 'pending_approval'
      ? `权限申请已提交${result.request_id ? `（${result.request_id}）` : ''}，等待集团超级管理员审批。`
      : '权限调整已提交并立即生效。'
    preview.value = null
    roleBindingDrafts.value = []
    reason.value = ''
    validUntil.value = ''
    await loadData()
    await authStore.refreshSession()
    successMessage.value = message
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

watch([selectedFactoryId, selectedDepartment], ([factoryId, department], previous) => {
  if (!previous || !factoryId || !department) return
  resetDraftForScope()
  roleBindingDrafts.value = []
  reason.value = ''
  validUntil.value = ''
})

onMounted(() => {
  void loadData()
})
</script>

<template>
  <main class="min-h-screen min-w-0 max-w-full overflow-x-clip bg-slate-100 text-slate-950">
    <IamNavigation title="用户权限配置" subtitle="按用户、模块、操作和组织范围精确调整；角色模板仍作为基础授权来源。" />

    <div class="mx-auto grid w-full min-w-0 max-w-[1480px] gap-5 px-4 py-5 sm:px-5 sm:py-6 xl:px-8">
      <RouterLink class="flex w-fit items-center gap-2 text-sm font-bold text-slate-600 hover:text-emerald-700" to="/system/users?tab=users">
        <ArrowLeft class="size-4" />返回用户列表
      </RouterLink>

      <div v-if="errorMessage" class="flex items-start gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
        <ShieldAlert class="mt-0.5 size-5 shrink-0" />
        <span>{{ errorMessage }}</span>
      </div>
      <div v-if="successMessage" class="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm font-semibold text-emerald-800">{{ successMessage }}</div>

      <div v-if="isLoading" class="grid min-h-72 place-items-center rounded-2xl border border-slate-200 bg-white">
        <div class="text-center text-slate-500"><LoaderCircle class="mx-auto mb-3 size-7 animate-spin text-emerald-700" /><p>正在读取用户有效权限…</p></div>
      </div>

      <template v-else-if="access">
        <IamIdentitySummary :access="access" />

        <div class="grid min-w-0 gap-5 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
          <IamScopeSelector
            v-model:factory-id="selectedFactoryId"
            v-model:department="selectedDepartment"
            :scopes="manageableScopes"
            :disabled="Boolean(changeCount)"
          />
          <IamRoleBindings
            :bindings="access.role_bindings"
            :roles="roles"
            :factory-id="selectedFactoryId"
            :department="selectedDepartment"
            :drafts="roleBindingDrafts"
            :disabled="!manageableScopes.length"
            @add="addRoleBinding"
            @revoke="revokeRoleBinding"
            @undo="undoRoleBindingDraft"
          />
        </div>

        <div v-if="!manageableScopes.length" class="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          当前管理员没有可管理的厂区 / 部门范围。你仍可查看授权来源，但不能修改权限。
        </div>

        <IamPermissionMatrix
          :permissions="activePermissions"
          :states="draftStates"
          :resolutions="resolutionByPermission"
          :disabled="!manageableScopes.length"
          @change="updatePermissionState"
        />

        <section data-testid="permission-action-panel" class="min-w-0 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <div class="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1fr)_220px_auto] xl:items-end">
            <label class="grid gap-1.5 text-sm font-semibold text-slate-700">
              变更原因 <span class="text-xs font-normal text-slate-400">必填，将进入审计记录</span>
              <input v-model="reason" type="text" maxlength="300" placeholder="例如：新增设备维修模块，需要开放查看和修改权限" class="h-11 w-full min-w-0 rounded-xl border border-slate-200 px-3 outline-none transition focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100">
            </label>
            <label class="grid gap-1.5 text-sm font-semibold text-slate-700">
              <span class="flex items-center gap-1.5"><CalendarClock class="size-4" />有效期至</span>
              <input v-model="validUntil" type="date" class="h-11 w-full min-w-0 rounded-xl border border-slate-200 px-3 outline-none transition focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100">
            </label>
            <div class="grid min-w-0 grid-cols-1 gap-2 sm:flex">
              <button type="button" class="inline-flex h-11 w-full min-w-0 items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 text-sm font-bold text-slate-700 hover:bg-slate-50 disabled:opacity-50 sm:w-auto" :disabled="!changeCount || isPreviewing" @click="discardDraft">
                <RefreshCw class="size-4" />取消草稿
              </button>
              <button type="button" class="inline-flex h-11 w-full min-w-0 items-center justify-center gap-2 rounded-xl bg-emerald-700 px-5 text-sm font-bold text-white hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto" :disabled="!changeCount || isPreviewing || !manageableScopes.length" @click="previewChanges">
                <LoaderCircle v-if="isPreviewing" class="size-4 animate-spin" />
                <Save v-else class="size-4" />预览 {{ changeCount }} 项变更
              </button>
            </div>
          </div>
        </section>
      </template>
    </div>

    <IamAccessPreviewDialog
      v-if="preview"
      :preview="preview"
      :permissions="permissions"
      :reason="reason"
      :is-committing="isCommitting"
      @close="preview = null"
      @commit="commitChanges"
    />
  </main>
</template>
