<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { renderSafeMarkdown } from './markdown'

const props = withDefaults(defineProps<{
  source: string
  streaming?: boolean
}>(), {
  streaming: false,
})

const html = ref('')
let timer: ReturnType<typeof setTimeout> | null = null

function render() {
  timer = null
  html.value = renderSafeMarkdown(props.source)
}

watch(
  () => [props.source, props.streaming] as const,
  () => {
    if (!props.streaming || props.source.length <= 1_000) {
      if (timer) clearTimeout(timer)
      render()
      return
    }
    timer ??= setTimeout(render, 75)
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  if (timer) clearTimeout(timer)
})
</script>

<template>
  <div class="ai-rich-text" data-ai-rich-text v-html="html" />
</template>

<style src="./rich-text.css"></style>
