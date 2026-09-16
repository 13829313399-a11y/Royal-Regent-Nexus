<script setup lang="ts">
import { computed } from 'vue'
import { X } from '@lucide/vue'

/**
 * 页内筛选条：筛选折叠在窄屏，条件与页内分页写入可分享 URL。
 * 敏感金额/人员明细不写 URL（由使用方控制）。
 */

export interface UvFilterChip {
  key: string
  label: string
  value: string
  /** 该条件当前是否生效。 */
  active?: boolean
  /** 可选值；为空时渲染为文本而非选择。 */
  options?: Array<{ value: string; label: string }>
  hint?: string
}

const props = withDefaults(defineProps<{
  chips: UvFilterChip[]
  /** 结果计数口径说明。 */
  summary?: string
  /** 是否允许清除全部条件。 */
  clearable?: boolean
}>(), {
  summary: '',
  clearable: true,
})

const emit = defineEmits<{
  change: [key: string, value: string]
  clear: []
}>()

const activeCount = computed(() => props.chips.filter((chip) => chip.active).length)
</script>

<template>
  <div class="uv-filters">
    <div class="uv-filters__row">
      <div v-for="chip in chips" :key="chip.key" class="uv-filter">
        <label class="uv-filter__label" :for="`uv-filter-${chip.key}`">{{ chip.label }}</label>
        <select
          v-if="chip.options?.length"
          :id="`uv-filter-${chip.key}`"
          class="uv-input uv-select"
          :class="chip.active ? 'uv-select--active' : ''"
          :value="chip.value"
          @change="emit('change', chip.key, ($event.target as HTMLSelectElement).value)"
        >
          <option v-for="option in chip.options" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
        <span v-else class="uv-filter__value">{{ chip.value }}</span>
        <span v-if="chip.hint" class="uv-filter__hint">{{ chip.hint }}</span>
      </div>

      <div class="uv-filters__meta">
        <span v-if="summary" class="uv-filters__summary">{{ summary }}</span>
        <button
          v-if="clearable && activeCount"
          type="button"
          class="uv-chip uv-chip--clear"
          @click="emit('clear')"
        >
          <X class="size-3" aria-hidden="true" />
          清除 {{ activeCount }} 个条件
        </button>
      </div>
    </div>
  </div>
</template>
