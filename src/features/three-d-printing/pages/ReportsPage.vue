<script setup lang="ts">
import { useWorkspaceContext } from "../context";
import TdpButton from "../components/TdpButton.vue";
import { Download } from "@lucide/vue";
const { canExport, saving, dateFrom, dateTo, exportWorkbook } =
  useWorkspaceContext();
</script>
<template>
  <section class="panel-card p-6">
    <h2>生产报表导出</h2>
    <p class="my-4 text-sm text-slate-500">
      导出生产记录、材料、产品、库存、排期和维修数据。
    </p>
    <div class="legacy-toolbar">
      <label>开始日期<input v-model="dateFrom" type="date" /></label
      ><label>结束日期<input v-model="dateTo" type="date" /></label
      ><TdpButton
        v-if="canExport"
        tone="primary"
        :busy="saving"
        @click="exportWorkbook"
      >
        <template #icon><Download :size="16" /></template>导出 Excel
      </TdpButton>
    </div>
  </section>
</template>
