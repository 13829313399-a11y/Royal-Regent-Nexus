<script setup lang="ts">
import ApprovalDetailPanel from '@/components/workbench/ApprovalDetailPanel.vue'
import ApprovalFilters from '@/components/workbench/ApprovalFilters.vue'
import ApprovalTable from '@/components/workbench/ApprovalTable.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import { useAppStore } from '@/stores/app'

const appStore = useAppStore()
</script>

<template>
  <div class="app-page space-y-6">
    <PageHeader
      eyebrow="Approval Workspace"
      title="业务审批与订单工作台"
      description="左侧列表高效筛选，右侧固定详情面板承载审批、进度与风险"
    />

    <div class="grid gap-6 xl:grid-cols-[1fr_358px]">
      <div class="min-w-0 space-y-6">
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
