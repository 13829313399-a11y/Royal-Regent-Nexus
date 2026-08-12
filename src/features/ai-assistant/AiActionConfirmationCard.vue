<script setup lang="ts">
import { computed, ref } from 'vue'
import { AlertTriangle, Ban, CheckCircle2 } from '@lucide/vue'
import {
  cancelAIAction,
  confirmAIAction,
  executeAIAction,
  newAIActionExecutionRequestId,
} from '@/api/aiActions'
import { getApiErrorMessage } from '@/lib/http'
import type { AIActionConfirmation } from './types'

const props = defineProps<{
  confirmation: AIActionConfirmation
}>()

const current = ref({ ...props.confirmation })
const busy = ref(false)
const errorMessage = ref('')
const outcomeLabel = ref('')
const reviewOverrideReason = ref('')
const executionRequestId = ref('')
const canAct = computed(() => ['PENDING', 'CONFIRMED'].includes(current.value.status) && !busy.value)
const canCancel = computed(() => current.value.status === 'PENDING' && !busy.value)

async function confirmAndExecute() {
  if (!canAct.value) return
  if (
    current.value.actionSummary.requiresOverrideReason
    && !reviewOverrideReason.value.trim()
  ) {
    errorMessage.value = '该方案含待复核安排，请由你本人填写覆盖原因。'
    return
  }
  busy.value = true
  errorMessage.value = ''
  try {
    if (current.value.status === 'PENDING') {
      current.value = await confirmAIAction(current.value)
    }
    executionRequestId.value ||= newAIActionExecutionRequestId()
    const executed = await executeAIAction(
      current.value,
      reviewOverrideReason.value.trim(),
      executionRequestId.value,
    )
    current.value = executed.confirmation
    outcomeLabel.value = executed.result.outcome_label
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    busy.value = false
  }
}

async function cancel() {
  if (!canCancel.value) return
  busy.value = true
  errorMessage.value = ''
  try {
    current.value = await cancelAIAction(current.value)
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section class="mt-2 space-y-2 rounded-lg border-2 border-amber-300 bg-amber-50 p-3" data-ai-action-confirmation>
    <div class="flex items-start gap-2">
      <AlertTriangle class="mt-0.5 size-4 shrink-0 text-amber-700" aria-hidden="true" />
      <div class="min-w-0 flex-1">
        <p class="text-xs font-bold text-amber-950">待确认的正式操作</p>
        <p class="mt-1 text-[11px] font-semibold text-amber-900">
          {{ current.actionSummary.effectLabel }}
        </p>
      </div>
    </div>
    <dl class="grid grid-cols-2 gap-2 rounded-md bg-white p-2.5 text-[11px] sm:grid-cols-4">
      <div><dt class="text-slate-500">Run</dt><dd class="break-all font-semibold text-slate-900">{{ current.actionSummary.runId }}</dd></div>
      <div><dt class="text-slate-500">计划 revision</dt><dd class="font-bold text-slate-900">{{ current.actionSummary.planRevision }}</dd></div>
      <div><dt class="text-slate-500">影响安排</dt><dd class="font-bold text-slate-900">{{ current.actionSummary.assignmentCount }}</dd></div>
      <div><dt class="text-slate-500">待复核</dt><dd class="font-bold text-slate-900">{{ current.actionSummary.reviewRequiredCount }}</dd></div>
    </dl>
    <label v-if="current.actionSummary.requiresOverrideReason && current.status === 'PENDING'" class="block text-[11px] font-semibold text-slate-700">
      人工覆盖原因（必须由你本人填写）
      <textarea
        v-model="reviewOverrideReason"
        rows="2"
        maxlength="2000"
        class="mt-1 w-full rounded-md border border-amber-300 bg-white px-2 py-1.5 text-xs text-slate-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-600"
      />
    </label>
    <p class="text-[10px] leading-4 text-slate-600">
      确认时会重新检查当前用户权限、厂区、Run、计划/规则 revision、预留和硬约束。不会 Publish 或 Rollback。
    </p>
    <div v-if="current.status === 'PENDING' || current.status === 'CONFIRMED'" class="flex flex-wrap gap-2">
      <button
        type="button"
        class="rounded-md bg-amber-700 px-3 py-1.5 text-[11px] font-bold text-white hover:bg-amber-800 disabled:cursor-not-allowed disabled:opacity-50"
        :disabled="!canAct"
        @click="confirmAndExecute"
      >
        {{ busy ? '正在复查并执行…' : current.status === 'CONFIRMED' ? '重试执行到 DRAFT' : '确认并应用到 DRAFT' }}
      </button>
      <button
        type="button"
        class="rounded-md bg-white px-3 py-1.5 text-[11px] font-semibold text-slate-700 ring-1 ring-inset ring-slate-300 disabled:opacity-50"
        :disabled="!canCancel"
        @click="cancel"
      >
        取消
      </button>
    </div>
    <p v-if="outcomeLabel" class="flex items-center gap-1 text-[11px] font-bold text-emerald-700" aria-live="polite">
      <CheckCircle2 class="size-4" aria-hidden="true" />
      {{ outcomeLabel }}
    </p>
    <p v-else-if="current.status === 'CANCELLED'" class="flex items-center gap-1 text-[11px] font-semibold text-slate-600" aria-live="polite">
      <Ban class="size-4" aria-hidden="true" />
      操作已取消，未修改计划草案。
    </p>
    <p v-else-if="current.status !== 'PENDING' && current.status !== 'CONFIRMED'" class="text-[11px] font-semibold text-slate-700" aria-live="polite">
      当前状态：{{ current.status }}
    </p>
    <p v-if="errorMessage" class="text-[11px] font-semibold text-rose-700" role="alert">
      {{ errorMessage }}
    </p>
    <p class="text-[10px] text-slate-500">确认有效期至 {{ current.expiresAt }}</p>
  </section>
</template>
