<script setup lang="ts">
import { computed } from 'vue'

/**
 * 表单字段容器：标签在上、错误与帮助在下，错误使用文字而不只改边框颜色。
 * 仓库尚无统一 Input/Select 原语，本组件是 UV 工作区内的局部基线，
 * 不写全局 input 覆盖规则。
 */

const props = withDefaults(defineProps<{
  label: string
  required?: boolean
  error?: string
  help?: string
  fieldId?: string
  /** 只读与禁用必须在视觉与交互上区分。 */
  readonly?: boolean
  span?: 1 | 2 | 3
}>(), {
  required: false,
  error: '',
  help: '',
  fieldId: '',
  readonly: false,
  span: 1,
})

const describedBy = computed(() => {
  const ids: string[] = []
  if (props.help) ids.push(`${props.fieldId}-help`)
  if (props.error) ids.push(`${props.fieldId}-error`)
  return ids.length ? ids.join(' ') : undefined
})
</script>

<template>
  <div class="uv-form-field" :class="[`uv-form-field--span-${span}`, readonly ? 'uv-form-field--readonly' : '']">
    <label class="uv-form-label" :for="fieldId || undefined">
      {{ label }}
      <span v-if="required" class="uv-form-required">必填</span>
      <span v-if="readonly" class="uv-form-readonly">只读</span>
    </label>

    <slot :described-by="describedBy" :invalid="Boolean(error)" />

    <p v-if="error" :id="fieldId ? `${fieldId}-error` : undefined" class="uv-form-error" role="alert">
      {{ error }}
    </p>
    <p v-else-if="help" :id="fieldId ? `${fieldId}-help` : undefined" class="uv-form-help">{{ help }}</p>
  </div>
</template>
