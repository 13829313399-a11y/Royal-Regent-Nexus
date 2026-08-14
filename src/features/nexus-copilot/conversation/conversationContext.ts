import type {
  AIContextOption,
  AIConversationContextBinding,
} from '@/api/aiConversations'
import type { AIPageContext } from '@/features/ai-assistant/types'

type ContextSource = AIContextOption | AIConversationContextBinding

function selectedEntity(source: AIConversationContextBinding) {
  if (!source.selected_entity_id || source.selected_entity_revision == null) return null
  if (source.module_id === 'injection-scheduling'
    && source.selected_entity_type === 'scheduling_backlog_order') {
    return {
      type: 'scheduling_backlog_order' as const,
      id: source.selected_entity_id,
      revision: source.selected_entity_revision,
    }
  }
  if (source.module_id === 'internal-quote'
    && source.selected_entity_type === 'internal_quote') {
    return {
      type: 'internal_quote' as const,
      id: source.selected_entity_id,
      revision: source.selected_entity_revision,
    }
  }
  return null
}

export function pageContextFromConversation(
  source: ContextSource | null | undefined,
): AIPageContext | null {
  if (!source) return null
  const entity = 'context_version' in source ? selectedEntity(source) : null
  switch (source.module_id) {
    case 'injection-scheduling':
      return source.route_name === 'injection-scheduling-v2'
        && source.path === '/modules/production/injection-scheduling'
        ? {
            route_name: source.route_name,
            path: source.path,
            factory_id: source.factory_scope,
            module_id: source.module_id,
            selected_entity: entity?.type === 'scheduling_backlog_order' ? entity : null,
          }
        : null
    case 'internal-quote':
      return source.route_name === 'internal-quote-desk-home'
        && source.path === '/modules/sales-business/internal-quote-desk'
        ? {
            route_name: source.route_name,
            path: source.path,
            factory_id: source.factory_scope,
            module_id: source.module_id,
            selected_entity: entity?.type === 'internal_quote' ? entity : null,
          }
        : null
    case 'molding-sample':
      return source.route_name === 'molding-sample' && source.path === '/modules/molding-sample'
        ? {
            route_name: source.route_name,
            path: source.path,
            factory_id: source.factory_scope,
            module_id: source.module_id,
            selected_entity: null,
          }
        : null
    case 'carton-procurement':
      return source.route_name === 'carton-procurement'
        && source.path === '/modules/pmc-warehouse/carton-procurement'
        ? {
            route_name: source.route_name,
            path: source.path,
            factory_id: source.factory_scope,
            module_id: source.module_id,
            selected_entity: null,
          }
        : null
    case 'raw-material':
      return source.route_name === 'raw-material-management'
        && source.path === '/modules/pmc-warehouse/raw-material-management'
        ? {
            route_name: source.route_name,
            path: source.path,
            factory_id: source.factory_scope,
            module_id: source.module_id,
            selected_entity: null,
          }
        : null
    case 'customer-order':
      return source.route_name === 'customer-order-center'
        && source.path === '/modules/sales-business/po-schedule-intake'
        ? {
            route_name: source.route_name,
            path: source.path,
            factory_id: source.factory_scope,
            module_id: source.module_id,
            selected_entity: null,
          }
        : null
    default:
      return null
  }
}

export function contextDisplayLabel(moduleId: string | null | undefined) {
  return {
    'injection-scheduling': '注塑排产',
    'internal-quote': '内部报价',
    'molding-sample': '啤办任务',
    'carton-procurement': '纸箱采购',
    'raw-material': '原料管理',
    'customer-order': '客户订单',
  }[moduleId ?? ''] ?? '无业务上下文'
}
