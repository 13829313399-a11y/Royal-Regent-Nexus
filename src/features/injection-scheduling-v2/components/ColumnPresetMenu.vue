<script setup lang="ts">
import { ChevronDown, ChevronUp, Columns3, RotateCcw, X } from '@lucide/vue'
import { schedulingColumns, uploadedPlanFieldCount } from '../composables/useSchedulingColumns'
import type { ColumnPreset } from '../types'

defineProps<{ open: boolean; preset: ColumnPreset; visibleKeys: string[]; widths: Record<string, number> }>()
const emit = defineEmits<{ close: []; preset: [value: ColumnPreset]; toggle: [key: string]; reset: []; resize: [key: string, width: number]; move: [key: string, direction: -1 | 1] }>()
const presets: Array<{ key: ColumnPreset; label: string; detail: string }> = [
  { key: 'planner', label: '计划员', detail: '交期、队列与物料' }, { key: 'production', label: '生产', detail: '进度与现场回报' },
  { key: 'fit', label: '资格适配', detail: '安数、射胶、机械手、夹具' }, { key: 'full', label: '完整字段', detail: `上传计划 ${uploadedPlanFieldCount} 字段全量可见` },
]
</script>

<template>
  <Transition name="popover">
  <aside v-if="open" class="column-menu" aria-label="列设置">
    <header><div><Columns3 :size="17" /><strong>字段与视图预设</strong></div><button aria-label="关闭" @click="emit('close')"><X :size="17" /></button></header>
    <div class="preset-list"><button v-for="item in presets" :key="item.key" :class="{ active: preset === item.key }" @click="emit('preset', item.key)"><strong>{{ item.label }}</strong><span>{{ item.detail }}</span></button></div>
    <div class="column-menu-title"><span>显示字段 · {{ visibleKeys.length }}/{{ schedulingColumns.length }}</span><button @click="emit('reset')"><RotateCcw :size="13" />重置</button></div>
    <div class="column-list">
      <label v-for="column in schedulingColumns" :key="column.key"><input type="checkbox" :checked="visibleKeys.includes(String(column.key))" @change="emit('toggle', String(column.key))" /><span>{{ column.title }}<small>{{ column.group }}</small></span><span class="column-row-actions"><input class="width-input" type="number" min="54" max="420" :value="widths[String(column.key)] ?? column.width" :aria-label="`${column.title}列宽`" @change="emit('resize', String(column.key), Number(($event.target as HTMLInputElement).value))" /><button type="button" :aria-label="`${column.title}前移`" @click.prevent="emit('move', String(column.key), -1)"><ChevronUp :size="13" /></button><button type="button" :aria-label="`${column.title}后移`" @click.prevent="emit('move', String(column.key), 1)"><ChevronDown :size="13" /></button></span></label>
    </div>
  </aside>
  </Transition>
</template>
