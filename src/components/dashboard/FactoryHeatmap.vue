<script setup lang="ts">
import { computed } from 'vue'
import { Factory } from '@lucide/vue'
import { factoryHeatmap } from '@/data/enterpriseMock'
import type { FactoryContextId } from '@/data/enterpriseMock'
import ProgressMeter from '@/components/common/ProgressMeter.vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import StatusPill from '@/components/common/StatusPill.vue'
import { useAppStore } from '@/stores/app'

/**
 * activeFactoryId 为纯展示属性：只用于轻强调当前厂区，不改变数据范围，
 * 也不替代全局顶栏的厂区切换。
 */
const props = withDefaults(defineProps<{
  activeFactoryId?: FactoryContextId
}>(), {
  activeFactoryId: undefined,
})

const appStore = useAppStore()

const resolvedActiveFactoryId = computed<FactoryContextId | undefined>(() =>
  props.activeFactoryId ?? appStore.activeFactoryId,
)

/**
 * 仅当当前上下文是一个具体厂区、且存在对应示例卡片时才强调。
 * group 状态不高亮任何单一厂区；没有示例卡的厂区也不回退到华康A。
 */
function isActiveFactory(factoryId: FactoryContextId) {
  const active = resolvedActiveFactoryId.value
  return active !== undefined && active !== 'group' && active === factoryId
}
</script>

<template>
  <SectionPanel
    class="dashboard-section dashboard-section--factories"
    title="厂区运行热力图"
    subtitle="厂区运行索引 · 以下状态与评分为示例数据"
  >
    <div class="dashboard-factory-grid grid gap-5 md:grid-cols-2">
      <article
        v-for="factory in factoryHeatmap"
        :key="factory.factoryId"
        class="dashboard-factory-card surface-subtle"
        :data-active="isActiveFactory(factory.factoryId) ? 'true' : 'false'"
      >
        <div class="mb-3 flex items-start justify-between gap-3">
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
              <h3 class="dashboard-factory-title"><Factory aria-hidden="true" />{{ factory.name }}</h3>
              <span v-if="isActiveFactory(factory.factoryId)" class="dashboard-factory-tag">
                当前厂区
              </span>
            </div>
            <p data-factory-metrics>{{ factory.metrics }}</p>
          </div>
          <StatusPill :label="factory.status" :tone="factory.statusTone" compact />
        </div>

        <div
          class="dashboard-factory-score"
          role="group"
          :aria-label="`${factory.name} 示例评分 ${factory.score} 分，满分 100 分`"
        >
          <ProgressMeter :value="factory.score" :tone="factory.statusTone" />
          <span class="dashboard-factory-score__value">
            <b>{{ factory.score }}</b> / 100 · 示例评分
          </span>
        </div>

        <p class="dashboard-factory-card__summary">{{ factory.summary }}</p>
      </article>
    </div>
  </SectionPanel>
</template>
