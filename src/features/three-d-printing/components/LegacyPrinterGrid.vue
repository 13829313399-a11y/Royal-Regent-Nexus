<script setup lang="ts">
import { useWorkspaceContext } from "../context";
import PrinterDetail from "./PrinterDetail.vue";
const { dashboard, selectedPrinter, stateLabel } = useWorkspaceContext();
const remaining = (n: number) =>
  n >= 60 ? `${Math.floor(n / 60)}h${n % 60}m` : `${n}m`;
const tone = (connected: boolean, state: string) =>
  !connected
    ? "idle"
    : state === "RUNNING"
      ? "running"
      : state === "FINISH"
        ? "complete"
        : ["ERROR", "FAILED"].includes(state)
          ? "fault"
          : "waiting";
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
      :class="tone(p.connected, p.state)"
      @click="selectedPrinter = p.id"
    >
      <div class="machine-number">
        #{{ p.machine_no }}
        <span class="live-badge" :class="{ offline: !p.connected }">{{
          p.connected ? "实时" : "离线"
        }}</span>
      </div>
      <div class="machine-model">
        {{ p.model || (p.printer_type === "bambu" ? "Bambu" : p.printer_type) }}
      </div>
      <span class="machine-state">{{
        p.connected ? stateLabel(p.state) : "离线"
      }}</span>
      <div class="machine-file" :title="p.current_file">
        {{
          p.connected && ["RUNNING", "FINISH"].includes(p.state)
            ? filename(p.current_file) || "—"
            : "—"
        }}
      </div>
      <template v-if="p.connected && p.state === 'RUNNING'">
        <div class="machine-progress">
          <i :style="{ width: `${p.progress_percent}%` }" />
        </div>
        <div class="machine-detail">
          ● {{ p.progress_percent }}% · 剩余{{ remaining(p.remaining_minutes)
          }}<template v-if="p.total_layers">
            · {{ p.layer_num }}/{{ p.total_layers }}层</template
          >
        </div>
      </template>
      <div v-if="p.connected" class="machine-detail">
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
    v-if="selectedPrinter"
    :id="selectedPrinter"
    @close="selectedPrinter = ''"
  />
</template>
