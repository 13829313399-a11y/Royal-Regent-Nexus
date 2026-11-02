<script setup lang="ts">
import { FileSpreadsheet } from '@lucide/vue'
import { computed } from 'vue'
import UsageGuideDialog from '@/components/common/UsageGuideDialog.vue'
import QuoteCenterPanel from '@/components/modules/sales/QuoteCenterPanel.vue'
import SalesModuleWorkbench from '@/components/modules/sales/SalesModuleWorkbench.vue'
import { customerPriceUsageGuide } from '@/data/salesUsageGuides'
import { useAppStore } from '@/stores/app'

const appStore = useAppStore()
appStore.setActiveDepartment('sales-business')
const hasConfiguredCustomerMappings = computed(() => ['huaxing', 'huakang-a'].includes(appStore.activeProductionFactory.id))

</script>

<template>
  <SalesModuleWorkbench
    title="客价转换台"
    description="接收内部报价或按客户临时路线直接导入旧表，核对后输出报客价。"
    badge="客户报价转换"
    search-placeholder="搜索客户、文件或导出版本"
  >
    <template #icon><FileSpreadsheet aria-hidden="true" /></template>
    <div class="mb-4 flex justify-end">
      <UsageGuideDialog v-bind="customerPriceUsageGuide" />
    </div>
    <QuoteCenterPanel v-if="hasConfiguredCustomerMappings" />
    <section
      v-else
      data-testid="customer-price-mapping-empty"
      class="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center shadow-sm"
    >
      <strong class="text-base text-slate-900">当前厂区尚未配置报客映射</strong>
      <p class="mt-2 text-sm text-slate-500">
        华兴支持 BuzzBee、迪士尼、Dickie、彩星、银辉及独立的360临时路线；华康 A 保留原360路线。请先为本厂区新增独立客户映射链路。
      </p>
    </section>
  </SalesModuleWorkbench>
</template>
