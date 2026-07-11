<script setup lang="ts">
import { Clock3, Layers3, Plus, RotateCcw, Trash2 } from '@lucide/vue'
import { computed, ref } from 'vue'
import type { RoleBinding, RoleBindingDraft, RoleSummary } from '@/api/iam'
import { departmentMap, factoryContexts } from '@/data/enterpriseMock'

const props = defineProps<{
  bindings: RoleBinding[]
  roles?: RoleSummary[]
  factoryId?: string
  department?: string
  drafts?: RoleBindingDraft[]
  disabled?: boolean
}>()

const emit = defineEmits<{
  add: [roleId: string]
  revoke: [binding: RoleBinding]
  undo: [index: number]
}>()

const selectedRoleId = ref('')
const activeBindingsInScope = computed(() => props.bindings.filter((binding) =>
  binding.state === 'active'
  && binding.factory_id === props.factoryId
  && binding.department === props.department,
))

function addBinding() {
  if (!selectedRoleId.value) return
  emit('add', selectedRoleId.value)
  selectedRoleId.value = ''
}

function factoryLabel(value: string) {
  if (value === '*') return '全部厂区'
  return factoryContexts.find((factory) => factory.id === value)?.shortName ?? value
}

function departmentLabel(value: string) {
  if (value === '*') return '全部部门'
  return departmentMap[value as keyof typeof departmentMap]?.name ?? value
}

function stateLabel(value: RoleBinding['state']) {
  return { active: '生效中', suspended: '已暂停', revoked: '已撤销' }[value]
}
</script>

<template>
  <section class="min-w-0 max-w-full rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
    <div class="mb-4 flex items-start justify-between gap-4">
      <div>
        <h2 class="flex items-center gap-2 font-bold text-slate-950"><Layers3 class="size-4 text-emerald-700" />角色授权来源</h2>
        <p class="mt-1 text-sm text-slate-500">角色是基础模板；下方单项权限可对角色结果进行允许或禁止。</p>
      </div>
      <span class="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-bold text-slate-600">{{ bindings.length }} 条</span>
    </div>
    <div v-if="bindings.length" class="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      <article v-for="binding in bindings" :key="binding.id" class="rounded-xl border border-slate-200 p-3.5">
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <strong class="block break-words text-sm text-slate-950 [overflow-wrap:anywhere]">{{ binding.role_name }}</strong>
            <p class="mt-1 break-words text-xs text-slate-500 [overflow-wrap:anywhere]">{{ factoryLabel(binding.factory_id) }} · {{ departmentLabel(binding.department) }}</p>
          </div>
          <span class="rounded-full px-2 py-0.5 text-[11px] font-bold" :class="binding.state === 'active' ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'">{{ stateLabel(binding.state) }}</span>
        </div>
        <div class="mt-3 flex items-center justify-between gap-2 border-t border-slate-100 pt-2 text-[11px] text-slate-500">
          <span>{{ binding.source_type }}</span>
          <span class="flex items-center gap-1"><Clock3 class="size-3" />{{ binding.valid_until ? `至 ${binding.valid_until.slice(0, 10)}` : '长期' }}</span>
        </div>
      </article>
    </div>
    <p v-else class="rounded-xl border border-dashed border-slate-200 p-5 text-center text-sm text-slate-500">该用户还没有角色绑定。</p>

    <div v-if="roles?.length" class="mt-4 border-t border-slate-100 pt-4">
      <div class="flex flex-col gap-2 sm:flex-row">
        <select v-model="selectedRoleId" aria-label="新增角色模板" class="h-10 w-full min-w-0 flex-1 rounded-lg border border-slate-200 bg-white px-3 text-sm" :disabled="disabled || !factoryId || !department">
          <option value="">选择要新增的角色模板</option>
          <option v-for="role in roles" :key="role.id" :value="role.id">{{ role.name }}（{{ role.code }}）</option>
        </select>
        <button type="button" class="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-slate-900 px-3 text-sm font-bold text-white disabled:opacity-40" :disabled="disabled || !selectedRoleId" @click="addBinding"><Plus class="size-4" />加入草稿</button>
      </div>

      <div v-if="activeBindingsInScope.length" class="mt-3 flex flex-wrap gap-2">
        <button v-for="binding in activeBindingsInScope" :key="`revoke-${binding.id}`" type="button" class="inline-flex items-center gap-1.5 rounded-lg border border-rose-200 bg-rose-50 px-2.5 py-1.5 text-xs font-bold text-rose-700 disabled:opacity-40" :disabled="disabled" @click="emit('revoke', binding)"><Trash2 class="size-3.5" />撤销 {{ binding.role_name }}</button>
      </div>

      <div v-if="drafts?.length" class="mt-3 grid gap-2">
        <div v-for="(draft, index) in drafts" :key="`${draft.operation}:${draft.binding_id || draft.role_id}:${index}`" class="flex items-center justify-between gap-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900">
          <span class="min-w-0 break-words [overflow-wrap:anywhere]">{{ draft.operation === 'revoke' ? '待撤销' : '待新增' }}：{{ roles.find((role) => role.id === draft.role_id)?.name || bindings.find((binding) => binding.id === draft.binding_id)?.role_name || draft.role_id }}</span>
          <button type="button" class="inline-flex items-center gap-1 font-bold" @click="emit('undo', index)"><RotateCcw class="size-3.5" />撤销草稿</button>
        </div>
      </div>
    </div>
  </section>
</template>
