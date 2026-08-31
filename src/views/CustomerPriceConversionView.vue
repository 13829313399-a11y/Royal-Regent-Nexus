<script setup lang="ts">
import { FileSpreadsheet } from '@lucide/vue'
import { computed } from 'vue'
import QuoteCenterPanel from '@/components/modules/sales/QuoteCenterPanel.vue'
import SalesModuleWorkbench from '@/components/modules/sales/SalesModuleWorkbench.vue'
import { useAppStore } from '@/stores/app'

const appStore = useAppStore()
appStore.setActiveDepartment('sales-business')
const hasConfiguredCustomerMappings = computed(() => ['huaxing', 'huakang-a'].includes(appStore.activeProductionFactory.id))

const metrics = computed(() => {
  if (!hasConfiguredCustomerMappings.value) {
    return [
      { label: '待转换', value: '0', detail: `${appStore.activeProductionFactory.shortName} 暂无待转换报价` },
      { label: '待复核', value: '0', detail: `${appStore.activeProductionFactory.shortName} 暂无待复核版本` },
      { label: '客户范围', value: '待配置', detail: '等待本厂客户与报价资料接入' },
    ]
  }

  if (appStore.activeProductionFactory.id === 'huakang-a') {
    return [
      { label: '待转换', value: '1', detail: '360 客户报价' },
      { label: '待复核', value: '0', detail: '等待首次 P4 转换' },
      { label: '客户范围', value: '360', detail: '当前仅华康 A 已建立映射' },
    ]
  }

  return [
    { label: '待转换', value: '5', detail: 'BuzzBee / 迪士尼 / Dickie / 彩星 / 银辉' },
    { label: '待复核', value: '1', detail: '主管核对输出版本' },
    { label: '客户范围', value: '全部', detail: '按账号权限导入和输出' },
  ]
})
</script>

<template>
  <SalesModuleWorkbench
    title="客价转换台"
    description="选择客户、导入内部报价 Excel，并按客户模板输出报客价文件与版本差异。"
    badge="客户报价转换"
    search-placeholder="搜索客户、文件或导出版本"
    :metrics="metrics"
  >
    <template #icon><FileSpreadsheet aria-hidden="true" /></template>
    <QuoteCenterPanel v-if="hasConfiguredCustomerMappings" />
    <section
      v-else
      data-testid="customer-price-mapping-empty"
      class="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center shadow-sm"
    >
      <strong class="text-base text-slate-900">当前厂区尚未配置报客映射</strong>
      <p class="mt-2 text-sm text-slate-500">
        BuzzBee、迪士尼、Dickie、彩星和银辉仅适用于华兴，360 仅适用于华康 A；请先为本厂区新增独立客户映射链路。
      </p>
    </section>
  </SalesModuleWorkbench>
</template>
