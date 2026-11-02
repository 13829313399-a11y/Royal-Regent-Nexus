<script setup lang="ts">
import CartonOrderImportDialog from './CartonOrderImportDialog.vue'
import type { BatchResult } from '@/api/cartonBatchOrders'
defineProps<{ open: boolean; file: File | null; factoryId: string; viewerKey: string; identityKey: string }>()
const emit = defineEmits<{ 'update:open': [value: boolean]; saved: [result: BatchResult] }>()
</script>

<template>
  <CartonOrderImportDialog v-bind="$props" mode="SPECIAL" @update:open="emit('update:open', $event)" @saved="emit('saved', $event)" />
</template>
