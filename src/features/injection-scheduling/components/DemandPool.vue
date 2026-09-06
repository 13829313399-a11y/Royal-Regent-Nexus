<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue';
import { useVirtualizer } from '@tanstack/vue-virtual';
import {
  PanelLeftClose,
  PanelLeftOpen,
  GripVertical,
  AlertCircle,
} from '@lucide/vue';
import { dateText, numberText, type DataRow } from '../types';
import { useInjectionViewState } from '../composables/useInjectionViewState';
import InjEmptyState from './ui/InjEmptyState.vue';
const props = defineProps<{
  rows: DataRow[];
  total: number;
  selectedId: string | null;
  canDrag: boolean;
  rail?: boolean;
  loading?: boolean;
  error?: string;
}>();
const emit = defineEmits<{
  select: [string, boolean?];
  drag: [DragEvent, DataRow];
}>();
const view = useInjectionViewState(),
  reasons = ref<string[]>([]);
const list = ref<HTMLElement>();
const context = view.contextGeneration;
const virtual = useVirtualizer(
  computed(() => ({
    count: props.rows.length,
    getScrollElement: () => list.value ?? null,
    estimateSize: () => 104,
    getItemKey: (index: number) => props.rows[index]!.id,
    overscan: 4,
  })),
);
const visibleRows = computed(() =>
  virtual.value
    .getVirtualItems()
    .map((vr) => ({ vr, d: props.rows[vr.index]!, index: vr.index })),
);
watch(list, (element) =>
  nextTick(() => {
    if (element && element === list.value)
      element.scrollTop = view.scroll.pool?.top || 0;
  }),
);
onBeforeUnmount(() => {
  if (list.value && context === view.contextGeneration)
    view.scroll.pool = { top: list.value.scrollTop, left: 0 };
});
const initialEntrance = !view.poolEntered;
const entered = new Set<string>();
watch(
  () => props.rows.length,
  (length) => {
    if (length) view.poolEntered = true;
  },
  { immediate: true },
);
let resizeStart = 0,
  previousWidth = 264;
function resize(event: PointerEvent) {
  resizeStart = event.clientX;
  previousWidth = view.poolWidth;
  (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
}
function move(event: PointerEvent) {
  if ((event.currentTarget as HTMLElement).hasPointerCapture(event.pointerId))
    view.poolWidth = Math.max(
      240,
      Math.min(320, previousWidth + event.clientX - resizeStart),
    );
}
function toggleReason(id: string) {
  reasons.value = reasons.value.includes(id)
    ? reasons.value.filter((value) => value !== id)
    : [...reasons.value, id];
}
</script>
<template>
  <aside
    class="inj-pool"
    :class="{ 'inj-pool-collapsed': rail || !view.poolExpanded }"
    :style="{ '--inj-pool-width': `${view.poolWidth}px` }"
    aria-label="未排需求池"
  >
    <header>
      <strong
        >未排需求 <span class="inj-mono">{{ numberText(total) }}</span></strong
      ><button
        :aria-label="view.poolExpanded && !rail ? '收起需求池' : '展开需求池'"
        :aria-expanded="view.poolExpanded && !rail"
        :disabled="rail"
        @click="view.poolExpanded = !view.poolExpanded"
      >
        <PanelLeftClose v-if="view.poolExpanded && !rail" /><PanelLeftOpen
          v-else
        />
      </button>
    </header>
    <span
      v-if="rail || !view.poolExpanded"
      class="inj-pool-rail-text"
      :title="rail ? '关闭详情后恢复需求池' : '点击展开需求池'"
      >未排 {{ numberText(total) }}</span
    >
    <template v-else>
      <p class="inj-muted">按交期排列 · 拖入机台排产</p>
      <div
        ref="list"
        class="inj-pool-list"
        @scroll="
          context === view.contextGeneration &&
          list &&
          (view.scroll.pool = { top: list.scrollTop, left: 0 })
        "
      >
        <div
          aria-hidden="true"
          :style="{ height: (visibleRows[0]?.vr.start || 0) + 'px' }"
        />
        <article
          v-for="{ d, index } in visibleRows"
          :key="d.id"
          :data-index="index"
          :ref="(element) => virtual.measureElement(element as Element)"
          class="inj-demand-item"
          :class="{
            selected: selectedId === d.id,
            'inj-first-pool-item':
              initialEntrance && index < 6 && !entered.has(d.id),
          }"
          :style="{ '--inj-enter-delay': `${Math.min(index, 5) * 30}ms` }"
          @animationend="entered.add(d.id)"
        >
          <button
            class="inj-demand-card"
            :draggable="canDrag"
            :title="`${d.mold_code} · ${d.order_no || '无单号'} · 交期 ${dateText(d.delivery_due_at)} · ${d.material_raw || '材料待补'}`"
            @dragstart="emit('drag', $event, d)"
            @click="emit('select', d.id)"
            @dblclick="emit('select', d.id, true)"
          >
            <span
              ><strong class="inj-mono">{{
                d.mold_code || '待识别模号'
              }}</strong
              ><em>{{ d.required_machine_a ?? '?' }}A</em></span
            >
            <span class="inj-demand-order"
              ><span>{{ d.order_no || '无单号' }}</span
              ><time :title="dateText(d.delivery_due_at)">{{
                dateText(d.delivery_due_at).slice(0, 10)
              }}</time></span
            >
            <span
              ><b class="inj-mono"
                >{{ numberText(d.remaining_shots) }}<small> 啤</small></b
              ><small
                >{{ d.color_name || '颜色待补' }} ·
                {{ d.material_raw || '材料待补' }}</small
              ></span
            >
          </button>
          <button
            v-if="d.unplaced_reason"
            class="inj-reason-toggle"
            :aria-expanded="reasons.includes(d.id)"
            @click="toggleReason(d.id)"
          >
            <AlertCircle />{{
              reasons.includes(d.id) ? '收起原因' : '查看未排原因'
            }}
          </button>
          <div
            class="inj-disclosure"
            :class="{ open: reasons.includes(d.id) }"
            :inert="!reasons.includes(d.id)"
          >
            <div>
              <p>{{ d.unplaced_reason }}</p>
            </div>
          </div>
        </article>
        <div
          aria-hidden="true"
          :style="{
            height:
              Math.max(
                0,
                virtual.getTotalSize() - (visibleRows.at(-1)?.vr.end || 0),
              ) + 'px',
          }"
        />
        <p v-if="total > rows.length" class="inj-help">
          先显示 {{ rows.length }} 条；计划表可查找全部 {{ total }} 条未排需求。
        </p>
        <InjEmptyState
          v-if="!rows.length && !loading"
          :failed="!!error"
          :title="error ? '需求读取未完成' : '当前没有未排需求'"
          :description="error || '仅表示未排池为空；已排批次请查看时间轴。'"
        />
      </div>
    </template>
    <div
      v-if="view.poolExpanded && !rail"
      class="inj-pool-resizer"
      role="separator"
      aria-label="调整需求池宽度"
      aria-orientation="vertical"
      tabindex="0"
      :aria-valuenow="view.poolWidth"
      aria-valuemin="240"
      aria-valuemax="320"
      @pointerdown="resize"
      @pointermove="move"
      @keydown.left.prevent="view.poolWidth = Math.max(240, view.poolWidth - 8)"
      @keydown.right.prevent="
        view.poolWidth = Math.min(320, view.poolWidth + 8)
      "
    >
      <GripVertical />
    </div>
  </aside>
</template>
