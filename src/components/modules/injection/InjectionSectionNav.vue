<script setup lang="ts">
import {
  Boxes,
  ClipboardList,
  Database,
  FileText,
  Package,
  SquareTerminal,
  Waypoints,
} from '@lucide/vue'
import type { InjectionSectionId } from '@/data/injectionSchedulingMock'
import { useInjectionModuleData } from '@/factories/injection/useInjectionModuleData'

defineProps<{
  activeSection: InjectionSectionId
}>()

defineEmits<{
  (e: 'change', section: InjectionSectionId): void
}>()

const { injectionSectionNav } = useInjectionModuleData()

const sectionIcons = {
  'monthly-plan': Boxes,
  'order-import': ClipboardList,
  'smart-scheduling': SquareTerminal,
  'scheduling-results': Waypoints,
  'daily-report': FileText,
  'inbound-orders': Package,
  'master-data': Database,
} as const
</script>

<template>
  <nav class="max-h-[calc(100vh-2rem)] overflow-y-auto rounded-[28px] border border-slate-200 bg-[linear-gradient(180deg,rgba(255,255,255,0.98),rgba(245,248,252,0.98))] p-4 shadow-[0_18px_38px_rgba(15,23,42,0.06)]">
    <div class="mb-4 px-3">
      <p class="text-xs uppercase tracking-[0.24em] text-slate-500">Injection Menu</p>
      <h3 class="mt-3 text-lg font-semibold text-slate-950">注塑排产</h3>
    </div>

    <button
      v-for="section in injectionSectionNav"
      :key="section.id"
      type="button"
      class="flex w-full items-center gap-3 rounded-2xl border border-transparent px-4 py-3 text-left transition-all"
      :class="section.id === activeSection
        ? 'border-sky-100 bg-sky-50 text-slate-950 shadow-[0_10px_22px_rgba(14,165,233,0.10)]'
        : 'text-slate-700 hover:border-slate-200 hover:bg-white'"
      @click="$emit('change', section.id)"
    >
      <span
        class="flex size-9 shrink-0 items-center justify-center rounded-xl"
        :class="section.id === activeSection ? 'bg-sky-500 text-white' : 'bg-slate-100 text-slate-600'"
      >
        <component :is="sectionIcons[section.id]" class="size-4" aria-hidden="true" />
      </span>
      <div class="min-w-0">
        <h3 class="font-medium">{{ section.label }}</h3>
        <p
          class="mt-1 text-xs leading-5"
          :class="section.id === activeSection ? 'text-slate-600' : 'text-slate-500'"
        >
          {{ section.summary }}
        </p>
      </div>
    </button>
  </nav>
</template>
