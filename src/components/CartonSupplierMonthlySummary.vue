<script setup lang="ts">
import CartonSettlementOverview from './CartonSettlementOverview.vue'

defineProps<{ factories?: { factory_id: string }[]; search?: string; viewerKey?: string; refreshKey?: number }>()
</script>

<template>
  <CartonSettlementOverview supplier :factories="factories" :search="search" :viewer-key="viewerKey" :refresh-key="refreshKey" />
</template>
