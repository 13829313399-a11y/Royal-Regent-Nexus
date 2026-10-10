import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { departmentModuleRegistry, getFactoryScopedModule, getFactoryScopedRoute, type ModuleDepartmentId } from '@/data/enterpriseMock'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import { SPRAY_BASE, isSprayFactory, sprayEnabled } from '@/features/spray-production/contracts'
import { isCuttingFactory } from '@/features/cutting-operations/navigation'
import { WAREHOUSES, isWarehouseFactory } from '@/features/warehouse-operations/navigation'

/** Final visible catalog shared by the module center and personal shortcuts. */
export function useVisibleModules(department: MaybeRefOrGetter<ModuleDepartmentId>) {
  const appStore = useAppStore(), authStore = useAuthStore()
return computed(() => {
  const factory = appStore.activeProductionFactory

  return departmentModuleRegistry[toValue(department)].modules
    .filter((module) => {
      // 新 UV 工作区仅属于华康 A，不采用集团厂区兜底。
      if (module.id === 'uv-printing' && appStore.activeFactoryId !== 'huakang-a') return false
      if (module.id === 'spray-production' && !isSprayFactory(appStore.activeFactoryId)) return false
      if (module.id === 'cutting' && !isCuttingFactory(appStore.activeFactoryId)) return false
      if (WAREHOUSES.some(warehouse => warehouse.id === module.id) && !isWarehouseFactory(appStore.activeFactoryId)) return false
      if (module.factoryIds?.length && !module.factoryIds.includes(factory.id)) return false
      if (toValue(department) === 'pmc-warehouse' && module.id === 'carton-procurement'
        && !authStore.can('carton_procurement:read', factory.id)) return false
      if (
        module.strictAccess
        && module.permissions?.length
        && !authStore.canAny(module.permissions, factory.id, module.permissionDepartment)
      ) return false
      return true
    })
    .map((module) => {
    const scopedModule = getFactoryScopedModule(module, factory.id)

    if (module.id === 'cutting' || WAREHOUSES.some(warehouse => warehouse.id === module.id)) {
      return { ...scopedModule, stats: module.stats }
    }

    if (toValue(department) === 'pmc-warehouse') {
      if (module.id === 'carton-supplier') {
        const internal = authStore.can('carton_procurement:read', factory.id)
        const supplier = authStore.can('carton_supplier:read', factory.id, '*')
        return { ...scopedModule, route: supplier ? '/carton-supplier'
          : internal ? `${getFactoryScopedRoute('/modules/pmc-warehouse/carton-procurement', factory.id)}&tab=receipts&receipt_page=supplier` : '/carton-supplier' }
      }
      if (module.id === 'carton-mark-check' && (authStore.can('carton_supplier:read', '*', '*') || !authStore.can('carton_mark:read', factory.id))) {
        return { ...scopedModule, route: '/carton-supplier/carton-mark',
          owner: '供应商协同',
          summary: '查看本供应商订单的箱唛资料，选择客人 Excel 并上传印刷 PDF 核对',
          status: '供应商工作区', statusTone: 'teal' as const, todos: [],
          children: scopedModule.children.filter(child => ['客人 Excel', '印刷 PDF', '内容核对'].includes(child.label)) }
      }
    }

    if (module.id === 'uv-printing') {
      const authorized = authStore.can('uv_ops:read', factory.id, 'production')
      return {...scopedModule, summary:'机台现场、任务排程、班次核数、品质交接与材料核算',
        status:authorized ? '工作区' : '权限待开通', statusTone:'teal' as const,
        stats:authorized ? '进入华康 A 工作区' : '需要华康 A 生产部授权', detailPage:authorized,
        route:authorized ? getFactoryScopedRoute('/modules/production/uv-printing/live', factory.id) : undefined}
    }

    if (module.id === 'spray-production' && sprayEnabled()) {
      const authorized = authStore.can('spray_ops:read', factory.id, 'production')
      return { ...scopedModule, summary: '分批来料、工序排产、实绩质量、用料与交收月结',
        status: authorized ? '工作区' : '权限待开通', statusTone: 'teal' as const,
        stats: authorized ? '进入当前工厂工作区' : '需要当前工厂授权',
        detailPage: authorized, route: authorized ? getFactoryScopedRoute(`${SPRAY_BASE}/overview`, factory.id) : undefined }
    }

    if (toValue(department) === 'engineering' && module.id === 'molding-sample') {
      return {
        ...scopedModule,
        owner: `${factory.shortName} · 工程部公共模块`,
        stats: '工程开单后流转到生产任务',
        route: getFactoryScopedRoute('/modules/molding-sample', factory.id),
        statusMetrics: [
          { label: '开单', value: '工程登记', tone: 'teal' as const },
          { label: '流转', value: '主管审核', tone: 'blue' as const },
          { label: '闭环', value: '生产回传', tone: 'green' as const },
        ],
      }
    }

    if (toValue(department) === 'production' && module.id === 'molding-sample-production-task') {
      const route = getFactoryScopedRoute('/modules/production/molding-sample-tasks', factory.id)

      return {
        ...scopedModule,
        owner: `${factory.shortName} · 啤机部任务单`,
        stats: '主管审核后进入任务队列',
        route,
        statusMetrics: [
          { label: '接收', value: '审核通知', tone: 'teal' as const },
          { label: '执行', value: '用料回填', tone: 'amber' as const },
          { label: '回传', value: '工程同步', tone: 'green' as const },
        ],
      }
    }

    return scopedModule
    })
})
}
