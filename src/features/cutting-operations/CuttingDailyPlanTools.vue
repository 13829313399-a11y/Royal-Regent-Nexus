<script setup lang="ts">
import { Button } from '@/components/ui/button'
import { computed, ref, watch } from 'vue'
import type { WorkCalendarData } from './api'
import type { PlanTaskInput } from './planning'
import { generateDailyPlan, copyDailyPlan } from './planningTools'
const props = defineProps<{ task: PlanTaskInput; calendar?: WorkCalendarData | null; sources: PlanTaskInput[] }>()
const start = ref(''), end = ref(''), sets = ref(1), mode = ref('replace'), source = ref('')
const preview = ref<PlanTaskInput['days']>([]), error = ref('')
const remaining = computed(() => props.task.target_sets - (mode.value === 'append' ? props.task.days.reduce((n, d) => n + d.sets, 0) : 0))
watch(() => JSON.stringify([props.task.days, props.task.target_sets, props.task.resource_id, props.task.resource_version, props.calendar, start.value, end.value, sets.value, mode.value, source.value, props.sources.find(t => t.task_id === source.value)?.days]), () => { preview.value = []; error.value = '' })
function build(copy = false) {
  try {
    if (props.calendar === undefined) throw new Error('请先查询并确认当前执行方资料／日历')
    const occupied = mode.value === 'append' ? props.task.days.map(d => d.day) : []
    const origin = props.sources.find(t => t.task_id === source.value)
    preview.value = copy ? copyDailyPlan(origin?.days ?? [], start.value, remaining.value, props.calendar, occupied) : generateDailyPlan(start.value, end.value, sets.value, remaining.value, props.calendar, occupied)
    error.value = ''
  } catch (e) { preview.value = []; error.value = (e as Error).message }
}
function apply() {
  if (!preview.value.length) return
  if (mode.value === 'replace' && props.task.days.length && !window.confirm('用已预览的日计划替换本任务草稿中的日计划？历史发布版保留。')) return
  props.task.days = [...(mode.value === 'append' ? props.task.days : []), ...preview.value.map(d => ({ ...d }))].sort((a,b) => a.day.localeCompare(b.day))
  preview.value = []
}
</script>
<template>
  <details class="daily-tools"><summary>批量生成／复制日计划（先预览）</summary><div class="daily-tools-fields">
    <label>开始日期 <input v-model="start" type="date" /></label><label>结束日期 <input v-model="end" type="date" /></label>
    <label>每日计划套数 <input v-model.number="sets" type="number" min="1" max="1000000000" step="1" /></label>
    <label>应用方式 <select v-model="mode"><option value="replace">替换本任务日计划</option><option value="append">追加并跳过已有日期</option></select></label>
    <Button variant="outline" type="button" @click="build()">生成预览</Button>
    <label>复制来源 <select v-model="source"><option value="">请选择任务</option><option v-for="t in sources.filter(t => t.days.length)" :key="t.task_id" :value="t.task_id">{{ t.name }}</option></select></label>
    <Button variant="outline" type="button" @click="build(true)">复制到开始日期并预览</Button>
    <p>按当前执行方日历跳过休息日，尾日按剩余目标截数；复制保留每日数量顺序。只生成草稿，物料就绪日期仍需核对。</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <template v-if="preview.length"><p>新增 {{ preview.length }} 个工作日 · {{ preview.reduce((n,d) => n+d.sets,0) }} 套</p><ul><li v-for="d in preview" :key="d.day">{{ d.day }}：{{ d.sets }} 套</li></ul><Button variant="outline" type="button" @click="apply">确认应用预览</Button></template>
  </div></details>
</template>
<style scoped>
.daily-tools { padding: 16px; border: 1px solid var(--border); border-radius: var(--radius); }
.daily-tools-fields { display: grid; gap: 16px; margin-top: 16px; }
</style>
