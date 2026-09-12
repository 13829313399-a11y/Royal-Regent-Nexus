<script setup lang="ts">
import { reactive } from 'vue'
import { Button } from '@/components/ui/button'
export interface Field { key: string; label: string; type?: string; value?: string; optional?: boolean; options?: { value: string; label: string }[]; hint?: string }
const props = defineProps<{ fields: Field[]; submitLabel?: string; busy?: boolean }>()
const emit = defineEmits<{ submit: [values: Record<string, string>] }>()
const values = reactive<Record<string, string>>(Object.fromEntries(props.fields.map(f => [f.key, f.value ?? ''])))
</script>
<template>
  <form class="spray-entry" @submit.prevent="emit('submit', { ...values })">
    <label v-for="field in fields" :key="field.key" class="spray-field">
      <span>{{ field.label }}<span v-if="field.optional" class="spray-muted"> · 可留空</span></span>
      <select v-if="field.options" v-model="values[field.key]" :required="!field.optional" :aria-label="field.label"><option value="">请选择</option><option v-for="o in field.options" :key="o.value" :value="o.value">{{ o.label }}</option></select>
      <textarea v-else-if="field.type === 'textarea'" v-model="values[field.key]" :required="!field.optional" rows="3" />
      <input v-else v-model="values[field.key]" :type="field.type === 'decimal' ? 'text' : field.type ?? 'text'" :inputmode="field.type === 'decimal' ? 'decimal' : undefined" :required="!field.optional" :aria-label="field.label" />
      <small v-if="field.hint">{{ field.hint }}</small>
    </label>
    <div class="spray-form-actions"><slot /><Button type="submit" :disabled="busy">{{ busy ? '正在保存…' : submitLabel ?? '保存记录' }}</Button></div>
  </form>
</template>
