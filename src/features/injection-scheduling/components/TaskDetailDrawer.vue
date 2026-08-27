<script setup lang="ts">
import { AlertTriangle, CheckCircle2, LoaderCircle, X } from '@lucide/vue'
import { computed, ref, watch } from 'vue'

import { Button } from '@/components/ui/button'
import { getApiErrorMessage } from '@/lib/http'

import { injectionSchedulingApi } from '../api'
import type { MatchEvaluation, SchedulingJob } from '../types'

const props = defineProps<{ open: boolean; factoryId: string; job: SchedulingJob | null }>()
const emit = defineEmits<{ close: [] }>()
const evaluation = ref<MatchEvaluation | null>(null)
const error = ref('')
const loading = ref(false)

const candidates = computed(() => evaluation.value?.results.filter(result => result.decision !== 'FAIL') ?? [])
const exclusions = computed(() => evaluation.value?.results.filter(result => result.decision === 'FAIL') ?? [])

watch(() => [props.open, props.job?.order_id] as const, async ([open]) => {
  evaluation.value = null
  error.value = ''
  if (!open || !props.job) return
  loading.value = true
  try {
    evaluation.value = await injectionSchedulingApi.evaluateOrder(
      props.factoryId,
      props.job.order_id,
      Boolean(props.job.task_id),
    )
  }
  catch (cause) {
    error.value = getApiErrorMessage(cause)
  }
  finally {
    loading.value = false
  }
}, { immediate: true })
</script>

<template>
  <Teleport to="body">
    <div v-if="open && job" class="wb-drawer-layer">
      <button class="wb-drawer-backdrop" aria-label="关闭任务详情" @click="emit('close')" />
      <aside class="wb-drawer" role="dialog" aria-modal="true" aria-labelledby="task-detail-title">
        <header>
          <div><p class="wb-eyebrow">来源第 {{ job.source_row_number || '—' }} 行</p><h2 id="task-detail-title">{{ job.product_name || job.order_no }}</h2></div>
          <Button variant="ghost" size="icon-sm" aria-label="关闭" @click="emit('close')"><X class="size-4" /></Button>
        </header>
        <div class="wb-drawer__body">
          <section><h3>订单资料</h3><dl><div><dt>单号</dt><dd>{{ job.order_no }}</dd></div><div><dt>工模</dt><dd>{{ job.mold_no || '未匹配主档' }}</dd></div><div><dt>欠数</dt><dd>{{ job.outstanding_quantity.toLocaleString() }}</dd></div><div><dt>交期</dt><dd>{{ job.delivery_due_date || '未填写' }}</dd></div><div><dt>优先级</dt><dd>{{ job.priority }}</dd></div><div><dt>来源</dt><dd>{{ job.source_sheet_name || '系统' }} · 第 {{ job.source_row_number || '—' }} 行</dd></div></dl></section>
          <section><h3>排机资料</h3><dl><div><dt>模具安数</dt><dd>{{ job.required_machine_a ?? '缺失' }}</dd></div><div><dt>整啤净重</dt><dd>{{ job.net_weight_g ? `${job.net_weight_g} g` : '缺失' }}</dd></div><div><dt>单双臂</dt><dd>{{ job.arm_requirement || '无要求' }}</dd></div><div><dt>夹具</dt><dd>{{ job.fixture_requirement || '无要求' }}</dd></div><div><dt>材料 / 颜色</dt><dd>{{ job.material_name || '—' }} / {{ job.color_name || '—' }}</dd></div></dl></section>
          <section><h3>候选机台与解释</h3><p v-if="loading" class="wb-drawer-state"><LoaderCircle class="size-4 animate-spin" /> 正在执行硬约束检查</p><p v-else-if="error" class="wb-drawer-state wb-text-danger"><AlertTriangle class="size-4" /> {{ error }}</p><div v-else class="space-y-2"><article v-for="candidate in candidates.slice(0, 5)" :key="candidate.machine_id" class="wb-match wb-match--pass"><CheckCircle2 class="size-4" /><div><strong>{{ candidate.machine_code }} · {{ candidate.decision === 'PASS' ? '可用' : '需复核' }}</strong><p>{{ candidate.explanation }}</p><small v-for="warning in candidate.warnings" :key="warning.rule_code">{{ warning.label }}：{{ warning.detail }}</small></div></article><article v-for="candidate in exclusions.slice(0, 5)" :key="candidate.machine_id" class="wb-match wb-match--fail"><AlertTriangle class="size-4" /><div><strong>{{ candidate.machine_code }} · 已排除</strong><p v-for="reason in candidate.hard_failures" :key="reason.rule_code">{{ reason.label }}：{{ reason.detail }}</p></div></article><p v-if="!candidates.length && !exclusions.length" class="wb-drawer-state">暂无可评估机台。</p></div></section>
        </div>
      </aside>
    </div>
  </Teleport>
</template>
