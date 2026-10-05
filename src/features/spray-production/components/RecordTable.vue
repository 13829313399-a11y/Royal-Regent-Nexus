<script setup lang="ts">
import { getCurrentInstance } from 'vue'
import { number, stateLabel, type Entity } from '../contracts'
defineProps<{ rows: Entity[]; columns: { key: string; label: string; numeric?: boolean }[]; selected?: string | null; empty?: string }>()
const instance=getCurrentInstance()
const emit = defineEmits<{ select: [row: Entity] }>()
function display(row: Entity, key: string, numeric = false) {
  const value = row[key]
  if (value === null || value === undefined || value === '') return '—'
  if (numeric) return number(value)
  if (key === 'status' || key === 'state' || key === 'kind') return stateLabel[String(value)] ?? value
  return typeof value === 'object' ? '查看明细' : value
}
</script>
<template>
  <div class="spray-table-wrap">
    <table class="spray-table"><thead><tr><th v-for="column in columns" :key="column.key" :class="{ numeric: column.numeric }" scope="col">{{ column.label }}</th><th v-if="$slots.actions" scope="col">操作</th></tr></thead>
      <tbody><tr v-for="row in rows" :key="row.id" :class="{ selected: row.id === selected }" @click="emit('select', row)">
        <td v-for="(column, index) in columns" :key="column.key" :class="{ numeric: column.numeric }"><button v-if="index === 0 && instance?.vnode.props?.onSelect" class="spray-text-button" @click.stop="emit('select', row)">{{ display(row, column.key, column.numeric) }}</button><span v-else>{{ display(row, column.key, column.numeric) }}</span></td>
        <td v-if="$slots.actions"><slot name="actions" :row="row" /></td>
      </tr></tbody>
    </table>
    <div v-if="!rows.length" class="spray-empty"><strong>{{ empty ?? '当前没有记录' }}</strong><p>登记业务后，这里将显示可追踪的真实记录。</p></div>
  </div>
</template>
