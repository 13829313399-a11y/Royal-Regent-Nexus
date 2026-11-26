<script setup lang="ts">
defineProps<{ note?: string }>()
</script>

<template>
  <p v-if="note?.trim()" class="mt-1 text-xs text-teal-800 [overflow-wrap:anywhere]">
    <span class="font-semibold">工艺备注</span> · <span class="whitespace-pre-wrap">{{ note.trim() }}</span>
  </p>
</template>
