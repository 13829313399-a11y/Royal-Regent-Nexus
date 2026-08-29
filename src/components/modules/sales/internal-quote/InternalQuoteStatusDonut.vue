<script setup lang="ts">
import { ChevronLeft, ChevronRight } from '@lucide/vue'
import { computed, ref, watch } from 'vue'

type QuoteStatusGroupKey = 'in_progress' | 'completed' | 'canceled'

interface QuoteStatusRow {
  key: QuoteStatusGroupKey
  label: string
  count: number
  percentage: number
  color: string
}

const props = defineProps<{
  rows: QuoteStatusRow[]
  total: number
  periodLabel: string
}>()

const selectedKey = ref<QuoteStatusGroupKey | null>(null)
const previewKey = ref<QuoteStatusGroupKey | null>(null)
const activeKey = computed(() => previewKey.value ?? selectedKey.value)
const activeItem = computed(() => props.rows.find((item) => item.key === activeKey.value) ?? null)

const arcRows = computed(() => {
  let cursor = 0
  return props.rows.map((item) => {
    const start = cursor
    cursor += item.percentage
    const gap = item.percentage > 0 && item.percentage < 100 ? Math.min(0.8, item.percentage / 4) : 0
    const visiblePercentage = Math.max(0, item.percentage - gap)
    return {
      ...item,
      dashArray: `${visiblePercentage} ${100 - visiblePercentage}`,
      dashOffset: -start,
    }
  })
})

const cursorIndex = computed({
  get: () => {
    if (!selectedKey.value) return 0
    const index = props.rows.findIndex((item) => item.key === selectedKey.value)
    return index < 0 ? 0 : index + 1
  },
  set: (value: number) => {
    selectedKey.value = value > 0 ? props.rows[value - 1]?.key ?? null : null
    previewKey.value = null
  },
})

const displayCount = computed(() => activeItem.value?.count ?? props.total)
const displayLabel = computed(() => activeItem.value?.label ?? '总报价')
const sliderLabel = computed(() => selectedKey.value
  ? `已锁定：${props.rows.find((item) => item.key === selectedKey.value)?.label ?? '全部状态'}`
  : '全部状态')

function previewStatus(key: QuoteStatusGroupKey | null) {
  previewKey.value = key
}

function toggleStatus(key: QuoteStatusGroupKey) {
  selectedKey.value = selectedKey.value === key ? null : key
  previewKey.value = null
}

function moveCursor(direction: -1 | 1) {
  const upperBound = props.rows.length
  const next = cursorIndex.value + direction
  cursorIndex.value = next < 0 ? upperBound : next > upperBound ? 0 : next
}

watch(() => props.rows.map((item) => item.key).join(','), () => {
  if (selectedKey.value && !props.rows.some((item) => item.key === selectedKey.value)) {
    selectedKey.value = null
  }
  previewKey.value = null
})
</script>

<template>
  <div class="quote-status-visual" role="group" :aria-label="`${periodLabel}报价状态占比交互图`">
    <div class="quote-status-chart-body">
      <div class="quote-status-donut">
        <svg viewBox="0 0 160 160" role="group" :aria-label="`${periodLabel}报价状态占比，当前显示${displayLabel} ${displayCount} 份`">
          <title>{{ periodLabel }}报价状态占比</title>
          <circle class="quote-status-track" cx="80" cy="80" r="60" pathLength="100" />
          <circle
            v-for="item in arcRows"
            v-show="item.percentage > 0"
            :key="item.key"
            class="quote-status-segment"
            :class="{
              active: activeKey === item.key,
              muted: Boolean(activeKey) && activeKey !== item.key,
            }"
            cx="80"
            cy="80"
            r="60"
            pathLength="100"
            :stroke="item.color"
            :stroke-dasharray="item.dashArray"
            :stroke-dashoffset="item.dashOffset"
            role="button"
            tabindex="0"
            :aria-label="`${item.label} ${item.count} 份，占 ${item.percentage.toFixed(1)}%`"
            :aria-pressed="selectedKey === item.key"
            @mouseenter="previewStatus(item.key)"
            @mouseleave="previewStatus(null)"
            @focus="previewStatus(item.key)"
            @blur="previewStatus(null)"
            @click="toggleStatus(item.key)"
            @keydown.enter.prevent="toggleStatus(item.key)"
            @keydown.space.prevent="toggleStatus(item.key)"
          />
        </svg>
        <div class="quote-status-center" aria-live="polite">
          <strong>{{ displayCount }}</strong>
          <small>{{ displayLabel }}</small>
          <span v-if="activeItem">{{ activeItem.percentage.toFixed(1) }}%</span>
        </div>
      </div>

      <div class="quote-status-legend" role="group" aria-label="报价状态图例">
        <button
          v-for="item in rows"
          :key="item.key"
          type="button"
          :class="{ active: activeKey === item.key }"
          :aria-pressed="selectedKey === item.key"
          @mouseenter="previewStatus(item.key)"
          @mouseleave="previewStatus(null)"
          @focus="previewStatus(item.key)"
          @blur="previewStatus(null)"
          @click="toggleStatus(item.key)"
        >
          <span><i :style="{ background: item.color }" />{{ item.label }}</span>
          <strong>{{ item.count }}<small>{{ item.percentage.toFixed(1) }}%</small></strong>
        </button>
      </div>
    </div>

    <div class="quote-status-scrubber">
      <button type="button" title="查看上一个状态" aria-label="查看上一个报价状态" @click="moveCursor(-1)"><ChevronLeft aria-hidden="true" /></button>
      <label>
        <span>滑动查看 · {{ sliderLabel }}</span>
        <input
          v-model.number="cursorIndex"
          type="range"
          min="0"
          :max="rows.length"
          step="1"
          aria-label="滑动查看报价状态"
        >
      </label>
      <button type="button" title="查看下一个状态" aria-label="查看下一个报价状态" @click="moveCursor(1)"><ChevronRight aria-hidden="true" /></button>
    </div>
    <p class="quote-status-help">悬停预览，点击可锁定；再次点击或把滑杆移回起点即可查看全部。</p>
  </div>
</template>

<style scoped>
.quote-status-visual{display:grid;min-height:0}.quote-status-chart-body{display:grid;grid-template-columns:156px minmax(0,1fr);align-items:center;gap:10px;padding:14px 14px 10px}.quote-status-donut{position:relative;display:grid;width:148px;height:148px;place-items:center}.quote-status-donut svg{display:block;width:100%;height:100%;overflow:visible;filter:drop-shadow(0 8px 16px rgb(37 99 235/.1));transform:translateZ(0)}.quote-status-track,.quote-status-segment{fill:none;stroke-width:22}.quote-status-track{stroke:#e8eef5}.quote-status-segment{cursor:pointer;outline:none;stroke-linecap:butt;transform:rotate(-90deg);transform-origin:80px 80px;transition:opacity .18s,stroke-width .18s,filter .18s}.quote-status-segment:hover,.quote-status-segment:focus-visible,.quote-status-segment.active{stroke-width:27;filter:drop-shadow(0 2px 4px rgb(15 23 42/.2))}.quote-status-segment:focus-visible{filter:drop-shadow(0 0 4px rgb(37 99 235/.7))}.quote-status-segment.muted{opacity:.2}.quote-status-center{pointer-events:none;position:absolute;display:grid;width:82px;place-items:center;text-align:center}.quote-status-center strong{color:#0f172a;font-size:27px;line-height:1}.quote-status-center small{overflow:hidden;max-width:78px;margin-top:5px;color:#64748b;font-size:10px;font-weight:850;text-overflow:ellipsis;white-space:nowrap}.quote-status-center span{margin-top:3px;color:#2563eb;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:9px;font-weight:900}.quote-status-legend{display:grid;gap:4px}.quote-status-legend button{display:flex;width:100%;align-items:center;justify-content:space-between;gap:8px;border:1px solid transparent;border-radius:9px;background:transparent;padding:7px 8px;text-align:left;transition:border-color .16s,background .16s,box-shadow .16s,transform .16s}.quote-status-legend button:hover,.quote-status-legend button:focus-visible,.quote-status-legend button.active{border-color:#dbeafe;background:#f8fafc;box-shadow:0 5px 14px rgb(37 99 235/.07);outline:none;transform:translateX(2px)}.quote-status-legend button>span{display:flex;align-items:center;gap:7px;color:#475569;font-size:11px;font-weight:850}.quote-status-legend i{width:8px;height:8px;flex:0 0 auto;border-radius:99px}.quote-status-legend strong{display:flex;align-items:baseline;gap:6px;color:#0f172a;font-size:13px}.quote-status-legend small{color:#94a3b8;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:8px}.quote-status-scrubber{display:grid;grid-template-columns:28px minmax(0,1fr) 28px;align-items:end;gap:7px;border-top:1px solid #eef2f6;background:#fbfdfe;padding:8px 12px 7px}.quote-status-scrubber>button{display:grid;width:28px;height:28px;place-items:center;border:1px solid #dbe5ea;border-radius:8px;background:#fff;color:#64748b;transition:border-color .16s,background .16s,color .16s}.quote-status-scrubber>button:hover,.quote-status-scrubber>button:focus-visible{border-color:#93c5fd;background:#eff6ff;color:#1d4ed8;outline:none}.quote-status-scrubber svg{width:14px}.quote-status-scrubber label{display:grid;gap:2px;color:#64748b;font-size:8px;font-weight:850;text-align:center}.quote-status-scrubber input{width:100%;height:15px;margin:0;cursor:ew-resize;accent-color:#2563eb}.quote-status-help{margin:0;background:#fbfdfe;padding:0 14px 8px;color:#94a3b8;font-size:8px;text-align:center}
@media(max-width:700px){.quote-status-chart-body{grid-template-columns:132px minmax(0,1fr)}.quote-status-donut{width:126px;height:126px}.quote-status-track,.quote-status-segment{stroke-width:23}.quote-status-segment:hover,.quote-status-segment:focus-visible,.quote-status-segment.active{stroke-width:28}}
@media(max-width:460px){.quote-status-chart-body{grid-template-columns:1fr}.quote-status-donut{margin:auto}.quote-status-legend{grid-template-columns:repeat(3,minmax(0,1fr))}.quote-status-legend button{align-items:flex-start;flex-direction:column}.quote-status-legend strong{width:100%;justify-content:space-between}}
@media(prefers-reduced-motion:reduce){.quote-status-segment,.quote-status-legend button,.quote-status-scrubber>button{transition:none!important}}
</style>
