<script setup lang="ts">
import { CircleAlert, CircleCheck, CircleHelp, Clock3, FileText, Pause, Power, Printer, Thermometer, Timer, WifiOff } from '@lucide/vue';
import { useWorkspaceContext } from "../context";
import { hasProgress, hasReading, isPrinterPreparing, isStaleObservation, printerPreparationText, temperature } from "../printerPresentation";
const { dashboard, selectedPrinter, stateLabel, openPrinter } = useWorkspaceContext();
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
  stale ? Clock3 : !connected ? WifiOff : state === 'RUNNING' ? Printer
    : state === 'FINISH' ? CircleCheck : ["ERROR", "FAILED"].includes(state) ? CircleAlert
      : isPrinterPreparing(state) ? FileText : state === 'PAUSE' ? Pause : state === 'IDLE' ? Power : CircleHelp;
const statusText = (connected: boolean, stale: boolean, state: string) =>
  stale ? '等待状态更新' : !connected ? '离线' : stateLabel(state);
const filename = (name: string) =>
  name.replace(/(?:\.gcode)?\.3mf$|\.gcode$/i, "");
</script>
<template>
  <div class="legacy-machine-grid" data-yl-help="three-d-printing.machines">
    <button
      v-for="p in dashboard?.printers"
      :key="p.id"
      type="button"
      class="legacy-machine"
      :class="tone(p.connected, isStaleObservation(p), p.state)"
      :aria-expanded="selectedPrinter === p.id"
      aria-haspopup="dialog"
      @click="openPrinter(p.id)"
    >
      <div class="machine-number">
        <Printer :size="15" aria-hidden="true" />#{{ p.machine_no }}
        <span class="live-badge" :class="{ offline: !p.connected || p.status_stale }">{{
          isStaleObservation(p) ? "待更新" : !p.connected ? "离线" : "实时"
        }}</span>
      </div>
      <div class="machine-model">
        {{ p.model || (p.printer_type === "bambu" ? "Bambu" : p.printer_type) }}
      </div>
      <span class="machine-state"><component :is="statusIcon(p.connected, isStaleObservation(p), p.state)" :size="12" aria-hidden="true" />{{ statusText(p.connected, isStaleObservation(p), p.state) }}</span>
      <div class="machine-file" :title="p.connected && !p.status_stale ? p.current_file : undefined">
        {{
          p.connected && !p.status_stale && (["RUNNING", "FINISH"].includes(p.state) || isPrinterPreparing(p.state))
            ? filename(p.current_file || "") || "—"
            : "—"
        }}
      </div>
      <div v-if="p.connected && !p.status_stale && isPrinterPreparing(p.state)" class="machine-detail">
        {{ printerPreparationText }}
      </div>
      <template v-if="p.connected && !p.status_stale && p.state === 'RUNNING'">
        <div v-if="hasProgress(p.progress_percent)" class="machine-progress" role="progressbar" aria-label="打印进度" :aria-valuenow="p.progress_percent" aria-valuemin="0" aria-valuemax="100">
          <i :style="{ width: p.progress_percent + '%' }" />
        </div>
        <div class="machine-detail">
          <Timer :size="12" aria-hidden="true" />{{ hasProgress(p.progress_percent) ? p.progress_percent + '%' : '进度待上报' }}
          <span v-if="hasReading(p.remaining_minutes) && p.remaining_minutes >= 0"> · 剩余{{ remaining(p.remaining_minutes) }}</span>
          <span v-if="hasReading(p.layer_num) && p.total_layers"> · {{ p.layer_num }}/{{ p.total_layers }}层</span>
        </div>
      </template>
      <div v-if="p.connected && !p.status_stale" class="machine-detail">
        <Thermometer :size="12" aria-hidden="true" />
        喷头 {{ temperature(p.nozzle_temperature) }}<template v-if="hasReading(p.nozzle_target)">/{{ temperature(p.nozzle_target) }}</template>
        · 热床 {{ temperature(p.bed_temperature) }}<template v-if="hasReading(p.bed_target)">/{{ temperature(p.bed_target) }}</template>
      </div>
      <p v-else class="machine-detail">{{ isStaleObservation(p) ? "最近上报已过期" : "尚无实时连接" }}</p>
      <div v-if="p.error_text" class="machine-error">{{ p.error_text }}</div>
    </button>
  </div>
</template>
