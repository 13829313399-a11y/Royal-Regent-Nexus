<script setup lang="ts">
import { Building2, CircleUserRound, IdCard, Mail, Phone } from '@lucide/vue'
import type { UserAccessResponse } from '@/api/iam'
import { departmentMap, factoryContexts } from '@/data/enterpriseMock'

const props = defineProps<{
  access: UserAccessResponse
}>()

function factoryLabel(value?: string) {
  if (!value) return '待确认'
  if (value === '*') return '全部厂区'
  return factoryContexts.find((factory) => factory.id === value)?.shortName ?? value
}

function departmentLabel(value?: string) {
  if (!value) return '待确认'
  if (value === '*') return '全部部门'
  return departmentMap[value as keyof typeof departmentMap]?.name ?? value
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    active: '正常',
    suspended: '已停用',
    retired: '已离职',
    pending: '待审批',
    rejected: '已拒绝',
  }
  return labels[status] ?? '未知状态'
}

function statusTone(status: string) {
  if (status === 'active') return 'bg-emerald-50 text-emerald-700'
  if (status === 'suspended') return 'bg-amber-50 text-amber-700'
  if (status === 'rejected') return 'bg-rose-50 text-rose-700'
  return 'bg-slate-100 text-slate-600'
}
</script>

<template>
  <section class="min-w-0 max-w-full overflow-hidden rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
    <div class="flex min-w-0 flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
      <div class="flex min-w-0 items-center gap-3 sm:gap-4">
        <div class="grid size-12 shrink-0 place-items-center rounded-2xl bg-emerald-50 text-emerald-700 sm:size-14">
          <CircleUserRound class="size-7" aria-hidden="true" />
        </div>
        <div class="min-w-0 flex-1">
          <div class="flex min-w-0 flex-wrap items-center gap-2">
            <h2 class="min-w-0 break-words text-xl font-bold text-slate-950 [overflow-wrap:anywhere]">{{ access.user.display_name || access.user.username }}</h2>
            <span class="rounded-full px-2.5 py-1 text-xs font-bold" :class="statusTone(access.user.status)">
              {{ statusLabel(access.user.status) }}
            </span>
          </div>
          <p class="mt-1 break-all text-sm text-slate-500 [overflow-wrap:anywhere]">{{ access.user.username }} · 授权版本 {{ access.authorization_version }}</p>
        </div>
      </div>

      <dl class="grid min-w-0 gap-3 text-sm sm:grid-cols-2 xl:grid-cols-4">
        <div class="min-w-0 rounded-xl bg-slate-50 px-3 py-2.5 sm:min-w-44">
          <dt class="flex items-center gap-1.5 text-xs font-semibold text-slate-500"><Building2 class="size-3.5" />主组织</dt>
          <dd class="mt-1 break-words font-semibold text-slate-900 [overflow-wrap:anywhere]">{{ factoryLabel(access.profile?.primary_factory_id) }} · {{ departmentLabel(access.profile?.primary_department) }}</dd>
        </div>
        <div class="min-w-0 rounded-xl bg-slate-50 px-3 py-2.5 sm:min-w-36">
          <dt class="flex items-center gap-1.5 text-xs font-semibold text-slate-500"><IdCard class="size-3.5" />职位</dt>
          <dd class="mt-1 break-words font-semibold text-slate-900 [overflow-wrap:anywhere]">{{ access.profile?.position || '待确认' }}</dd>
        </div>
        <div class="min-w-0 rounded-xl bg-slate-50 px-3 py-2.5 sm:min-w-36">
          <dt class="flex items-center gap-1.5 text-xs font-semibold text-slate-500"><Phone class="size-3.5" />电话</dt>
          <dd class="mt-1 break-all font-semibold text-slate-900 [overflow-wrap:anywhere]">{{ access.user.phone || '未填写' }}</dd>
        </div>
        <div class="min-w-0 rounded-xl bg-slate-50 px-3 py-2.5 sm:min-w-44">
          <dt class="flex items-center gap-1.5 text-xs font-semibold text-slate-500"><Mail class="size-3.5" />邮箱</dt>
          <dd class="mt-1 break-all font-semibold text-slate-900 [overflow-wrap:anywhere]">{{ access.user.email || '未填写' }}</dd>
        </div>
      </dl>
    </div>
  </section>
</template>
