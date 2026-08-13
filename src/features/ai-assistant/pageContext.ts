import type { RouteLocationNormalizedLoaded } from 'vue-router'
import { isFactoryContextId, productionFactoryContextIds } from '@/data/enterpriseMock'
import type { ProductionFactoryContextId } from '@/data/enterpriseMock'
import type { AIPageContext, AISelectedEntityHint } from './types'

function routeQueryValue(value: unknown) {
  if (Array.isArray(value)) return typeof value[0] === 'string' ? value[0] : ''
  return typeof value === 'string' ? value : ''
}

function verifiedFactoryHint(route: Pick<RouteLocationNormalizedLoaded, 'query'>, fallbackFactoryId: string) {
  const queryFactory = routeQueryValue(route.query.factory)
  const candidate = queryFactory || fallbackFactoryId
  return isFactoryContextId(candidate) && productionFactoryContextIds.includes(candidate as ProductionFactoryContextId)
    ? candidate
    : null
}

export function buildAIPageContext(
  route: Pick<RouteLocationNormalizedLoaded, 'name' | 'path' | 'query'>,
  fallbackFactoryId: string,
  selectedEntity: AISelectedEntityHint | null = null,
): AIPageContext | null {
  if (route.name === 'ai-workbench' && route.path === '/workbench/ai') {
    return {
      route_name: 'ai-workbench',
      path: '/workbench/ai',
      factory_id: null,
      module_id: 'ai-workbench',
      selected_entity: null,
    }
  }
  if (
    route.name === 'injection-scheduling-v2'
    && route.path === '/modules/production/injection-scheduling'
  ) {
    return {
      route_name: 'injection-scheduling-v2',
      path: '/modules/production/injection-scheduling',
      factory_id: verifiedFactoryHint(route, fallbackFactoryId),
      module_id: 'injection-scheduling',
      selected_entity: selectedEntity?.type === 'scheduling_backlog_order'
        ? {
            type: selectedEntity.type,
            id: selectedEntity.id,
            revision: selectedEntity.revision,
          }
        : null,
    }
  }
  if (
    route.name === 'internal-quote-desk-home'
    && route.path === '/modules/sales-business/internal-quote-desk'
  ) {
    return {
      route_name: 'internal-quote-desk-home',
      path: '/modules/sales-business/internal-quote-desk',
      factory_id: verifiedFactoryHint(route, fallbackFactoryId),
      module_id: 'internal-quote',
      selected_entity: selectedEntity?.type === 'internal_quote'
        ? {
            type: selectedEntity.type,
            id: selectedEntity.id,
            revision: selectedEntity.revision,
          }
        : null,
    }
  }
  if (
    route.name === 'molding-sample'
    && route.path === '/modules/molding-sample'
  ) {
    return {
      route_name: 'molding-sample',
      path: '/modules/molding-sample',
      factory_id: verifiedFactoryHint(route, fallbackFactoryId),
      module_id: 'molding-sample',
      selected_entity: null,
    }
  }
  if (
    route.name === 'carton-procurement'
    && route.path === '/modules/pmc-warehouse/carton-procurement'
  ) {
    return {
      route_name: 'carton-procurement',
      path: '/modules/pmc-warehouse/carton-procurement',
      factory_id: verifiedFactoryHint(route, fallbackFactoryId),
      module_id: 'carton-procurement',
      selected_entity: null,
    }
  }
  if (
    route.name === 'raw-material-management'
    && route.path === '/modules/pmc-warehouse/raw-material-management'
  ) {
    return {
      route_name: 'raw-material-management',
      path: '/modules/pmc-warehouse/raw-material-management',
      factory_id: verifiedFactoryHint(route, fallbackFactoryId),
      module_id: 'raw-material',
      selected_entity: null,
    }
  }
  if (
    route.name === 'customer-order-center'
    && route.path === '/modules/sales-business/po-schedule-intake'
  ) {
    return {
      route_name: 'customer-order-center',
      path: '/modules/sales-business/po-schedule-intake',
      factory_id: verifiedFactoryHint(route, fallbackFactoryId),
      module_id: 'customer-order',
      selected_entity: null,
    }
  }
  return null
}

export function supportsAIVisionContext(context: AIPageContext | null) {
  return context?.module_id === 'injection-scheduling' && Boolean(context.factory_id)
}

export function isAIBusinessRoute(
  route: Pick<RouteLocationNormalizedLoaded, 'name' | 'path' | 'meta'>,
) {
  const excludedNames = new Set(['login', 'register', 'change-password', 'forbidden'])
  if (typeof route.name === 'string' && excludedNames.has(route.name)) return false
  if (route.meta.requiresAuth === false || route.path.startsWith('/system/')) return false
  return route.path === '/'
    || route.path === '/workbench'
    || route.path === '/tools'
    || route.path.startsWith('/modules/')
}
