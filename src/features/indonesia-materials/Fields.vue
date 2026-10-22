<script setup lang="ts">
import type { Data } from '@/api/indonesiaMaterials'
import type { Field } from './forms'
import { createRandomUuid } from '@/lib/randomUuid'
defineProps<{ model: Data; fields: Field[] }>()
const fieldId = createRandomUuid()
function change(model: Data, field: Field, event: Event) {
  const value = (event.target as HTMLInputElement).value
  model[field.key] = value === '' && field.nullable ? null : value
}
</script>
<template>
  <div class="im-fields">
    <label v-for="field in fields" :key="field.key" class="im-field">
      <span>{{ field.label }}<span v-if="field.required" aria-hidden="true"> *</span></span>
      <select v-if="field.type === 'select'" :value="model[field.key]" :required="field.required" :disabled="field.readonly" @change="change(model, field, $event)">
        <option v-for="option in field.options" :key="option.value" :value="option.value">{{ option.label }}</option>
      </select>
      <template v-else-if="field.type === 'search'">
        <input type="search" :list="`${fieldId}-${field.key}`" :value="model[field.key]" :required="field.required" :readonly="field.readonly" placeholder="输入关键词搜索或填写" @input="change(model, field, $event)">
        <datalist :id="`${fieldId}-${field.key}`"><option v-for="option in field.options?.filter(item => item.value)" :key="option.value" :value="option.value">{{ option.label }}</option></datalist>
      </template>
      <textarea v-else-if="field.type === 'textarea'" :value="model[field.key]" :required="field.required" :readonly="field.readonly" @input="change(model, field, $event)" />
      <input v-else :type="field.type ?? 'text'" :value="model[field.key]" :required="field.required" :readonly="field.readonly" :min="field.min" :step="field.step" @input="change(model, field, $event)">
    </label>
  </div>
</template>
