<script setup lang="ts">
import { Boxes, Database, Settings2, SquareTerminal, Waypoints } from '@lucide/vue'
import type { InjectionSectionId } from '@/data/injectionSchedulingMock'
import { injectionSectionNav } from '@/data/injectionSchedulingMock'

defineProps<{
  activeSection: InjectionSectionId
}>()

defineEmits<{
  (e: 'change', section: InjectionSectionId): void
}>()

const sectionIcons = {
  dashboard: Boxes,
  'data-center': Database,
  execution: SquareTerminal,
  reporting: Waypoints,
  config: Settings2,
} as const
</script>

<template>
  <nav class="grid gap-3 lg:grid-cols-5">
    <button
      v-for="section in injectionSectionNav"
      :key="section.id"
      type="button"
      class="rounded-2xl border px-4 py-4 text-left transition-all"
      :class="section.id === activeSection
        ? 'border-slate-950 bg-slate-950 text-white shadow-[0_14px_28px_rgba(15,23,42,0.18)]'
        : 'border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50'"
      @click="$emit('change', section.id)"
    >
      <div class="flex items-start gap-3">
        <span
          class="flex size-10 shrink-0 items-center justify-center rounded-2xl"
          :class="section.id === activeSection ? 'bg-white/12 text-white' : 'bg-slate-100 text-slate-700'"
        >
          <component :is="sectionIcons[section.id]" class="size-4" aria-hidden="true" />
        </span>
        <div class="min-w-0">
          <h3 class="font-semibold">{{ section.label }}</h3>
          <p
            class="mt-2 text-xs leading-5"
            :class="section.id === activeSection ? 'text-slate-300' : 'text-slate-500'"
          >
            {{ section.summary }}
          </p>
        </div>
      </div>
    </button>
  </nav>
</template>
