<script setup lang="ts">
import ApprovalDetailPanel from '@/components/workbench/ApprovalDetailPanel.vue'
import ApprovalFilters from '@/components/workbench/ApprovalFilters.vue'
import ApprovalTable from '@/components/workbench/ApprovalTable.vue'
import PortalHero from '@/components/portal/PortalHero.vue'
import { useAppStore } from '@/stores/app'

const appStore = useAppStore()
</script>

<template>
  <div class="rrn-portal app-page space-y-6" data-portal-ui="jade-v3" data-portal-region="workbench">
    <PortalHero
      eyebrow="Approval Workspace"
      title="业务审批与订单工作台"
      description="左侧列表高效筛选，右侧固定详情面板承载审批、进度与风险"
      motif="flow"
      pending-note="筛选与审批动作暂未接入 · 当前为示例数据"
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

<style scoped>
/* 容器查询只能匹配后代元素，容器声明在门户根节点上。 */
.rrn-portal {
  container: portal-page / inline-size;
}
</style>
