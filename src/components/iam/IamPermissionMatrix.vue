<script setup lang="ts">
import { computed } from 'vue'
import { AlertTriangle, CheckCircle2, MinusCircle, XCircle } from '@lucide/vue'
import type { PermissionCatalogItem, PermissionDraftEffect } from '@/api/iam'
import { permissionDisplayLabel } from '@/components/iam/permissionCatalogLabels'

export interface PermissionMatrixResolution {
  allowed: boolean
  source_label: string
}

const props = defineProps<{
  permissions: PermissionCatalogItem[]
  states: Record<string, PermissionDraftEffect>
  resolutions: Record<string, PermissionMatrixResolution | undefined>
  factoryId?: string
  department?: string
  disabled?: boolean
}>()

const emit = defineEmits<{
  change: [permissionCode: string, effect: PermissionDraftEffect]
}>()

const groups = computed(() => {
  const grouped = new Map<string, { moduleName: string; items: PermissionCatalogItem[] }>()
  props.permissions.forEach((permission) => {
    const existing = grouped.get(permission.module_code)
    if (existing) {
      existing.items.push(permission)
    } else {
      grouped.set(permission.module_code, { moduleName: permission.module_name, items: [permission] })
    }
  })
  return [...grouped.entries()].map(([moduleCode, group]) => ({ moduleCode, ...group }))
})

const stateOptions: Array<{ value: PermissionDraftEffect; label: string; icon: typeof MinusCircle }> = [
  { value: 'inherit', label: '继承', icon: MinusCircle },
  { value: 'allow', label: '允许', icon: CheckCircle2 },
  { value: 'deny', label: '禁止', icon: XCircle },
]

function stateButtonClass(permissionCode: string, effect: PermissionDraftEffect) {
  if (props.states[permissionCode] !== effect) {
    return 'text-slate-500 hover:text-slate-800'
  }
  if (effect === 'allow') return 'bg-emerald-600 text-white shadow-sm'
  if (effect === 'deny') return 'bg-rose-600 text-white shadow-sm'
  return 'bg-white text-slate-800 shadow-sm'
}

function scopeIsApplicable(permission: PermissionCatalogItem) {
  if (permission.requires_global_factory) {
    return props.factoryId === '*' && props.department === '*'
  }
  const applicableDepartments = permission.applicable_departments ?? []
  if (!applicableDepartments.length) return true
  return props.department === '*' || applicableDepartments.includes(props.department ?? '')
}

function scopeWarning(permission: PermissionCatalogItem) {
  if (scopeIsApplicable(permission)) return ''
  const guidance = permission.scope_guidance || '请切换到该权限适用的厂区 / 部门范围后再配置。'
  if (props.states[permission.code] !== 'inherit') {
    return `当前范围不适用；现有用户级${props.states[permission.code] === 'allow' ? '允许' : '禁止'}配置不生效，请选择“继承”清理。${guidance}`
  }
  if (permission.requires_global_factory && props.resolutions[permission.code]?.allowed) {
    const source = props.resolutions[permission.code]?.source_label || '全局授权'
    return `当前允许来自“${source}”的全局授权；本地范围只展示结果，不能新增用户级覆盖。${guidance}`
  }
  if (props.resolutions[permission.code]?.allowed) {
    return `当前范围不适用；当前显示的授权来源在业务接口中不生效，请检查并清理角色绑定。${guidance}`
  }
  return `当前范围不适用，不能在这里授予该权限。${guidance}`
}

function stateOptionDisabled(permission: PermissionCatalogItem, effect: PermissionDraftEffect) {
  if (props.disabled) return true
  if (scopeIsApplicable(permission)) return false
  return effect !== 'inherit' || props.states[permission.code] === 'inherit'
}
</script>

<template>
  <section class="min-w-0 max-w-full overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
    <div class="flex flex-wrap items-start justify-between gap-3 border-b border-slate-200 px-4 py-4 sm:px-5">
      <div class="min-w-0">
        <h2 class="font-bold text-slate-950">模块权限矩阵</h2>
        <p class="mt-1 text-sm text-slate-500">禁止优先于允许，允许优先于角色继承；改动保存为草稿，预览确认后才提交。</p>
      </div>
      <div class="flex flex-wrap gap-2 text-xs font-semibold text-slate-500">
        <span class="rounded-full bg-slate-100 px-2.5 py-1">继承角色</span>
        <span class="rounded-full bg-emerald-50 px-2.5 py-1 text-emerald-700">单独允许</span>
        <span class="rounded-full bg-rose-50 px-2.5 py-1 text-rose-700">单独禁止</span>
      </div>
    </div>

    <div v-if="groups.length" class="divide-y divide-slate-200">
      <section v-for="group in groups" :key="group.moduleCode" class="min-w-0 p-4 sm:p-5">
        <div class="mb-3 flex items-center justify-between gap-3">
          <div class="min-w-0">
            <h3 class="font-bold text-slate-900">{{ group.moduleName }}</h3>
            <code class="block break-all text-xs text-slate-400 [overflow-wrap:anywhere]">{{ group.moduleCode }}</code>
          </div>
          <span class="text-xs font-semibold text-slate-400">{{ group.items.length }} 项操作</span>
        </div>

        <div data-testid="mobile-permission-list" class="grid gap-3 md:hidden">
          <article
            v-for="permission in group.items"
            :key="`mobile-${permission.code}`"
            class="min-w-0 rounded-xl border p-3.5"
            :class="scopeIsApplicable(permission) ? 'border-slate-200 bg-white' : 'border-amber-200 bg-amber-50/40'"
          >
            <div class="flex min-w-0 items-start justify-between gap-3">
              <div class="min-w-0">
                <strong class="block break-words text-sm text-slate-900 [overflow-wrap:anywhere]">{{ permissionDisplayLabel(permission) }}</strong>
                <code class="mt-0.5 block break-all text-xs text-slate-400 [overflow-wrap:anywhere]">{{ permission.code }}</code>
              </div>
              <span v-if="permission.risk_level === 'high'" class="inline-flex shrink-0 items-center gap-1 rounded-full bg-amber-50 px-2 py-1 text-xs font-bold text-amber-700"><AlertTriangle class="size-3" aria-hidden="true" />高风险</span>
              <span v-else class="shrink-0 rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-500">普通</span>
            </div>

            <p
              v-if="!scopeIsApplicable(permission)"
              data-testid="permission-scope-warning"
              class="mt-3 flex items-start gap-1.5 rounded-lg border border-amber-200 bg-amber-50 p-2.5 text-xs leading-5 text-amber-900"
            >
              <AlertTriangle class="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
              <span>{{ scopeWarning(permission) }}</span>
            </p>

            <div class="mt-3 rounded-lg bg-slate-50 p-2.5">
              <span v-if="resolutions[permission.code]?.allowed" class="inline-flex items-center gap-1 text-sm font-semibold text-emerald-700"><CheckCircle2 class="size-4" aria-hidden="true" />当前允许</span>
              <span v-else class="inline-flex items-center gap-1 text-sm font-semibold text-slate-600"><XCircle class="size-4" aria-hidden="true" />当前拒绝</span>
              <small class="mt-1 block break-words text-xs text-slate-500 [overflow-wrap:anywhere]">{{ resolutions[permission.code]?.source_label || '默认拒绝' }}</small>
            </div>

            <fieldset class="mt-3 min-w-0">
              <legend class="sr-only">{{ permissionDisplayLabel(permission) }}用户级调整</legend>
              <div class="grid min-w-0 grid-cols-3 rounded-lg bg-slate-100 p-1">
                <button
                  v-for="option in stateOptions"
                  :key="`mobile-${permission.code}-${option.value}`"
                  type="button"
                  class="flex min-w-0 items-center justify-center gap-1 rounded-md px-1.5 py-2 text-xs font-bold transition disabled:cursor-not-allowed disabled:opacity-40"
                  :class="stateButtonClass(permission.code, option.value)"
                  :aria-pressed="states[permission.code] === option.value"
                  :disabled="stateOptionDisabled(permission, option.value)"
                  :title="!scopeIsApplicable(permission) && option.value !== 'inherit' ? '当前厂区 / 部门范围不适用' : undefined"
                  @click="emit('change', permission.code, option.value)"
                >
                  <component :is="option.icon" class="size-3.5 shrink-0" aria-hidden="true" />
                  <span class="truncate">{{ option.label }}</span>
                </button>
              </div>
            </fieldset>
          </article>
        </div>

        <div data-testid="desktop-permission-table" class="hidden overflow-x-auto rounded-xl border border-slate-200 md:block">
          <table class="w-full min-w-[780px] border-collapse text-left text-sm">
            <thead class="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th class="px-4 py-3">权限</th>
                <th class="px-4 py-3">风险</th>
                <th class="px-4 py-3">当前结果</th>
                <th class="px-4 py-3 text-right">用户级调整</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              <tr
                v-for="permission in group.items"
                :key="permission.code"
                :class="scopeIsApplicable(permission) ? 'hover:bg-slate-50/70' : 'bg-amber-50/40'"
              >
                <td class="px-4 py-3">
                  <strong class="block text-slate-900">{{ permissionDisplayLabel(permission) }}</strong>
                  <code class="mt-0.5 block break-all text-xs text-slate-400 [overflow-wrap:anywhere]">{{ permission.code }}</code>
                  <small
                    v-if="!scopeIsApplicable(permission)"
                    data-testid="permission-scope-warning"
                    class="mt-1.5 flex max-w-md items-start gap-1 text-xs leading-5 text-amber-800"
                  >
                    <AlertTriangle class="mt-0.5 size-3 shrink-0" aria-hidden="true" />
                    <span>{{ scopeWarning(permission) }}</span>
                  </small>
                </td>
                <td class="px-4 py-3">
                  <span v-if="permission.risk_level === 'high'" class="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-1 text-xs font-bold text-amber-700"><AlertTriangle class="size-3" />高风险</span>
                  <span v-else class="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-500">普通</span>
                </td>
                <td class="px-4 py-3">
                  <span v-if="resolutions[permission.code]?.allowed" class="inline-flex items-center gap-1 font-semibold text-emerald-700"><CheckCircle2 class="size-4" />允许</span>
                  <span v-else class="inline-flex items-center gap-1 font-semibold text-slate-500"><XCircle class="size-4" />拒绝</span>
                  <small class="mt-0.5 block max-w-52 truncate text-xs text-slate-400" :title="resolutions[permission.code]?.source_label">{{ resolutions[permission.code]?.source_label || '默认拒绝' }}</small>
                </td>
                <td class="px-4 py-3">
                  <div class="ml-auto flex w-fit rounded-lg bg-slate-100 p-1">
                    <button
                      v-for="option in stateOptions"
                      :key="option.value"
                      type="button"
                      class="flex items-center gap-1 rounded-md px-2.5 py-1.5 text-xs font-bold transition disabled:cursor-not-allowed disabled:opacity-40"
                      :class="stateButtonClass(permission.code, option.value)"
                      :aria-pressed="states[permission.code] === option.value"
                      :disabled="stateOptionDisabled(permission, option.value)"
                      :title="!scopeIsApplicable(permission) && option.value !== 'inherit' ? '当前厂区 / 部门范围不适用' : undefined"
                      @click="emit('change', permission.code, option.value)"
                    >
                      <component :is="option.icon" class="size-3.5" aria-hidden="true" />
                      {{ option.label }}
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
    <p v-else class="p-8 text-center text-sm text-slate-500">权限目录为空，开发迁移登记权限后会自动显示。</p>
  </section>
</template>
