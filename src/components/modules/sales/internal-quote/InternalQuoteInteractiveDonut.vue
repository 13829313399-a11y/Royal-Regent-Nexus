<script setup lang="ts">
import { computed, ref, watch } from 'vue'

type DonutEntry = {
  key: string
  label: string
  amount: number
  color: string
  inactive?: boolean
  detail?: string
}

const props = withDefaults(defineProps<{
  entries: DonutEntry[]
  totalLabel: string
  displayTotal?: number
  unit?: string
  emptyLabel?: string
}>(), {
  displayTotal: undefined,
  unit: 'HKD / PCS',
  emptyLabel: '尚无有效成本',
})

const hoveredKey = ref('')
const pinnedKey = ref('')
const positiveTotal = computed(() => props.entries.reduce(
  (sum, entry) => sum + Math.max(Number(entry.amount) || 0, 0),
  0,
))
const chartTotal = computed(() => props.displayTotal ?? positiveTotal.value)
const activeKey = computed(() => hoveredKey.value || pinnedKey.value)
const activeEntry = computed(() => props.entries.find((entry) => entry.key === activeKey.value))
const centerAmount = computed(() => activeEntry.value?.amount ?? chartTotal.value)

function polarPoint(angle: number, radius: number) {
  const radians = (angle - 90) * Math.PI / 180
  return {
    x: 100 + radius * Math.cos(radians),
    y: 100 + radius * Math.sin(radians),
  }
}

function donutPath(startAngle: number, endAngle: number) {
  const safeEndAngle = Math.min(endAngle, startAngle + 359.999)
  const outerStart = polarPoint(startAngle, 82)
  const outerEnd = polarPoint(safeEndAngle, 82)
  const innerEnd = polarPoint(safeEndAngle, 49)
  const innerStart = polarPoint(startAngle, 49)
  const largeArc = safeEndAngle - startAngle > 180 ? 1 : 0
  return [
    `M ${outerStart.x.toFixed(3)} ${outerStart.y.toFixed(3)}`,
    `A 82 82 0 ${largeArc} 1 ${outerEnd.x.toFixed(3)} ${outerEnd.y.toFixed(3)}`,
    `L ${innerEnd.x.toFixed(3)} ${innerEnd.y.toFixed(3)}`,
    `A 49 49 0 ${largeArc} 0 ${innerStart.x.toFixed(3)} ${innerStart.y.toFixed(3)}`,
    'Z',
  ].join(' ')
}

const slices = computed(() => {
  const positiveEntries = props.entries.filter((entry) => entry.amount > 0)
  const total = positiveTotal.value
  let cursor = 0
  return positiveEntries.map((entry) => {
    const sweep = total > 0 ? entry.amount / total * 360 : 0
    const gap = positiveEntries.length > 1 ? Math.min(1.6, sweep * 0.18) : 0
    const startAngle = cursor + gap / 2
    const endAngle = cursor + sweep - gap / 2
    const midAngle = cursor + sweep / 2
    const offsetPoint = polarPoint(midAngle, 8)
    cursor += sweep
    return {
      ...entry,
      percentage: total > 0 ? entry.amount / total * 100 : 0,
      path: donutPath(startAngle, endAngle),
      offsetX: offsetPoint.x - 100,
      offsetY: offsetPoint.y - 100,
    }
  })
})

function shareFor(amount: number) {
  return positiveTotal.value > 0 ? Math.max(amount, 0) / positiveTotal.value * 100 : 0
}

function setHovered(key: string) {
  hoveredKey.value = key
}

function clearHovered(key: string) {
  if (hoveredKey.value === key) hoveredKey.value = ''
}

function togglePinned(key: string) {
  pinnedKey.value = pinnedKey.value === key ? '' : key
}

watch(
  () => props.entries.map((entry) => entry.key).join('|'),
  () => {
    if (pinnedKey.value && !props.entries.some((entry) => entry.key === pinnedKey.value)) pinnedKey.value = ''
    if (hoveredKey.value && !props.entries.some((entry) => entry.key === hoveredKey.value)) hoveredKey.value = ''
  },
)
</script>

<template>
  <div class="interactive-donut-layout">
    <div class="interactive-donut-chart">
      <svg viewBox="0 0 200 200" role="img" :aria-label="`${totalLabel}分布图，总额 ${chartTotal.toFixed(4)} ${unit}`">
        <circle class="donut-track" cx="100" cy="100" r="65.5" />
        <g v-if="slices.length">
          <path
            v-for="slice in slices"
            :key="slice.key"
            class="donut-slice"
            :class="{ active: activeKey === slice.key, pinned: pinnedKey === slice.key }"
            :d="slice.path"
            :fill="slice.color"
            :style="{
              transform: activeKey === slice.key ? `translate(${slice.offsetX}px, ${slice.offsetY}px)` : 'translate(0, 0)',
            }"
            role="button"
            tabindex="0"
            :aria-label="`${slice.label}，${slice.amount.toFixed(4)} ${unit}，占比 ${slice.percentage.toFixed(1)}%`"
            @mouseenter="setHovered(slice.key)"
            @mouseleave="clearHovered(slice.key)"
            @focus="setHovered(slice.key)"
            @blur="clearHovered(slice.key)"
            @click="togglePinned(slice.key)"
            @keydown.enter.prevent="togglePinned(slice.key)"
            @keydown.space.prevent="togglePinned(slice.key)"
          >
            <title>{{ slice.label }}：{{ slice.amount.toFixed(4) }} {{ unit }}（{{ slice.percentage.toFixed(1) }}%）</title>
          </path>
        </g>
      </svg>
      <div class="donut-center" aria-live="polite">
        <span>{{ activeEntry?.label ?? totalLabel }}</span>
        <strong>{{ centerAmount.toFixed(4) }}</strong>
        <small v-if="activeEntry">{{ shareFor(activeEntry.amount).toFixed(1) }}% · {{ activeEntry.detail || '成本占比' }}</small>
        <small v-else-if="positiveTotal > 0">悬停查看 · 点击固定</small>
        <small v-else>{{ emptyLabel }}</small>
      </div>
    </div>

    <dl class="interactive-donut-legend">
      <div
        v-for="entry in entries"
        :key="entry.key"
        class="donut-legend-row"
        :class="{
          active: activeKey === entry.key,
          pinned: pinnedKey === entry.key,
          inactive: entry.inactive || entry.amount === 0,
        }"
        :style="activeKey === entry.key ? {
          borderColor: entry.color,
          background: `${entry.color}12`,
          boxShadow: `inset 3px 0 0 ${entry.color}`,
        } : undefined"
        role="button"
        tabindex="0"
        :aria-label="`${entry.label}，${entry.amount.toFixed(4)} ${unit}，占比 ${shareFor(entry.amount).toFixed(1)}%`"
        @mouseenter="setHovered(entry.key)"
        @mouseleave="clearHovered(entry.key)"
        @focus="setHovered(entry.key)"
        @blur="clearHovered(entry.key)"
        @click="togglePinned(entry.key)"
        @keydown.enter.prevent="togglePinned(entry.key)"
        @keydown.space.prevent="togglePinned(entry.key)"
      >
        <dt>
          <i :style="{ background: entry.color, color: entry.color }" />
          <span>{{ entry.label }}<small v-if="entry.detail">{{ entry.detail }}</small></span>
        </dt>
        <dd><strong>{{ entry.amount.toFixed(4) }}</strong><small>{{ shareFor(entry.amount).toFixed(1) }}%</small></dd>
      </div>
      <div v-if="!entries.length" class="donut-legend-row inactive">
        <dt><span>{{ emptyLabel }}</span></dt><dd><strong>0.0000</strong><small>0.0%</small></dd>
      </div>
    </dl>
  </div>
</template>

<style scoped>
.interactive-donut-layout{display:grid;grid-template-columns:200px minmax(0,1fr);align-items:center;gap:16px;min-width:0}.interactive-donut-chart{position:relative;display:grid;width:196px;height:196px;place-items:center}.interactive-donut-chart svg{width:196px;height:196px;overflow:visible}.donut-track{fill:none;stroke:#e2e8f0;stroke-width:33}.donut-slice{cursor:pointer;stroke:#fff;stroke-width:1.8;transform-box:view-box;transform-origin:center;transition:transform .18s ease,filter .18s ease,opacity .18s ease}.donut-slice:hover,.donut-slice:focus-visible,.donut-slice.active{filter:drop-shadow(0 6px 5px rgb(15 23 42/.22));outline:none}.donut-slice.pinned{stroke:#0f172a;stroke-width:2.4}.donut-center{pointer-events:none;position:absolute;display:grid;width:102px;place-items:center;text-align:center}.donut-center span{overflow:hidden;max-width:100%;color:#475569;font-size:10px;font-weight:900;text-overflow:ellipsis;white-space:nowrap}.donut-center strong{margin-top:4px;color:#0f172a;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:16px;line-height:1}.donut-center small{max-width:96px;margin-top:5px;color:#64748b;font-size:8px;line-height:1.35}.interactive-donut-legend{display:grid;grid-template-columns:repeat(2,minmax(140px,1fr));gap:7px;min-width:0;margin:0}.donut-legend-row{display:flex;min-width:0;align-items:center;justify-content:space-between;gap:8px;border:1px solid #e2e8f0;border-radius:9px;background:#fff;padding:8px 9px;cursor:pointer;transition:border-color .16s ease,background .16s ease,box-shadow .16s ease,transform .16s ease}.donut-legend-row:hover,.donut-legend-row:focus-visible,.donut-legend-row.active{outline:none;transform:translateY(-1px)}.donut-legend-row.inactive{background:#f8fafc;opacity:.58}.donut-legend-row dt{display:flex;min-width:0;align-items:center;gap:7px;color:#334155;font-size:10px;font-weight:800}.donut-legend-row dt i{width:9px;height:9px;flex:0 0 auto;border-radius:3px;box-shadow:0 0 0 2px #fff,0 0 0 3px currentColor}.donut-legend-row dt span{display:grid;min-width:0}.donut-legend-row dt small{overflow:hidden;max-width:120px;margin-top:2px;color:#94a3b8;font-size:7px;font-weight:500;text-overflow:ellipsis;white-space:nowrap}.donut-legend-row dd{display:grid;justify-items:end;margin:0;color:#0f172a;font-family:ui-monospace,SFMono-Regular,Consolas,monospace}.donut-legend-row dd strong{font-size:10px}.donut-legend-row dd small{margin-top:2px;color:#64748b;font-size:8px}.donut-legend-row.pinned dd small{color:#0f766e;font-weight:900}
@media(max-width:900px){.interactive-donut-layout{grid-template-columns:170px minmax(0,1fr)}.interactive-donut-chart,.interactive-donut-chart svg{width:166px;height:166px}.interactive-donut-legend{grid-template-columns:repeat(2,minmax(120px,1fr))}}
@media(max-width:620px){.interactive-donut-layout{grid-template-columns:1fr}.interactive-donut-chart{margin:auto}.interactive-donut-legend{grid-template-columns:1fr}}
</style>
