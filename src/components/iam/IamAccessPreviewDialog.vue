<script setup lang="ts">
import { computed, ref } from 'vue'
import { AlertTriangle, ArrowRight, CheckCircle2, LoaderCircle, X } from '@lucide/vue'
import type { PermissionCatalogItem, UserAccessPreviewResponse } from '@/api/iam'
import { permissionDisplayLabel } from '@/components/iam/permissionCatalogLabels'

const props = defineProps<{
  preview: UserAccessPreviewResponse
  permissions: PermissionCatalogItem[]
  reason: string
  isCommitting?: boolean
}>()

const emit = defineEmits<{
  close: []
  commit: [confirmHighRisk: boolean]
}>()

const confirmedHighRisk = ref(false)
const permissionNames = computed(() => new Map(props.permissions.map((permission) => [permission.code, permissionDisplayLabel(permission)])))

function stateLabel(value: 'allow' | 'deny' | 'none') {
  return { allow: '允许', deny: '禁止', none: '继承 / 无覆盖' }[value]
}
</script>

<template>
  <div class="fixed inset-0 z-50 grid place-items-center bg-slate-950/45 p-4" role="presentation" @click.self="emit('close')">
    <section class="max-h-[90vh] w-full max-w-3xl overflow-hidden rounded-2xl bg-white shadow-2xl" role="dialog" aria-modal="true" aria-labelledby="iam-preview-title">
      <header class="flex items-start justify-between gap-4 border-b border-slate-200 px-5 py-4">
        <div>
          <h2 id="iam-preview-title" class="text-lg font-bold text-slate-950">确认权限变更</h2>
          <p class="mt-1 text-sm text-slate-500">以下差异将以同一事务提交；提交前请核对范围和风险。</p>
        </div>
        <button type="button" class="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-700" :disabled="isCommitting" aria-label="关闭" @click="emit('close')">
          <X class="size-5" />
        </button>
      </header>

      <div class="max-h-[62vh] overflow-y-auto p-5">
        <div class="mb-4 rounded-xl bg-slate-50 p-3 text-sm text-slate-700">
          <span class="font-bold">变更原因：</span>{{ reason }}
        </div>

        <div v-if="preview.diffs.length" class="overflow-hidden rounded-xl border border-slate-200">
          <div v-for="diff in preview.diffs" :key="`${diff.permission_code}:${diff.factory_id}:${diff.department}`" class="flex flex-col gap-3 border-b border-slate-100 p-4 last:border-b-0 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div class="flex flex-wrap items-center gap-2">
                <strong class="text-sm text-slate-900">{{ permissionNames.get(diff.permission_code) || diff.permission_code }}</strong>
                <span v-if="diff.risk_level === 'high'" class="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-bold text-amber-700"><AlertTriangle class="size-3" />高风险</span>
              </div>
              <code class="mt-1 block text-xs text-slate-400">{{ diff.permission_code }} @ {{ diff.factory_id }} / {{ diff.department }}</code>
            </div>
            <div class="flex items-center gap-2 text-xs font-bold">
              <span class="rounded-lg bg-slate-100 px-2.5 py-1.5 text-slate-600">{{ stateLabel(diff.before) }}</span>
              <ArrowRight class="size-4 text-slate-400" />
              <span class="rounded-lg px-2.5 py-1.5" :class="diff.after === 'allow' ? 'bg-emerald-50 text-emerald-700' : diff.after === 'deny' ? 'bg-rose-50 text-rose-700' : 'bg-slate-100 text-slate-600'">{{ stateLabel(diff.after) }}</span>
            </div>
          </div>
        </div>
        <p v-else class="rounded-xl border border-dashed border-slate-200 p-6 text-center text-sm text-slate-500">预览结果没有有效差异。</p>

        <label v-if="preview.high_risk" class="mt-4 flex cursor-pointer items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          <input v-model="confirmedHighRisk" type="checkbox" class="mt-0.5 size-4 accent-amber-600">
          <span><b>二次确认高风险变更</b><br><span class="text-amber-700">我已核对删除、审批、导出、管理或系统级权限的影响。</span></span>
        </label>
      </div>

      <footer class="flex justify-end gap-3 border-t border-slate-200 bg-slate-50 px-5 py-4">
        <button type="button" class="rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-bold text-slate-700 hover:bg-slate-50" :disabled="isCommitting" @click="emit('close')">返回修改</button>
        <button
          type="button"
          class="inline-flex items-center gap-2 rounded-xl bg-emerald-700 px-4 py-2.5 text-sm font-bold text-white hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="isCommitting || !preview.diffs.length || (preview.high_risk && !confirmedHighRisk)"
          @click="emit('commit', confirmedHighRisk)"
        >
          <LoaderCircle v-if="isCommitting" class="size-4 animate-spin" />
          <CheckCircle2 v-else class="size-4" />
          确认并立即生效
        </button>
      </footer>
    </section>
  </div>
</template>
