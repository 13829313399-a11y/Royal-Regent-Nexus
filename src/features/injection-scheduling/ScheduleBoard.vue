<script setup lang="ts">
import { vInjDialog } from '@/features/injection-scheduling/composables/injDialog';
import {
  computed,
  ref,
  toRef,
  watch,
  onMounted,
  onBeforeUnmount,
  nextTick,
} from 'vue';
import { Pin, PanelLeftOpen } from '@lucide/vue';
import DemandPool from './components/DemandPool.vue';
import MachineBoard from './components/MachineBoard.vue';
import InjSegmentedControl from './components/ui/InjSegmentedControl.vue';
import { useInjMotionPreference } from './composables/useInjMotionPreference';
import {
  useInjectionViewState,
  rowHeight,
} from './composables/useInjectionViewState';
import { useVirtualizer } from '@tanstack/vue-virtual';
import { useInjectionStore } from '@/stores/injectionScheduling';
import { dateText, numberText, statusText, type DataRow } from './types';
const props = defineProps<{
  mode: 'timeline' | 'machines';
  canPlan: boolean;
  canReport: boolean;
  collapsePool?: boolean;
}>();
const runningOnly = defineModel<boolean>('runningOnly', { default: false });
const emit = defineEmits<{ report: [DataRow]; action: [DataRow, string] }>();
const store = useInjectionStore(),
  view = useInjectionViewState();
const zoom = toRef(view, 'zoom'),
  date = toRef(view, 'date'),
  workshop = toRef(view, 'workshop'),
  machineSearch = toRef(view, 'machineSearch');
const viewContext = view.contextGeneration;
const { motionAllowed } = useInjMotionPreference();
const machineColumnWidth = 200;
const machineRowHeight = computed(() => rowHeight(view.density, 'timeline'));
const drag = ref<{ run_id?: string; demand_id?: string; a?: number } | null>(
    null,
  ),
  dragError = ref(''),
  target = ref(''),
  scroller = ref<HTMLElement>();
const oversizedMove = ref<{
  data: Record<string, unknown>;
  description: string;
} | null>(null);
const start = computed(() =>
  new Date(
    date.value +
      'T' +
      (zoom.value === 'shift' ? store.settings.day_start || '08:00' : '00:00') +
      ':00+08:00',
  ).getTime(),
);
const hours = computed(() =>
    zoom.value === 'hour' ? 1 : zoom.value === 'shift' ? 12 : 24,
  ),
  width = computed(() =>
    zoom.value === 'hour' ? 90 : zoom.value === 'shift' ? 148 : 176,
  ),
  slots = computed(() =>
    zoom.value === 'hour' ? 72 : zoom.value === 'shift' ? 28 : 31,
  );
const scale = computed(() => width.value / (hours.value * 3600000)),
  chartWidth = computed(() => slots.value * width.value);
const visibleMachines = computed(() =>
  store.machines
    .filter(
      (m) =>
        (!runningOnly.value ||
          store.runs.some(
            (r) => r.machine_id === m.id && r.status === 'RUNNING',
          )) &&
        (!workshop.value || m.workshop === workshop.value) &&
        (!machineSearch.value ||
          [m.code, m.machine_a, m.notes, m.speed_class]
            .join(' ')
            .includes(machineSearch.value)),
    )
    .sort(
      (a, b) =>
        String(a.workshop).localeCompare(String(b.workshop), 'zh-CN') ||
        String(a.code).localeCompare(String(b.code), 'zh-CN', {
          numeric: true,
        }),
    ),
);
const machineVirtual = useVirtualizer(
  computed(() => ({
    count: visibleMachines.value.length,
    getScrollElement: () => scroller.value ?? null,
    estimateSize: () => machineRowHeight.value,
    getItemKey: (i: number) => visibleMachines.value[i]!.id,
    overscan: 5,
  })),
);
const machineRows = computed(() => machineVirtual.value.getVirtualItems());
watch(machineRowHeight, () => nextTick(() => machineVirtual.value.measure()));
const rememberScroll = () => {
  if (viewContext !== view.contextGeneration) return;
  if (scroller.value)
    view.scroll.timeline = {
      top: scroller.value.scrollTop,
      left: scroller.value.scrollLeft,
    };
};
const restoreScroll = () =>
  nextTick(() => {
    const pos = view.scroll.timeline;
    if (scroller.value && pos) {
      scroller.value.scrollTop = pos.top;
      scroller.value.scrollLeft = pos.left;
    }
  });
onMounted(restoreScroll);
watch(() => props.mode, restoreScroll);
onBeforeUnmount(rememberScroll);
const gridLines = computed(() =>
  Array.from(
    { length: slots.value + 1 },
    (_, i) => (slotStart(i) - start.value) * scale.value,
  ),
);
const dayHeaders = computed(() => {
  const result: { label: string; left: number; width: number }[] = [];
  for (let i = 0; i < slots.value; i++) {
    const instant = new Date(slotStart(i)),
      label = instant.toLocaleDateString('zh-CN', {
        month: '2-digit',
        day: '2-digit',
        weekday: 'short',
      });
    const previous = result.at(-1),
      size = (slotStart(i + 1) - slotStart(i)) * scale.value;
    if (previous?.label === label) previous.width += size;
    else
      result.push({
        label,
        left: (slotStart(i) - start.value) * scale.value,
        width: size,
      });
  }
  return result;
});
const changedRunIds = ref<string[]>([]);
let flashTimer: ReturnType<typeof setTimeout> | undefined;
watch(
  () => store.lastResult,
  (result) => {
    clearTimeout(flashTimer);
    changedRunIds.value = motionAllowed.value
      ? (result?.changed_runs || []).map((r: any) =>
          typeof r === 'string' ? r : r.id || r.run_id,
        )
      : [];
    if (changedRunIds.value.length)
      flashTimer = setTimeout(() => {
        changedRunIds.value = [];
      }, 600);
  },
);
onBeforeUnmount(() => clearTimeout(flashTimer));
function dragEnd() {
  drag.value = null;
  target.value = '';
  dragError.value = '';
}
function tooltip(run: DataRow) {
  return `${info(run).mold_code} | ${statusText[run.status]} | ${info(run).order_no || ''} | ${info(run).color_name || ''} · ${info(run).material_raw || ''} | ${dateText(run.planned_start_at)} → ${run.forecast_unknown ? '等待恢复，预计结束未知' : dateText(run.planned_end_at)}`;
}
const workshops = computed(() => [
  ...new Set(store.machines.map((m) => m.workshop).filter(Boolean)),
]);
const queues = computed(() =>
  Object.fromEntries(
    store.machines.map((m) => [
      m.id,
      store.runs
        .filter((r) => r.machine_id === m.id)
        .sort((a, b) => a.sequence - b.sequence),
    ]),
  ),
);
const selectedAsset = computed(() => store.detail?.run?.mold_asset_id);
function info(run: DataRow) {
  return run.snapshot || {};
}
function runSegments(run: DataRow) {
  if (run.forecast_unknown)
    return [
      {
        start: run.planned_start_at || run.actual_start_at,
        end: new Date(
          start.value + chartWidth.value / scale.value,
        ).toISOString(),
      },
    ];
  const segments = run.segments?.filter((s: any) => s.kind === 'PRODUCTION');
  if (run.status === 'PLANNED' && segments?.length) return segments;
  return [{ start: run.planned_start_at, end: run.planned_end_at }];
}
function demandId(run: DataRow) {
  return run.demand_ids?.[0] || info(run).demand_ids?.[0] || info(run).id;
}
function selectRun(run: DataRow, drawer = false) {
  if (demandId(run)) void store.select(demandId(run), drawer);
}
function bar(startAt: string, endAt: string) {
  const left = (new Date(startAt).getTime() - start.value) * scale.value,
    right = (new Date(endAt).getTime() - start.value) * scale.value;
  return {
    left: Math.max(0, left) + 'px',
    width:
      Math.max(0, Math.min(chartWidth.value, right) - Math.max(0, left)) + 'px',
    display: right < 0 || left > chartWidth.value ? 'none' : undefined,
  };
}
function isEventFor(e: DataRow, m: DataRow) {
  return (
    e.resource_type === 'FACTORY' ||
    (e.resource_type === 'MACHINE' && e.resource_id === m.id)
  );
}
function beginDrag(event: DragEvent, row: DataRow, kind: 'run' | 'demand') {
  drag.value =
    kind === 'run'
      ? { run_id: row.id, a: info(row).required_machine_a }
      : { demand_id: row.id, a: row.required_machine_a };
  event.dataTransfer?.setData('text/plain', JSON.stringify(drag.value));
  if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move';
}
function over(event: DragEvent, machine: DataRow) {
  if (!props.canPlan || !drag.value || store.busy || store.dirty) return;
  event.preventDefault();
  target.value = machine.id;
  dragError.value =
    drag.value.a && Number(machine.machine_a) < drag.value.a
      ? `${drag.value.a}A 模不能放 ${machine.machine_a}A 机`
      : '';
  if (event.dataTransfer)
    event.dataTransfer.dropEffect = dragError.value ? 'none' : 'move';
}
async function drop(event: DragEvent, machine: DataRow, before?: string) {
  event.preventDefault();
  event.stopPropagation();
  target.value = '';
  if (!drag.value || dragError.value || store.busy || store.dirty) return;
  const { a, ...payload } = drag.value;
  drag.value = null;
  const data = {
    ...payload,
    machine_id: machine.id,
    before_run_id: before || null,
  };
  const allowed = store.settings.allowed_upsize?.[String(a)] || [a];
  if (
    a &&
    machine.machine_a > a &&
    !allowed.includes(Number(machine.machine_a))
  ) {
    oversizedMove.value = {
      data,
      description: `${a}A 模 → ${machine.code}（${machine.machine_a}A）`,
    };
    return;
  }
  await store.mutate('/schedule/move', data);
}
async function confirmOversized() {
  if (!oversizedMove.value) return;
  const result = await store.mutate('/schedule/move', {
    ...oversizedMove.value.data,
    allow_oversized: true,
  });
  if (result) oversizedMove.value = null;
}
function progress(run: DataRow) {
  const denominator = Number(run.planned_physical_shots);
  return denominator > 0 && run.physical_shots != null
    ? Math.min(
        100,
        Math.max(0, (100 * Number(run.physical_shots)) / denominator),
      )
    : null;
}
function slotLabel(i: number) {
  const instant = new Date(slotStart(i));
  return zoom.value === 'hour'
    ? instant.toLocaleTimeString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      })
    : `${instant.getMonth() + 1}/${instant.getDate()}${zoom.value === 'shift' ? (i % 2 === 0 ? ' 白班' : ' 夜班') : ''}`;
}
function slotStart(i: number) {
  if (zoom.value !== 'shift') return start.value + i * hours.value * 3600000;
  const minutes = (value: string) => {
    const [h, m] = value.split(':').map(Number);
    return h! * 60 + m!;
  };
  const day = minutes(store.settings.day_start || '08:00'),
    night = minutes(store.settings.night_start || '20:00');
  return (
    start.value +
    (Math.floor(i / 2) * 1440 + (i % 2 ? (night - day + 1440) % 1440 : 0)) *
      60000
  );
}
function current(machine: DataRow) {
  return queues.value[machine.id]?.find((r) =>
    ['RUNNING', 'PAUSED'].includes(r.status),
  );
}
function upcoming(machine: DataRow) {
  return queues.value[machine.id]?.find((r) => r.status === 'PLANNED');
}
</script>
<template>
  <section
    class="inj-board"
    :class="{ 'inj-dragging': !!drag }"
    :style="{
      '--inj-machine-column': machineColumnWidth + 'px',
      '--inj-machine-row': machineRowHeight + 'px',
    }"
    @dragend="dragEnd"
  >
    <div class="inj-toolbar">
      <select v-model="workshop" aria-label="车间">
        <option value="">全部车间</option>
        <option v-for="w in workshops" :key="w">{{ w }}</option></select
      ><input
        v-model="machineSearch"
        aria-label="机台筛选"
        placeholder="机号 / A / 设备状态"
      /><label v-if="mode === 'machines'"
        ><input v-model="runningOnly" type="checkbox" /> 仅实际在产</label
      ><template v-if="mode === 'timeline'"
        ><input v-model="date" type="date" aria-label="时间轴日期" /><button
          @click="date = new Date().toLocaleDateString('en-CA')"
        >
          今天
        </button>
        <InjSegmentedControl
          v-model="zoom"
          :options="[
            { value: 'day', label: '日' },
            { value: 'shift', label: '班次' },
            { value: 'hour', label: '小时' },
          ]"
          label="时间轴缩放" /></template
      ><span class="inj-spacer" /><span class="inj-legend"
        ><i class="inj-dot" /> 在产 <i class="inj-dot planned" /> 计划
        <i class="inj-dot setup" /> 换模 / 清洗</span
      >
    </div>
    <div v-if="mode === 'timeline'" class="inj-schedule-body">
      <DemandPool
        :rows="store.pending"
        :total="store.summary.pending_count || 0"
        :selected-id="store.selectedId"
        :can-drag="canPlan && !store.busy && !store.dirty"
        :rail="collapsePool || view.focusMode"
        :loading="store.loading"
        :error="store.error"
        @select="(id, open) => store.select(id, open)"
        @drag="(event, row) => beginDrag(event, row, 'demand')"
      />
      <div ref="scroller" class="inj-gantt-scroll" @scroll="rememberScroll">
        <div
          :style="{
            width: chartWidth + machineColumnWidth + 'px',
            minHeight: '100%',
          }"
        >
          <div class="inj-time-header">
            <div class="inj-machine-label">
              机台 / 能力 <small>{{ visibleMachines.length }} 台</small>
            </div>
            <div class="inj-time-scale">
              <div class="inj-date-slots">
                <span
                  v-for="day in dayHeaders"
                  :key="day.label"
                  :style="{ width: day.width + 'px' }"
                  >{{ day.label }}</span
                >
              </div>
              <div class="inj-time-slots">
                <span
                  v-for="i in slots"
                  :key="i"
                  :style="{
                    width: (slotStart(i) - slotStart(i - 1)) * scale + 'px',
                  }"
                  >{{ slotLabel(i - 1) }}</span
                >
              </div>
            </div>
          </div>
          <div
            :style="{
              height: machineVirtual.getTotalSize() + 'px',
              position: 'relative',
            }"
          >
            <div
              v-for="vr in machineRows"
              :key="visibleMachines[vr.index]!.id"
              class="inj-machine-row"
              :style="{ transform: `translateY(${vr.start}px)` }"
              :class="{
                'inj-drop-target': target === visibleMachines[vr.index]!.id,
                'inj-drop-invalid':
                  target === visibleMachines[vr.index]!.id && dragError,
              }"
              @dragover="over($event, visibleMachines[vr.index]!)"
              @drop="drop($event, visibleMachines[vr.index]!)"
            >
              <div class="inj-machine-label">
                <strong
                  >{{ visibleMachines[vr.index]!.code }}
                  <span
                    >{{ visibleMachines[vr.index]!.machine_a ?? '?' }}A</span
                  ></strong
                ><small
                  >{{ visibleMachines[vr.index]!.workshop }} ·
                  {{
                    current(visibleMachines[vr.index]!)
                      ? statusText[current(visibleMachines[vr.index]!)!.status]
                      : statusText[
                          visibleMachines[vr.index]!.operating_status
                        ] || '待开工'
                  }}</small
                >
              </div>
              <div
                class="inj-machine-track"
                :style="{
                  width: chartWidth + 'px',
                }"
              >
                <i
                  v-for="(line, index) in gridLines"
                  :key="'grid' + index"
                  class="inj-grid-line"
                  :style="{ left: line + 'px' }"
                  aria-hidden="true"
                />
                <div
                  v-for="e in store.events.filter((e) =>
                    isEventFor(e, visibleMachines[vr.index]!),
                  )"
                  :key="e.id"
                  class="inj-maintenance"
                  :style="
                    bar(
                      e.start_at,
                      e.end_at ||
                        new Date(start + chartWidth / scale).toISOString(),
                    )
                  "
                  :title="e.notes"
                >
                  检修 / 停工 · {{ e.notes }}
                </div>
                <template
                  v-for="run in queues[visibleMachines[vr.index]!.id]"
                  :key="run.id"
                  ><div
                    v-for="(segment, i) in run.segments?.filter(
                      (s: any) => s.kind === 'SETUP',
                    )"
                    :key="'s' + run.id + i"
                    class="inj-setup-bar"
                    :style="bar(segment.start, segment.end)"
                    :title="
                      '换模 / 清洗：' +
                      dateText(segment.start) +
                      ' → ' +
                      dateText(segment.end)
                    "
                  />
                  <button
                    v-for="(production, index) in runSegments(run)"
                    :key="'p' + run.id + index"
                    class="inj-run-bar"
                    :class="[
                      run.status.toLowerCase(),
                      {
                        selected: store.detail?.run?.id === run.id,
                        related:
                          selectedAsset &&
                          selectedAsset === run.mold_asset_id &&
                          store.detail?.run?.id !== run.id,
                        'inj-run-changed': changedRunIds.includes(run.id),
                      },
                    ]"
                    :style="bar(production.start, production.end)"
                    :draggable="
                      canPlan &&
                      !store.busy &&
                      !store.dirty &&
                      run.status === 'PLANNED'
                    "
                    :title="tooltip(run)"
                    :aria-label="tooltip(run)"
                    @keydown.enter="selectRun(run, true)"
                    @dragstart="beginDrag($event, run, 'run')"
                    @dragover.stop="over($event, visibleMachines[vr.index]!)"
                    @drop="drop($event, visibleMachines[vr.index]!, run.id)"
                    @click="selectRun(run)"
                    @dblclick="selectRun(run, true)"
                  >
                    <span
                      v-if="run.status === 'RUNNING' && progress(run) !== null"
                      class="inj-run-progress"
                      :style="{ width: progress(run) + '%' }"
                    /><span class="inj-run-text"
                      ><Pin v-if="run.pinned" />{{ info(run).mold_code }}
                      <small
                        >{{ info(run).color_name }} ·
                        {{ info(run).material_raw }} ·
                        {{
                          run.forecast_unknown
                            ? '等待恢复'
                            : statusText[run.status]
                        }}</small
                      ></span
                    >
                  </button></template
                >
                <div
                  v-if="
                    Date.now() >= start &&
                    Date.now() < start + chartWidth / scale
                  "
                  class="inj-now-line"
                  :style="{ left: (Date.now() - start) * scale + 'px' }"
                />
              </div>
            </div>
          </div>
        </div>
        <div v-if="!visibleMachines.length" class="inj-empty">
          尚无符合条件的机台，请在基础资料中建立设备台账。
        </div>
      </div>
    </div>
    <MachineBoard
      v-else
      :machines="visibleMachines"
      :queues="queues"
      :can-report="canReport"
      :running-only="runningOnly"
      :filter-scope="JSON.stringify([view.workshop, view.machineSearch])"
      @select="selectRun"
      @action="(run, verb) => emit('action', run, verb)"
      @report="(run) => emit('report', run)"
    />
    <div v-if="drag" class="inj-drag-brief" role="status">
      {{ drag.a ?? '?' }}A 模 ·
      {{
        target
          ? store.machines.find((m) => m.id === target)?.code +
            ' / ' +
            store.machines.find((m) => m.id === target)?.machine_a +
            'A'
          : '拖入目标机台'
      }}
      · {{ dragError || '放到批次上可插入该批之前' }}
    </div>
    <div v-if="dragError" class="inj-inline inj-error-text">
      {{ dragError }}
    </div>
    <div v-if="oversizedMove" class="inj-modal-backdrop">
      <section
        class="inj-modal"
        role="dialog"
        aria-modal="true"
        aria-label="手动使用大机"
        v-inj-dialog="{
          close: () => {
            oversizedMove = null;
          },
          busy: store.busy,
        }"
      >
        <h2>本次手动使用大机</h2>
        <p>{{ oversizedMove.description }}</p>
        <p>
          超出当前允许上放等级。确认后只对本次拖排使用大机，仍校验设备能力、日历和模具占用。
        </p>
        <p class="inj-error-text">{{ store.error }}</p>
        <div class="inj-actions">
          <button @click="oversizedMove = null">取消</button
          ><button
            class="inj-primary"
            :disabled="store.busy"
            @click="confirmOversized"
          >
            确认本次使用
          </button>
        </div>
      </section>
    </div>
  </section>
</template>
