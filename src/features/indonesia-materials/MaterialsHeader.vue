<script setup lang="ts">
import { ArrowLeft, Building2, Search, Ship } from '@lucide/vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import AccountMenu from '@/components/layout/AccountMenu.vue'
import NotificationCenter from '@/components/notifications/NotificationCenter.vue'
import { factoryContexts, type FactoryContextId } from '@/data/enterpriseMock'
import { canChangeFactory } from '@/lib/factoryChangeGuard'
import { useAppStore } from '@/stores/app'
defineProps<{ search: string; disabled: boolean }>()
const emit = defineEmits<{ search: [value: string] }>()
const app = useAppStore()
const route = useRoute()
const router = useRouter()
function changeFactory(event: Event) {
  const select = event.target as HTMLSelectElement
  const factory = select.value as FactoryContextId
  if (factory === app.activeFactoryId || !factoryContexts.some(item => item.id === factory) || !canChangeFactory()) {
    select.value = app.activeFactoryId
    return
  }
  app.setActiveFactory(factory)
  void router.replace({ path: route.path, query: { ...route.query, factory }, hash: route.hash })
}
</script>
<template>
  <header class="im-header">
    <div class="im-header-row">
      <RouterLink class="im-back" :to="{ path: '/modules/sales-business', query: { factory: app.activeFactoryId } }"><ArrowLeft :size="16" /><span>业务部</span></RouterLink>
      <div class="im-brand"><span class="im-brand-icon"><Ship :size="23" /></span><div><strong>送印尼物料</strong><small>Indonesia Materials · 合同 / 回料 / 出货</small></div></div>
      <label class="im-header-search"><Search :size="16" /><input :value="search" type="search" aria-label="搜索合同、客户或货号" placeholder="搜索合同 / 客户 / 货号…" @input="emit('search', ($event.target as HTMLInputElement).value)"></label>
      <div class="im-header-tools">
        <label class="im-factory"><Building2 :size="15" /><span>当前厂区</span><select :value="app.activeFactoryId" :disabled="disabled" aria-label="当前厂区" @change="changeFactory"><option v-for="factory in factoryContexts" :key="factory.id" :value="factory.id">{{ factory.id === 'group' ? '集团' : factory.shortName }}</option></select></label>
        <NotificationCenter /><AccountMenu />
      </div>
    </div>
    <slot />
  </header>
</template>
