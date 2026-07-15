<script setup lang="ts">
import { Layers3 } from '@lucide/vue'
import InternalQuotePanel from '@/components/modules/sales/InternalQuotePanel.vue'
import SalesModuleWorkbench from '@/components/modules/sales/SalesModuleWorkbench.vue'
import { useAppStore } from '@/stores/app'

const appStore = useAppStore()
appStore.setActiveDepartment('sales-business')

const metrics = [
  { label: '业务维度', value: '车间', detail: '按厂区和车间独立归集' },
  { label: '协同分段', value: '8 个', detail: '业务至装配完整核价' },
  { label: '放行条件', value: '全审', detail: '八段通过后受控导出' },
]
</script>

<template>
  <SalesModuleWorkbench
    title="内部报价明细"
    description="按厂区和车间建立报价单，组织业务、工程、电子、啤机、喷油、搪胶、车缝和装配分段填报与主管审核。"
    badge="车间协同 · 八段审核"
    search-placeholder="搜索车间内部报价、产品或客户"
    :metrics="metrics"
  >
    <template #icon><Layers3 aria-hidden="true" /></template>
    <InternalQuotePanel />
  </SalesModuleWorkbench>
</template>
