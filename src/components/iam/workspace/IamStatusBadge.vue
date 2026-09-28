<script setup lang="ts">
import type { StatusPresentation } from './iam-status'
defineProps<{ presentation: StatusPresentation }>()
</script>
<template>
  <span class="iamx-badge" :data-tone="presentation.tone"
    ><i aria-hidden="true" />{{ presentation.label }}</span
  >
</template>
