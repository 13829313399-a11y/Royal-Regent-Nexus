<script setup lang="ts">
import { computed } from 'vue'
const props = withDefaults(defineProps<{ text: string; query?: string }>(), { query: '' })
const parts = computed(() => {
  const needle = props.query.trim().toLocaleLowerCase()
  if (!needle) return [{ text: props.text, match: false }]
  const result: { text: string; match: boolean }[] = []
  let offset = 0
  const haystack = props.text.toLocaleLowerCase()
  while (offset < props.text.length) {
    const at = haystack.indexOf(needle, offset)
    if (at < 0) { result.push({ text: props.text.slice(offset), match: false }); break }
    if (at > offset) result.push({ text: props.text.slice(offset, at), match: false })
    result.push({ text: props.text.slice(at, at + needle.length), match: true })
    offset = at + needle.length
  }
  return result
})
</script>
<template><span><template v-for="(part, index) in parts" :key="index"><mark v-if="part.match" class="home-search-mark">{{ part.text }}</mark><template v-else>{{ part.text }}</template></template></span></template>
