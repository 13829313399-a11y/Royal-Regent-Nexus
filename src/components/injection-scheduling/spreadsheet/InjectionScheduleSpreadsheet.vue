<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import ScheduleColumnChooser from './ScheduleColumnChooser.vue'
import ScheduleMachineGroupRow from './ScheduleMachineGroupRow.vue'
import ScheduleOrderRow from './ScheduleOrderRow.vue'
import ScheduleRowContextMenu from './ScheduleRowContextMenu.vue'
import ScheduleSpreadsheetHeader from './ScheduleSpreadsheetHeader.vue'
import ScheduleSpreadsheetToolbar from './ScheduleSpreadsheetToolbar.vue'
import {
  defaultScheduleSpreadsheetWidths,
  scheduleColumnsForScheme,
  type ScheduleSpreadsheetColumnKey,
} from './scheduleSpreadsheetColumns'
import type {
  InjectionMachine,
  ScheduleFieldScheme,
  ScheduleTask,
  SchedulingDensity,
  SchedulingFilters,
  SchedulingViewMode,
} from '@/types/injectionScheduling'

const props = defineProps<{
  factoryId: string
  machines: InjectionMachine[]
  tasksByMachine: Map<string, ScheduleTask[]>
  selectedTaskId: string
  viewMode: SchedulingViewMode
  density: SchedulingDensity
  fieldScheme: ScheduleFieldScheme
  filters: SchedulingFilters
  backlogCount: number
  bigScreen: boolean
}>()

const emit = defineEmits<{
  'update:viewMode': [value: SchedulingViewMode]
  'update:density': [value: SchedulingDensity]
  'update:fieldScheme': [value: ScheduleFieldScheme]
  'update:filters': [value: SchedulingFilters]
  selectTask: [taskId: string]
  selectMachine: [machineId: string]
  requestMove: [taskId: string, targetMachineId: string, targetIndex?: number]
  nudgeTask: [taskId: string, direction: 'up' | 'down']
  openBacklog: []
  enterBigScreen: []
}>()

const rootRef = ref<HTMLElement | null>(null)
const scrollRef = ref<HTMLElement | null>(null)
const toolbarRef = ref<InstanceType<typeof ScheduleSpreadsheetToolbar> | null>(null)
const columnChooserOpen = ref(false)
const hiddenColumns = ref<ScheduleSpreadsheetColumnKey[]>([])
const widths = reactive<Record<ScheduleSpreadsheetColumnKey, number>>({
  ...defaultScheduleSpreadsheetWidths,
})
const collapsedMachines = ref(new Set<string>())
const contextMenu = reactive({ open: false, x: 0, y: 0, taskId: '' })
const autoScrollPaused = ref(false)
let bigScreenTimer: ReturnType<typeof window.setInterval> | undefined
let bigScreenIndex = 0

const effectiveScheme = computed(() => props.bigScreen ? 'screen' : props.fieldScheme)
const schemeColumns = computed(() => scheduleColumnsForScheme(effectiveScheme.value))
const availableColumnKeys = computed(() => schemeColumns.value.map((column) => column.key))
const activeColumns = computed(() => {
  const visible = schemeColumns.value.filter((column) => !hiddenColumns.value.includes(column.key))
  return visible.length ? visible : schemeColumns.value.slice(0, 1)
})
const activeColumnSignature = computed(() => activeColumns.value.map((column) => column.key).join('|'))
const frozenOffsets = computed(() => {
  const result: Record<string, number> = {}
  let left = 0
  for (const column of activeColumns.value) {
    if (!column.frozen) continue
    result[column.key] = left
    left += widths[column.key]
  }
  return result
})
const tableWidth = computed(() => activeColumns.value.reduce((total, column) => total + widths[column.key], 0))

function preferenceKey(suffix: string) {
  return `rr:injection-scheduling:${props.factoryId}:${suffix}`
}

function loadPreferences() {
  try {
    const storedHidden = JSON.parse(window.localStorage.getItem(preferenceKey('hidden-columns')) || '[]')
    if (Array.isArray(storedHidden)) {
      const validKeys = new Set(Object.keys(defaultScheduleSpreadsheetWidths))
      hiddenColumns.value = storedHidden.filter((key): key is ScheduleSpreadsheetColumnKey => typeof key === 'string' && validKeys.has(key))
    }
    const storedWidths = JSON.parse(window.localStorage.getItem(preferenceKey('column-widths')) || '{}')
    if (storedWidths && typeof storedWidths === 'object') {
      for (const column of scheduleColumnsForScheme('full')) {
        const value = Number(storedWidths[column.key])
        if (Number.isFinite(value)) widths[column.key] = Math.max(column.minWidth, Math.min(column.maxWidth, value))
      }
    }
  } catch {
    hiddenColumns.value = []
  }
}

function savePreferences() {
  window.localStorage.setItem(preferenceKey('hidden-columns'), JSON.stringify(hiddenColumns.value))
  window.localStorage.setItem(preferenceKey('column-widths'), JSON.stringify(widths))
}

function toggleMachine(machineId: string) {
  const next = new Set(collapsedMachines.value)
  if (next.has(machineId)) next.delete(machineId)
  else next.add(machineId)
  collapsedMachines.value = next
}

function expandAll() {
  collapsedMachines.value = new Set()
}

function collapseAll() {
  collapsedMachines.value = new Set(props.machines.map((machine) => machine.id))
}

function toggleColumn(key: ScheduleSpreadsheetColumnKey) {
  if (!availableColumnKeys.value.includes(key)) return
  const next = new Set(hiddenColumns.value)
  if (next.has(key)) next.delete(key)
  else if (activeColumns.value.length > 1) next.add(key)
  hiddenColumns.value = [...next]
  savePreferences()
}

function resetColumns() {
  hiddenColumns.value = []
  Object.assign(widths, defaultScheduleSpreadsheetWidths)
  savePreferences()
}

function resizeColumn(key: ScheduleSpreadsheetColumnKey, width: number) {
  widths[key] = Math.round(width)
  savePreferences()
}

function tasksForMachine(machineId: string) {
  return props.tasksByMachine.get(machineId) ?? []
}

function moveTask(taskId: string, machineId: string, targetIndex?: number) {
  if (props.bigScreen) return
  const task = [...props.tasksByMachine.values()].flat().find((item) => item.id === taskId)
  if (!task || task.current || task.locked) return
  emit('requestMove', taskId, machineId, targetIndex)
}

function navigateTask(taskId: string, direction: 'up' | 'down') {
  const taskIds = props.machines.flatMap((machine) => (
    collapsedMachines.value.has(machine.id) ? [] : tasksForMachine(machine.id).map((task) => task.id)
  ))
  const index = taskIds.indexOf(taskId)
  const nextTaskId = taskIds[index + (direction === 'up' ? -1 : 1)]
  if (!nextTaskId) return
  document.getElementById(`schedule-task-${nextTaskId}`)?.focus()
}

function openContextMenu(event: MouseEvent, taskId: string) {
  const menuWidth = 176
  const menuHeight = 156
  contextMenu.x = Math.min(event.clientX, window.innerWidth - menuWidth - 8)
  contextMenu.y = Math.min(event.clientY, window.innerHeight - menuHeight - 8)
  contextMenu.taskId = taskId
  contextMenu.open = true
}

function contextTask() {
  return [...props.tasksByMachine.values()].flat().find((task) => task.id === contextMenu.taskId)
}

function handleShortcut(event: KeyboardEvent) {
  if ((event.ctrlKey || event.metaKey) && event.key.toLocaleLowerCase() === 'f') {
    event.preventDefault()
    toolbarRef.value?.focusSearch()
  }
}

function stopBigScreenRotation() {
  if (bigScreenTimer) window.clearInterval(bigScreenTimer)
  bigScreenTimer = undefined
}

function startBigScreenRotation() {
  stopBigScreenRotation()
  if (!props.bigScreen || props.machines.length < 2) return
  bigScreenTimer = window.setInterval(() => {
    if (autoScrollPaused.value || !scrollRef.value) return
    bigScreenIndex = (bigScreenIndex + 1) % props.machines.length
    const machineId = props.machines[bigScreenIndex]?.id
    const machineRow = [...scrollRef.value.querySelectorAll<HTMLElement>('[data-machine-id]')]
      .find((element) => element.dataset.machineId === machineId)
    machineRow?.scrollIntoView({ behavior: 'smooth', block: 'start', inline: 'nearest' })
  }, 8000)
}

function saveScroll(viewMode: SchedulingViewMode = props.viewMode) {
  if (!scrollRef.value) return
  window.sessionStorage.setItem(preferenceKey(`scroll:${viewMode}`), JSON.stringify({
    top: scrollRef.value.scrollTop,
    left: scrollRef.value.scrollLeft,
  }))
}

async function restoreScroll() {
  await nextTick()
  if (!scrollRef.value) return
  try {
    const stored = JSON.parse(window.sessionStorage.getItem(preferenceKey(`scroll:${props.viewMode}`)) || '{}')
    scrollRef.value.scrollTop = Number(stored.top) || 0
    scrollRef.value.scrollLeft = Number(stored.left) || 0
  } catch {
    scrollRef.value.scrollTop = 0
    scrollRef.value.scrollLeft = 0
  }
}

watch(() => props.filters.search, (search) => {
  if (search.trim()) expandAll()
})
watch(() => props.bigScreen, (active) => {
  columnChooserOpen.value = false
  if (active) expandAll()
  startBigScreenRotation()
})
watch(() => props.viewMode, (_viewMode, previousViewMode) => {
  saveScroll(previousViewMode)
  void restoreScroll()
})
watch(() => props.factoryId, () => {
  loadPreferences()
  collapsedMachines.value = new Set()
  void restoreScroll()
})

onMounted(() => {
  loadPreferences()
  void restoreScroll()
  window.addEventListener('keydown', handleShortcut)
  startBigScreenRotation()
})

onBeforeUnmount(() => {
  saveScroll()
  savePreferences()
  stopBigScreenRotation()
  window.removeEventListener('keydown', handleShortcut)
})

defineExpose({ expandAll, collapseAll })
</script>

<template>
  <section
    ref="rootRef"
    class="relative grid min-h-0 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm"
    :class="[bigScreen ? 'grid-rows-[minmax(0,1fr)] border-slate-800 bg-[#071a19]' : 'grid-rows-[40px_minmax(0,1fr)]']"
    data-testid="injection-schedule-spreadsheet"
  >
    <ScheduleSpreadsheetToolbar
      v-if="!bigScreen"
      ref="toolbarRef"
      :view-mode="viewMode"
      :density="density"
      :field-scheme="fieldScheme"
      :filters="filters"
      :backlog-count="backlogCount"
      :column-chooser-open="columnChooserOpen"
      @update:view-mode="emit('update:viewMode', $event)"
      @update:density="emit('update:density', $event)"
      @update:field-scheme="emit('update:fieldScheme', $event)"
      @update:filters="emit('update:filters', $event)"
      @toggle-column-chooser="columnChooserOpen = !columnChooserOpen"
      @expand-all="expandAll"
      @collapse-all="collapseAll"
      @open-backlog="emit('openBacklog')"
      @enter-big-screen="emit('enterBigScreen')"
    />

    <ScheduleColumnChooser
      :open="columnChooserOpen && !bigScreen"
      :hidden-columns="hiddenColumns"
      :available-columns="availableColumnKeys"
      @close="columnChooserOpen = false"
      @toggle="toggleColumn"
      @reset="resetColumns"
    />

    <div
      v-if="viewMode === 'spreadsheet' || bigScreen"
      ref="scrollRef"
      class="min-h-0 overflow-auto [overscroll-behavior:contain] [scrollbar-gutter:stable] [scrollbar-width:thin]"
      data-testid="schedule-spreadsheet-scroll"
      @pointerenter="autoScrollPaused = true"
      @pointerleave="autoScrollPaused = false"
      @focusin="autoScrollPaused = true"
      @focusout="autoScrollPaused = false"
    >
      <table
        class="border-separate border-spacing-0 table-fixed"
        :class="bigScreen ? 'text-slate-100' : 'text-slate-800'"
        :style="{ width: `${tableWidth}px`, minWidth: `${tableWidth}px` }"
        aria-label="注塑机台日排程表"
      >
        <ScheduleSpreadsheetHeader
          :columns="activeColumns"
          :widths="widths"
          :frozen-offsets="frozenOffsets"
          @resize="resizeColumn"
        />
        <tbody
          v-for="machine in machines"
          :key="machine.id"
          class="[content-visibility:auto] [contain-intrinsic-size:120px]"
        >
          <ScheduleMachineGroupRow
            :machine="machine"
            :tasks="tasksForMachine(machine.id)"
            :column-count="activeColumns.length"
            :collapsed="collapsedMachines.has(machine.id)"
            :big-screen="bigScreen"
            @toggle="toggleMachine"
            @select="emit('selectMachine', $event)"
            @drop-task="(taskId, machineId) => moveTask(taskId, machineId)"
          />
          <ScheduleOrderRow
            v-for="(task, rowIndex) in collapsedMachines.has(machine.id) ? [] : tasksForMachine(machine.id)"
            :key="task.id"
            v-memo="[task.id, task.sequence, task.risk, task.current, selectedTaskId === task.id, density, effectiveScheme, activeColumnSignature, tableWidth]"
            :task="task"
            :machine="machine"
            :previous-task="tasksForMachine(machine.id)[rowIndex - 1]"
            :row-index="rowIndex"
            :columns="activeColumns"
            :widths="widths"
            :frozen-offsets="frozenOffsets"
            :density="density"
            :selected="selectedTaskId === task.id"
            :big-screen="bigScreen"
            @select="emit('selectTask', $event)"
            @navigate="navigateTask"
            @nudge="(taskId, direction) => emit('nudgeTask', taskId, direction)"
            @drop-task="moveTask"
            @contextmenu="openContextMenu"
          />
        </tbody>
      </table>
      <div v-if="!machines.length" class="grid h-full min-h-72 place-items-center p-8 text-center text-sm text-slate-500">
        没有匹配当前筛选条件的机台或任务。
      </div>
    </div>

    <slot v-else name="timeline" />

    <ScheduleRowContextMenu
      :open="contextMenu.open"
      :x="contextMenu.x"
      :y="contextMenu.y"
      :current="Boolean(bigScreen || contextTask()?.current || contextTask()?.locked)"
      @close="contextMenu.open = false"
      @inspect="contextTask() && emit('selectTask', contextMenu.taskId)"
      @move="contextTask() && emit('selectTask', contextMenu.taskId)"
      @nudge="(direction) => emit('nudgeTask', contextMenu.taskId, direction)"
    />
  </section>
</template>
