<script setup lang="ts">
/**
 * 详情字段：标签在上、值在下，缺失值显式标注。
 * 「我看到了什么 / 我确认什么 / 会影响什么」三段抽屉统一复用本组件。
 */
withDefaults(defineProps<{
  label: string
  value?: string | number | null
  /** 值缺失时的业务原因，例如「设备未提供」。 */
  missingLabel?: string
  hint?: string
  mono?: boolean
  emphasis?: boolean
  span?: 1 | 2 | 3
}>(), {
  value: undefined,
  missingLabel: '—',
  hint: '',
  mono: false,
  emphasis: false,
  span: 1,
})
</script>

<template>
  <div class="uv-field" :class="[`uv-field--span-${span}`, emphasis ? 'uv-field--emphasis' : '']">
    <dt class="uv-field__label">{{ label }}</dt>
    <dd class="uv-field__value">
      <span v-if="value === null || value === undefined || value === ''" class="uv-field__missing">
        {{ missingLabel }}
      </span>
      <span v-else :class="mono ? 'uv-mono' : ''">{{ value }}</span>
      <span v-if="hint" class="uv-field__hint">{{ hint }}</span>
    </dd>
  </div>
</template>
