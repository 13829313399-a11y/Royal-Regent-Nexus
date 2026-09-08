<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue';
import BulkStartDialog from '../BulkStartDialog.vue';
import type { StartSelection } from '../bulkStart';
import { useInjectionViewState } from '../composables/useInjectionViewState';
import { useInjectionStore } from '@/stores/injectionScheduling';
import { dateText, numberText, statusText, type DataRow } from '../types';
const props = defineProps<{
  machines: DataRow[];
  queues: Record<string, DataRow[]>;
  canReport: boolean;
  runningOnly: boolean;
  filterScope?: string;
}>();
const emit = defineEmits<{
  report: [DataRow];
  action: [DataRow, string];
  select: [DataRow, boolean?];
}>();
const store = useInjectionStore();
const view = useInjectionViewState(),
  scroller = ref<HTMLElement>(),
  context = view.contextGeneration;
function rememberScroll() {
  if (scroller.value && context === view.contextGeneration)
    view.scroll.machines = {
      top: scroller.value.scrollTop,
      left: scroller.value.scrollLeft,
    };
}
onMounted(() => {
  if (scroller.value && view.scroll.machines)
    scroller.value.scrollTop = view.scroll.machines.top;
});
onBeforeUnmount(rememberScroll);
const deviceText = (status: string) =>
  status === 'IDLE' ? '可用' : statusText[status] || status;
const info = (run: DataRow) => run.snapshot || {};
const current = (m: DataRow) =>
  props.queues[m.id]?.find((r) => ['RUNNING', 'PAUSED'].includes(r.status));
const upcoming = (m: DataRow) =>
  props.queues[m.id]?.find((r) => r.status === 'PLANNED');
const selected = ref<Record<string, StartSelection>>({});
const pendingOnly = ref(false),
  showBulkStart = ref(false);
const selection = computed(() => Object.values(selected.value));
const reason = (m: DataRow) =>
  current(m)
    ? '已有开工或暂停批次'
    : ['MAINTENANCE', 'FAULT', 'DISABLED'].includes(m.operating_status)
      ? '设备停机中'
      : !upcoming(m)
        ? '没有待开工批次'
        : '';
const shownMachines = computed(() =>
  props.machines.filter((m) => !pendingOnly.value || !reason(m)),
);
const candidates = computed(() =>
  shownMachines.value.filter((m) => !reason(m)),
);
function toggle(m: DataRow) {
  if (store.busy || store.dirty || !props.canReport) return;
  if (selected.value[m.id]) delete selected.value[m.id];
  else if (!reason(m))
    selected.value[m.id] = { machine_id: m.id, run_id: upcoming(m)!.id };
}
function selectAll() {
  if (store.busy || store.dirty || !props.canReport) return;
  selected.value = Object.fromEntries(
    candidates.value.map((m) => [
      m.id,
      { machine_id: m.id, run_id: upcoming(m)!.id },
    ]),
  );
}
function removeSelection(ids: string[]) {
  for (const id of ids) delete selected.value[id];
}
watch(
  () => [
    store.factory,
    props.filterScope,
    props.runningOnly,
    pendingOnly.value,
    props.canReport,
    JSON.stringify(store.filter),
    JSON.stringify(store.search),
  ],
  () => {
    selected.value = {};
    showBulkStart.value = false;
  },
);
const selectRun = (run: DataRow, open = false) => emit('select', run, open);
function progress(run: DataRow) {
  const denominator = Number(run.planned_physical_shots);
  return denominator > 0 && run.physical_shots != null
    ? Math.min(
        100,
        Math.max(0, (100 * Number(run.physical_shots)) / denominator),
      )
    : null;
}
</script>
<template>
  <div class="inj-machine-board">
    <div v-if="canReport" class="inj-bulk-toolbar">
      <label
        ><input
          v-model="pendingOnly"
          type="checkbox"
          :disabled="store.busy || store.dirty"
        />仅待开工</label
      >
      <button
        :disabled="store.busy || store.dirty || !candidates.length"
        @click="selectAll"
      >
        全选待开工机台
      </button>
      <button
        :disabled="store.busy || store.dirty || !selection.length"
        @click="selected = {}"
      >
        取消选择
      </button>
      <span role="status"
        >已选 <strong>{{ selection.length }}</strong> 台</span
      >
      <small class="inj-muted">当前筛选范围 · 每台只选下一批</small>
      <button
        class="inj-primary inj-bulk-open"
        :disabled="store.busy || store.dirty || !selection.length"
        @click="showBulkStart = true"
      >
        批量开工（{{ selection.length }}）
      </button>
    </div>
    <div ref="scroller" class="inj-machine-cards" @scroll="rememberScroll">
      <article
        v-for="m in shownMachines"
        :key="m.id"
        class="inj-machine-card"
        :class="{
          running: current(m)?.status === 'RUNNING',
          paused: current(m)?.status === 'PAUSED',
          'inj-machine-selected': !!selected[m.id],
        }"
      >
        <header>
          <input
            v-if="canReport"
            type="checkbox"
            class="inj-machine-select"
            :aria-label="`选择机台 ${m.code}`"
            :title="reason(m) || '选择下一批开工'"
            :checked="!!selected[m.id]"
            :disabled="
              store.busy || store.dirty || (!!reason(m) && !selected[m.id])
            "
            @change="toggle(m)"
          />
          <strong
            >{{ m.code }}
            <span
              >{{ m.machine_a ?? '?' }}A / {{ m.clamp_ton ?? '?' }}T</span
            ></strong
          ><span
            class="inj-badge"
            :class="{
              'inj-status-paused': current(m)?.status === 'PAUSED',
              'inj-status-running': current(m)?.status === 'RUNNING',
            }"
            >{{
              current(m)
                ? statusText[current(m)!.status]
                : upcoming(m)
                  ? '待开工'
                  : '空闲'
            }}</span
          >
        </header>
        <p
          v-if="selected[m.id] && selected[m.id].run_id !== upcoming(m)?.id"
          class="inj-error-text"
          role="status"
        >
          下一批已变化，请取消勾选后重新选择
        </p>
        <small v-else-if="canReport && reason(m)" class="inj-muted"
          >不可勾选：{{ reason(m) }}</small
        >
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
          {{ m.manipulator || '机械手未录' }} · 设备：{{
            deviceText(m.operating_status)
          }}
        </p>
        <template v-if="current(m)"
          ><h3 class="inj-mono" :title="info(current(m)!).mold_code">
            {{ info(current(m)!).mold_code }}
          </h3>
          <p>
            {{ info(current(m)!).order_no || '未填订单' }}
            <span class="inj-muted">{{
              (info(current(m)!).demand_ids?.length || 1) > 1
                ? '等 ' + info(current(m)!).demand_ids.length + ' 单'
                : ''
            }}</span>
          </p>
          <p
            class="inj-card-material"
            :title="
              (info(current(m)!).color_name || '') +
              ' · ' +
              (info(current(m)!).material_raw || '')
            "
          >
            {{ info(current(m)!).color_name || '颜色待补' }} ·
            {{ info(current(m)!).material_raw || '材料待补' }}
          </p>
          <div class="inj-card-metrics">
            <div>
              <small>实际啤数</small
              ><strong>{{ numberText(current(m)!.physical_shots) }}</strong>
            </div>
            <div>
              <small>剩余啤数</small
              ><strong>{{ numberText(current(m)!.remaining_shots) }}</strong>
            </div>
            <div>
              <small>本班累计</small
              ><strong>{{
                current(m)!.current_shift_shots == null
                  ? '未报'
                  : numberText(current(m)!.current_shift_shots)
              }}</strong>
            </div>
          </div>
          <div class="inj-card-progress">
            <div v-if="progress(current(m)!) !== null" class="inj-progress">
              <i :style="{ width: progress(current(m)!) + '%' }" />
            </div>
            <small>{{
              progress(current(m)!) === null
                ? '进度待确认'
                : progress(current(m)!)!.toFixed(1) + '%'
            }}</small>
          </div>
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
        <div
          class="inj-card-bottom"
          :class="{ 'inj-card-bottom-compact': current(m) }"
        >
          <div
            class="inj-next-run"
            :title="
              upcoming(m)
                ? `${info(upcoming(m)!).mold_code} · ${info(upcoming(m)!).color_name} · ${dateText(upcoming(m)!.planned_start_at)}`
                : '暂无下一批'
            "
          >
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
              :disabled="store.dirty || store.busy"
              @click="emit('report', current(m)!)"
            >
              报数</button
            ><button
              v-if="current(m) || upcoming(m)"
              @click="selectRun((current(m) || upcoming(m))!, true)"
            >
              详情</button
            ><button
              class="inj-primary"
              v-if="canReport && !current(m) && upcoming(m)"
              :disabled="store.busy || store.dirty"
              @click="emit('action', upcoming(m)!, 'start')"
            >
              开工</button
            ><button
              v-if="current(m) && canReport"
              :disabled="store.busy || store.dirty"
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
        </div>
      </article>
      <div v-if="!shownMachines.length" class="inj-empty">
        {{
          store.machines.length
            ? runningOnly
              ? '当前没有符合筛选条件的实际在产机台。'
              : '没有符合筛选条件的机台。'
            : '还没有设备，请到基础资料新增机台或导入计划。'
        }}
      </div>
    </div>
    <BulkStartDialog
      v-if="showBulkStart"
      :items="selection"
      :can-report="canReport"
      @close="showBulkStart = false"
      @remove="(id) => removeSelection([id])"
      @started="removeSelection"
    />
  </div>
</template>
<style scoped>
.inj-machine-board {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  min-width: 0;
  overflow: hidden;
}
.inj-machine-cards {
  min-height: 0;
  flex: 1;
}
.inj-bulk-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px 14px;
  border-bottom: 1px solid var(--inj-line);
}
.inj-bulk-toolbar label {
  display: flex;
  align-items: center;
  gap: 5px;
}
.inj-bulk-open {
  margin-left: auto;
}
.inj-machine-select {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  accent-color: var(--inj-accent);
}
.inj-machine-card header strong {
  flex: 1;
}
.inj-machine-card.inj-machine-selected {
  border-color: var(--inj-accent);
  background: #f0faf7;
  box-shadow: inset 0 0 0 1px var(--inj-accent);
}
</style>
