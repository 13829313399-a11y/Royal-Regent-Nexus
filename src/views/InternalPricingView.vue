<script setup lang="ts">
import { Calculator } from '@lucide/vue'
import InternalPricingPanel from '@/components/modules/sales/InternalPricingPanel.vue'
import SalesModuleWorkbench from '@/components/modules/sales/SalesModuleWorkbench.vue'
import { useAppStore } from '@/stores/app'

const appStore = useAppStore()
appStore.setActiveDepartment('sales-business')

const metrics = [
  { label: '计算方式', value: '实时', detail: '输入变化立即重算' },
  { label: '保存校验', value: '双端', detail: '服务器独立复算' },
  { label: '规则来源', value: '客户', detail: '定价上下文集中下发' },
]
</script>

<template>
  <SalesModuleWorkbench
    title="内部报价"
    description="按客户定价上下文填写报价行项，实时测算规则、返点和税费，并由服务器复算保存。"
    badge="实时定价与留痕"
    search-placeholder="搜索内部报价、项目或客户"
    :metrics="metrics"
  >
    <template #icon><Calculator aria-hidden="true" /></template>
    <InternalPricingPanel />
  </SalesModuleWorkbench>
</template>
