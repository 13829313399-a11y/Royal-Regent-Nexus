<script setup lang="ts">
import { Info } from '@lucide/vue'
import { armLabels } from '@/lib/injectionSchedulingPresentation'
import type { InjectionMachine } from '@/types/injectionScheduling'

defineProps<{ machine: InjectionMachine }>()
const emit = defineEmits<{ open: [machineId: string] }>()
</script>

<template>
  <button
    type="button"
    class="grid size-6 place-items-center rounded-md border border-slate-200 bg-white text-slate-500 transition hover:border-teal-200 hover:text-teal-700"
    :aria-label="`查看${machine.name}机台能力`"
    :title="`${machine.capability.machineClass} · ${machine.capability.shotCapacityGrams}g · ${armLabels[machine.capability.armType]}`"
    @click.stop="emit('open', machine.id)"
  >
    <Info class="size-3" aria-hidden="true" />
  </button>
</template>
