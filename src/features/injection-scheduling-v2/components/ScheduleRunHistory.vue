<script setup lang="ts">
import { CheckCircle2, Clock3, Eye, Sparkles, TriangleAlert } from '@lucide/vue'
import type { AutoScheduleRunRecord } from '../types'

defineProps<{ runs: AutoScheduleRunRecord[] }>()
const emit = defineEmits<{ select: [run: AutoScheduleRunRecord] }>()
const statusLabels: Partial<Record<AutoScheduleRunRecord['status'], string>> = { SUCCEEDED: '可应用', PARTIAL: '部分完成', APPLIED: '已应用', FAILED: '失败', CANCELLED: '已取消' }
const statusLabel = (status: AutoScheduleRunRecord['status']) => statusLabels[status] ?? status
</script>

<template>
  <div class="run-history-table">
    <div class="run-history-head"><span>状态</span><span>方案 / 求解器</span><span>运行时间</span><span>结果</span><span>计划/规则</span><span></span></div>
    <article v-for="run in runs" :key="run.id"><span class="run-status" :class="run.status.toLowerCase()"><CheckCircle2 v-if="run.status === 'APPLIED' || run.status === 'SUCCEEDED'" :size="14" /><TriangleAlert v-else-if="run.status === 'FAILED' || run.status === 'CANCELLED'" :size="14" /><Sparkles v-else :size="14" />{{ statusLabel(run.status) }}</span><span><strong>{{ run.scenarioName }}</strong><small>{{ run.solverType }} · {{ run.solverStatus }}{{ run.fallbackUsed ? ' · 回退' : '' }}</small></span><time><Clock3 :size="13" />{{ run.createdAt }}</time><span>排 {{ run.summary.scheduledCount }} · 核 {{ run.summary.reviewCount }} · 未 {{ run.summary.unassignedCount }}</span><span>r{{ run.expectedPlanRevision }} / 规则 r{{ run.ruleRevision }}</span><button @click="emit('select', run)"><Eye :size="14" />查看</button></article>
    <p v-if="!runs.length" class="empty-copy">暂无自动排期运行记录</p>
  </div>
</template>
