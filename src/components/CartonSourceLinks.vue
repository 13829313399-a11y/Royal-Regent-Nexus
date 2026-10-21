<script setup lang="ts">
import { RouterLink } from 'vue-router'
import { sourceRequestRoute, sourceDeliveryRoute, sourceKindLabel, type CartonSourceRequest } from '@/features/carton-procurement/sourceLinks'
defineProps<{ factoryId: string; sources?: CartonSourceRequest[]; deliveryId?: string | null; supplier?: boolean; marks?: boolean }>()
</script>
<template>
  <div v-if="sources?.length || deliveryId" class="flex min-w-0 flex-wrap gap-x-3 gap-y-1 text-xs" aria-label="关联来源">
    <template v-for="source in sources" :key="source.id">
      <RouterLink :to="sourceRequestRoute(factoryId, source, supplier)" class="break-all font-semibold text-teal-700 hover:underline">{{ sourceKindLabel(source.kind) }} {{ source.request_no }}</RouterLink>
      <RouterLink v-if="marks && !supplier" :to="sourceRequestRoute(factoryId, source, false, true)" class="text-teal-700 hover:underline">本单箱唛</RouterLink>
    </template>
    <RouterLink v-if="deliveryId && !supplier" :to="sourceDeliveryRoute(factoryId, deliveryId)" class="font-semibold text-teal-700 hover:underline">原送货与验收记录</RouterLink>
  </div>
</template>
