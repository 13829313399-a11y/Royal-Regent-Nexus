<script setup lang="ts">
defineProps<{ title?: string; subtitle?: string }>()
</script>
<template>
  <section class="im-panel">
    <div v-if="title || subtitle || $slots.action" class="im-panel-heading">
      <div><h2 v-if="title">{{ title }}</h2><p v-if="subtitle">{{ subtitle }}</p></div>
      <div v-if="$slots.action" class="im-toolbar"><slot name="action" /></div>
    </div>
    <div class="im-panel-body"><slot /></div>
  </section>
</template>
