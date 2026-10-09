<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  CheckCircle2,
  CircleOff,
  Code2,
  Copy,
  Info,
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
import IamDialogSurface from '@/components/iam/workspace/IamDialogSurface.vue'
import IamDisclosure from '@/components/iam/workspace/IamDisclosure.vue'
import IamNavigation from '@/components/iam/IamNavigation.vue'
import {
  permissionAccessKindLabel,
  permissionDisplayLabel,
  permissionEffectiveScopeLabel,
  roleScopeModeDescription,
  roleScopeModeLabel,
} from '@/components/iam/permissionCatalogLabels'
import { getApiErrorMessage } from '@/lib/http'
import { useAuthStore } from '@/stores/auth'

type PermissionViewMode = 'all' | 'configured'
type DisplayPermission = PermissionCatalogItem & { catalog_missing?: boolean }

const authStore = useAuthStore()
const roles = ref<RoleSummary[]>([])
const permissions = ref<PermissionCatalogItem[]>([])
const selectedRoleId = ref('')
const roleAccess = ref<RoleAccessResponse | null>(null)
const roleSearchQuery = ref('')
const permissionSearchQuery = ref('')
const selectedModuleCode = ref('all')
const permissionViewMode = ref<PermissionViewMode>('configured')
const permissionViewOptions: Array<{ value: PermissionViewMode; label: string }> = [
  { value: 'configured', label: '已包含' },
  { value: 'all', label: '全部权限' },
]
const permissionScrollContainer = ref<HTMLElement | null>(null)
const definitionDetailsTrigger = ref<HTMLButtonElement | null>(null)
const showDefinitionDetails = ref(false)
const definitionCopyFeedback = ref('')
const expandedPermissionCodes = ref(new Set<string>())
const isLoading = ref(false)
const isRoleLoading = ref(false)
const errorMessage = ref('')
let roleAccessRequestSequence = 0

const canReadPermissionCatalog = computed(() => authStore.can('system:permission_catalog_read'))
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

  return [...permissions.value, ...missingItems].sort(
    (left, right) => left.sort_order - right.sort_order || left.code.localeCompare(right.code),
  )
})

const permissionModuleOptions = computed(() => {
  const groups = new Map<string, string>()
  allDisplayPermissions.value.forEach((permission) =>
    groups.set(permission.module_code, permission.module_name),
  )
  return [...groups.entries()].map(([moduleCode, moduleName]) => ({ moduleCode, moduleName }))
})

const permissionCoverageByModule = computed(() => {
  const coverage = new Map<string, { configured: number; total: number }>()
  allDisplayPermissions.value.forEach((permission) => {
    const current = coverage.get(permission.module_code) ?? { configured: 0, total: 0 }
    current.total += 1
    if (configuredPermissionCodes.value.has(permission.code)) current.configured += 1
    coverage.set(permission.module_code, current)
  })
  return coverage
})

const filteredPermissionGroups = computed(() => {
  const query = permissionSearchQuery.value.trim().toLocaleLowerCase('zh-CN')
  const groups = new Map<string, { moduleName: string; permissions: DisplayPermission[] }>()

  allDisplayPermissions.value
    .filter(
      (permission) =>
        selectedModuleCode.value === 'all' || permission.module_code === selectedModuleCode.value,
    )
    .filter(
      (permission) =>
        permissionViewMode.value === 'all' || configuredPermissionCodes.value.has(permission.code),
    )
    .filter(
      (permission) =>
        !query ||
        [
          permissionDisplayLabel(permission),
          permission.code,
          permission.module_name,
          permission.module_code,
          permission.description ?? '',
        ].some((value) => value.toLocaleLowerCase('zh-CN').includes(query)),
    )
    .forEach((permission) => {
      const group = groups.get(permission.module_code)
      if (group) group.permissions.push(permission)
      else
        groups.set(permission.module_code, {
          moduleName: permission.module_name,
          permissions: [permission],
        })
    })

  return [...groups.entries()].map(([moduleCode, value]) => ({
    moduleCode,
    ...value,
    configuredCount: permissionCoverageByModule.value.get(moduleCode)?.configured ?? 0,
    totalCount: permissionCoverageByModule.value.get(moduleCode)?.total ?? value.permissions.length,
  }))
})

const groupedSystemPositions = computed(() => {
  const groups = new Map<string, { department: string; name: string; roles: RoleSummary[] }>()
  const sortedRoles = [...roles.value].sort(
    (left, right) =>
      left.position_sort_order - right.position_sort_order ||
      left.name.localeCompare(right.name, 'zh-CN'),
  )

  sortedRoles.forEach((role) => {
    const department = role.position_department || 'other'
    const group = groups.get(department)
    if (group) group.roles.push(role)
    else
      groups.set(department, {
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
      roles: group.roles.filter((role) =>
        [group.name, role.name, role.description, role.code].some((value) =>
          value?.toLocaleLowerCase('zh-CN').includes(query),
        ),
      ),
    }))
    .filter((group) => group.roles.length)
})

const visibleSystemPositionCount = computed(() =>
  visibleSystemPositionGroups.value.reduce((total, group) => total + group.roles.length, 0),
)
const filteredPermissionCount = computed(() =>
  filteredPermissionGroups.value.reduce((total, group) => total + group.permissions.length, 0),
)
const roleDataScopeSummary = computed(() =>
  isGeneralManager.value
    ? '跨厂操作 · 全业务部门'
    : roleScopeModeLabel(roleAccess.value?.scope_mode),
)
const hasPermissionFilters = computed(() =>
  Boolean(permissionSearchQuery.value.trim() || selectedModuleCode.value !== 'all'),
)

function isConfigured(permissionCode: string) {
  return configuredPermissionCodes.value.has(permissionCode)
}

function roleSourceLabel(source?: string) {
  return source === 'code' ? '代码固定' : '数据库配置'
}

function clearPermissionFilters() {
  permissionSearchQuery.value = ''
  selectedModuleCode.value = 'all'
}

async function openDefinitionDetails() {
  showDefinitionDetails.value = true
  definitionCopyFeedback.value = ''
  await nextTick()
}

async function copyDefinitionHash() {
  const hash = roleAccess.value?.definition_hash
  if (!hash) return
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(hash)
    } else {
      const textarea = document.createElement('textarea')
      textarea.value = hash
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      textarea.remove()
    }
    definitionCopyFeedback.value = '已复制定义哈希'
  } catch {
    definitionCopyFeedback.value = '复制失败，请手动复制'
  }
}

async function loadRoleAccess(roleId: string, resetPermissionScroll = true) {
  if (!canReadPermissionCatalog.value) return false
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
      clearPermissionFilters()
      expandedPermissionCodes.value = new Set()
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
  if (!canReadPermissionCatalog.value) {
    roles.value = []
    permissions.value = []
    selectedRoleId.value = ''
    roleAccess.value = null
    isLoading.value = false
    isRoleLoading.value = false
    errorMessage.value = ''
    return
  }
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

onMounted(() => {
  void loadData()
})
onBeforeUnmount(() => {
  ++roleAccessRequestSequence
})
</script>

<template>
  <section class="iamx-role-page">
    <IamNavigation
      data-testid="role-templates-sticky-navigation"
      compact
      appearance="portal"
      class="iam-navigation sticky top-0 z-30 shrink-0 shadow-[0_1px_2px_rgba(15,23,42,0.04)]"
      title="内置职位权限"
      subtitle="查看系统内置职位的权限范围与定义状态。"
    />

    <section
      v-if="!canReadPermissionCatalog"
      data-testid="role-catalog-protected-notice"
      role="status"
      class="mx-auto mt-5 flex w-[calc(100%-2rem)] max-w-[1568px] items-start gap-3 rounded-[14px] border border-slate-300 bg-white p-5 text-sm text-slate-700 shadow-[0_1px_2px_rgba(15,23,42,0.04)]"
    >
      <span
        class="grid size-10 shrink-0 place-items-center rounded-xl bg-emerald-50 text-emerald-700"
        ><LockKeyhole class="size-5" aria-hidden="true"
      /></span>
      <div>
        <h2 class="font-bold text-slate-950">页面可访问 · 权限目录受保护</h2>
        <p class="mt-1 leading-6 text-slate-500">
          当前账号没有权限目录查看权限。内置职位及其权限定义不会在此模式下读取或展示；此页面本身没有在线修改入口。
        </p>
      </div>
    </section>

    <div v-else data-testid="role-viewer-workspace" class="iamx-role-layout">
      <aside
        data-testid="role-directory-panel"
        class="iam-directory-panel hidden min-w-0 overflow-hidden rounded-[14px] border border-slate-200 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04),0_4px_12px_rgba(15,23,42,0.03)] xl:flex xl:flex-col"
      >
        <div class="shrink-0 border-b border-slate-100 p-3">
          <div class="flex items-center justify-between gap-3 px-1 py-1">
            <h2 class="text-sm font-bold text-slate-900">内置职位目录</h2>
            <span class="text-xs font-semibold text-slate-400">{{ roles.length }} 个职位</span>
          </div>
          <label class="mt-2 grid gap-1.5 text-xs font-semibold text-slate-600">
            搜索职位
            <span class="relative block">
              <Search
                class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400"
                aria-hidden="true"
              />
              <input
                v-model="roleSearchQuery"
                type="search"
                class="h-9 w-full rounded-[10px] border border-slate-200 pl-9 pr-3 text-[13px] font-normal outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
                placeholder="部门、职位或代码"
              />
            </span>
          </label>
          <p class="mt-2 px-1 text-xs text-slate-500" aria-live="polite">
            显示 {{ visibleSystemPositionCount }} / {{ roles.length }} 个职位
          </p>
        </div>

        <div
          data-testid="role-directory-scroll-region"
          role="region"
          aria-label="内置职位目录"
          tabindex="0"
          class="iam-directory-scroll min-h-0 flex-1 p-2.5 outline-none focus:ring-2 focus:ring-inset focus:ring-emerald-200"
        >
          <section
            v-for="group in visibleSystemPositionGroups"
            :key="group.department"
            class="mt-2 border-t border-slate-100 pt-2 first:mt-0 first:border-t-0"
          >
            <h3
              class="sticky top-0 z-10 -mx-0.5 bg-white/95 px-2.5 py-1.5 text-[11px] font-bold uppercase tracking-[0.08em] text-slate-400 backdrop-blur"
            >
              {{ group.name }}
            </h3>
            <button
              v-for="role in group.roles"
              :key="role.id"
              type="button"
              class="relative mt-1 w-full min-w-0 rounded-[10px] border border-transparent px-3 py-2.5 text-left transition focus:outline-none focus:ring-2 focus:ring-emerald-300 disabled:cursor-wait disabled:opacity-60"
              :class="
                selectedRoleId === role.id
                  ? 'border-emerald-100 bg-[#f0fdfa] text-emerald-950 shadow-[inset_3px_0_0_#0f766e]'
                  : 'hover:border-slate-100 hover:bg-slate-50'
              "
              :aria-pressed="selectedRoleId === role.id"
              :aria-current="selectedRoleId === role.id ? 'true' : undefined"
              @click="requestRoleChange(role.id)"
            >
              <span class="flex min-w-0 items-center gap-2">
                <b class="min-w-0 flex-1 truncate text-sm">{{ role.name }}</b>
                <LockKeyhole
                  v-if="role.scope_mode_locked"
                  class="size-4 shrink-0 text-emerald-700"
                  aria-label="数据范围由代码锁定"
                />
              </span>
              <span class="mt-1 block truncate text-[11px] text-slate-500"
                >{{ roleScopeModeLabel(role.scope_mode) }} · {{ role.permission_count }} 项权限 ·
                {{ role.binding_count }} 条绑定</span
              >
            </button>
          </section>
          <p
            v-if="!visibleSystemPositionGroups.length && !isLoading"
            class="p-4 text-center text-sm text-slate-500"
          >
            没有匹配的内置职位。
          </p>
        </div>
      </aside>

      <section class="iamx-role-content">
        <label class="mb-4 grid gap-1.5 text-sm font-semibold text-slate-700 xl:hidden">
          选择内置职位
          <select
            :value="selectedRoleId"
            class="h-10 rounded-[10px] border border-slate-200 bg-white px-3 outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
            @change="handleMobileRoleSelect"
          >
            <optgroup
              v-for="group in groupedSystemPositions"
              :key="group.department"
              :label="group.name"
            >
              <option v-for="role in group.roles" :key="role.id" :value="role.id">
                {{ role.name }} · {{ roleScopeModeLabel(role.scope_mode) }}（{{
                  role.permission_count
                }}
                项权限）
              </option>
            </optgroup>
          </select>
        </label>

        <div
          v-if="errorMessage"
          role="alert"
          class="mb-3 shrink-0 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800"
        >
          {{ errorMessage }}
        </div>
        <div
          v-if="isLoading || isRoleLoading || !roleAccess"
          class="min-h-64 flex-1 rounded-[14px] border border-slate-200 bg-white p-5 shadow-[0_1px_2px_rgba(15,23,42,0.04)]"
        >
          <div
            v-if="isLoading || isRoleLoading"
            class="animate-pulse space-y-4"
            aria-label="正在加载职位权限"
          >
            <div class="h-6 w-40 rounded bg-slate-200" />
            <div class="h-4 w-2/3 rounded bg-slate-100" />
            <div class="grid gap-3 border-t border-slate-100 pt-4 sm:grid-cols-4">
              <div v-for="index in 4" :key="index" class="h-12 rounded bg-slate-100" />
            </div>
            <div class="h-14 rounded bg-slate-100" />
            <div class="grid gap-3 md:grid-cols-2">
              <div
                v-for="index in 4"
                :key="`permission-${index}`"
                class="h-28 rounded bg-slate-100"
              />
            </div>
          </div>
          <p v-else class="text-sm text-slate-500">当前没有可查看的内置职位。</p>
        </div>

        <template v-else>
          <div data-testid="role-viewer-panel" class="iam-viewer-panel grid min-h-0 gap-3">
            <header
              data-testid="role-summary-panel"
              class="shrink-0 rounded-[14px] border border-slate-200 bg-white px-5 py-4 shadow-[0_1px_2px_rgba(15,23,42,0.04),0_4px_12px_rgba(15,23,42,0.03)]"
            >
              <div class="flex flex-wrap items-start justify-between gap-3">
                <div class="min-w-0 flex-1">
                  <div class="flex flex-wrap items-center gap-2">
                    <h2 class="text-xl font-bold tracking-tight text-slate-950">
                      {{ roleAccess.name }}
                    </h2>
                    <span
                      class="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-bold text-emerald-800"
                    >
                      <LockKeyhole class="size-3" aria-hidden="true" />代码固定 · 只读
                    </span>
                  </div>
                  <p class="mt-1 truncate text-[13px] text-slate-500">
                    {{ roleAccess.position_department_name }} ·
                    {{ roleAccess.description || roleAccess.code }}
                  </p>
                </div>
                <button
                  ref="definitionDetailsTrigger"
                  data-testid="definition-details-trigger"
                  type="button"
                  class="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-[10px] border border-slate-200 bg-white px-3 text-xs font-bold text-slate-700 transition hover:border-emerald-200 hover:text-emerald-800 focus:outline-none focus:ring-2 focus:ring-emerald-200"
                  @click="openDefinitionDetails"
                >
                  <Info class="size-3.5" aria-hidden="true" />查看定义信息
                </button>
              </div>

              <dl
                data-testid="fixed-role-metadata"
                class="mt-3 grid grid-cols-2 gap-x-4 gap-y-3 border-t border-slate-100 pt-3 sm:grid-cols-4"
              >
                <div class="min-w-0">
                  <dt class="text-[11px] font-semibold text-slate-400">数据范围</dt>
                  <dd class="mt-0.5 truncate text-[13px] font-bold text-slate-800">
                    {{ roleDataScopeSummary }}
                  </dd>
                </div>
                <div class="min-w-0">
                  <dt class="text-[11px] font-semibold text-slate-400">已包含权限</dt>
                  <dd class="mt-0.5 text-[13px] font-bold text-slate-800">
                    {{ configuredPermissionCount }} 项
                  </dd>
                </div>
                <div class="min-w-0">
                  <dt class="text-[11px] font-semibold text-slate-400">授权绑定</dt>
                  <dd class="mt-0.5 text-[13px] font-bold text-slate-800">
                    {{ roleAccess.binding_count }} 条
                  </dd>
                </div>
                <div class="min-w-0">
                  <dt class="text-[11px] font-semibold text-slate-400">定义版本</dt>
                  <dd class="mt-0.5 truncate font-mono text-xs font-bold text-slate-700">
                    {{ roleAccess.definition_version || '待同步' }}
                  </dd>
                </div>
              </dl>

              <div
                v-if="isGeneralManager"
                data-testid="general-manager-boundary"
                class="mt-3 flex items-start gap-2 rounded-[10px] border border-blue-100 bg-blue-50/70 px-3 py-2 text-xs text-blue-950"
              >
                <ShieldCheck class="mt-0.5 size-4 shrink-0 text-blue-700" aria-hidden="true" />
                <p>
                  <b>跨厂操作 · 全业务部门。</b>
                  不包含账号与权限管理；业务状态、审批隔离、版本校验和审计规则仍然生效。
                </p>
              </div>
            </header>

            <section
              data-testid="permission-filter-toolbar"
              aria-label="权限筛选工具栏"
              class="iam-toolbar shrink-0 rounded-[14px] border border-slate-200 bg-white/95 p-3 shadow-[0_1px_2px_rgba(15,23,42,0.04)] backdrop-blur"
            >
              <div class="grid gap-2.5 lg:grid-cols-[minmax(260px,1fr)_190px_auto] lg:items-center">
                <label class="relative block">
                  <span class="sr-only">搜索权限</span>
                  <Search
                    class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400"
                    aria-hidden="true"
                  />
                  <input
                    v-model="permissionSearchQuery"
                    type="search"
                    class="h-10 w-full rounded-[10px] border border-slate-200 bg-white pl-9 pr-3 text-[13px] outline-none transition focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
                    placeholder="搜索权限名称、模块或代码"
                  />
                </label>
                <label>
                  <span class="sr-only">权限模块</span>
                  <select
                    v-model="selectedModuleCode"
                    class="h-10 w-full rounded-[10px] border border-slate-200 bg-white px-3 text-[13px] outline-none transition focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
                  >
                    <option value="all">全部模块</option>
                    <option
                      v-for="group in permissionModuleOptions"
                      :key="group.moduleCode"
                      :value="group.moduleCode"
                    >
                      {{ group.moduleName }}
                    </option>
                  </select>
                </label>
                <div
                  class="flex min-w-0 flex-wrap items-center justify-between gap-2 lg:justify-end"
                >
                  <div
                    class="inline-flex h-10 rounded-[10px] border border-slate-200 bg-slate-50 p-1"
                    role="group"
                    aria-label="权限显示范围"
                  >
                    <button
                      v-for="option in permissionViewOptions"
                      :key="option.value"
                      type="button"
                      class="rounded-[7px] px-3 text-xs font-bold transition"
                      :class="
                        permissionViewMode === option.value
                          ? 'bg-white text-emerald-800 shadow-sm'
                          : 'text-slate-500 hover:text-slate-800'
                      "
                      :aria-pressed="permissionViewMode === option.value"
                      @click="permissionViewMode = option.value"
                    >
                      {{ option.label }}
                      {{
                        option.value === 'configured'
                          ? configuredPermissionCount
                          : allDisplayPermissions.length
                      }}
                    </button>
                  </div>
                  <button
                    v-if="hasPermissionFilters"
                    type="button"
                    class="h-9 rounded-[9px] px-2.5 text-xs font-bold text-slate-500 transition hover:bg-slate-100 hover:text-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-200"
                    @click="clearPermissionFilters"
                  >
                    清除筛选
                  </button>
                  <p class="w-full text-xs text-slate-500 lg:w-auto" aria-live="polite">
                    显示 {{ filteredPermissionCount }} / {{ allDisplayPermissions.length }} 项
                  </p>
                </div>
              </div>
            </section>

            <div
              ref="permissionScrollContainer"
              data-testid="role-permission-scroll-region"
              role="region"
              :aria-label="`${roleAccess.name}的权限清单`"
              tabindex="0"
              class="iam-permission-list grid min-h-0 content-start gap-3 outline-none focus:ring-2 focus:ring-inset focus:ring-emerald-200"
            >
              <section
                v-for="group in filteredPermissionGroups"
                :key="group.moduleCode"
                class="rounded-[14px] border border-slate-200 bg-white p-3 shadow-[0_1px_2px_rgba(15,23,42,0.04)]"
              >
                <div class="mb-2.5 flex items-center justify-between gap-3 px-1">
                  <div class="min-w-0">
                    <h3 class="truncate text-[15px] font-bold text-slate-900">
                      {{ group.moduleName }}
                    </h3>
                    <code class="block truncate text-[11px] text-slate-400">{{
                      group.moduleCode
                    }}</code>
                  </div>
                  <span
                    class="shrink-0 rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-bold text-slate-500"
                    >已包含 {{ group.configuredCount }} / 共 {{ group.totalCount }} 项</span
                  >
                </div>
                <div class="iamx-permission-rows">
                  <article
                    v-for="permission in group.permissions"
                    :key="permission.code"
                    class="iamx-permission-row"
                    :class="{
                      'iamx-permission-alert':
                        permission.catalog_missing || permission.status === 'inactive',
                    }"
                  >
                    <div class="iamx-permission-line">
                      <span class="iamx-permission-name"
                        ><CheckCircle2 v-if="isConfigured(permission.code)" :size="16" /><CircleOff
                          v-else
                          :size="16"
                        /><strong>{{ permissionDisplayLabel(permission) }}</strong></span
                      ><span>{{ permissionAccessKindLabel(permission.access_kind) }}</span
                      ><span>{{
                        permissionEffectiveScopeLabel(permission, roleAccess.scope_mode)
                      }}</span
                      ><small>{{ isConfigured(permission.code) ? '已包含' : '未包含' }}</small>
                    </div>
                    <p
                      v-if="
                        permission.risk_level === 'high' ||
                        permission.status === 'inactive' ||
                        permission.catalog_missing
                      "
                      class="iamx-permission-warning"
                    >
                      {{ permission.catalog_missing ? '定义异常：权限目录缺失。' : '' }}
                      {{ permission.risk_level === 'high' ? '高风险权限' : '' }}
                      {{ permission.status === 'inactive' ? '当前未启用' : '' }}
                    </p>
                    <IamDisclosure title="说明与权限代码"
                      ><code>{{ permission.code }}</code>
                      <p>{{ permission.description || '暂无说明。' }}</p>
                      <p v-if="permission.scope_guidance">
                        范围说明：{{ permission.scope_guidance }}
                      </p></IamDisclosure
                    >
                  </article>
                </div>
              </section>
              <div
                v-if="!filteredPermissionGroups.length"
                class="grid min-h-40 place-items-center rounded-[14px] border border-dashed border-slate-300 bg-white p-6 text-center text-sm text-slate-500"
              >
                <div>
                  <Code2 class="mx-auto mb-2 size-5 text-slate-300" aria-hidden="true" />
                  <b class="block text-slate-700">没有找到匹配的权限</b>
                  <p class="mt-1 text-xs">请尝试更换关键词、权限模块或显示范围。</p>
                  <button
                    v-if="hasPermissionFilters"
                    type="button"
                    class="mt-3 rounded-[9px] border border-slate-200 px-3 py-2 text-xs font-bold text-slate-700 hover:bg-slate-50"
                    @click="clearPermissionFilters"
                  >
                    清除筛选
                  </button>
                </div>
              </div>
            </div>
          </div>
        </template>
      </section>
    </div>

    <IamDialogSurface
      :open="showDefinitionDetails"
      :title="`${roleAccess?.name || '职位'} · 定义信息`"
      description="用于系统同步、审计和问题排查。"
      drawer
      @update:open="showDefinitionDetails = $event"
      ><div v-if="roleAccess" data-testid="definition-details-panel">
        <div class="space-y-5 p-5">
          <div
            class="flex items-start gap-3 rounded-[12px] border border-emerald-100 bg-emerald-50/60 p-3 text-sm text-emerald-950"
          >
            <LockKeyhole class="mt-0.5 size-4 shrink-0 text-emerald-700" aria-hidden="true" />
            <p>
              <b>{{ roleSourceLabel(roleAccess.source) }} · 只读。</b>
              内置职位由系统代码固定维护；管理员可以查看，但不能在线修改。
            </p>
          </div>

          <dl class="grid gap-4 sm:grid-cols-2">
            <div>
              <dt class="text-xs font-semibold text-slate-500">权限来源</dt>
              <dd class="mt-1 text-sm font-bold text-slate-900">
                {{ roleSourceLabel(roleAccess.source) }}
              </dd>
            </div>
            <div>
              <dt class="text-xs font-semibold text-slate-500">职位代码</dt>
              <dd class="mt-1 break-all font-mono text-xs font-bold leading-5 text-slate-800">
                {{ roleAccess.code }}
              </dd>
            </div>
            <div class="sm:col-span-2">
              <dt class="text-xs font-semibold text-slate-500">定义版本</dt>
              <dd class="mt-1 font-mono text-xs font-bold leading-5 text-slate-800">
                {{ roleAccess.definition_version || '待同步' }}
              </dd>
            </div>
            <div class="sm:col-span-2">
              <dt class="text-xs font-semibold text-slate-500">数据范围</dt>
              <dd class="mt-1 text-sm font-bold text-slate-900">{{ roleDataScopeSummary }}</dd>
              <p class="mt-1 text-xs leading-5 text-slate-500">
                {{ roleScopeModeDescription(roleAccess.scope_mode) }}
              </p>
            </div>
            <div class="sm:col-span-2">
              <dt class="text-xs font-semibold text-slate-500">修改方式</dt>
              <dd class="mt-1 text-sm leading-6 text-slate-800">
                提交明确需求，通过代码变更、测试和发布流程生效。
              </dd>
            </div>
            <div class="sm:col-span-2">
              <div class="flex items-center justify-between gap-3">
                <dt class="text-xs font-semibold text-slate-500">定义哈希</dt>
                <button
                  type="button"
                  class="inline-flex items-center gap-1 rounded-[8px] px-2 py-1 text-[11px] font-bold text-emerald-700 hover:bg-emerald-50 focus:outline-none focus:ring-2 focus:ring-emerald-200"
                  :disabled="!roleAccess.definition_hash"
                  @click="copyDefinitionHash"
                >
                  <Copy class="size-3" aria-hidden="true" />复制
                </button>
              </div>
              <dd
                class="mt-1 break-all rounded-[10px] bg-slate-50 p-3 font-mono text-xs font-bold leading-5 text-slate-700"
              >
                {{ roleAccess.definition_hash || '待同步' }}
              </dd>
              <p
                class="mt-2 min-h-4 text-xs font-semibold"
                :class="
                  definitionCopyFeedback.includes('失败') ? 'text-rose-700' : 'text-emerald-700'
                "
                aria-live="polite"
              >
                {{ definitionCopyFeedback }}
              </p>
            </div>
          </dl>
        </div>
      </div>
    </IamDialogSurface>
  </section>
</template>

<style scoped>
.iamx-role-layout {
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr);
  gap: 20px;
  align-items: start;
}
.iamx-role-content {
  min-width: 0;
}
.iam-viewer-panel {
  grid-template-columns: minmax(0, 1fr);
}
.iam-viewer-panel > * {
  min-width: 0;
}
.iam-directory-panel {
  max-height: calc(100dvh - 168px);
  position: sticky;
  top: 20px;
}
.iam-directory-scroll {
  overflow: auto;
}
.iam-permission-list {
  min-width: 0;
}
.iamx-permission-row {
  border-top: 1px solid var(--border);
  padding: 12px 4px;
}
.iamx-permission-line {
  display: grid;
  grid-template-columns: minmax(180px, 1fr) 72px minmax(120px, 0.8fr) 52px;
  gap: 12px;
  align-items: center;
  font-size: 13px;
}
.iamx-permission-name {
  display: flex;
  align-items: center;
  gap: 9px;
}
.iamx-permission-name svg {
  flex-shrink: 0;
  color: var(--primary);
}
.iamx-permission-row :deep(.iamx-disclosure) {
  margin: 6px 0 0;
  border: 0;
}
.iamx-permission-row :deep(.iamx-disclosure-trigger) {
  padding: 3px 0;
  font-size: 12px;
  font-weight: 400;
  color: var(--muted-foreground);
  justify-content: flex-start;
}
.iamx-permission-warning {
  margin: 7px 0;
  color: #9b5925;
  font-size: 12px;
}
.iamx-permission-alert {
  background: #fff5f3;
}
@media (max-width: 1279px) {
  .iamx-role-layout {
    grid-template-columns: minmax(0, 1fr);
  }
}
@media (max-width: 767px) {
  .iamx-permission-line {
    grid-template-columns: minmax(0, 1fr) 55px;
    gap: 8px;
  }
  .iamx-permission-name {
    grid-column: 1/-1;
  }
}
</style>
