<script setup lang="ts">
import { computed } from 'vue'
import type { Message } from './types'
import { businessFacts } from './businessFacts'
import { factoryContexts } from '@/data/enterpriseMock'
const props = defineProps<{message: Message}>()
const emit = defineEmits<{sources: []}>()
const panels = computed(() => businessFacts(props.message))
const clock = (value: string) => value.replace('T',' ')
const unitLabel = (value: string) => ['未确定','未明确'].includes(value) ? '单位未确定' : value
const scopeLabel = (value: string) => {
  const factory = factoryContexts.find(f => value.startsWith(`${f.id} / `))
  return factory ? `${factory.name}${value.slice(factory.id.length)}` : value
}
</script>
<template>
  <section v-for="panel in panels" :key="panel.id" class="yl-business-facts" :aria-label="panel.title + '原查询指标'">
    <header><strong>原查询指标 · {{ panel.title }}</strong><span>{{ panel.status }}</span></header>
    <p class="yl-facts-scope">{{ scopeLabel(panel.scope) }}</p>
    <dl class="yl-facts-grid">
      <div v-for="metric in panel.primary" :key="metric.key" :class="{'yl-fact-unknown':metric.unknown}">
        <dt>{{ metric.label }}</dt><dd>{{ metric.value }} <small>{{ unitLabel(metric.unit) }}</small></dd>
      </div>
    </dl>
    <p v-for="metric in panel.otherStates" :key="metric.key" class="yl-facts-state">{{ metric.label }}：{{ metric.value }}</p>
    <p class="yl-facts-clock">数据时点：<time :datetime="panel.asOf">{{ clock(panel.asOf) }}</time></p>
    <p v-if="panel.cacheHit" class="yl-facts-clock">复用近期快照，原数据时点保留。缓存创建：<time :datetime="panel.cacheCreatedAt">{{ clock(panel.cacheCreatedAt) }}</time></p>
    <p v-if="panel.observedAt" class="yl-facts-clock">设备观测：<time :datetime="panel.observedAt">{{ clock(panel.observedAt) }}</time></p>
    <details>
      <summary>全部指标与口径（{{ panel.metrics.length }}）</summary>
      <dl class="yl-facts-definitions"><div v-for="metric in panel.metrics" :key="metric.key"><dt>{{ metric.label }} · {{ metric.value }} {{ unitLabel(metric.unit) }}</dt><dd>{{ metric.definition }}</dd></div></dl>
      <ul v-if="panel.unknowns.length" class="yl-facts-unknowns"><li v-for="(reason,index) in panel.unknowns" :key="index">{{ reason }}</li></ul>
      <p class="yl-facts-clock">读取时点：<time :datetime="panel.retrievedAt">{{ clock(panel.retrievedAt) }}</time> · {{ panel.timezone }}</p>
      <p class="yl-facts-clock">返回 {{ panel.returned }} / {{ panel.total ?? '总数未知' }} 条{{ panel.truncated ? '，明细已截断，可从原列表继续查看' : '' }}。指标沿用原查询范围。</p>
      <button type="button" @click="emit('sources')">核对原查询来源</button>
    </details>
  </section>
</template>
