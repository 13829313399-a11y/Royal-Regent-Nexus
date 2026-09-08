<script setup lang="ts">
import { useOperationsContext } from "../../operationsContext";
import PageControls from "../PageControls.vue";
import ProductPicker from "../ProductPicker.vue";
import EntityPicker from "../EntityPicker.vue";
import DataQualityBadge from "../DataQualityBadge.vue";
const {
  canOperate,
  loading,
  reason,
  pending,
  pendingTotal,
  pendingPage,
  matchedProduct,
  selectedRun,
  thread,
  loadPending,
  match,
  trace,
} = useOperationsContext();
</script>
<template>
  <div class="panel-card p-5">
    <h2 class="text-xl font-bold">待对账任务与追溯</h2>
    <p class="my-2 text-sm">
      仅允许为未匹配的连接器任务指定产品；不明结束状态仍保留待核对。
    </p>
    <ProductPicker v-if="canOperate" v-model="matchedProduct" /><label
      v-if="canOperate"
      >匹配备注（可选）<input v-model="reason" maxlength="500" /></label
    ><PageControls
      :page="pendingPage"
      :total="pendingTotal"
      @change="loadPending"
    />
    <article
      v-for="run in pending"
      :key="run.id"
      class="flex flex-wrap items-center justify-between gap-3 border-b py-3"
    >
      <span
        >{{ run.business_date }} · {{ run.machine_no }}号 ·
        {{ run.gcode_file || run.product_name }} · {{ run.run_status }}</span
      >
      <div>
        <button class="action-button secondary" @click="trace(run.id)">
          查看追溯</button
        ><button
          v-if="
            canOperate &&
            !run.product_id &&
            run.source_system === 'cloud-connector'
          "
          class="action-button ml-2"
          :disabled="loading || !matchedProduct"
          @click="match(run)"
        >
          确认匹配
        </button>
      </div>
    </article>
    <div class="my-4 max-w-3xl space-y-3">
      <EntityPicker
        :model-value="selectedRun"
        kind="records"
        @update:model-value="selectedRun = String($event)"
      />
      <button
        class="action-button secondary"
        :disabled="!selectedRun"
        @click="trace()"
      >
        查看完整追溯
      </button>
    </div>
    <div
      v-if="thread"
      class="space-y-4 rounded-xl bg-slate-50 p-4"
      aria-label="生产追溯"
    >
      <div>
        <h3 class="text-lg font-bold">
          {{
            thread.record.product_name ||
            thread.record.gcode_file ||
            "未匹配任务"
          }}
        </h3>
        <p>
          {{ thread.record.business_date }} · {{ thread.record.machine_no }}号机
          · {{ thread.record.quantity }}件 ·
          {{ thread.record.material_name || "材料待补充" }}
        </p>
        <p class="text-sm text-slate-600">
          开始 {{ thread.record.print_start_at || "未记录" }} · 结束
          {{ thread.record.print_end_at || "未记录" }}
        </p>
        <DataQualityBadge :flags="thread.quality_flags" />
      </div>
      <div class="grid gap-4 md:grid-cols-2">
        <section class="rounded-lg bg-white p-3">
          <h4 class="font-bold">耗材流水</h4>
          <p v-for="movement in thread.inventory_movements" :key="movement.id">
            {{ movement.business_date }} · {{ movement.material_name }} ·
            {{ movement.delta_g > 0 ? "+" : "" }}{{ movement.delta_g }}g ·
            结余{{ movement.balance_after_g }}g
          </p>
          <p
            v-if="!thread.inventory_movements.length"
            class="text-sm text-slate-500"
          >
            暂无关联流水
          </p>
        </section>
        <section class="rounded-lg bg-white p-3">
          <h4 class="font-bold">打印文件版本</h4>
          <p v-for="(file, index) in thread.file_versions" :key="index">
            {{ file.file_name }} · {{ file.version }}
          </p>
          <p v-if="!thread.file_versions.length" class="text-sm text-slate-500">
            该次运行未记录文件版本
          </p>
        </section>
        <section class="rounded-lg bg-white p-3">
          <h4 class="font-bold">质量与批次凭证</h4>
          <article v-for="evidence in thread.run_evidence" :key="evidence.id">
            <p>
              {{
                { passed: "通过", failed: "不通过", pending: "待确认" }[
                  String(evidence.data.quality)
                ]
              }}
              · {{ evidence.data.note }}
            </p>
            <p
              v-for="spool in (evidence.data.spool_snapshots as {
                id: string;
                resource_key: string;
                data: Record<string, unknown>;
              }[]) ?? []"
              :key="spool.id"
              class="text-sm text-slate-600"
            >
              {{ spool.resource_key }} · {{ spool.data.material }} · 批次
              {{ spool.data.lot }}
            </p>
          </article>
          <p v-if="!thread.run_evidence.length" class="text-sm text-slate-500">
            尚未登记质量凭证
          </p>
        </section>
        <section class="rounded-lg bg-white p-3">
          <h4 class="font-bold">内部需求回传</h4>
          <p v-for="request in thread.requests" :key="request.id">
            {{ request.data.cost_center }} · {{ request.data.quantity }}件 ·
            {{ request.data.feedback || "已完成" }}
          </p>
          <p v-if="!thread.requests.length" class="text-sm text-slate-500">
            暂无关联需求
          </p>
        </section>
      </div>
    </div>
  </div>
</template>
