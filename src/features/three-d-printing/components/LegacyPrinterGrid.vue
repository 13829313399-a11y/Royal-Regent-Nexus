<script setup lang="ts">
import { ref, watch } from 'vue';
import { CircleAlert, CircleCheck, CircleHelp, Clock3, FileText, Pause, Power, Printer, Thermometer, Timer, WifiOff } from '@lucide/vue';
import { useWorkspaceContext } from "../context";
import PrinterDetail from "./PrinterDetail.vue";
import { isPrinterPreparing, printerPreparationText } from "../printerPresentation";
const { dashboard, selectedPrinter, stateLabel } = useWorkspaceContext();
const detailId = ref('');
const detailOpen = ref(false);
watch(selectedPrinter, id => {
  if (id) { detailId.value = id; detailOpen.value = true; }
  else detailOpen.value = false;
}, { immediate: true });
function closeDetail() { selectedPrinter.value = ''; }
function afterDetailClose() { if (!selectedPrinter.value) detailId.value = ''; }
const remaining = (n: number) =>
  n >= 60 ? `${Math.floor(n / 60)}h${n % 60}m` : `${n}m`;
const tone = (connected: boolean, stale: boolean, state: string) =>
  !connected || stale
    ? "idle"
    : state === "RUNNING"
      ? "running"
      : state === "FINISH"
        ? "complete"
        : ["ERROR", "FAILED"].includes(state)
          ? "fault"
          : isPrinterPreparing(state) ? 'preparing' : state === 'PAUSE' ? 'paused' : 'waiting';
const statusIcon = (connected: boolean, stale: boolean, state: string) =>
  !connected ? WifiOff : stale ? Clock3 : state === 'RUNNING' ? Printer
    : state === 'FINISH' ? CircleCheck : ["ERROR", "FAILED"].includes(state) ? CircleAlert
      : isPrinterPreparing(state) ? FileText : state === 'PAUSE' ? Pause : state === 'IDLE' ? Power : CircleHelp;
const statusText = (connected: boolean, stale: boolean, state: string) =>
  !connected ? '离线' : stale ? '等待状态更新' : stateLabel(state);
const filename = (name: string) =>
  name.replace(/(?:\.gcode)?\.3mf$|\.gcode$/i, "");
</script>
<template>
  <div class="legacy-machine-grid">
    <button
      v-for="p in dashboard?.printers"
      :key="p.id"
      type="button"
      class="legacy-machine"
      :class="tone(p.connected, !!p.status_stale, p.state)"
      :aria-expanded="selectedPrinter === p.id"
      aria-haspopup="dialog"
      @click="selectedPrinter = p.id"
    >
      <div class="machine-number">
        <Printer :size="15" aria-hidden="true" />#{{ p.machine_no }}
        <span class="live-badge" :class="{ offline: !p.connected || p.status_stale }">{{
          !p.connected ? "离线" : p.status_stale ? '待更新' : "实时"
        }}</span>
      </div>
      <div class="machine-model">
        {{ p.model || (p.printer_type === "bambu" ? "Bambu" : p.printer_type) }}
      </div>
      <span class="machine-state"><component :is="statusIcon(p.connected, !!p.status_stale, p.state)" :size="12" aria-hidden="true" />{{ statusText(p.connected, !!p.status_stale, p.state) }}</span>
      <div class="machine-file" :title="p.current_file">
        {{
          p.connected && !p.status_stale && (["RUNNING", "FINISH"].includes(p.state) || isPrinterPreparing(p.state))
            ? filename(p.current_file) || "—"
            : "—"
        }}
      </div>
      <div v-if="p.connected && !p.status_stale && isPrinterPreparing(p.state)" class="machine-detail">
        {{ printerPreparationText }}
      </div>
      <template v-if="p.connected && !p.status_stale && p.state === 'RUNNING'">
        <div class="machine-progress" role="progressbar" aria-label="打印进度" :aria-valuenow="p.progress_percent" aria-valuemin="0" aria-valuemax="100">
          <i :style="{ width: `${p.progress_percent}%` }" />
        </div>
        <div class="machine-detail">
          <Timer :size="12" aria-hidden="true" />{{ p.progress_percent }}% · 剩余{{ remaining(p.remaining_minutes)
          }}<template v-if="p.total_layers">
            · {{ p.layer_num }}/{{ p.total_layers }}层</template
          >
        </div>
      </template>
      <div v-if="p.connected && !p.status_stale" class="machine-detail">
        <Thermometer :size="12" aria-hidden="true" />
        喷头 {{ Math.round(p.nozzle_temperature) }}°<template
          v-if="p.nozzle_target !== undefined"
          >/{{ Math.round(p.nozzle_target) }}°</template
        >
        · 热床 {{ Math.round(p.bed_temperature) }}°<template
          v-if="p.bed_target !== undefined"
          >/{{ Math.round(p.bed_target) }}°</template
        >
      </div>
      <div v-if="p.error_text" class="machine-error">{{ p.error_text }}</div>
    </button>
  </div>
  <PrinterDetail
    v-if="detailId"
    :key="detailId"
    :open="detailOpen"
    :id="detailId"
    :printer="dashboard?.printers.find(p => p.id === detailId)"
    @close="closeDetail"
    @after-close="afterDetailClose"
  />
</template>
