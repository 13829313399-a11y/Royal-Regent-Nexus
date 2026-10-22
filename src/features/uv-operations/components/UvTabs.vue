<script setup lang="ts">
import { ref, useId, watch } from 'vue'
import { useUvIndicator } from '../composables/useUvIndicator'
const props = defineProps<{ modelValue: string; tabs: (readonly string[])[]; label: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const root = ref<HTMLElement|null>(null), id = 'uv-tabs-' + useId(), focused = ref(props.modelValue)
const tabId = (value: string) => id + '-tab-' + encodeURIComponent(value)
const indicator = useUvIndicator(root, () => props.modelValue + JSON.stringify(props.tabs))
watch(() => props.modelValue, value => { focused.value = value })
function keydown(event: KeyboardEvent, key: string) {
  const keys = props.tabs.map(item => item[0]!).filter(Boolean), index = keys.indexOf(key)
  let next: string | undefined
  if (event.key === 'ArrowRight') next = keys[(index + 1) % keys.length]
  else if (event.key === 'ArrowLeft') next = keys[(index + keys.length - 1) % keys.length]
  else if (event.key === 'Home') next = keys[0]
  else if (event.key === 'End') next = keys.at(-1)
  if (!next) return
  event.preventDefault(); focused.value = next
  document.getElementById(tabId(next))?.focus({ preventScroll: true })
  document.getElementById(tabId(next))?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
}
</script>
<template>
  <div ref="root" class="uv-tabs uv-indicator-host" role="tablist" :aria-label="label">
    <span class="uv-active-plate" :style="indicator.style" aria-hidden="true"/>
    <button v-for="item in tabs" :id="tabId(item[0]!)" :key="item[0]" type="button" role="tab" :tabindex="focused===item[0]?0:-1" :aria-selected="modelValue===item[0]" :aria-controls="id+'-panel-'+encodeURIComponent(item[0]!)" @keydown="keydown($event,item[0]!)" @click="emit('update:modelValue',item[0]!)">{{item[1]}}</button>
  </div>
  <div v-for="item in tabs" :id="id+'-panel-'+encodeURIComponent(item[0]!)" :key="item[0]" class="uv-tab-panel" role="tabpanel" tabindex="0" :hidden="modelValue!==item[0]" :aria-labelledby="tabId(item[0]!)"><slot v-if="modelValue===item[0]"/></div>
</template>
