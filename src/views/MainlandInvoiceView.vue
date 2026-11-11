<script setup lang="ts">
import { computed } from 'vue'
import { FileSpreadsheet } from '@lucide/vue'
import SalesModuleWorkbench from '@/components/modules/sales/SalesModuleWorkbench.vue'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'

const app = useAppStore()
const auth = useAuthStore()
app.setActiveDepartment('accounting')
const factory = computed(() => app.activeFactory.id)
const supported = computed(() => ['huakang-a', 'huakang-b', 'huakang-d'].includes(factory.value))
const allowed = computed(() => auth.can('mainland_invoice:generate', factory.value, 'accounting'))
const frameKey = computed(() => [factory.value, auth.currentUser?.id ?? '', auth.currentUser?.identity?.employment_epoch ?? 1].join(':'))
const source = computed(() => '/mainland-invoice/?factory_id=' + encodeURIComponent(factory.value))
</script>

<template>
  <SalesModuleWorkbench title="大陆发票" description="按当前厂区生成发票并下载，第一版不保存服务器台账。" badge="在线生成" back-to="/modules/accounting" back-label="返回会计部"
    department-to="/modules/accounting" department-label="会计部模块中心">
    <template #icon><FileSpreadsheet aria-hidden="true" /></template>
    <section v-if="!supported" class="rounded-xl border bg-white p-8" role="status">
      第一版仅开放华康 A、B、D。兴信不接入，其他厂区暂未开放。
    </section>
    <section v-else-if="!allowed" class="rounded-xl border bg-white p-8" role="status">
      当前账号没有本厂区大陆发票权限，请管理员按厂区与会计部授予权限。
    </section>
    <iframe v-else :key="frameKey" :src="source" title="当前厂区大陆发票生成"
      class="min-h-[1100px] w-full rounded-xl border bg-white"
      referrerpolicy="same-origin" />
  </SalesModuleWorkbench>
</template>
