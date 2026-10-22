<script setup lang="ts">
defineProps<{ modelValue: string | number }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
function move(value: string | number, direction: number) {
  const match = /^(\d*)(?:\.(\d{0,8}))?$/.exec(String(value))
  if (!match) return
  const scale = 100000000n
  const current = BigInt(match[1] || '0') * scale + BigInt((match[2] || '').padEnd(8, '0'))
  const next = current + BigInt(direction) * scale
  const safe = next < 0n ? 0n : next
  const fraction = (safe % scale).toString().padStart(8, '0').replace(/0+$/, '')
  emit('update:modelValue', (safe / scale).toString() + (fraction ? '.' + fraction : ''))
}
</script>
<template>
  <div class="im-usage-input">
    <input :value="modelValue" aria-label="单件用量" type="number" min="0.00000001" step="any" required @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)" @keydown.up.prevent="move(modelValue, 1)" @keydown.down.prevent="move(modelValue, -1)">
    <button type="button" aria-label="减少单件用量1" @click="move(modelValue, -1)">−</button><button type="button" aria-label="增加单件用量1" @click="move(modelValue, 1)">＋</button>
  </div>
</template>
