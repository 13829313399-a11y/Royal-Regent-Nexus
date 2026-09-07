<script setup lang="ts">
import PrinterDetail from "../components/PrinterDetail.vue";
import { useWorkspaceContext } from "../context";
const {
  selectedPrinter,
  dashboard,
  canControl,
  printerMetrics,
  stateLabel,
  stateClass,
  money,
  sendCommand,
  CirclePause,
  CirclePlay,
  Printer,
} = useWorkspaceContext();
</script>
<template>
  <template v-if="dashboard">
    <section class="space-y-6">
      <div
        v-if="dashboard.network_health"
        class="rounded-xl border p-4 text-sm"
        :class="
          dashboard.network_health.status === 'healthy'
            ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
            : 'border-amber-200 bg-amber-50 text-amber-900'
        "
      >
        <strong>河源站点网络</strong>
        <p>{{ dashboard.network_health.message }}</p>
        <small v-if="dashboard.network_health.observed_at"
          >最近探测：{{ dashboard.network_health.observed_at }}</small
        >
      </div>
      <p
        v-if="dashboard.summary.incompleteCostRecordCount"
        class="rounded-xl bg-amber-50 p-4 text-amber-800"
      >
        {{ dashboard.summary.incompleteCostRecordCount }}
        条记录缺少完整历史成本，汇总仅包含已知金额；旧系统快照费率不等于已核实实际成本。
      </p>
      <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div class="metric-card">
          <span>打印机总数</span><strong>{{ printerMetrics.total }}</strong
          ><small>华康A 已配置机台</small>
        </div>
        <div class="metric-card">
          <span>在线</span
          ><strong class="text-emerald-700">{{
            printerMetrics.connected
          }}</strong
          ><small>30 秒内收到状态</small>
        </div>
        <div class="metric-card">
          <span>打印中</span
          ><strong class="text-sky-700">{{ printerMetrics.running }}</strong
          ><small>由边缘代理实时回传</small>
        </div>
        <div class="metric-card">
          <span>低库存</span
          ><strong class="text-amber-700">{{
            dashboard.summary.lowInventoryCount ?? 0
          }}</strong
          ><small>低于物料预警线</small>
        </div>
      </div>

      <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <PrinterDetail
          v-if="selectedPrinter"
          :id="selectedPrinter"
          @close="selectedPrinter = ''"
        />
        <article
          v-for="printerItem in dashboard.printers"
          :key="printerItem.id"
          class="panel-card p-5"
        >
          <div class="flex items-start justify-between gap-3">
            <div class="flex items-center gap-3">
              <div class="rounded-xl bg-teal-50 p-3 text-teal-700">
                <Printer class="size-5" />
              </div>
              <div>
                <h2 class="font-bold text-slate-950">
                  {{ printerItem.machine_no }}号机
                </h2>
                <p class="text-xs text-slate-500">
                  {{ printerItem.model || printerItem.printer_type }}
                </p>
              </div>
            </div>
            <span
              class="rounded-full px-2.5 py-1 text-xs font-semibold"
              :class="stateClass(printerItem)"
              >{{ stateLabel(printerItem.state) }}</span
            >
          </div>
          <p class="mt-5 min-h-10 truncate text-sm font-medium text-slate-800">
            {{ printerItem.current_file || "暂无打印文件" }}
          </p>
          <div class="mt-3 h-2 overflow-hidden rounded-full bg-slate-100">
            <div
              class="h-full rounded-full bg-teal-600 transition-all"
              :style="{ width: `${printerItem.progress_percent}%` }"
            />
          </div>
          <div class="mt-2 flex justify-between text-xs text-slate-500">
            <span>{{ printerItem.progress_percent }}%</span
            ><span>剩余 {{ printerItem.remaining_minutes }} 分钟</span>
          </div>
          <div class="mt-4 grid grid-cols-3 gap-2 text-center text-xs">
            <div class="rounded-lg bg-slate-50 p-2">
              <span class="block text-slate-400">喷嘴</span
              ><strong>{{ printerItem.nozzle_temperature }}°</strong>
            </div>
            <div class="rounded-lg bg-slate-50 p-2">
              <span class="block text-slate-400">热床</span
              ><strong>{{ printerItem.bed_temperature }}°</strong>
            </div>
            <div class="rounded-lg bg-slate-50 p-2">
              <span class="block text-slate-400">材料</span
              ><strong class="truncate">{{
                printerItem.live_material || "—"
              }}</strong>
            </div>
          </div>
          <p
            v-if="printerItem.error_text"
            class="mt-3 rounded-lg bg-rose-50 p-2 text-xs text-rose-700"
          >
            {{ printerItem.error_text }}
          </p>
          <div
            v-if="canControl"
            class="mt-4 flex gap-2 border-t border-slate-100 pt-4"
          >
            <button
              v-if="printerItem.connected && printerItem.state === 'RUNNING'"
              class="action-button warning flex-1"
              type="button"
              @click="sendCommand(printerItem, 'pause')"
            >
              <CirclePause class="size-4" />远程暂停
            </button>
            <button
              v-if="printerItem.connected && printerItem.state === 'PAUSE'"
              class="action-button flex-1"
              type="button"
              @click="sendCommand(printerItem, 'resume')"
            >
              <CirclePlay class="size-4" />恢复打印
            </button>
          </div>
          <button
            class="mt-3 text-sm text-teal-700"
            @click="selectedPrinter = printerItem.id"
          >
            状态与命令时间线
          </button>
        </article>
      </div>

      <div class="grid gap-4 lg:grid-cols-4">
        <div class="metric-card">
          <span>记录数</span
          ><strong>{{ dashboard.summary.recordCount ?? 0 }}</strong
          ><small>{{ dashboard.summary.productionDays ?? 0 }} 个生产日</small>
        </div>
        <div class="metric-card">
          <span>估算收入</span
          ><strong>{{ money(dashboard.summary.revenue) }}</strong
          ><small>使用记录保存时的计算快照</small>
        </div>
        <div class="metric-card">
          <span>总成本</span
          ><strong>{{ money(dashboard.summary.totalCost) }}</strong
          ><small>已知快照合计，人工按记录工时分摊</small>
        </div>
        <div class="metric-card">
          <span>结余</span
          ><strong>{{ money(dashboard.summary.balance) }}</strong
          ><small>当前筛选期间</small>
        </div>
      </div>
    </section>
  </template>
</template>
