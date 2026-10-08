<script setup lang="ts">
import { computed, provide, reactive, ref } from 'vue'
import { RouterView, useRoute, onBeforeRouteUpdate } from 'vue-router'
import { LayoutDashboard, ClipboardList, PackageCheck, Boxes, AlertTriangle, CalendarCheck2, Settings2, History } from '@lucide/vue'
import WarehouseWorkbench from '@/features/warehouse-foundation/WarehouseWorkbench.vue'
import { WAREHOUSES, WAREHOUSE_FACTORY, WAREHOUSE_HOME, isWarehouseFactory, warehousePath, type WarehouseWorkspace } from './navigation'
import { guardWarehouseFactory } from './routes'
import WarehouseGuide from './WarehouseGuide.vue'
import './workspace.css'
import { purchaseSearchKey } from './purchaseSearch'

const props = defineProps<{ warehouse: WarehouseWorkspace }>()
const route = useRoute()
const purchaseSearch = ref(''), searchSubmitted = ref(0)
provide(purchaseSearchKey, { search: purchaseSearch, submitted: searchSubmitted })
const validFactory = computed(() => isWarehouseFactory(route.query.factory))
const icons = { overview: LayoutDashboard, orders: ClipboardList, receipts: PackageCheck, inventory: Boxes, exceptions: AlertTriangle, closing: CalendarCheck2, master: Settings2, activity: History }
const home = { path: WAREHOUSE_HOME, query: { factory: WAREHOUSE_FACTORY } }
const sectionViews = reactive<Record<string, string>>({})
const showPurchaseSearch = computed(() => {
  if (props.warehouse.id !== 'fabric-warehouse' || !route.path.endsWith('/receipts')) return false
  const requested = route.query.view === undefined ? sectionViews[route.path] : route.query.view
  const views = props.warehouse.sections.find(section => section.path === 'receipts')?.views ?? []
  const active = views.some(view => view.id === requested) ? requested : 'pending'
  return active === 'pending' || (active === 'import-review' && ['all', 'returned'].includes(String(route.query.source)))
})
const guideOpen = ref(false)
const showMasterSearch = computed(() => props.warehouse.id === 'fabric-warehouse' && route.path.endsWith('/master'))
function sectionTarget(section: string) {
  const path = warehousePath(props.warehouse, section)
  return { path, query: { ...home.query, view: sectionViews[path] } }
}
function rememberView(path: string, view: string) { sectionViews[path] = view }
const sections = computed(() => props.warehouse.sections.map(section => ({
  title: section.title, path: warehousePath(props.warehouse, section.path), to: sectionTarget(section.path),
  icon: icons[section.path as keyof typeof icons],
})))
const workspaces = computed(() => WAREHOUSES.map(item => ({ title: item.title, active: item.id === props.warehouse.id, to: { path: warehousePath(item), query: home.query } })))
onBeforeRouteUpdate(guardWarehouseFactory)
</script>

<template>
  <WarehouseWorkbench v-if="validFactory" :class="{ 'fabric-receiving-workbench': warehouse.id === 'fabric-warehouse' && (route.path.endsWith('/receipts') || showMasterSearch) }" :title="warehouse.title" :description="warehouse.summary" factory-label="华康 C" :home="home" :active-path="route.path" :sections="sections" :workspaces="workspaces" @guide="guideOpen = true">
    <template #search><form v-if="showPurchaseSearch || showMasterSearch" class="fabric-header-search" role="search" @submit.prevent="searchSubmitted++"><input v-model="purchaseSearch" type="search" maxlength="128" :aria-label="showMasterSearch ? '查找基础资料' : '查找采购明细'" :placeholder="showMasterSearch ? '编码 / 名称 / 规格 / 仓库 / 仓位' : '采购单 / 生产单 / 款号 / 物料 / 供应商'" /></form></template>
    <RouterView v-slot="{ Component }"><component :is="Component" :key="route.path" :remembered-view="sectionViews[route.path]" @view-change="rememberView" /></RouterView>
    <template #overlay><WarehouseGuide v-model:open="guideOpen" :warehouse="warehouse" /></template>
  </WarehouseWorkbench>
</template>
