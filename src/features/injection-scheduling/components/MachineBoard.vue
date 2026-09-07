<script setup lang="ts">
import InjEmptyState from './ui/InjEmptyState.vue';
import { ref, onMounted, onBeforeUnmount } from 'vue';
import { useInjectionViewState } from '../composables/useInjectionViewState';
import { useInjectionStore } from '@/stores/injectionScheduling';
import { dateText, numberText, statusText, type DataRow } from '../types';
const props = defineProps<{
  machines: DataRow[];
  queues: Record<string, DataRow[]>;
  canReport: boolean;
  runningOnly: boolean;
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
  <div ref="scroller" class="inj-machine-cards" @scroll="rememberScroll">
    <article
      v-for="m in machines"
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
    <div v-if="!machines.length" class="inj-empty">
      {{
        store.machines.length
          ? runningOnly
            ? '当前没有符合筛选条件的实际在产机台。'
            : '没有符合筛选条件的机台。'
          : '还没有设备，请到基础资料新增机台或导入计划。'
      }}
    </div>
  </div>
</template>
