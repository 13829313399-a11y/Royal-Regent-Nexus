<script setup lang="ts">
defineProps<{ name: string; department?: string; description?: string; scope?: string; count?: number }>()
</script>
<template>
  <span class="iw-package-summary"><strong>{{ name }}</strong><small v-if="department || count !== undefined">{{ department }}{{ count !== undefined ? ` · ${count} 项能力` : '' }}</small><span v-if="scope">{{ scope }}</span><span v-if="description" class="iw-package-description">{{ description }}</span></span>
</template>
<style scoped>
.iw-package-summary{display:flex;flex-direction:column;gap:3px;min-width:0}.iw-package-summary strong{font-weight:650;overflow-wrap:anywhere}.iw-package-summary small,.iw-package-summary>span{font-size:12px;color:var(--iamx-muted,#526761);font-weight:400;line-height:1.5}.iw-package-summary .iw-package-description{color:var(--iamx-text,#213c37)}
</style>
