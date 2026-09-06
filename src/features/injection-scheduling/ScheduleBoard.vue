<script setup lang="ts">
import { computed, ref } from 'vue';
import { useVirtualizer } from '@tanstack/vue-virtual';
import { useInjectionStore } from '@/stores/injectionScheduling';
import { dateText, numberText, statusText, type DataRow } from './types';
const props = defineProps<{
  mode: 'timeline' | 'machines';
  canPlan: boolean;
  canReport: boolean;
}>();
const runningOnly = defineModel<boolean>('runningOnly', { default: false });
const emit = defineEmits<{ report: [DataRow]; action: [DataRow, string] }>();
const store = useInjectionStore(),
  poolOpen = ref(true),
  zoom = ref('shift'),
  date = ref(new Date().toLocaleDateString('en-CA')),
  workshop = ref(''),
  machineSearch = ref('');
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
    estimateSize: () => 64,
    overscan: 5,
  })),
);
const machineRows = computed(() => machineVirtual.value.getVirtualItems());
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
  return Math.min(
    100,
    Math.max(
      0,
      (100 * Number(run.physical_shots || 0)) /
        Number(run.planned_physical_shots || 1),
    ),
  );
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
  <section class="inj-board">
    <div class="inj-toolbar">
      <button v-if="mode === 'timeline'" @click="poolOpen = !poolOpen">
        {{ poolOpen ? '收起' : '展开' }}需求池</button
      ><select v-model="workshop" aria-label="车间">
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
        <div class="inj-segmented">
          <button
            v-for="(name, key) in { day: '日', shift: '班次', hour: '小时' }"
            :key="key"
            :class="{ active: zoom === key }"
            @click="zoom = key"
          >
            {{ name }}
          </button>
        </div></template
      ><span class="inj-spacer" /><span class="inj-legend"
        ><i class="inj-dot" /> 在产 <i class="inj-dot planned" /> 计划
        <i class="inj-dot setup" /> 换模 / 清洗</span
      >
    </div>
    <div v-if="mode === 'timeline'" class="inj-schedule-body">
      <aside v-if="poolOpen" class="inj-pool">
        <header>
          <strong>未排需求</strong
          ><span>{{ numberText(store.summary.pending_count) }}</span>
        </header>
        <p class="inj-muted">按交期排列 · 拖入机台即可排产</p>
        <button
          v-for="d in store.pending"
          :key="d.id"
          class="inj-demand-card"
          :class="{ selected: store.selectedId === d.id }"
          :draggable="canPlan"
          @dragstart="beginDrag($event, d, 'demand')"
          @click="store.select(d.id)"
          @dblclick="store.select(d.id, true)"
        >
          <strong>{{ d.mold_code || '待识别模号' }}</strong
          ><span
            >{{ d.order_no || '无单号' }} ·
            {{ d.color_name || '颜色待补' }}</span
          ><span
            ><b>{{ numberText(d.remaining_shots) }}</b> 啤
            <em>{{ d.required_machine_a ?? '?' }} A</em></span
          ><small :class="{ 'inj-error-text': d.unplaced_reason }">{{
            d.unplaced_reason || '交期 ' + dateText(d.delivery_due_at)
          }}</small>
        </button>
        <p
          v-if="store.summary.pending_count > store.pending.length"
          class="inj-muted"
        >
          先显示 {{ store.pending.length }} 条；全字段计划表可查找全部未排需求。
        </p>
        <p v-if="!store.pending.length" class="inj-empty">没有待排需求</p>
      </aside>
      <div ref="scroller" class="inj-gantt-scroll">
        <div :style="{ width: chartWidth + 174 + 'px', minHeight: '100%' }">
          <div class="inj-time-header">
            <div class="inj-machine-label">
              机台 / 能力 <small>{{ visibleMachines.length }} 台</small>
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
                      ? '在产 / 暂停'
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
                  backgroundSize: width + 'px 100%',
                }"
              >
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
                      { selected: selectedAsset === run.mold_asset_id },
                    ]"
                    :style="bar(production.start, production.end)"
                    :draggable="canPlan && run.status === 'PLANNED'"
                    :title="`${info(run).mold_code} | ${statusText[run.status]} | ${dateText(run.planned_start_at)} → ${run.forecast_unknown ? '等待恢复' : dateText(run.planned_end_at)}`"
                    @dragstart="beginDrag($event, run, 'run')"
                    @dragover.stop="over($event, visibleMachines[vr.index]!)"
                    @drop="drop($event, visibleMachines[vr.index]!, run.id)"
                    @click="selectRun(run)"
                    @dblclick="selectRun(run, true)"
                  >
                    <span
                      v-if="run.status === 'RUNNING'"
                      class="inj-run-progress"
                      :style="{ width: progress(run) + '%' }"
                    /><span class="inj-run-text"
                      >{{ run.pinned ? '⌖ ' : '' }}{{ info(run).mold_code }}
                      <small
                        >{{ info(run).color_name }} ·
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
    <div v-else class="inj-machine-cards">
      <article
        v-for="m in visibleMachines"
        :key="m.id"
        class="inj-machine-card"
        :class="{
          running: current(m)?.status === 'RUNNING',
          paused: current(m)?.status === 'PAUSED',
        }"
      >
        <header>
          <strong
            >{{ m.code }}
            <span
              >{{ m.machine_a ?? '?' }}A / {{ m.clamp_ton ?? '?' }}T</span
            ></strong
          ><span class="inj-badge">{{
            current(m)
              ? statusText[current(m)!.status]
              : statusText[m.operating_status] || '空闲 / 待开工'
          }}</span>
        </header>
        <p class="inj-muted">
          {{ m.workshop || '未分车间' }} ·
          {{
            m.speed_class === 'HIGH_SPEED'
              ? '高速'
              : m.speed_class === 'ELECTRIC'
                ? '全电'
                : '普通速度'
          }}
          ·
          {{ m.manipulator || '机械手未录' }}
        </p>
        <template v-if="current(m)"
          ><h3>{{ info(current(m)!).mold_code }}</h3>
          <p>
            {{ info(current(m)!).order_no || '未填订单' }}
            <span class="inj-muted">{{
              (info(current(m)!).demand_ids?.length || 1) > 1
                ? '等 ' + info(current(m)!).demand_ids.length + ' 单'
                : ''
            }}</span>
          </p>
          <p>
            {{ info(current(m)!).color_name || '颜色待补' }} ·
            {{ info(current(m)!).material_raw || '材料待补' }}
          </p>
          <div class="inj-progress">
            <i :style="{ width: progress(current(m)!) + '%' }" />
          </div>
          <p class="inj-inline">
            <strong>实际 {{ numberText(current(m)!.physical_shots) }} 啤</strong
            ><span class="inj-spacer" />{{ progress(current(m)!).toFixed(1) }}%
          </p>
          <p class="inj-muted">
            本班
            {{
              current(m)!.current_shift_shots == null
                ? '未报'
                : numberText(current(m)!.current_shift_shots) + ' 啤'
            }}
            · 余 {{ numberText(current(m)!.remaining_shots) }} 啤
          </p>
          <p class="inj-muted">
            {{
              current(m)!.forecast_unknown
                ? '等待恢复 · 预计结束未知'
                : '预计结束 ' + dateText(current(m)!.planned_end_at)
            }}
          </p></template
        >
        <div v-else class="inj-idle">
          {{
            ['MAINTENANCE', 'FAULT', 'DISABLED'].includes(m.operating_status)
              ? m.notes || '设备停工'
              : '当前没有实际开工批次'
          }}<small v-if="m.recovery_at"
            >预计恢复 {{ dateText(m.recovery_at) }}</small
          >
        </div>
        <div class="inj-next-run">
          下一批
          <strong>{{
            upcoming(m) ? info(upcoming(m)!).mold_code : '暂无'
          }}</strong
          ><small v-if="upcoming(m)"
            >{{ info(upcoming(m)!).color_name }} ·
            {{ dateText(upcoming(m)!.planned_start_at) }}</small
          >
        </div>
        <footer>
          <button
            v-if="current(m) && canReport"
            class="inj-primary"
            @click="emit('report', current(m)!)"
          >
            报数</button
          ><button
            v-if="current(m) || upcoming(m)"
            @click="selectRun((current(m) || upcoming(m))!, true)"
          >
            详情</button
          ><button
            v-if="canReport && !current(m) && upcoming(m)"
            @click="emit('action', upcoming(m)!, 'start')"
          >
            开工</button
          ><button
            v-if="current(m) && canReport"
            @click="
              emit(
                'action',
                current(m)!,
                current(m)!.status === 'PAUSED' ? 'resume' : 'pause',
              )
            "
          >
            {{ current(m)!.status === 'PAUSED' ? '恢复' : '暂停' }}
          </button>
        </footer>
      </article>
      <div v-if="!visibleMachines.length" class="inj-empty">
        {{
          store.machines.length
            ? runningOnly
              ? '当前没有符合筛选条件的实际在产机台。'
              : '没有符合筛选条件的机台。'
            : '还没有设备，请到基础资料新增机台或导入计划。'
        }}
      </div>
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
