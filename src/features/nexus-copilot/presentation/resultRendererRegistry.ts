import type { Component } from 'vue'
import type { AIBusinessResult } from '@/features/ai-assistant/types'
import ActionResultRenderer from './renderers/ActionResultRenderer.vue'
import CommercialResultRenderer from './renderers/CommercialResultRenderer.vue'
import KnowledgeResultRenderer from './renderers/KnowledgeResultRenderer.vue'
import SafeFallbackRenderer from './renderers/SafeFallbackRenderer.vue'
import SchedulingResultRenderer from './renderers/SchedulingResultRenderer.vue'

const schedulingKinds = new Set<AIBusinessResult['kind']>([
  'plan_context', 'backlog', 'scheduling_preview', 'scheduling_comparison',
])
const commercialKinds = new Set<AIBusinessResult['kind']>([
  'internal_quote_list', 'molding_sample_list', 'carton_procurement_list',
  'raw_material_master_list', 'raw_material_inventory_list',
  'customer_order_capabilities', 'customer_order_export_audit_list',
])

export function resultRendererFor(kind: string): Component {
  if (schedulingKinds.has(kind as AIBusinessResult['kind'])) return SchedulingResultRenderer
  if (commercialKinds.has(kind as AIBusinessResult['kind'])) return CommercialResultRenderer
  if (kind === 'knowledge_search') return KnowledgeResultRenderer
  if (kind === 'action_confirmation') return ActionResultRenderer
  return SafeFallbackRenderer
}
