<script setup lang="ts">
import ApprovalDetailPanel from '@/components/workbench/ApprovalDetailPanel.vue'
import ApprovalFilters from '@/components/workbench/ApprovalFilters.vue'
import ApprovalTable from '@/components/workbench/ApprovalTable.vue'
import { useAppStore } from '@/stores/app'

const appStore = useAppStore()
</script>

<template>
  <div class="space-y-6">
    <div>
      <h1 class="text-3xl font-semibold tracking-tight text-slate-950">业务审批与订单工作台</h1>
      <p class="mt-2 text-sm text-slate-600">
        左侧列表高效筛选，右侧固定详情面板承载审批、进度、风险
      </p>
    </div>

    <div class="grid gap-6 xl:grid-cols-[1fr_358px]">
      <div class="space-y-6">
        <ApprovalFilters />
        <ApprovalTable
          :selected-id="appStore.selectedApproval.id"
          @select="appStore.selectApproval"
        />
      </div>

      <ApprovalDetailPanel :approval="appStore.selectedApproval" />
    </div>
  </div>
</template>
