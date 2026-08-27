<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import { factoryContexts, isFactoryContextId } from '@/data/enterpriseMock'
import InjectionSchedulingPage from '@/features/injection-scheduling/InjectionSchedulingPage.vue'

const route = useRoute()

const factoryId = computed(() => {
  const value = String(route.query.factory ?? '')
  return isFactoryContextId(value) ? value : 'huaxing'
})

const factoryName = computed(() => (
  factoryContexts.find((factory) => factory.id === factoryId.value)?.shortName ?? '当前厂区'
))

</script>

<template>
  <InjectionSchedulingPage :factory-id="factoryId" :factory-name="factoryName" />
</template>
