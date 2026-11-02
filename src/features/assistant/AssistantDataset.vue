<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { ArtifactDataset } from './types'
import { formatBusinessDateTime } from '@/lib/dateTime'
const props = defineProps<{ dataset: ArtifactDataset; initialView?: 'table' | 'chart' }>()
const view = ref<'table' | 'chart'>(props.initialView || 'table'), page = ref(0), chartIndex = ref(0)
watch(() => props.dataset.dataset_id, () => { page.value = 0; chartIndex.value = 0 })
const pageCount = computed(() => Math.max(1, Math.ceil(props.dataset.rows.length / 20)))
const records = computed(() => props.dataset.rows.slice(page.value * 20, (page.value + 1) * 20))
const chart = computed(() => props.dataset.charts[chartIndex.value])
const plotted = computed(() => {
  const spec = chart.value
  if (!spec || spec.type !== 'bar' || spec.dataset_id !== props.dataset.dataset_id) return []
  return props.dataset.metrics.filter(m => spec.metric_keys.includes(m.key) && m.status === 'known'
    && m.unit === spec.unit && (m.currency || null) === (spec.currency || null)
    && m.value !== null && Number.isFinite(Number(m.value))).slice(0, 16)
})
const scale = computed(() => Math.max(1, ...plotted.value.map(m => Math.abs(Number(m.value)))))
const zero = computed(() => plotted.value.some(m => Number(m.value) < 0) ? 310 : 175)
function length(value: number | string | null) { return Math.abs(Number(value)) / scale.value * 175 }
function cell(value: unknown): string { return value == null ? '未知' : typeof value === 'boolean' ? value ? '是' : '否' : typeof value === 'object' ? JSON.stringify(value) : String(value) }
function display(key: string, value: unknown) {
  if (props.dataset.scope.module_id === 'customer-orders' && typeof value === 'string') {
    if (key === 'status') return ({active:'有效',cancelled:'已取消'} as Record<string,string>)[value] || value
    if (key === 'dispatch_status') return ({unsent:'未发送',sent:'已发送'} as Record<string,string>)[value] || value
  }
  return cell(value)
}
</script>
<template>
  <section class="yl-dataset" :aria-label="dataset.title + '原查询数据'">
    <header><h4>{{ dataset.title }}</h4><span>历史查询快照</span></header>
    <p>{{ dataset.scope.label }}</p>
    <p class="yl-muted">数据时点：{{ dataset.as_of ? formatBusinessDateTime(dataset.as_of) + '（北京时间）' : '未知' }}<template v-if="dataset.observed_at"> · 观测于 {{ formatBusinessDateTime(dataset.observed_at) }}</template></p>
    <p class="yl-muted">实际返回 {{ dataset.returned_count }} / {{ dataset.total_count ?? '未知' }} 条。{{ dataset.truncated ? '仅含当时返回的记录，导出不补查后续页。' : '此处保留原查询结果，不代表重新查询的当前状态。' }}</p>
    <div class="yl-data-tabs" aria-label="原数据展示"><button type="button" :aria-pressed="view === 'table'" @click="view = 'table'">表格</button><button type="button" :aria-pressed="view === 'chart'" :disabled="!dataset.charts.length" @click="view = 'chart'">图表</button></div>
    <div v-if="view === 'chart'" class="yl-data-chart">
      <label v-if="dataset.charts.length > 1">图表单位 <select v-model.number="chartIndex" aria-label="图表单位"><option v-for="(spec,index) in dataset.charts" :key="index" :value="index">{{ spec.unit }}{{ spec.currency ? ' · ' + spec.currency : '' }}</option></select></label>
      <p v-if="chart">单位：{{ chart.unit }}{{ chart.currency ? ' · ' + chart.currency : '' }}；图形位置近似，准确值见指标原值。</p>
      <svg v-if="plotted.length" :viewBox="`0 0 560 ${plotted.length * 38 + 10}`" role="img" :aria-label="`${dataset.title}指标图表，单位${chart?.unit}，准确值见指标原值`">
        <line :x1="zero" :x2="zero" y1="0" :y2="plotted.length * 38" stroke="currentColor" opacity=".25"/>
        <g v-for="(metric,index) in plotted" :key="metric.key">
          <text x="158" :y="index * 38 + 23" text-anchor="end"><title>{{ metric.label }}</title>{{ metric.label.length > 15 ? metric.label.slice(0,15) + '…' : metric.label }}</text>
          <rect :x="Number(metric.value) < 0 ? zero - length(metric.value) : zero" :y="index * 38 + 7" :width="length(metric.value)" height="23" rx="4" fill="#397765"/>
          <text x="550" :y="index * 38 + 23" text-anchor="end">{{ cell(metric.value) }}</text>
        </g>
      </svg>
      <p v-else class="yl-muted">当前没有可绘制的已知数值。未知值保留在下方，不绘制为零。</p>
    </div>
    <div class="yl-data-table" tabindex="0" :aria-label="dataset.title + '指标原值，可横向滚动'">
      <table><caption class="sr-only">{{ dataset.title }}指标原值</caption><thead><tr><th>指标</th><th>原值</th><th>单位</th><th>口径</th></tr></thead><tbody><tr v-for="metric in dataset.metrics" :key="metric.key"><th scope="row">{{ metric.label }}</th><td>{{ cell(metric.value) }}</td><td>{{ metric.unit }} {{ metric.currency }}</td><td>{{ dataset.definitions[metric.definition_id] || metric.definition_id }}</td></tr></tbody></table>
    </div>
    <template v-if="dataset.columns.length">
      <div class="yl-data-table" tabindex="0" :aria-label="dataset.title + '明细，可横向滚动'"><table><caption>原查询明细</caption><thead><tr><th v-for="column in dataset.columns" :key="column.key">{{ column.label }}</th></tr></thead><tbody><tr v-for="(record,index) in records" :key="page * 20 + index"><td v-for="column in dataset.columns" :key="column.key">{{ display(column.key,record[column.key]) }}</td></tr></tbody></table></div>
      <div v-if="pageCount > 1" class="yl-data-pagination"><button type="button" :disabled="page === 0" @click="page--">上一页明细</button><span>{{ page + 1 }} / {{ pageCount }} 页</span><button type="button" :disabled="page >= pageCount - 1" @click="page++">下一页明细</button></div>
    </template>
    <p v-else class="yl-muted">此次快照未返回明细；请根据范围和未知说明判断。</p>
    <ul v-if="dataset.unknown_fields.length" class="yl-data-unknown"><li v-for="(unknown,index) in dataset.unknown_fields" :key="index">待核对：{{ unknown.reason }}</li></ul>
    <details class="yl-data-fingerprint"><summary>查看数据集与筛选</summary><p>{{ dataset.dataset_id }}</p><pre>{{ JSON.stringify(dataset.scope.filters, null, 2) }}</pre></details>
  </section>
</template>
