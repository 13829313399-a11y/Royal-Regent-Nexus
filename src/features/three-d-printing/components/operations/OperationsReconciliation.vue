<script setup lang="ts">
import { useOperationsContext } from "../../operationsContext";
import PageControls from "../PageControls.vue";
import ProductPicker from "../ProductPicker.vue";
const {
  canOperate,
  items,
  page,
  total,
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
      >匹配原因<input v-model="reason" maxlength="500" /></label
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
          :disabled="loading || !matchedProduct || !reason.trim()"
          @click="match(run)"
        >
          确认匹配
        </button>
      </div>
    </article>
    <div class="my-4 flex gap-2">
      <input
        v-model="selectedRun"
        placeholder="输入生产记录ID"
        aria-label="追溯生产记录ID"
      /><button class="action-button secondary" @click="trace()">
        查看完整追溯
      </button>
    </div>
    <pre
      v-if="thread"
      class="max-h-96 overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-3 text-xs"
      >{{ JSON.stringify(thread, null, 2) }}</pre
    >
  </div>
</template>
