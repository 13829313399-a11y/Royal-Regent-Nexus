<script setup lang="ts">
import { FileSpreadsheet } from '@lucide/vue'
import QuoteCenterPanel from '@/components/modules/sales/QuoteCenterPanel.vue'
import SalesModuleWorkbench from '@/components/modules/sales/SalesModuleWorkbench.vue'
import { useAppStore } from '@/stores/app'

const appStore = useAppStore()
appStore.setActiveDepartment('sales-business')

const metrics = [
  { label: '待转换', value: '5', detail: 'BuzzBee / 迪士尼 / Dickie / 彩星' },
  { label: '待复核', value: '1', detail: '主管核对输出版本' },
  { label: '客户范围', value: '全部', detail: '按账号权限导入和输出' },
]
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
    <QuoteCenterPanel />
  </SalesModuleWorkbench>
</template>
