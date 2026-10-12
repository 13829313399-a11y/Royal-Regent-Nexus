<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { Eye, EyeOff, LockKeyhole } from '@lucide/vue'
import AuthField from './AuthField.vue'
withDefaults(defineProps<{ modelValue: string; id: string; name: string; label: string; error?: string; hint?: string; autocomplete?: string; disabled?: boolean }>(), { autocomplete: 'new-password' })
const emit = defineEmits<{ 'update:modelValue': [string] }>()
const visible = ref(false), capsLock = ref(false)
const input = ref<HTMLInputElement>()
function caps(event: KeyboardEvent) { capsLock.value = event.getModifierState?.('CapsLock') ?? false }
async function toggle() {
  const start = input.value?.selectionStart, end = input.value?.selectionEnd
  visible.value = !visible.value
  await nextTick(); input.value?.focus()
  if (start != null && end != null) input.value?.setSelectionRange(start, end)
}
defineExpose({ focus: () => input.value?.focus() })
</script>
<template>
  <AuthField :id="id" :label="label" :error="error" :hint="capsLock ? '大写锁定已开启' : hint" required v-slot="field">
    <div class="ng-control">
      <LockKeyhole class="ng-icon" aria-hidden="true" />
      <input ref="input" :id="id" :name="name" :type="visible ? 'text' : 'password'" :value="modelValue" :autocomplete="autocomplete" autocapitalize="off" :spellcheck="false" :disabled="disabled" :aria-invalid="field.invalid" :aria-describedby="field.describedby" :placeholder="label" @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)" @keydown="caps" @keyup="caps" @blur="capsLock = false" />
      <button type="button" class="ng-eye" :aria-label="`${visible ? '隐藏' : '显示'}${label}`" :aria-pressed="visible" :disabled="disabled" @mousedown.prevent @click="toggle"><component :is="visible ? EyeOff : Eye" class="ng-icon" aria-hidden="true" /></button>
    </div>
  </AuthField>
</template>
