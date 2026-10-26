<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
const svg = ref(''), controller = new AbortController()
onMounted(async () => {
  try {
    // The repository-owned vector is reused verbatim; names are isolated from other brand instances.
    const response = await fetch('/brand/huadeng_group_dynamic_logo_topbar.svg', { signal: controller.signal })
    if (response.ok) svg.value = (await response.text()).replaceAll('hd-', 'uv-logo-')
  } catch { /* Accessible brand text remains available if the asset cannot be read. */ }
})
onBeforeUnmount(() => controller.abort())
</script>
<template><span class="uv-brand-logo" role="img" aria-label="华登集团" v-html="svg"/></template>
