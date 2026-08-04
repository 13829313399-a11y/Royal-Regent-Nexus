<script setup lang="ts">
import { ChevronDown, ChevronRight, CircleStop } from '@lucide/vue'
import type { ScheduleGridRow } from '../types'

defineProps<{ row: ScheduleGridRow; collapsed: boolean; top: number; width: number; taskCount: number; currentLabel: string; releaseAt: string; dropEnabled: boolean }>()
const emit = defineEmits<{ toggle: [machineId: string]; dropTask: [machineId: string, event: DragEvent] }>()
</script>

<template>
  <tr class="machine-group-row" :class="{ 'drop-enabled': dropEnabled }" :style="{ transform: `translateY(${top}px)`, width: `${width}px` }" @dragover.prevent @drop="emit('dropTask', row.machine.id, $event)">
    <td :style="{ width: `${width}px` }">
      <button class="machine-toggle" :aria-label="collapsed ? '展开机台' : '折叠机台'" @click="emit('toggle', row.machine.id)"><ChevronRight v-if="collapsed" :size="14" /><ChevronDown v-else :size="14" /></button>
      <span class="machine-state" :class="row.machine.status"><CircleStop :size="12" /></span>
      <strong class="machine-code">{{ row.machine.code }}</strong>
      <div class="machine-specs"><span>{{ row.machine.aClass ? `${row.machine.aClass}A` : row.machine.aClassRaw || '安数待复核' }}</span><span>射胶 {{ row.machine.injectionCapacityG ?? '—' }}g</span><span>{{ row.machine.armCapabilities.join(' / ') || '机械手待补充' }}</span><span>{{ row.machine.fixtureCapabilities.join(' / ') || '夹具待补充' }}</span><span v-for="restriction in row.machine.processRestrictions" :key="restriction" class="restriction">{{ restriction }}</span></div>
      <div class="machine-current"><span>当前</span><strong>{{ currentLabel || '无生产任务' }}</strong></div>
      <div class="machine-metrics"><span>队列 <b>{{ taskCount }}</b></span><span>预计释放 <b>{{ releaseAt || '—' }}</b></span></div>
    </td>
  </tr>
</template>
