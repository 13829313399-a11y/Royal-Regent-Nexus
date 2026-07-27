<script setup lang="ts">
type ScheduleKpiTone = 'teal' | 'blue' | 'red' | 'green' | 'amber'

interface ScheduleKpiItem {
  id: string
  label: string
  value: string
  helper: string
  tone: ScheduleKpiTone
  badge?: string
}

defineProps<{
  items: ScheduleKpiItem[]
}>()

const toneStyles: Record<ScheduleKpiTone, {
  accent: string
  badge: string
}> = {
  teal: {
    accent: 'bg-[#0F766E]',
    badge: 'bg-[#E6F7F4] text-[#0F766E]',
  },
  blue: {
    accent: 'bg-[#2563EB]',
    badge: 'bg-[#EAF1FF] text-[#2563EB]',
  },
  red: {
    accent: 'bg-[#DC2626]',
    badge: 'bg-[#FEECEC] text-[#DC2626]',
  },
  green: {
    accent: 'bg-[#15803D]',
    badge: 'bg-[#EAF8EE] text-[#15803D]',
  },
  amber: {
    accent: 'bg-[#D97706]',
    badge: 'bg-[#FFF4D8] text-[#9A5B05]',
  },
}
</script>

<template>
  <section
    class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5"
    aria-label="排产关键指标"
    role="list"
    data-testid="schedule-kpi-strip"
  >
    <article
      v-for="item in items"
      :key="item.id"
      class="relative h-[93px] min-h-[93px] min-w-0 overflow-hidden rounded-xl border border-[#DDE5E8] bg-white py-3 pl-8 pr-3.5 shadow-[0_10px_28px_-24px_rgba(15,23,42,0.28)]"
      role="listitem"
      :aria-label="`${item.label}：${item.value}。${item.helper}`"
      :data-testid="`schedule-kpi-${item.id}`"
    >
      <span
        class="absolute bottom-3 left-3 top-3 w-2 rounded-full"
        :class="toneStyles[item.tone].accent"
        aria-hidden="true"
      />

      <div class="flex h-5 min-w-0 items-center justify-between gap-2">
        <span class="min-w-0 truncate text-[14px] font-medium leading-5 text-[#64748B]">
          {{ item.label }}
        </span>
        <span
          v-if="item.badge"
          class="inline-flex h-5 max-w-[52%] shrink-0 items-center truncate rounded-full px-2 text-[11px] font-semibold leading-none"
          :class="toneStyles[item.tone].badge"
        >
          {{ item.badge }}
        </span>
      </div>

      <div class="mt-1 truncate text-[27px] font-bold leading-[27px] tracking-[-0.025em] text-[#0F172A] tabular-nums">
        {{ item.value }}
      </div>
      <p class="mt-0.5 truncate text-[10.5px] leading-[14px] text-[#64748B]" :title="item.helper">
        {{ item.helper }}
      </p>
    </article>
  </section>
</template>
