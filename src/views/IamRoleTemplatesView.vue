<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import {
  AlertTriangle,
  CheckCircle2,
  CircleOff,
  Code2,
  LoaderCircle,
  LockKeyhole,
  Search,
  ShieldCheck,
} from '@lucide/vue'
import {
  iamApi,
  type PermissionCatalogItem,
  type RoleAccessResponse,
  type RoleSummary,
} from '@/api/iam'
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
import { getApiErrorMessage } from '@/lib/http'

type PermissionViewMode = 'all' | 'configured'
type DisplayPermission = PermissionCatalogItem & { catalog_missing?: boolean }

const roles = ref<RoleSummary[]>([])
const permissions = ref<PermissionCatalogItem[]>([])
const selectedRoleId = ref('')
const roleAccess = ref<RoleAccessResponse | null>(null)
const roleSearchQuery = ref('')
const permissionSearchQuery = ref('')
const selectedModuleCode = ref('all')
const permissionViewMode = ref<PermissionViewMode>('all')
const permissionViewOptions: Array<{ value: PermissionViewMode; label: string }> = [
  { value: 'all', label: '全部' },
  { value: 'configured', label: '已配置' },
]
const permissionScrollContainer = ref<HTMLElement | null>(null)
const isLoading = ref(false)
const isRoleLoading = ref(false)
const errorMessage = ref('')
let roleAccessRequestSequence = 0

const configuredPermissionCodes = computed(() => new Set(roleAccess.value?.permission_codes ?? []))
const configuredPermissionCount = computed(() => roleAccess.value?.permission_codes.length ?? 0)
const isGeneralManager = computed(() => roleAccess.value?.id === 'position_general_manager')

const allDisplayPermissions = computed<DisplayPermission[]>(() => {
  const knownCodes = new Set(permissions.value.map((permission) => permission.code))
  const missingItems = [...configuredPermissionCodes.value]
    .filter((code) => !knownCodes.has(code))
    .map<DisplayPermission>((code, index) => ({
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
    }))

  return [...permissions.value, ...missingItems]
    .sort((left, right) => left.sort_order - right.sort_order || left.code.localeCompare(right.code))
})

const permissionModuleOptions = computed(() => {
  const groups = new Map<string, string>()
  allDisplayPermissions.value.forEach((permission) => groups.set(permission.module_code, permission.module_name))
  return [...groups.entries()].map(([moduleCode, moduleName]) => ({ moduleCode, moduleName }))
})

const filteredPermissionGroups = computed(() => {
  const query = permissionSearchQuery.value.trim().toLocaleLowerCase('zh-CN')
  const groups = new Map<string, { moduleName: string; permissions: DisplayPermission[] }>()

  allDisplayPermissions.value
    .filter((permission) => selectedModuleCode.value === 'all' || permission.module_code === selectedModuleCode.value)
    .filter((permission) => permissionViewMode.value === 'all' || configuredPermissionCodes.value.has(permission.code))
    .filter((permission) => !query || [
      permissionDisplayLabel(permission),
      permission.code,
      permission.module_name,
      permission.module_code,
      permission.description ?? '',
    ].some((value) => value.toLocaleLowerCase('zh-CN').includes(query)))
    .forEach((permission) => {
      const group = groups.get(permission.module_code)
      if (group) group.permissions.push(permission)
      else groups.set(permission.module_code, {
        moduleName: permission.module_name,
        permissions: [permission],
      })
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

const visibleSystemPositionCount = computed(() => visibleSystemPositionGroups.value
  .reduce((total, group) => total + group.roles.length, 0))
const filteredPermissionCount = computed(() => filteredPermissionGroups.value
  .reduce((total, group) => total + group.permissions.length, 0))
const roleDataScopeSummary = computed(() => isGeneralManager.value
  ? '跨厂操作 · 全业务部门'
  : roleScopeModeLabel(roleAccess.value?.scope_mode))

function isConfigured(permissionCode: string) {
  return configuredPermissionCodes.value.has(permissionCode)
}

function roleSourceLabel(source?: string) {
  return source === 'code' ? '代码固定' : '数据库配置'
}

async function loadRoleAccess(roleId: string, resetPermissionScroll = true) {
  const requestSequence = ++roleAccessRequestSequence
  selectedRoleId.value = roleId
  isRoleLoading.value = true
  errorMessage.value = ''
  try {
    const result = await iamApi.getRoleAccess(roleId)
    if (requestSequence !== roleAccessRequestSequence) return false
    roleAccess.value = result
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
  if (!roleId || (roleId === selectedRoleId.value && roleAccess.value?.id === roleId)) return true
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
    const [roleItems, permissionItems] = await Promise.all([
      iamApi.listSystemPositions(),
      iamApi.listPermissions('all'),
    ])
    roles.value = roleItems
    permissions.value = permissionItems
    if (roleItems.length) await loadRoleAccess(roleItems[0].id)
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    isLoading.value = false
  }
}

onMounted(() => void loadData())
</script>

<template>
  <main class="min-h-screen overflow-x-clip bg-slate-100 text-slate-950 xl:flex xl:h-dvh xl:min-h-0 xl:flex-col xl:overflow-hidden">
    <IamNavigation
      data-testid="role-templates-sticky-navigation"
      class="sticky top-0 z-30 shadow-sm xl:static xl:shrink-0"
      title="内置职位权限"
      subtitle="内置职位由系统代码固定维护；管理员可以查看，但不能在线修改。"
    />

    <div data-testid="role-viewer-workspace" class="mx-auto grid min-w-0 max-w-[1480px] gap-4 px-4 py-5 sm:px-5 xl:min-h-0 xl:w-full xl:flex-1 xl:grid-cols-[300px_minmax(0,1fr)] xl:px-8 xl:py-4">
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
            <button
              v-for="role in group.roles"
              :key="role.id"
              type="button"
              class="mt-1 w-full min-w-0 rounded-xl px-3 py-2.5 text-left transition focus:outline-none focus:ring-2 focus:ring-emerald-300 disabled:cursor-wait disabled:opacity-60"
              :class="selectedRoleId === role.id ? 'bg-emerald-50 text-emerald-900' : 'hover:bg-slate-50'"
              :aria-pressed="selectedRoleId === role.id"
              :aria-current="selectedRoleId === role.id ? 'true' : undefined"
              @click="requestRoleChange(role.id)"
            >
              <span class="flex min-w-0 items-center gap-2">
                <b class="min-w-0 flex-1 truncate text-sm">{{ role.name }}</b>
                <span class="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-bold text-slate-600">{{ roleScopeModeLabel(role.scope_mode) }}</span>
                <LockKeyhole v-if="role.scope_mode_locked" class="size-4 shrink-0 text-emerald-700" aria-label="数据范围由代码锁定" />
              </span>
              <span class="mt-1 block text-xs text-slate-500">已包含 {{ role.permission_count }} 项权限 · {{ role.binding_count }} 位用户</span>
            </button>
          </section>
          <p v-if="!visibleSystemPositionGroups.length && !isLoading" class="p-4 text-center text-sm text-slate-500">没有匹配的内置职位。</p>
        </div>
      </aside>

      <section class="min-w-0 xl:flex xl:min-h-0 xl:flex-col">
        <label class="mb-4 grid gap-1.5 text-sm font-semibold text-slate-700 xl:hidden">
          选择内置职位
          <select :value="selectedRoleId" class="h-11 rounded-xl border border-slate-200 bg-white px-3 outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100" @change="handleMobileRoleSelect">
            <optgroup v-for="group in groupedSystemPositions" :key="group.department" :label="group.name">
              <option v-for="role in group.roles" :key="role.id" :value="role.id">{{ role.name }} · {{ roleScopeModeLabel(role.scope_mode) }}（{{ role.permission_count }} 项权限）</option>
            </optgroup>
          </select>
        </label>

        <div v-if="errorMessage" role="alert" class="mb-3 shrink-0 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">{{ errorMessage }}</div>
        <div v-if="isLoading || isRoleLoading || !roleAccess" class="grid min-h-64 flex-1 place-items-center rounded-2xl border border-slate-200 bg-white">
          <LoaderCircle v-if="isLoading || isRoleLoading" class="size-7 animate-spin text-emerald-700" />
          <p v-else class="text-sm text-slate-500">当前没有可查看的内置职位。</p>
        </div>

        <template v-else>
          <div data-testid="role-viewer-panel" class="grid min-h-0 gap-3 xl:flex-1 xl:grid-rows-[auto_minmax(0,1fr)]">
            <header class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <div class="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 class="text-xl font-bold">{{ roleAccess.name }}</h2>
                  <p class="mt-1 text-sm text-slate-500">{{ roleAccess.position_department_name }} · {{ roleAccess.description || roleAccess.code }}</p>
                </div>
                <span class="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1.5 text-xs font-bold text-emerald-800">
                  <LockKeyhole class="size-3.5" aria-hidden="true" />代码固定 · 不可在线修改
                </span>
              </div>

              <dl data-testid="fixed-role-metadata" class="mt-4 grid gap-2 border-t border-slate-100 pt-4 sm:grid-cols-2 xl:grid-cols-3">
                <div class="rounded-xl bg-slate-50 p-3">
                  <dt class="text-xs font-semibold text-slate-500">权限来源</dt>
                  <dd class="mt-1 font-bold text-slate-900">{{ roleSourceLabel(roleAccess.source) }}</dd>
                </div>
                <div class="rounded-xl bg-slate-50 p-3">
                  <dt class="text-xs font-semibold text-slate-500">数据范围</dt>
                  <dd class="mt-1 font-bold text-slate-900">{{ roleDataScopeSummary }}</dd>
                  <p class="mt-1 text-xs leading-5 text-slate-500">{{ roleScopeModeDescription(roleAccess.scope_mode) }}</p>
                </div>
                <div class="rounded-xl bg-slate-50 p-3">
                  <dt class="text-xs font-semibold text-slate-500">修改方式</dt>
                  <dd class="mt-1 text-sm font-bold leading-5 text-slate-900">提交明确需求，由代码变更和发布生效</dd>
                </div>
                <div class="rounded-xl bg-slate-50 p-3">
                  <dt class="text-xs font-semibold text-slate-500">定义版本</dt>
                  <dd class="mt-1 font-mono text-sm font-bold text-slate-900">{{ roleAccess.definition_version || '待同步' }}</dd>
                </div>
                <div class="min-w-0 rounded-xl bg-slate-50 p-3 sm:col-span-2">
                  <dt class="text-xs font-semibold text-slate-500">定义哈希</dt>
                  <dd class="mt-1 break-all font-mono text-xs font-bold text-slate-700">{{ roleAccess.definition_hash || '待同步' }}</dd>
                </div>
              </dl>

              <div v-if="isGeneralManager" data-testid="general-manager-boundary" class="mt-3 flex items-start gap-3 rounded-xl border border-blue-200 bg-blue-50 p-3 text-sm text-blue-950">
                <ShieldCheck class="mt-0.5 size-5 shrink-0 text-blue-700" aria-hidden="true" />
                <div><b>跨厂操作 · 全业务部门</b><p class="mt-1 text-blue-800">不包含账号与权限管理；业务状态、审批隔离、版本校验和审计规则仍然生效。</p></div>
              </div>

              <div class="mt-4 grid gap-3 border-t border-slate-100 pt-4 lg:grid-cols-[minmax(0,1fr)_210px_auto] lg:items-end">
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
                    <option v-for="group in permissionModuleOptions" :key="group.moduleCode" :value="group.moduleCode">{{ group.moduleName }}</option>
                  </select>
                </label>
                <fieldset class="grid gap-1.5">
                  <legend class="text-xs font-semibold text-slate-600">显示范围</legend>
                  <div class="inline-flex h-10 rounded-xl border border-slate-200 bg-slate-50 p-1" role="group" aria-label="权限显示范围">
                    <button v-for="option in permissionViewOptions" :key="option.value" type="button" class="rounded-lg px-3 text-xs font-bold transition" :class="permissionViewMode === option.value ? 'bg-white text-emerald-800 shadow-sm' : 'text-slate-500 hover:text-slate-800'" :aria-pressed="permissionViewMode === option.value" @click="permissionViewMode = option.value">{{ option.label }}</button>
                  </div>
                </fieldset>
              </div>
              <p class="mt-2 text-xs text-slate-500" aria-live="polite">显示 {{ filteredPermissionCount }} / {{ allDisplayPermissions.length }} 项权限；此职位固定包含 {{ configuredPermissionCount }} 项。</p>
            </header>

            <div ref="permissionScrollContainer" data-testid="role-permission-scroll-region" role="region" :aria-label="`${roleAccess.name}的权限清单`" tabindex="0" class="grid min-h-0 content-start gap-3 outline-none focus:ring-2 focus:ring-inset focus:ring-emerald-200 xl:overflow-y-auto xl:pr-2">
              <section v-for="group in filteredPermissionGroups" :key="group.moduleCode" class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <div class="mb-3 flex items-start justify-between gap-3">
                  <div><h3 class="font-bold">{{ group.moduleName }}</h3><code class="text-xs text-slate-400">{{ group.moduleCode }}</code></div>
                  <span class="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-bold text-slate-500">{{ group.permissions.length }} 项</span>
                </div>
                <div class="grid gap-2 md:grid-cols-2 2xl:grid-cols-3">
                  <article
                    v-for="permission in group.permissions"
                    :key="permission.code"
                    class="flex min-w-0 items-start gap-3 rounded-xl border p-3"
                    :class="[
                      permission.catalog_missing ? 'border-rose-300 bg-rose-50' : isConfigured(permission.code) ? 'border-emerald-200 bg-emerald-50/70' : 'border-slate-200 bg-white',
                    ]"
                  >
                    <CheckCircle2 v-if="isConfigured(permission.code)" class="mt-0.5 size-4 shrink-0 text-emerald-600" aria-hidden="true" />
                    <CircleOff v-else class="mt-0.5 size-4 shrink-0 text-slate-300" aria-hidden="true" />
                    <div class="min-w-0 flex-1">
                      <div class="flex items-start justify-between gap-2">
                        <span class="min-w-0">
                          <b class="block text-sm text-slate-900">{{ permissionDisplayLabel(permission) }}</b>
                          <code class="block break-all text-xs text-slate-400">{{ permission.code }}</code>
                        </span>
                        <span class="shrink-0 rounded-full px-2 py-0.5 text-[11px] font-bold" :class="isConfigured(permission.code) ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-500'">{{ isConfigured(permission.code) ? '已包含' : '未包含' }}</span>
                      </div>
                      <div class="mt-2 flex flex-wrap gap-1.5">
                        <span class="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-bold text-slate-600">{{ permission.module_name }}</span>
                        <span class="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-bold text-slate-600">{{ permissionAccessKindLabel(permission.access_kind) }}</span>
                        <span class="rounded-full bg-blue-50 px-2 py-0.5 text-[11px] font-bold text-blue-700">{{ permissionEffectiveScopeLabel(permission, roleAccess.scope_mode) }}</span>
                        <span class="rounded-full px-2 py-0.5 text-[11px] font-bold" :class="permission.risk_level === 'high' ? 'bg-amber-50 text-amber-700' : 'bg-slate-100 text-slate-600'">{{ permissionRiskLabel(permission.risk_level) }}</span>
                        <span class="rounded-full px-2 py-0.5 text-[11px] font-bold" :class="permission.status === 'inactive' ? 'bg-rose-50 text-rose-700' : 'bg-emerald-50 text-emerald-700'">{{ permissionStatusLabel(permission.status) }}</span>
                      </div>
                      <p class="mt-1.5 text-xs leading-5 text-slate-500">{{ permission.description || '暂无说明。' }}</p>
                      <p v-if="permission.scope_guidance" class="mt-1 text-xs leading-5 text-slate-400">范围说明：{{ permission.scope_guidance }}</p>
                      <p v-if="permission.catalog_missing" class="mt-1 inline-flex items-start gap-1 text-xs font-semibold text-rose-700"><AlertTriangle class="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />权限目录缺失，当前定义异常。</p>
                    </div>
                  </article>
                </div>
              </section>
              <div v-if="!filteredPermissionGroups.length" class="grid min-h-40 place-items-center rounded-2xl border border-dashed border-slate-300 bg-white p-6 text-center text-sm text-slate-500"><Code2 class="mb-2 size-5 text-slate-300" aria-hidden="true" />当前筛选条件下没有权限。</div>
            </div>
          </div>
        </template>
      </section>
    </div>
  </main>
</template>
