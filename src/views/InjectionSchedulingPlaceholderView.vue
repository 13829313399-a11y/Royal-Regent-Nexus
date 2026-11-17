<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { ArrowLeft, CalendarClock } from '@lucide/vue'
import { getFactoryScopedRoute } from '@/data/enterpriseMock'
import { useAppStore } from '@/stores/app'

const app = useAppStore()
const back = computed(() => getFactoryScopedRoute('/modules/production', app.activeFactoryId))
</script>

<template>
  <div class="space-y-6">
    <RouterLink :to="back" class="inline-flex items-center gap-2 rounded-md text-sm text-slate-600 hover:text-slate-950 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-teal-600">
      <ArrowLeft class="size-4" aria-hidden="true" />返回生产部模块中心
    </RouterLink>
    <section class="enterprise-panel rounded-xl p-6 sm:p-8" data-testid="injection-placeholder">
      <CalendarClock class="mb-4 size-8 text-teal-700" aria-hidden="true" />
      <h1 data-route-motion-anchor class="text-2xl font-semibold text-slate-950">注塑排产中枢</h1>
      <p class="mt-2 text-sm leading-6 text-slate-600">排产功能待重新设计。</p>
    </section>
  </div>
</template>
