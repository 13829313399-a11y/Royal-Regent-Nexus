<script setup lang="ts">
import type { WarehousePreviewField, WarehousePreviewValues } from './documentPreview'

defineProps<{ fields: WarehousePreviewField[]; values: WarehousePreviewValues; detail: boolean }>()
const emit = defineEmits<{ change: [id: string, value: string] }>()
function update(id: string, event: Event) {
  // Keep decimals, leading zeros and an explicit zero exactly as entered.
  emit('change', id, (event.target as HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement).value)
}
</script>

<template>
  <div v-if="!detail" class="warehouse-preview-fields">
    <label v-for="field in fields" :key="field.id" :class="{ 'warehouse-preview-wide': field.type === 'textarea' }">
      {{ field.label }}
      <select v-if="field.type === 'select'" :value="values[field.id] ?? ''" :aria-label="field.label" @change="update(field.id, $event)">
        <option value="">请选择{{ field.label }}</option>
        <option v-for="option in field.options" :key="option" :value="option">{{ option }}</option>
      </select>
      <textarea v-else-if="field.type === 'textarea'" :value="values[field.id] ?? ''" rows="2" :placeholder="field.placeholder || `填写${field.label}`" :aria-label="field.label" @input="update(field.id, $event)" />
      <input v-else :value="values[field.id] ?? ''" :type="field.type || 'text'" :step="field.type === 'number' ? 'any' : undefined" :placeholder="field.placeholder || `填写${field.label}`" :aria-label="field.label" autocomplete="off" @input="update(field.id, $event)" />
    </label>
  </div>
  <dl v-else class="warehouse-preview-facts">
    <template v-for="field in fields" :key="field.id">
      <dt>{{ field.label }}</dt>
      <dd>{{ values[field.id] === undefined || values[field.id] === '' ? '未填写' : values[field.id] }}</dd>
    </template>
  </dl>
</template>
