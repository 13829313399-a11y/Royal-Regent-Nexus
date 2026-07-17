<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { AlertTriangle, CheckCircle2, LoaderCircle, RotateCcw, Save, Search, ShieldCheck, X } from '@lucide/vue'
import {
  iamApi,
  type PermissionCatalogItem,
  type RoleAccessPreviewResponse,
  type RoleAccessResponse,
  type RoleScopeMode,
  type RoleSummary,
} from '@/api/iam'
import IamNavigation from '@/components/iam/IamNavigation.vue'
import {
  isBuiltInPositionPermissionVisible,
  permissionDisplayLabel,
} from '@/components/iam/permissionCatalogLabels'
import { getApiErrorMessage } from '@/lib/http'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
const roles = ref<RoleSummary[]>([])
const permissions = ref<PermissionCatalogItem[]>([])
const selectedRoleId = ref('')
const canManageRoleTemplates = ref(false)
const roleAccess = ref<RoleAccessResponse | null>(null)
const selectedPermissionCodes = ref<string[]>([])
const selectedScopeMode = ref<RoleScopeMode>('own_factory')
const roleSearchQuery = ref('')
const permissionSearchQuery = ref('')
const selectedModuleCode = ref('all')
const permissionViewMode = ref<'all' | 'selected' | 'changed'>('all')
const permissionViewOptions: Array<{ value: 'all' | 'selected' | 'changed'; label: string }> = [
  { value: 'all', label: '全部' },
  { value: 'selected', label: '已选' },
  { value: 'changed', label: '有变更' },
]
const roleScopeOptions: Array<{ value: RoleScopeMode; label: string; description: string }> = [
  { value: 'own_factory', label: '本厂', description: '查看和操作均只在员工所属厂区生效。' },
  { value: 'cross_factory_read', label: '跨厂查看', description: '查看类权限可跨厂，操作类权限仍限本厂。' },
  { value: 'cross_factory_operate', label: '跨厂操作', description: '查看和操作类权限均可跨厂，提交时按高风险变更核对。' },
]
const permissionScrollContainer = ref<HTMLElement | null>(null)
const reason = ref('')
const preview = ref<RoleAccessPreviewResponse | null>(null)
const confirmedHighRisk = ref(false)
const isLoading = ref(false)
const isRoleLoading = ref(false)
const isSaving = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
let roleAccessRequestSequence = 0

const groupedPermissions = computed(() => {
  const groups = new Map<string, { moduleName: string; permissions: PermissionCatalogItem[] }>()
  permissions.value
    .filter((item) => item.status === 'active' && isBuiltInPositionPermissionVisible(item.code))
    .forEach((permission) => {
    const group = groups.get(permission.module_code)
    if (group) group.permissions.push(permission)
    else groups.set(permission.module_code, { moduleName: permission.module_name, permissions: [permission] })
    })
  return [...groups.entries()].map(([moduleCode, value]) => ({ moduleCode, ...value }))
})
const groupedSystemPositions = computed(() => {
  const groups = new Map<string, { department: string; name: string; roles: RoleSummary[] }>()
  const sortedRoles = [...roles.value]
    .sort((left, right) => left.position_sort_order - right.position_sort_order || left.name.localeCompare(right.name, 'zh-CN'))
  sortedRoles.forEach((role) => {
      const department = role.position_department || 'other'
      const group = groups.get(department)
      if (group) group.roles.push(role)
      else groups.set(department, {
        department,
        name: role.position_department_name || department,
        roles: [role],
      })
  })
  return [...groups.values()]
})
const visibleSystemPositionGroups = computed(() => {
  const query = roleSearchQuery.value.trim().toLocaleLowerCase('zh-CN')
  if (!query) return groupedSystemPositions.value
  return groupedSystemPositions.value
    .map((group) => ({
      ...group,
      roles: group.roles.filter((role) => [group.name, role.name, role.description, role.code]
        .some((value) => value?.toLocaleLowerCase('zh-CN').includes(query))),
    }))
    .filter((group) => group.roles.length)
})
const visibleSystemPositionCount = computed(() => visibleSystemPositionGroups.value.reduce((total, group) => total + group.roles.length, 0))
const activePermissionCount = computed(() => permissions.value.filter((item) => item.status === 'active').length)
const templatePermissionCount = computed(() => roleAccess.value?.permission_codes.length ?? 0)
const permissionLabels = computed(() => new Map(permissions.value.map((permission) => [permission.code, permissionDisplayLabel(permission)])))
const originalPermissionCodes = computed(() => new Set(roleAccess.value?.permission_codes ?? []))
const originalScopeMode = computed<RoleScopeMode>(() => roleAccess.value?.scope_mode ?? 'own_factory')
const selectedPermissionCodeSet = computed(() => new Set(selectedPermissionCodes.value))
const addedPermissionCount = computed(() => selectedPermissionCodes.value.filter((code) => !originalPermissionCodes.value.has(code)).length)
const removedPermissionCount = computed(() => [...originalPermissionCodes.value].filter((code) => !selectedPermissionCodeSet.value.has(code)).length)
const filteredPermissionGroups = computed(() => {
  const query = permissionSearchQuery.value.trim().toLocaleLowerCase('zh-CN')
  return groupedPermissions.value
    .filter((group) => selectedModuleCode.value === 'all' || group.moduleCode === selectedModuleCode.value)
    .map((group) => ({
      ...group,
      permissions: group.permissions.filter((permission) => {
        const selected = selectedPermissionCodeSet.value.has(permission.code)
        const changed = selected !== originalPermissionCodes.value.has(permission.code)
        if (permissionViewMode.value === 'selected' && !selected) return false
        if (permissionViewMode.value === 'changed' && !changed) return false
        if (!query) return true
        return [permissionDisplayLabel(permission), permission.code, group.moduleName, group.moduleCode]
          .some((value) => value.toLocaleLowerCase('zh-CN').includes(query))
      }),
    }))
    .filter((group) => group.permissions.length)
})
const filteredPermissionCount = computed(() => filteredPermissionGroups.value.reduce((total, group) => total + group.permissions.length, 0))
const editablePermissionCount = computed(() => groupedPermissions.value.reduce((total, group) => total + group.permissions.length, 0))
const scopeModeChanged = computed(() => selectedScopeMode.value !== originalScopeMode.value)
const selectedScopeDescription = computed(() => roleScopeOptions.find((option) => option.value === selectedScopeMode.value)?.description ?? '')

const hasChanges = computed(() => {
  if (!roleAccess.value) return false
  return scopeModeChanged.value
    || [...selectedPermissionCodes.value].sort().join('|') !== [...roleAccess.value.permission_codes].sort().join('|')
})

function roleScopeLabel(scopeMode?: RoleScopeMode) {
  return roleScopeOptions.find((option) => option.value === (scopeMode ?? 'own_factory'))?.label ?? '本厂'
}

function permissionAccessKindLabel(permission: PermissionCatalogItem) {
  return permission.access_kind === 'read' ? '查看' : '操作'
}

function permissionEffectiveScopeLabel(permission: PermissionCatalogItem) {
  if (permission.scope_type === 'global') return '全局生效'
  if (selectedScopeMode.value === 'own_factory') return '本厂'
  if (selectedScopeMode.value === 'cross_factory_read') {
    return permission.access_kind === 'read' ? '跨厂查看' : '本厂操作'
  }
  return permission.access_kind === 'read' ? '跨厂查看' : '跨厂操作'
}

function isSelected(permissionCode: string) {
  return selectedPermissionCodes.value.includes(permissionCode)
}

function togglePermission(permissionCode: string) {
  if (roleAccess.value?.is_protected || !canManageRoleTemplates.value || isSaving.value) return
  selectedPermissionCodes.value = isSelected(permissionCode)
    ? selectedPermissionCodes.value.filter((code) => code !== permissionCode)
    : [...selectedPermissionCodes.value, permissionCode]
  preview.value = null
  successMessage.value = ''
}

function selectScopeMode(scopeMode: RoleScopeMode) {
  if (roleAccess.value?.is_protected || !canManageRoleTemplates.value || isSaving.value) return
  selectedScopeMode.value = scopeMode
  preview.value = null
  successMessage.value = ''
}

function resetChanges() {
  if (!roleAccess.value) return
  selectedPermissionCodes.value = [...roleAccess.value.permission_codes]
  selectedScopeMode.value = originalScopeMode.value
  reason.value = ''
  preview.value = null
  confirmedHighRisk.value = false
  errorMessage.value = ''
}

async function loadRoleAccess(roleId: string, resetPermissionScroll = true) {
  const requestSequence = ++roleAccessRequestSequence
  selectedRoleId.value = roleId
  isRoleLoading.value = true
  preview.value = null
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const result = await iamApi.getRoleAccess(roleId)
    if (requestSequence !== roleAccessRequestSequence) return false
    roleAccess.value = result
    selectedPermissionCodes.value = [...result.permission_codes]
    selectedScopeMode.value = result.scope_mode ?? 'own_factory'
    reason.value = ''
    confirmedHighRisk.value = false
    isRoleLoading.value = false
    if (resetPermissionScroll) {
      await nextTick()
      permissionScrollContainer.value?.scrollTo?.({ top: 0 })
    }
    return true
  } catch (error) {
    if (requestSequence === roleAccessRequestSequence) {
      selectedRoleId.value = roleAccess.value?.id ?? ''
      errorMessage.value = getApiErrorMessage(error)
    }
    return false
  } finally {
    if (requestSequence === roleAccessRequestSequence) isRoleLoading.value = false
  }
}

async function requestRoleChange(roleId: string) {
  if (isSaving.value) return false
  if (!roleId || (roleId === selectedRoleId.value && roleAccess.value?.id === roleId)) return true
  if (hasChanges.value && !window.confirm('当前职位还有未保存的权限修改，切换职位将放弃这些修改。是否继续？')) return false
  return loadRoleAccess(roleId)
}

async function handleMobileRoleSelect(event: Event) {
  const select = event.target as HTMLSelectElement
  const changed = await requestRoleChange(select.value)
  if (!changed) select.value = selectedRoleId.value
}

async function loadData() {
  isLoading.value = true
  errorMessage.value = ''
  try {
    const [roleItems, permissionItems, scopeResponse] = await Promise.all([
      iamApi.listSystemPositions(),
      iamApi.listPermissions('active'),
      iamApi.getManageableScopes(),
    ])
    roles.value = roleItems
    permissions.value = permissionItems
    canManageRoleTemplates.value = scopeResponse.can_manage_role_templates
    if (roleItems.length) await loadRoleAccess(roleItems[0].id)
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    isLoading.value = false
  }
}

async function previewChanges() {
  if (!roleAccess.value || !hasChanges.value) return
  if (!reason.value.trim()) {
    errorMessage.value = '角色模板变更必须填写原因。'
    return
  }
  isSaving.value = true
  errorMessage.value = ''
  try {
    preview.value = await iamApi.previewRoleAccess(roleAccess.value.id, {
      base_version: roleAccess.value.version,
      reason: reason.value.trim(),
      permission_codes: selectedPermissionCodes.value,
      scope_mode: selectedScopeMode.value,
    })
    confirmedHighRisk.value = false
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    isSaving.value = false
  }
}

async function commitChanges() {
  if (!roleAccess.value || !preview.value) return
  const roleId = roleAccess.value.id
  isSaving.value = true
  errorMessage.value = ''
  try {
    await iamApi.commitRoleAccess(roleAccess.value.id, preview.value.preview_token, confirmedHighRisk.value)
    const message = `内置职位“${roleAccess.value.name}”的权限已更新，数据范围设置已同步，绑定用户的有效权限已重新计算。`
    preview.value = null
    roles.value = await iamApi.listSystemPositions()
    await loadRoleAccess(roleId, false)
    await authStore.refreshSession()
    successMessage.value = message
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
    preview.value = null
  } finally {
    isSaving.value = false
  }
}

onMounted(() => void loadData())
</script>

<template>
  <main class="min-h-screen overflow-x-clip bg-slate-100 text-slate-950 xl:flex xl:h-dvh xl:min-h-0 xl:flex-col xl:overflow-hidden">
    <IamNavigation data-testid="role-templates-sticky-navigation" class="sticky top-0 z-30 shadow-sm xl:static xl:shrink-0" title="内置职位权限" subtitle="按部门维护固定职位权限；员工只需绑定一个内置权限职位。" />
    <div data-testid="role-editor-workspace" class="mx-auto grid min-w-0 max-w-[1480px] gap-4 px-4 py-5 sm:px-5 xl:min-h-0 xl:w-full xl:flex-1 xl:grid-cols-[300px_minmax(0,1fr)] xl:px-8 xl:py-4">
      <aside data-testid="role-directory-panel" class="hidden min-w-0 rounded-2xl border border-slate-200 bg-white shadow-sm xl:flex xl:min-h-0 xl:flex-col">
        <div class="shrink-0 border-b border-slate-100 p-3">
          <div class="flex items-center justify-between gap-3 px-1 py-1">
            <h2 class="text-sm font-bold text-slate-900">内置职位目录</h2>
            <span class="text-xs font-semibold text-slate-400">{{ roles.length }} 个职位</span>
          </div>
          <label class="mt-2 grid gap-1.5 text-xs font-semibold text-slate-600">
            搜索职位
            <span class="relative block">
              <Search class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
              <input v-model="roleSearchQuery" type="search" class="h-10 w-full rounded-xl border border-slate-200 pl-9 pr-3 text-sm font-normal outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100" placeholder="部门、职位或代码">
            </span>
          </label>
          <p class="mt-2 px-1 text-xs text-slate-500" aria-live="polite">显示 {{ visibleSystemPositionCount }} / {{ roles.length }} 个职位</p>
        </div>

        <div data-testid="role-directory-scroll-region" role="region" aria-label="内置职位目录" tabindex="0" class="min-h-0 flex-1 overflow-y-auto p-3 outline-none focus:ring-2 focus:ring-inset focus:ring-emerald-200">
          <section v-for="group in visibleSystemPositionGroups" :key="group.department" class="mt-2 border-t border-slate-100 pt-2 first:mt-0 first:border-t-0">
            <h3 class="px-2 py-1 text-xs font-bold text-slate-400">{{ group.name }}</h3>
            <button v-for="role in group.roles" :key="role.id" type="button" class="mt-1 min-w-0 w-full rounded-xl px-3 py-2.5 text-left transition focus:outline-none focus:ring-2 focus:ring-emerald-300 disabled:cursor-wait disabled:opacity-60" :class="selectedRoleId === role.id ? 'bg-emerald-50 text-emerald-900' : 'hover:bg-slate-50'" :aria-pressed="selectedRoleId === role.id" :aria-current="selectedRoleId === role.id ? 'true' : undefined" :disabled="isSaving" @click="requestRoleChange(role.id)">
              <span class="flex min-w-0 items-center gap-2">
                <b class="min-w-0 flex-1 truncate text-sm">{{ role.name }}</b>
                <span class="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-bold text-slate-600">{{ roleScopeLabel(role.scope_mode) }}</span>
                <ShieldCheck v-if="role.is_protected" class="size-4 shrink-0 text-amber-600" aria-label="受保护职位" />
              </span>
              <span class="mt-1 block text-xs text-slate-500">{{ role.permission_count ? `已配置 ${role.permission_count} 项权限` : '权限待配置' }} · {{ role.binding_count }} 位用户</span>
            </button>
          </section>
          <p v-if="!visibleSystemPositionGroups.length && !isLoading" class="p-4 text-center text-sm text-slate-500">没有匹配的内置职位。</p>
        </div>
      </aside>

      <section class="min-w-0 xl:flex xl:min-h-0 xl:flex-col">
        <label class="mb-4 grid gap-1.5 text-sm font-semibold text-slate-700 xl:hidden">
          选择内置职位
          <select :value="selectedRoleId" class="h-11 rounded-xl border border-slate-200 bg-white px-3 outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100 disabled:cursor-wait disabled:opacity-60" :disabled="isSaving" @change="handleMobileRoleSelect">
            <optgroup v-for="group in groupedSystemPositions" :key="group.department" :label="group.name">
              <option v-for="role in group.roles" :key="role.id" :value="role.id">{{ role.name }} · {{ roleScopeLabel(role.scope_mode) }}（{{ role.permission_count }} 项权限）</option>
            </optgroup>
          </select>
        </label>

        <div v-if="errorMessage" class="mb-3 shrink-0 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">{{ errorMessage }}</div>
        <div v-if="successMessage" class="mb-3 shrink-0 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm font-semibold text-emerald-800">{{ successMessage }}</div>
        <div v-if="isLoading || isRoleLoading || !roleAccess" class="grid min-h-64 flex-1 place-items-center rounded-2xl border border-slate-200 bg-white"><LoaderCircle v-if="isLoading || isRoleLoading" class="size-7 animate-spin text-emerald-700" /></div>

        <template v-else>
          <div data-testid="role-editor-panel" class="grid min-h-0 gap-3 xl:flex-1 xl:grid-rows-[auto_minmax(0,1fr)_auto]">
            <div class="grid gap-3">
              <header class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <div class="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h2 class="text-xl font-bold">{{ roleAccess.name }}</h2>
                    <p class="mt-1 text-sm text-slate-500">{{ roleAccess.position_department_name }} · {{ roleAccess.description || roleAccess.code }} · 权限版本 {{ roleAccess.version }}</p>
                  </div>
                  <span v-if="roleAccess.is_protected" class="rounded-full bg-amber-50 px-3 py-1.5 text-xs font-bold text-amber-700">受保护角色，不可在线修改</span>
                  <span v-else class="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-bold text-slate-600">影响 {{ roleAccess.binding_count }} 位绑定用户</span>
                </div>

                <fieldset class="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3" :disabled="roleAccess.is_protected || !canManageRoleTemplates || isSaving">
                  <legend class="sr-only">职位数据范围</legend>
                  <span class="mr-1 text-xs font-semibold text-slate-600" aria-hidden="true">数据范围</span>
                  <label
                    v-for="option in roleScopeOptions"
                    :key="option.value"
                    class="inline-flex h-9 cursor-pointer items-center gap-2 rounded-xl border px-3 text-xs font-bold transition has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-60"
                    :class="selectedScopeMode === option.value ? 'border-emerald-300 bg-emerald-50 text-emerald-800' : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'"
                  >
                    <input
                      type="radio"
                      name="role-scope-mode"
                      class="size-3.5 accent-emerald-700"
                      :value="option.value"
                      :checked="selectedScopeMode === option.value"
                      :disabled="roleAccess.is_protected || !canManageRoleTemplates || isSaving"
                      aria-describedby="role-scope-description"
                      @change="selectScopeMode(option.value)"
                    >
                    {{ option.label }}
                  </label>
                  <p id="role-scope-description" class="min-w-[240px] flex-1 text-xs leading-5 text-slate-500">{{ selectedScopeDescription }}</p>
                </fieldset>

                <div class="mt-3 grid gap-3 lg:grid-cols-[minmax(0,1fr)_210px_auto] lg:items-end">
                  <label class="grid gap-1.5 text-xs font-semibold text-slate-600">
                    搜索权限
                    <span class="relative block">
                      <Search class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
                      <input v-model="permissionSearchQuery" type="search" class="h-10 w-full rounded-xl border border-slate-200 pl-9 pr-3 text-sm font-normal outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100" placeholder="权限名称、模块或代码">
                    </span>
                  </label>
                  <label class="grid gap-1.5 text-xs font-semibold text-slate-600">
                    权限模块
                    <select v-model="selectedModuleCode" class="h-10 rounded-xl border border-slate-200 bg-white px-3 text-sm font-normal outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100">
                      <option value="all">全部模块</option>
                      <option v-for="group in groupedPermissions" :key="group.moduleCode" :value="group.moduleCode">{{ group.moduleName }}</option>
                    </select>
                  </label>
                  <fieldset class="grid gap-1.5">
                    <legend class="text-xs font-semibold text-slate-600">显示范围</legend>
                    <div class="inline-flex h-10 rounded-xl border border-slate-200 bg-slate-50 p-1" role="group" aria-label="权限显示范围">
                      <button v-for="option in permissionViewOptions" :key="option.value" type="button" class="rounded-lg px-3 text-xs font-bold transition" :class="permissionViewMode === option.value ? 'bg-white text-emerald-800 shadow-sm' : 'text-slate-500 hover:text-slate-800'" :aria-pressed="permissionViewMode === option.value" @click="permissionViewMode = option.value">{{ option.label }}</button>
                    </div>
                  </fieldset>
                </div>
                <p class="mt-2 text-xs text-slate-500" aria-live="polite">显示 {{ filteredPermissionCount }} / {{ editablePermissionCount }} 项权限，当前已选择 {{ selectedPermissionCodes.length }} 项。</p>
              </header>

              <div v-if="roleAccess.is_protected" class="rounded-2xl border border-amber-200 bg-amber-50 p-3 text-sm leading-6 text-amber-950">
                <div class="flex items-start gap-3">
                  <ShieldCheck class="mt-0.5 size-5 shrink-0 text-amber-700" aria-hidden="true" />
                  <div>
                    <p class="font-bold">超级管理员按系统规则自动拥有全部启用权限</p>
                    <p class="mt-1">下方勾选仅表示角色模板已记录 {{ templatePermissionCount }} 项；实际有效权限为系统已登记的全部 {{ activePermissionCount }} 项。以后新增并启用的权限也会自动包含，无需修改此模板。</p>
                  </div>
                </div>
              </div>

              <div v-if="!canManageRoleTemplates" class="rounded-xl border border-blue-200 bg-blue-50 p-3 text-sm text-blue-800">当前账号可以查看角色模板，但只有集团超级管理员可以提交模板变更。</div>
            </div>

            <div ref="permissionScrollContainer" data-testid="role-permission-scroll-region" role="region" :aria-label="`${roleAccess.name}的权限清单`" tabindex="0" class="grid min-h-0 content-start gap-3 outline-none focus:ring-2 focus:ring-inset focus:ring-emerald-200 xl:overflow-y-auto xl:pr-2">
              <section v-for="group in filteredPermissionGroups" :key="group.moduleCode" class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <div class="mb-3 flex items-start justify-between gap-3">
                  <div><h3 class="font-bold">{{ group.moduleName }}</h3><code class="text-xs text-slate-400">{{ group.moduleCode }}</code></div>
                  <span class="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-bold text-slate-500">{{ group.permissions.length }} 项</span>
                </div>
                <div class="grid gap-2 md:grid-cols-2 2xl:grid-cols-3">
                  <label v-for="permission in group.permissions" :key="permission.code" class="flex min-w-0 items-start gap-3 rounded-xl border p-3 transition" :class="isSelected(permission.code) ? 'border-emerald-200 bg-emerald-50/70' : 'border-slate-200 bg-white'">
                    <input type="checkbox" class="mt-0.5 size-4 accent-emerald-700" :aria-label="`${permissionDisplayLabel(permission)}（${permission.code}）`" :checked="isSelected(permission.code)" :disabled="roleAccess.is_protected || !canManageRoleTemplates || isSaving" @change="togglePermission(permission.code)">
                    <span class="min-w-0 flex-1">
                      <b class="block text-sm text-slate-900">{{ permissionDisplayLabel(permission) }}</b>
                      <code class="block break-all text-xs text-slate-400">{{ permission.code }}</code>
                      <span class="mt-2 flex flex-wrap gap-1.5">
                        <span class="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-bold text-slate-600">{{ permissionAccessKindLabel(permission) }}</span>
                        <span class="rounded-full bg-blue-50 px-2 py-0.5 text-[11px] font-bold text-blue-700">{{ permissionEffectiveScopeLabel(permission) }}</span>
                      </span>
                      <span v-if="permission.description" class="mt-1.5 block text-xs leading-5 text-slate-500">{{ permission.description }}</span>
                      <span v-if="roleAccess.is_protected" class="mt-1 block text-xs font-semibold" :class="isSelected(permission.code) ? 'text-emerald-700' : 'text-amber-700'">{{ isSelected(permission.code) ? '模板已记录' : '系统自动拥有' }}</span>
                    </span>
                    <span v-if="permission.risk_level === 'high'" class="ml-auto inline-flex shrink-0 items-center gap-1 text-xs font-bold text-amber-700"><AlertTriangle class="size-4" aria-hidden="true" />高风险</span>
                  </label>
                </div>
              </section>
              <div v-if="!filteredPermissionGroups.length" class="grid min-h-40 place-items-center rounded-2xl border border-dashed border-slate-300 bg-white p-6 text-center text-sm text-slate-500">当前筛选条件下没有权限。</div>
            </div>

            <section v-if="!roleAccess.is_protected && canManageRoleTemplates" data-testid="role-editor-action-bar" class="grid shrink-0 gap-3 rounded-2xl border border-slate-200 bg-white p-3 shadow-sm xl:grid-cols-[auto_minmax(260px,1fr)_auto] xl:items-end">
              <div class="flex flex-wrap items-center gap-2 text-xs font-bold" aria-live="polite">
                <span class="rounded-full bg-slate-100 px-2.5 py-1.5 text-slate-600">已选 {{ selectedPermissionCodes.length }}</span>
                <span class="rounded-full bg-emerald-50 px-2.5 py-1.5 text-emerald-700">新增 {{ addedPermissionCount }}</span>
                <span class="rounded-full bg-rose-50 px-2.5 py-1.5 text-rose-700">移除 {{ removedPermissionCount }}</span>
                <span class="rounded-full px-2.5 py-1.5" :class="scopeModeChanged ? 'bg-amber-50 text-amber-700' : 'bg-blue-50 text-blue-700'">范围 {{ roleScopeLabel(selectedScopeMode) }}</span>
              </div>
              <label class="grid gap-1.5 text-xs font-semibold text-slate-700">变更原因（必填）<input v-model="reason" class="h-10 rounded-xl border border-slate-200 px-3 text-sm font-normal outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100" placeholder="说明为什么调整此内置职位权限"></label>
              <div class="flex flex-wrap justify-end gap-2">
                <button type="button" class="inline-flex h-10 items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 text-sm font-bold text-slate-700 disabled:opacity-40" :disabled="!hasChanges || isSaving" @click="resetChanges"><RotateCcw class="size-4" />撤销修改</button>
                <button type="button" class="inline-flex h-10 items-center justify-center gap-2 rounded-xl bg-emerald-700 px-5 text-sm font-bold text-white disabled:opacity-50" :disabled="!hasChanges || !reason.trim() || isSaving" @click="previewChanges"><LoaderCircle v-if="isSaving" class="size-4 animate-spin" /><Save v-else class="size-4" />预览职位影响</button>
              </div>
            </section>
          </div>
        </template>
      </section>
    </div>

    <div v-if="preview" class="fixed inset-0 z-50 grid place-items-center bg-slate-950/45 p-4" @click.self="preview = null">
      <section class="w-full min-w-0 max-w-2xl rounded-2xl bg-white shadow-2xl" role="dialog" aria-modal="true" aria-labelledby="role-preview-title">
        <header class="flex items-start justify-between border-b border-slate-200 p-5"><div><h2 id="role-preview-title" class="text-lg font-bold">内置职位影响预览</h2><p class="mt-1 text-sm text-slate-500">将影响 {{ preview.affected_user_count }} 位当前绑定用户。</p></div><button type="button" aria-label="关闭内置职位影响预览" class="rounded-lg p-2 hover:bg-slate-100" @click="preview = null"><X class="size-5" /></button></header>
        <div class="max-h-[55vh] overflow-y-auto p-5">
          <div v-if="preview.before_scope_mode !== preview.after_scope_mode" class="mb-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-950">
            <b class="block">职位数据范围变化</b>
            <span class="mt-1 block font-semibold">{{ roleScopeLabel(preview.before_scope_mode) }} → {{ roleScopeLabel(preview.after_scope_mode) }}</span>
          </div>
          <div v-for="diff in preview.diffs" :key="diff.permission_code" class="flex items-center justify-between gap-4 border-b border-slate-100 py-3 text-sm"><span class="min-w-0"><b class="block text-slate-900">{{ permissionLabels.get(diff.permission_code) || diff.permission_code }}</b><code class="block break-all text-xs text-slate-400">{{ diff.permission_code }}</code></span><span class="shrink-0 font-bold" :class="diff.after ? 'text-emerald-700' : 'text-rose-700'">{{ diff.before ? '已有' : '无' }} → {{ diff.after ? '授予' : '移除' }}</span></div>
          <p v-if="!preview.diffs.length" class="rounded-xl border border-dashed border-slate-200 p-4 text-center text-sm text-slate-500">权限组合未变化，本次仅调整职位数据范围。</p>
          <label v-if="preview.high_risk" class="mt-4 flex gap-3 rounded-xl bg-amber-50 p-3 text-sm text-amber-900"><input v-model="confirmedHighRisk" type="checkbox" class="mt-0.5 size-4 accent-amber-600"><span>我已核对高风险权限、数据范围及全部受影响用户。</span></label>
        </div>
        <footer class="flex justify-end gap-2 border-t border-slate-200 bg-slate-50 p-4"><button class="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-bold" @click="preview = null">返回修改</button><button class="inline-flex items-center gap-2 rounded-xl bg-emerald-700 px-4 py-2 text-sm font-bold text-white disabled:opacity-50" :disabled="isSaving || (preview.high_risk && !confirmedHighRisk)" @click="commitChanges"><CheckCircle2 class="size-4" />确认提交</button></footer>
      </section>
    </div>
  </main>
</template>
