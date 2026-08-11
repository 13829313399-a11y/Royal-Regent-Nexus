<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ChevronDown, ChevronUp, Columns3, Pin, PinOff, RotateCcw, Save, Trash2, X } from '@lucide/vue'
import { getColumnMoveDecision, getFrozenColumnToggleDecision, normalizeSchedulingColumnOrder, schedulingColumns, schedulingFrozenKeysByPreset, uploadedPlanFieldCount } from '../composables/useSchedulingColumns'
import { defaultSchedulingDensity, type SchedulingDensityMode } from '../config/schedulingLayout'
import type { SchedulingCustomPreset } from '../config/schedulingPreferences'
import type { ColumnPreset } from '../types'

const props = withDefaults(defineProps<{
  open: boolean
  preset: ColumnPreset
  visibleKeys: string[]
  widths: Record<string, number>
  columnOrder: string[]
  density?: SchedulingDensityMode
  frozenKeys?: string[]
  customPresets?: SchedulingCustomPreset[]
  activeCustomPresetId?: string | null
}>(), {
  density: defaultSchedulingDensity,
  frozenKeys: undefined,
  customPresets: () => [],
  activeCustomPresetId: null,
})
const emit = defineEmits<{
  close: []
  preset: [value: ColumnPreset]
  density: [value: SchedulingDensityMode]
  toggle: [key: string]
  toggleFreeze: [key: string]
  reset: []
  resize: [key: string, width: number]
  move: [key: string, direction: -1 | 1]
  saveCustomPreset: [name: string]
  applyCustomPreset: [id: string]
  deleteCustomPreset: [id: string]
}>()
const menuRoot = ref<HTMLElement | null>(null)
const menuAnnouncement = ref('')
const customPresetName = ref('')
let previousFocus: HTMLElement | null = null
let restoreFocusOnClose = true
const presets: Array<{ key: ColumnPreset; label: string; detail: string }> = [
  { key: 'planner', label: '计划员', detail: '交期、队列与物料' }, { key: 'production', label: '生产', detail: '进度与现场回报' },
  { key: 'fit', label: '资格适配', detail: '安数、射胶、机械手、夹具' }, { key: 'full', label: '完整字段', detail: `50 列（其中上传来源 ${uploadedPlanFieldCount} 字段）` },
]
const effectiveFrozenKeys = computed(() => props.frozenKeys ?? [...schedulingFrozenKeysByPreset[props.preset]])
const orderedColumns = computed(() => normalizeSchedulingColumnOrder(props.columnOrder, props.preset, effectiveFrozenKeys.value)
  .map((key) => schedulingColumns.find((column) => String(column.key) === key))
  .filter((column): column is typeof schedulingColumns[number] => Boolean(column)))
const moveDecisions = computed(() => new Map(orderedColumns.value.flatMap((column) => ([-1, 1] as const).map((direction) => [
  `${String(column.key)}:${direction}`,
  getColumnMoveDecision(props.columnOrder, String(column.key), direction, props.preset, effectiveFrozenKeys.value),
]))))
const freezeDecisions = computed(() => new Map(orderedColumns.value.map((column) => [
  String(column.key),
  getFrozenColumnToggleDecision(effectiveFrozenKeys.value, String(column.key), props.visibleKeys, props.widths),
])))
function moveDecision(key: string, direction: -1 | 1) {
  return moveDecisions.value.get(`${key}:${direction}`) ?? { allowed: false, reason: '字段不可移动', targetKey: null }
}
function freezeDecision(key: string) {
  return freezeDecisions.value.get(key) ?? { allowed: false, reason: '字段不可冻结' }
}
function saveCustomPreset() {
  const name = customPresetName.value.trim()
  if (!name) return
  emit('saveCustomPreset', name)
  customPresetName.value = ''
}

function menuItems() {
  return menuRoot.value
    ? Array.from(menuRoot.value.querySelectorAll<HTMLElement>('[role="menuitemradio"], [role="menuitemcheckbox"], [role="menuitem"]'))
      .filter((item) => !('disabled' in item) || !(item as HTMLButtonElement).disabled)
    : []
}

function handleMenuKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    event.stopPropagation()
    emit('close')
    return
  }
  if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return

  const current = document.activeElement as HTMLElement | null
  const menuItemSelector = '[role="menuitemradio"], [role="menuitemcheckbox"], [role="menuitem"]'
  if (current !== menuRoot.value && !current?.matches(menuItemSelector)) return
  const items = menuItems()
  if (!items.length) return
  event.preventDefault()
  const currentIndex = current ? items.indexOf(current) : -1
  let targetIndex = 0
  if (currentIndex < 0 || event.key === 'Home') targetIndex = 0
  else if (event.key === 'End') targetIndex = items.length - 1
  else if (event.key === 'ArrowDown') targetIndex = (currentIndex + 1) % items.length
  else targetIndex = (currentIndex - 1 + items.length) % items.length
  if (currentIndex < 0 && (event.key === 'ArrowUp' || event.key === 'End')) targetIndex = items.length - 1
  items[targetIndex]?.focus({ preventScroll: true })
}

function handleDocumentPointerDown(event: PointerEvent) {
  if (!props.open || !menuRoot.value || !(event.target instanceof Node)) return
  if (menuRoot.value.contains(event.target)) return
  if (event.target instanceof Element && event.target.closest('[aria-controls="column-preset-menu"]')) return
  restoreFocusOnClose = false
  emit('close')
}

watch(() => props.open, async (open) => {
  if (typeof document === 'undefined') return
  if (open) {
    previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    restoreFocusOnClose = true
    menuAnnouncement.value = '列设置菜单已打开，使用方向键浏览，按 Escape 关闭。'
    await nextTick()
    if (!props.open) return
    menuRoot.value?.querySelector<HTMLElement>('[role="menuitemradio"]')?.focus({ preventScroll: true })
    return
  }
  menuAnnouncement.value = ''
  if (restoreFocusOnClose) previousFocus?.focus({ preventScroll: true })
  previousFocus = null
  restoreFocusOnClose = true
}, { flush: 'post', immediate: true })

onMounted(() => document.addEventListener('pointerdown', handleDocumentPointerDown, true))
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', handleDocumentPointerDown, true)
  previousFocus?.focus({ preventScroll: true })
})
</script>

<template>
  <Transition name="popover">
  <aside v-if="open" id="column-preset-menu" ref="menuRoot" class="column-menu" role="menu" aria-label="列设置菜单" tabindex="-1" @keydown="handleMenuKeydown">
    <p class="scheduling-sr-only menu-live-announcement" role="status" aria-live="polite">{{ menuAnnouncement }}</p>
    <header><div><Columns3 :size="17" /><strong>字段与视图预设</strong></div><button role="menuitem" aria-label="关闭" @click="emit('close')"><X :size="17" /></button></header>
    <section class="density-setting" aria-label="表格密度"><span>显示密度</span><div><button role="menuitem" aria-label="使用舒适密度" :aria-pressed="density === 'comfortable'" :class="{ active: density === 'comfortable' }" @click="emit('density', 'comfortable')">舒适</button><button role="menuitem" aria-label="使用紧凑密度" :aria-pressed="density === 'compact'" :class="{ active: density === 'compact' }" @click="emit('density', 'compact')">紧凑</button></div></section>
    <div class="preset-list"><button v-for="item in presets" :key="item.key" role="menuitemradio" :aria-checked="!activeCustomPresetId && preset === item.key" :class="{ active: !activeCustomPresetId && preset === item.key }" @click="emit('preset', item.key)"><strong>{{ item.label }}</strong><span>{{ item.detail }}</span></button></div>
    <section v-if="customPresets.length" class="custom-preset-list" aria-label="自定义视图"><span>我的视图</span><div v-for="item in customPresets" :key="item.id"><button role="menuitemradio" :aria-checked="activeCustomPresetId === item.id" :class="{ active: activeCustomPresetId === item.id }" @click="emit('applyCustomPreset', item.id)"><strong>{{ item.name }}</strong><small>{{ item.layout.density === 'comfortable' ? '舒适' : '紧凑' }} · {{ item.layout.frozenKeys.length }} 个冻结列</small></button><button role="menuitem" :aria-label="`删除自定义视图${item.name}`" @click="emit('deleteCustomPreset', item.id)"><Trash2 :size="13" /></button></div></section>
    <section class="custom-preset-save"><input v-model="customPresetName" data-testid="custom-preset-name" maxlength="40" placeholder="自定义视图名称" aria-label="自定义视图名称" @keydown.enter.prevent="saveCustomPreset" /><button role="menuitem" aria-label="保存当前布局为自定义视图" :disabled="!customPresetName.trim()" @click="saveCustomPreset"><Save :size="13" />保存当前布局</button></section>
    <div class="column-menu-title"><span>显示字段 · {{ visibleKeys.length }}/{{ schedulingColumns.length }}</span><button role="menuitem" @click="emit('reset')"><RotateCcw :size="13" />重置</button></div>
    <div class="column-list">
      <label v-for="column in orderedColumns" :key="column.key" role="none"><input type="checkbox" role="menuitemcheckbox" :aria-checked="visibleKeys.includes(String(column.key))" :checked="visibleKeys.includes(String(column.key))" @change="emit('toggle', String(column.key))" /><span>{{ column.title }}<small>{{ column.group }}</small></span><span class="column-row-actions"><button type="button" role="menuitem" :class="{ active: effectiveFrozenKeys.includes(String(column.key)) }" :aria-label="`${effectiveFrozenKeys.includes(String(column.key)) ? '取消冻结' : '冻结'}${column.title}`" :disabled="!freezeDecision(String(column.key)).allowed" :title="freezeDecision(String(column.key)).reason || (effectiveFrozenKeys.includes(String(column.key)) ? '取消冻结' : '冻结到左侧')" @click.prevent="emit('toggleFreeze', String(column.key))"><PinOff v-if="effectiveFrozenKeys.includes(String(column.key))" :size="13" /><Pin v-else :size="13" /></button><input class="width-input" type="number" min="54" max="420" :value="widths[String(column.key)] ?? column.width" :aria-label="`${column.title}列宽`" @change="emit('resize', String(column.key), Number(($event.target as HTMLInputElement).value))" /><button type="button" role="menuitem" :aria-label="`${column.title}前移`" :disabled="!moveDecision(String(column.key), -1).allowed" :title="moveDecision(String(column.key), -1).reason" @click.prevent="emit('move', String(column.key), -1)"><ChevronUp :size="13" /></button><button type="button" role="menuitem" :aria-label="`${column.title}后移`" :disabled="!moveDecision(String(column.key), 1).allowed" :title="moveDecision(String(column.key), 1).reason" @click.prevent="emit('move', String(column.key), 1)"><ChevronDown :size="13" /></button></span></label>
    </div>
    <p class="layout-storage-note">视图设置按当前账号和厂区保存，仅保存在当前浏览器，不跨设备同步。</p>
  </aside>
  </Transition>
</template>
