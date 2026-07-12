<script setup lang="ts">
import type { Tone } from '@/data/enterpriseMock'
import { crossFactoryItems } from '@/data/enterpriseMock'
import SectionPanel from '@/components/common/SectionPanel.vue'

const dotClasses: Record<Tone, string> = {
  teal: 'bg-teal-700',
  blue: 'bg-blue-600',
  amber: 'bg-amber-600',
  red: 'bg-red-700',
  slate: 'bg-slate-500',
  green: 'bg-emerald-700',
}
</script>

<template>
  <SectionPanel title="跨厂区事项" subtitle="按 SLA 排序的重点事项">
    <div class="space-y-7">
      <div v-for="(item, index) in crossFactoryItems" :key="item.title" class="relative pl-8">
        <span
          class="absolute left-0 top-1.5 size-3 rounded-full ring-4 ring-white shadow-sm"
          :class="dotClasses[item.tone]"
        />
        <span
          v-if="index !== crossFactoryItems.length - 1"
          class="absolute left-[5px] top-5 h-12 w-px bg-gradient-to-b from-slate-300 to-slate-100"
        />
        <h3 class="text-sm font-semibold text-slate-950">{{ item.title }}</h3>
        <p class="mt-1 text-xs text-slate-500">{{ item.meta }}</p>
      </div>
    </div>
  </SectionPanel>
</template>
