<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { AlertTriangle, CheckCircle2, LoaderCircle, Save, ShieldCheck, X } from '@lucide/vue'
import {
  iamApi,
  type PermissionCatalogItem,
  type RoleAccessPreviewResponse,
  type RoleAccessResponse,
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
const reason = ref('')
const preview = ref<RoleAccessPreviewResponse | null>(null)
const confirmedHighRisk = ref(false)
const isLoading = ref(false)
const isSaving = ref(false)
const errorMessage = ref('')
const successMessage = ref('')

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
const activePermissionCount = computed(() => permissions.value.filter((item) => item.status === 'active').length)
const templatePermissionCount = computed(() => roleAccess.value?.permission_codes.length ?? 0)
const permissionLabels = computed(() => new Map(permissions.value.map((permission) => [permission.code, permissionDisplayLabel(permission)])))

const hasChanges = computed(() => {
  if (!roleAccess.value) return false
  return [...selectedPermissionCodes.value].sort().join('|') !== [...roleAccess.value.permission_codes].sort().join('|')
})

function isSelected(permissionCode: string) {
  return selectedPermissionCodes.value.includes(permissionCode)
}

function togglePermission(permissionCode: string) {
  if (roleAccess.value?.is_protected || !canManageRoleTemplates.value) return
  selectedPermissionCodes.value = isSelected(permissionCode)
    ? selectedPermissionCodes.value.filter((code) => code !== permissionCode)
    : [...selectedPermissionCodes.value, permissionCode]
  preview.value = null
}

async function loadRoleAccess(roleId: string) {
  selectedRoleId.value = roleId
  roleAccess.value = null
  preview.value = null
  errorMessage.value = ''
  try {
    const result = await iamApi.getRoleAccess(roleId)
    roleAccess.value = result
    selectedPermissionCodes.value = [...result.permission_codes]
    reason.value = ''
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  }
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
    const message = `内置职位“${roleAccess.value.name}”的权限已更新，绑定用户的有效权限已重新计算。`
    preview.value = null
    roles.value = await iamApi.listSystemPositions()
    await loadRoleAccess(roleId)
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
  <main class="min-h-screen overflow-x-clip bg-slate-100 text-slate-950">
    <IamNavigation data-testid="role-templates-sticky-navigation" class="sticky top-0 z-30 shadow-sm" title="内置职位权限" subtitle="按部门维护固定职位权限；员工只需绑定一个内置权限职位。" />
    <div class="mx-auto grid min-w-0 max-w-[1480px] gap-5 px-4 py-6 sm:px-5 xl:grid-cols-[300px_minmax(0,1fr)] xl:px-8">
      <aside class="min-w-0 h-fit rounded-2xl border border-slate-200 bg-white p-3 shadow-sm">
        <h2 class="px-2 py-2 text-sm font-bold text-slate-900">内置职位目录</h2>
        <section v-for="group in groupedSystemPositions" :key="group.department" class="mt-2 border-t border-slate-100 pt-2 first:mt-0 first:border-t-0">
          <h3 class="px-2 py-1 text-xs font-bold text-slate-400">{{ group.name }}</h3>
          <button v-for="role in group.roles" :key="role.id" type="button" class="mt-1 min-w-0 w-full rounded-xl px-3 py-3 text-left transition" :class="selectedRoleId === role.id ? 'bg-emerald-50 text-emerald-900' : 'hover:bg-slate-50'" :aria-pressed="selectedRoleId === role.id" @click="loadRoleAccess(role.id)">
            <span class="flex items-center justify-between gap-2"><b class="text-sm">{{ role.name }}</b><ShieldCheck v-if="role.is_protected" class="size-4 text-amber-600" /></span>
            <span class="mt-1 block text-xs text-slate-500">{{ role.permission_count ? `已配置 ${role.permission_count} 项权限` : '权限待配置' }} · {{ role.binding_count }} 位用户</span>
          </button>
        </section>
        <p v-if="!roles.length && !isLoading" class="p-4 text-center text-sm text-slate-500">暂无内置职位。</p>
      </aside>

      <section class="min-w-0">
        <div v-if="errorMessage" class="mb-4 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">{{ errorMessage }}</div>
        <div v-if="successMessage" class="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm font-semibold text-emerald-800">{{ successMessage }}</div>
        <div v-if="isLoading || !roleAccess" class="grid min-h-64 place-items-center rounded-2xl border border-slate-200 bg-white"><LoaderCircle v-if="isLoading" class="size-7 animate-spin text-emerald-700" /></div>

        <template v-else>
          <header class="mb-5 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div class="flex flex-wrap items-start justify-between gap-4">
              <div><h2 class="text-xl font-bold">{{ roleAccess.name }}</h2><p class="mt-1 text-sm text-slate-500">{{ roleAccess.position_department_name }} · {{ roleAccess.description || roleAccess.code }} · 权限版本 {{ roleAccess.version }}</p></div>
              <span v-if="roleAccess.is_protected" class="rounded-full bg-amber-50 px-3 py-1.5 text-xs font-bold text-amber-700">受保护角色，不可在线修改</span>
              <span v-else class="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-bold text-slate-600">影响 {{ roleAccess.binding_count }} 位绑定用户</span>
            </div>
          </header>

          <div v-if="roleAccess.is_protected" class="mb-5 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-950">
            <div class="flex items-start gap-3">
              <ShieldCheck class="mt-0.5 size-5 shrink-0 text-amber-700" aria-hidden="true" />
              <div>
                <p class="font-bold">超级管理员按系统规则自动拥有全部启用权限</p>
                <p class="mt-1">
                  下方勾选仅表示角色模板已记录 {{ templatePermissionCount }} 项；实际有效权限为系统已登记的全部
                  {{ activePermissionCount }} 项。以后新增并启用的权限也会自动包含，无需修改此模板。
                </p>
              </div>
            </div>
          </div>

          <div v-if="!canManageRoleTemplates" class="mb-5 rounded-xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-800">当前账号可以查看角色模板，但只有集团超级管理员可以提交模板变更。</div>

          <div class="grid gap-4">
            <section v-for="group in groupedPermissions" :key="group.moduleCode" class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div class="mb-3"><h3 class="font-bold">{{ group.moduleName }}</h3><code class="text-xs text-slate-400">{{ group.moduleCode }}</code></div>
              <div class="grid gap-2 md:grid-cols-2 2xl:grid-cols-3">
                <label v-for="permission in group.permissions" :key="permission.code" class="flex min-w-0 items-start gap-3 rounded-xl border p-3 transition" :class="isSelected(permission.code) ? 'border-emerald-200 bg-emerald-50/70' : 'border-slate-200 bg-white'">
                  <input type="checkbox" class="mt-0.5 size-4 accent-emerald-700" :aria-label="`${permissionDisplayLabel(permission)}（${permission.code}）`" :checked="isSelected(permission.code)" :disabled="roleAccess.is_protected || !canManageRoleTemplates" @change="togglePermission(permission.code)">
                  <span class="min-w-0 flex-1">
                    <b class="block text-sm text-slate-900">{{ permissionDisplayLabel(permission) }}</b>
                    <code class="block break-all text-xs text-slate-400">{{ permission.code }}</code>
                    <span v-if="permission.scope_guidance" class="mt-1.5 block text-xs leading-5 text-slate-500">适用范围：{{ permission.scope_guidance }}</span>
                    <span v-if="roleAccess.is_protected" class="mt-1 block text-xs font-semibold" :class="isSelected(permission.code) ? 'text-emerald-700' : 'text-amber-700'">{{ isSelected(permission.code) ? '模板已记录' : '系统自动拥有' }}</span>
                  </span>
                  <AlertTriangle v-if="permission.risk_level === 'high'" class="ml-auto size-4 shrink-0 text-amber-600" />
                </label>
              </div>
            </section>
          </div>

          <section v-if="!roleAccess.is_protected && canManageRoleTemplates" class="mt-5 grid gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm lg:grid-cols-[1fr_auto] lg:items-end">
            <label class="grid gap-1.5 text-sm font-semibold text-slate-700">变更原因（必填）<input v-model="reason" class="h-11 rounded-xl border border-slate-200 px-3 outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100" placeholder="说明为什么调整此内置职位权限"></label>
            <button type="button" class="inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-emerald-700 px-5 text-sm font-bold text-white disabled:opacity-50" :disabled="!hasChanges || isSaving" @click="previewChanges"><LoaderCircle v-if="isSaving" class="size-4 animate-spin" /><Save v-else class="size-4" />预览职位影响</button>
          </section>
        </template>
      </section>
    </div>

    <div v-if="preview" class="fixed inset-0 z-50 grid place-items-center bg-slate-950/45 p-4" @click.self="preview = null">
      <section class="w-full min-w-0 max-w-2xl rounded-2xl bg-white shadow-2xl" role="dialog" aria-modal="true" aria-labelledby="role-preview-title">
        <header class="flex items-start justify-between border-b border-slate-200 p-5"><div><h2 id="role-preview-title" class="text-lg font-bold">内置职位影响预览</h2><p class="mt-1 text-sm text-slate-500">将影响 {{ preview.affected_user_count }} 位当前绑定用户。</p></div><button type="button" aria-label="关闭内置职位影响预览" class="rounded-lg p-2 hover:bg-slate-100" @click="preview = null"><X class="size-5" /></button></header>
        <div class="max-h-[55vh] overflow-y-auto p-5">
          <div v-for="diff in preview.diffs" :key="diff.permission_code" class="flex items-center justify-between gap-4 border-b border-slate-100 py-3 text-sm"><span class="min-w-0"><b class="block text-slate-900">{{ permissionLabels.get(diff.permission_code) || diff.permission_code }}</b><code class="block break-all text-xs text-slate-400">{{ diff.permission_code }}</code></span><span class="shrink-0 font-bold" :class="diff.after ? 'text-emerald-700' : 'text-rose-700'">{{ diff.before ? '已有' : '无' }} → {{ diff.after ? '授予' : '移除' }}</span></div>
          <label v-if="preview.high_risk" class="mt-4 flex gap-3 rounded-xl bg-amber-50 p-3 text-sm text-amber-900"><input v-model="confirmedHighRisk" type="checkbox" class="mt-0.5 size-4 accent-amber-600"><span>我已核对高风险权限及全部受影响用户。</span></label>
        </div>
        <footer class="flex justify-end gap-2 border-t border-slate-200 bg-slate-50 p-4"><button class="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-bold" @click="preview = null">返回修改</button><button class="inline-flex items-center gap-2 rounded-xl bg-emerald-700 px-4 py-2 text-sm font-bold text-white disabled:opacity-50" :disabled="isSaving || (preview.high_risk && !confirmedHighRisk)" @click="commitChanges"><CheckCircle2 class="size-4" />确认提交</button></footer>
      </section>
    </div>
  </main>
</template>
