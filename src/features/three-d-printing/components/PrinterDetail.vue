<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import {
  X,
  RefreshCw,
  Printer,
  Thermometer,
  CircleCheck,
  CircleAlert,
  CircleHelp,
  Clock3,
  FileText,
  History,
  Pause,
  Power,
  WifiOff,
} from "@lucide/vue";
import { useDialogFocus } from "@/composables/useDialogFocus";
import { http, getApiErrorMessage } from "@/lib/http";
import type { ThreeDPrinter } from "@/types/threeDPrinting";
import {
  chinaTime,
  freshestPrinter,
  groupPrinterEvents,
  printerStateText,
  isPrinterPreparing,
  printerPreparationText,
  type PrinterEvent,
} from "../printerPresentation";
const props = defineProps<{ id: string; printer?: ThreeDPrinter; open: boolean }>();
const emit = defineEmits<{ close: []; 'after-close': [] }>();
const root = ref<HTMLElement | null>(null);
useDialogFocus(() => true, root, { onEscape: () => emit("close") });
const data = ref<{
  printer: ThreeDPrinter;
  events: PrinterEvent[];
  commands: {
    id: string;
    action: string;
    status: string;
    requested_at: string;
    result_message: string;
  }[];
}>();
const error = ref(""),
  loading = ref(false);
const printer = computed(() =>
  freshestPrinter(props.printer, data.value?.printer),
);
const online = computed(
  () => !!printer.value?.connected && !printer.value.status_stale,
);
const state = computed(() =>
  online.value ? printer.value?.state || "UNKNOWN" : "OFFLINE",
);
const stateTone = computed(() => ["ERROR", "FAILED"].includes(state.value) ? 'fault'
  : state.value === 'RUNNING' ? 'running' : state.value === 'FINISH' ? 'complete'
    : state.value === 'PAUSE' ? 'paused' : isPrinterPreparing(state.value) ? 'preparing' : 'idle');
const stateIcon = (value: string) => value === 'RUNNING' ? Printer
  : value === 'FINISH' ? CircleCheck : ["ERROR", "FAILED"].includes(value) ? CircleAlert
    : value === 'PAUSE' ? Pause : isPrinterPreparing(value) ? FileText
      : value === 'IDLE' ? Power : value === 'OFFLINE' ? WifiOff : Clock3;
const eventTone = (value: string) => ["ERROR", "FAILED"].includes(value) ? 'fault'
  : value === 'FINISH' ? 'complete' : value === 'PAUSE' ? 'paused' : isPrinterPreparing(value) ? 'preparing' : 'normal';
const events = computed(() => groupPrinterEvents(data.value?.events || []));
const progress = computed(() =>
  Math.min(100, Math.max(0, printer.value?.progress_percent || 0)),
);
const duration = (n: number) =>
  n >= 60
    ? `${Math.floor(n / 60)} 小时 ${Math.round(n % 60)} 分钟`
    : `${Math.round(n)} 分钟`;
const guidance = computed(() =>
  !online.value
    ? "暂未收到最新状态，请检查现场电脑、网络及打印机是否在线。"
    : isPrinterPreparing(state.value)
      ? printerPreparationText
    : {
        RUNNING: "任务进行中，可在这里查看进度和预计剩余时间。",
        FINISH: "设备报告打印完成，请到机台确认成品并取件。",
        PAUSE: "请到机台查看暂停原因，确认耗材和设备提示。",
        FAILED: "请到机台查看失败原因，再安排后续生产。",
        ERROR: "设备有异常，请按屏幕提示处理。",
        IDLE: "机台当前空闲，可以安排下一项任务。",
      }[state.value] || "正在接收设备状态。",
);
const commandText = (status: string) =>
  ({
    queued: "等待发送",
    pending: "等待发送",
    claimed: "正在处理",
    dispatched: "已发送，等待确认",
    sent: "已发送，等待确认",
    acknowledged: "设备已确认",
    acked: "设备已确认",
    succeeded: "操作成功",
    success: "操作成功",
    failed: "操作失败",
    rejected: "设备拒绝",
    expired: "已超时",
    cancelled: "已取消",
    unknown: "结果待确认",
  })[status] || "结果待确认";
let timer: ReturnType<typeof setInterval> | undefined;
let disposed = false;
async function refresh() {
  if (loading.value) return;
  loading.value = true;
  try {
    const response = await http.get(
      `/three-d-printing/printers/${props.id}/timeline`,
      { params: { factory_id: "huakang-a" } },
    );
    if (!disposed) {
      data.value = response.data;
      error.value = "";
    }
  } catch (e) {
    if (!disposed) error.value = getApiErrorMessage(e);
  } finally {
    loading.value = false;
  }
}
onMounted(() => {
  void refresh();
  timer = setInterval(() => void refresh(), 15000);
});
onBeforeUnmount(() => {
  disposed = true;
  clearInterval(timer);
});
</script>
<template>
  <Teleport to="body">
    <Transition name="tdp-drawer" appear @after-leave="emit('after-close')">
  <div v-if="open" translate="no" class="printer-overlay tdp-theme" @click.self="emit('close')">
    <aside
      ref="root"
      role="dialog"
      aria-modal="true"
      aria-labelledby="printer-detail-title"
      class="printer-detail"
      tabindex="-1"
    >
      <header class="detail-header">
        <div class="device-icon"><Printer :size="24" /></div>
        <div class="header-title">
          <p>机台详情</p>
          <h2 id="printer-detail-title">
            {{ printer ? `${printer.machine_no} 号机` : "打印机"
            }}<small>{{ printer?.model || "Bambu" }}</small>
          </h2>
        </div>
        <button
          type="button"
          class="icon-button"
          aria-label="关闭机台详情"
          @click="emit('close')"
        >
          <X />
        </button>
      </header>
      <div class="detail-body">
        <div class="connection-line">
          <span :class="{ connected: online }"
            >● {{ online ? "设备在线" : "等待连接" }}</span
          ><button
            class="refresh-button"
            type="button"
            :disabled="loading"
            @click="refresh"
          >
            <RefreshCw :size="14" />{{ loading ? "刷新中…" : "刷新" }}
          </button>
        </div>
        <p v-if="error" role="alert" class="error-message">
          详情加载失败：{{ error }}，可点击刷新重试。
        </p>
        <section class="status-panel" :class="`status-panel--${stateTone}`">
          <span class="eyebrow">当前状态</span>
          <h3><component :is="stateIcon(state)" :size="24" aria-hidden="true" />{{ printerStateText(state) }}</h3>
          <p>{{ guidance }}</p>
          <p v-if="printer?.error_text" class="error-message">
            设备提示：{{ printer.error_text }}
          </p>
        </section>
        <section v-if="printer" class="task-panel">
          <h3>
            {{
              online && (["RUNNING", "PAUSE"].includes(state) || isPrinterPreparing(state))
                ? "当前打印任务"
                : "最近一次任务"
            }}
          </h3>
          <p class="file-name">
            {{ printer.current_file || "设备尚未上报任务名称" }}
          </p>
          <template v-if="online && ['RUNNING', 'PAUSE'].includes(state)">
            <div class="progress-caption">
              <strong>{{ progress }}%</strong
              ><span>预计剩余 {{ duration(printer.remaining_minutes) }}</span>
            </div>
            <div
              class="progress-track"
              role="progressbar"
              aria-label="打印进度"
              :aria-valuenow="progress"
              :aria-valuemin="0"
              :aria-valuemax="100"
            >
              <i :style="{ width: `${progress}%` }" />
            </div>
            <p v-if="printer.total_layers" class="muted">
              已打印 {{ printer.layer_num || 0 }} /
              {{ printer.total_layers }} 层
            </p>
          </template>
          <div v-if="online" class="device-readings">
            <div>
              <Thermometer :size="16" /><span>喷头温度</span
              ><strong>{{ Math.round(printer.nozzle_temperature) }}°C</strong
              ><small v-if="printer.nozzle_target !== undefined"
                >目标 {{ Math.round(printer.nozzle_target) }}°C</small
              >
            </div>
            <div>
              <Thermometer :size="16" /><span>热床温度</span
              ><strong>{{ Math.round(printer.bed_temperature) }}°C</strong
              ><small v-if="printer.bed_target !== undefined"
                >目标 {{ Math.round(printer.bed_target) }}°C</small
              >
            </div>
          </div>
          <p class="muted">
            材料：{{ printer.live_material || "设备未提供材料信息" }}
          </p>
        </section>
        <section class="history-panel">
          <div class="section-heading">
            <History :size="18" />
            <h3>最近状态变化</h3>
          </div>
          <p class="muted">
            相同连续上报已合并 · 北京时间<br />仅展示最近
            {{ data?.events.length || 0 }} 次上报，不代表完整任务历史。
          </p>
          <p v-if="!events.length" class="empty-state">
            {{
              loading
                ? "正在读取机台状态…"
                : "暂时没有状态记录，收到设备上报后会显示在这里。"
            }}
          </p>
          <ol class="event-list">
            <li v-for="item in events" :key="item.id" :class="`event--${eventTone(item.state)}`">
              <component :is="stateIcon(item.state)" :size="17" aria-hidden="true" />
              <div>
                <div class="event-heading">
                  <strong>{{ printerStateText(item.state) }}</strong
                  ><time>{{ chinaTime(item.observed_at) }}</time>
                </div>
                <p v-if="item.current_file" class="event-file">
                  {{ item.current_file }}
                </p>
                <p v-if="item.error_text">{{ item.error_text }}</p>
                <small v-if="item.count > 1"
                  >{{ chinaTime(item.first_at) }} 起，共
                  {{ item.count }} 次相同状态上报</small
                >
              </div>
            </li>
          </ol>
        </section>
        <details class="command-history">
          <summary>
            远程操作记录 <span>{{ data?.commands.length || 0 }}</span>
          </summary>
          <p v-if="!data?.commands.length" class="muted">暂无远程操作记录。</p>
          <ol>
            <li v-for="item in data?.commands" :key="item.id">
              <strong
                >{{
                  item.action === "pause"
                    ? "暂停打印"
                    : item.action === "resume"
                      ? "继续打印"
                      : "设备操作"
                }}
                · {{ commandText(item.status) }}</strong
              >
              <p class="muted">{{ chinaTime(item.requested_at) }}</p>
              <p v-if="item.result_message">{{ item.result_message }}</p>
            </li>
          </ol>
        </details>
      </div>
      <footer>
        最后上报：{{ chinaTime(printer?.last_seen_at || "") }} · 北京时间
      </footer>
    </aside>
  </div>
    </Transition>
  </Teleport>
</template>
<style scoped>
.printer-detail .section-heading {
  justify-content: flex-start;
  margin: 0;
  gap: 8px;
}
.printer-detail .section-heading h3 {
  margin: 0;
}
.printer-overlay {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: flex;
  justify-content: flex-end;
  background: rgb(15 23 42 / 0.42);
}
.tdp-drawer-enter-active { transition: background-color 160ms ease; }
.tdp-drawer-leave-active { transition: background-color 180ms ease; }
.tdp-drawer-enter-from,
.tdp-drawer-leave-to { background-color: transparent; }
.tdp-drawer-enter-active .printer-detail { transition: transform 260ms cubic-bezier(.16,1,.3,1), opacity 260ms cubic-bezier(.16,1,.3,1); }
.tdp-drawer-leave-active .printer-detail { transition: transform 180ms cubic-bezier(.2,.8,.2,1), opacity 180ms cubic-bezier(.2,.8,.2,1); }
.tdp-drawer-enter-from .printer-detail { transform: translateX(20px); opacity: 0; }
.tdp-drawer-leave-to .printer-detail { transform: translateX(12px); opacity: 0; }
.printer-detail {
  width: 100%;
  max-width: 620px;
  height: 100dvh;
  display: flex;
  flex-direction: column;
  background: var(--background);
  color: var(--foreground);
  box-shadow: -8px 0 40px rgb(0 0 0 / 0.12);
}
.detail-header {
  display: flex;
  gap: 14px;
  align-items: center;
  padding: 22px 26px;
  border-bottom: 1px solid var(--border);
}
.device-icon {
  padding: 12px;
  border-radius: 12px;
  background: var(--muted);
  color: var(--primary);
}
.header-title {
  flex: 1;
}
.header-title p,
.eyebrow {
  font-size: 12px;
  color: var(--muted-foreground);
}
h2 {
  font-size: 24px;
  font-weight: 700;
  margin: 2px 0;
}
h2 small {
  font-size: 13px;
  font-weight: 400;
  margin-left: 12px;
  color: var(--muted-foreground);
}
h3 {
  font-weight: 650;
}
.icon-button {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px;
  background: var(--background);
  cursor: pointer;
}
.detail-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 22px 26px;
}
.connection-line {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  color: var(--muted-foreground);
  margin-bottom: 16px;
}
.connected {
  color: var(--primary);
}
.refresh-button {
  display: flex;
  gap: 6px;
  align-items: center;
  color: var(--primary);
  cursor: pointer;
}
.status-panel {
  padding: 20px;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: var(--muted);
}
.status-panel h3 {
  font-size: 27px;
  color: var(--primary);
  margin: 5px 0;
  display: flex;
  align-items: center;
  gap: 9px;
}
.status-panel--fault { background: color-mix(in oklch, var(--destructive) 5%, var(--card)); border-color: color-mix(in oklch, var(--destructive) 24%, var(--border)); }
.status-panel--fault h3 { color: var(--color-red-800); }
.status-panel--paused { background: var(--color-amber-50); border-color: var(--color-amber-200); }
.status-panel--paused h3 { color: var(--color-amber-800); }
.status-panel--preparing { background: var(--color-blue-50); border-color: var(--color-blue-200); }
.status-panel--preparing h3 { color: var(--color-blue-700); }
.status-panel--complete { background: var(--color-emerald-50); border-color: var(--color-emerald-200); }
.status-panel--complete h3 { color: var(--color-emerald-700); }
.status-panel--idle h3 { color: var(--foreground); }
.status-panel p {
  font-size: 14px;
  line-height: 1.8;
}
.error-message {
  color: var(--destructive);
  font-size: 13px;
  margin: 10px 0;
}
.task-panel,
.history-panel {
  margin-top: 26px;
}
.file-name {
  font-size: 15px;
  overflow-wrap: anywhere;
  margin: 10px 0 18px;
  line-height: 1.7;
}
.progress-caption {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
}
.progress-caption strong {
  font-size: 24px;
  color: var(--primary);
}
.progress-caption span {
  font-size: 13px;
}
.progress-track {
  height: 7px;
  border-radius: 8px;
  background: var(--muted);
  overflow: hidden;
  margin: 8px 0;
}
.progress-track i {
  display: block;
  height: 100%;
  background: var(--primary);
}
.muted,
small {
  color: var(--muted-foreground);
  font-size: 12px;
  line-height: 1.8;
}
.device-readings {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin: 16px 0;
}
.device-readings > div {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 5px 8px;
  background: var(--muted);
  border-radius: 10px;
  padding: 14px;
  font-size: 12px;
}
.device-readings strong,
.device-readings small {
  grid-column: 2;
}
.device-readings strong {
  font-size: 22px;
}
.section-heading {
  display: flex;
  align-items: center;
  gap: 8px;
}
.event-list {
  list-style: none;
  margin: 16px 0 0;
  padding: 0;
}
.event-list li {
  display: flex;
  gap: 12px;
  padding: 14px 0;
  border-top: 1px solid var(--border);
}
.event-list svg {
  color: var(--primary);
  flex-shrink: 0;
  margin-top: 3px;
}
.event-list .event--fault svg { color: var(--color-red-800); }
.event-list .event--paused svg { color: var(--color-amber-800); }
.event-list .event--preparing svg { color: var(--color-blue-700); }
.event-list .event--complete svg { color: var(--color-emerald-700); }
.event-list li > div {
  flex: 1;
  min-width: 0;
}
.event-heading {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  font-size: 14px;
}
.event-heading time {
  font-size: 12px;
  color: var(--muted-foreground);
  white-space: nowrap;
}
.event-file {
  font-size: 12px;
  overflow-wrap: anywhere;
  margin: 6px 0;
}
.empty-state {
  padding: 20px 0;
  font-size: 13px;
  color: var(--muted-foreground);
}
.command-history {
  margin-top: 20px;
  border-top: 1px solid var(--border);
  padding-top: 16px;
  font-size: 13px;
}
.command-history summary {
  cursor: pointer;
  font-weight: 600;
}
.command-history span {
  margin-left: 8px;
  color: var(--muted-foreground);
}
.command-history li {
  padding: 12px 0;
}
.printer-detail footer {
  padding: 14px 26px;
  border-top: 1px solid var(--border);
  font-size: 12px;
  color: var(--muted-foreground);
}
@media (max-width: 600px) {
  .detail-header,
  .detail-body {
    padding: 18px;
  }
  .event-heading {
    flex-direction: column;
    gap: 3px;
  }
  .progress-caption {
    flex-wrap: wrap;
  }
}
@media (prefers-reduced-motion: reduce) {
  .tdp-drawer-enter-active,
  .tdp-drawer-leave-active,
  .tdp-drawer-enter-active .printer-detail,
  .tdp-drawer-leave-active .printer-detail { transition: none; }
  .tdp-drawer-enter-from .printer-detail,
  .tdp-drawer-leave-to .printer-detail { transform: none; opacity: 1; }
}
</style>
