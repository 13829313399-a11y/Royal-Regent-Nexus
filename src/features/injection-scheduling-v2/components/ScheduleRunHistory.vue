<script setup lang="ts">
import { CheckCircle2, Clock3, Eye, Sparkles, TriangleAlert } from '@lucide/vue'
import type { AutoScheduleRunRecord } from '../types'
import SchedulingTechnicalDetails from './SchedulingTechnicalDetails.vue'
import { autoScheduleRunStatusMeta, solverStatusMeta, solverTypeMeta } from '../presentation/schedulingLabels'
import { formatPlanRevision } from '../presentation/schedulingFormatters'
import { autoScheduleTechnicalDetails } from '../presentation/technicalDetails'

defineProps<{ runs: AutoScheduleRunRecord[] }>()
const emit = defineEmits<{ select: [run: AutoScheduleRunRecord] }>()
</script>

<template>
  <div class="run-history-table">
    <div class="run-history-head"><span>状态</span><span>方案 / 排产方式</span><span>运行时间</span><span>结果</span><span>计划版本</span><span></span></div>
    <article v-for="run in runs" :key="run.id"><span class="run-status" :class="autoScheduleRunStatusMeta(run.status).cssToken"><CheckCircle2 v-if="run.status === 'APPLIED' || run.status === 'SUCCEEDED'" :size="14" /><TriangleAlert v-else-if="run.status === 'FAILED' || run.status === 'CANCELLED'" :size="14" /><Sparkles v-else :size="14" />{{ autoScheduleRunStatusMeta(run.status).label }}</span><span><strong>{{ run.scenarioName }}</strong><small>{{ solverTypeMeta(run.solverType).label }} · {{ solverStatusMeta(run.solverStatus).label }}{{ run.fallbackUsed ? ' · 已自动切换排产方式' : '' }}</small><SchedulingTechnicalDetails :items="autoScheduleTechnicalDetails(run)" /></span><time><Clock3 :size="13" />{{ run.createdAt }}</time><span>排 {{ run.summary.scheduledCount }} · 核 {{ run.summary.reviewCount }} · 未 {{ run.summary.unassignedCount }}</span><span>{{ formatPlanRevision(run.expectedPlanRevision) }}</span><button @click="emit('select', run)"><Eye :size="14" />查看</button></article>
    <p v-if="!runs.length" class="empty-copy">暂无自动排期运行记录</p>
  </div>
</template>
