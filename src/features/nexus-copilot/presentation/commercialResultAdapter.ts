import type { RouteLocationRaw } from 'vue-router'
import type { AIBusinessResult } from '@/features/ai-assistant/types'

export interface CommercialResultItem {
  id: string
  title: string
  description: string
  meta: string
  status?: string
  to?: RouteLocationRaw
  actionLabel?: string
}

export interface CommercialResultView {
  summary: string
  notice?: string
  emptyLabel: string
  total: number
  returned: number
  offset: number
  limit: number
  items: CommercialResultItem[]
}

const cartonStatusLabels: Record<string, string> = {
  DRAFT: '草稿',
  PENDING_SUPPLIER: '待供应商确认',
  CONFIRMED: '已确认',
  PARTIALLY_RECEIVED: '部分收料',
  COMPLETED: '已完成',
  CANCELLED: '已取消',
}

function factoryQuery(factoryId?: string) {
  return factoryId ? { factory: factoryId } : {}
}

export function commercialResultView(result: AIBusinessResult): CommercialResultView | null {
  if (result.kind === 'internal_quote_list' && result.internalQuote) {
    const value = result.internalQuote
    return {
      summary: `共 ${value.total} 条，本次返回 ${value.returned} 条`,
      emptyLabel: '当前筛选条件下没有内部报价',
      total: value.total, returned: value.returned, offset: value.offset, limit: value.limit,
      items: value.quotes.map((quote) => ({
        id: quote.quoteId,
        title: quote.quoteNo,
        description: `客户：${quote.customer || '—'} · 版本：${quote.versionLabel || '—'}`,
        meta: `当前环节：${quote.currentStageLabel} · 更新时间：${quote.updatedAt || '—'}`,
        status: quote.statusLabel,
        to: {
          name: quote.navigationTarget === 'summary' ? 'internal-quote-summary' : 'internal-quote-collaboration',
          params: { quoteId: quote.quoteId },
          query: factoryQuery(result.factoryId),
        },
        actionLabel: '打开内部报价',
      })),
    }
  }
  if (result.kind === 'molding_sample_list' && result.moldingSample) {
    const value = result.moldingSample
    return {
      summary: `共 ${value.total} 条，本次返回 ${value.returned} 条`,
      emptyLabel: '当前筛选条件下没有啤办任务',
      total: value.total, returned: value.returned, offset: value.offset, limit: value.limit,
      items: value.orders.map((order) => ({
        id: order.orderId,
        title: order.orderNumber || order.orderId,
        description: `${order.productName || '产品待补充'} · ${order.clientName || '客户待补充'}`,
        meta: `阶段：${order.stage || '—'} · 开单日期：${order.orderDate || '—'} · 生产厂区：${order.productionFactoryId || '未分配'} · 更新时间：${order.updatedAt || '—'}`,
        status: order.status || '状态待确认',
        to: { name: 'molding-sample', query: { order_id: order.orderId, ...factoryQuery(result.factoryId) } },
        actionLabel: '打开啤办追踪',
      })),
    }
  }
  if (result.kind === 'carton_procurement_list' && result.cartonProcurement) {
    const value = result.cartonProcurement
    return {
      summary: `共 ${value.total} 条，本次返回 ${value.returned} 条`,
      emptyLabel: '当前筛选条件下没有纸箱采购订单',
      total: value.total, returned: value.returned, offset: value.offset, limit: value.limit,
      items: value.orders.map((order) => ({
        id: order.orderId,
        title: order.orderNo,
        description: `${order.customerName || '客户待补充'} · ${order.productName || order.itemNo || '产品待补充'}`,
        meta: `合同：${order.contractNo || '—'} · 货号：${order.itemNo || '—'} · 订单日 ${order.orderDate || '—'} · 交期 ${order.dueDate || '—'} · 版本 ${order.revision}`,
        status: cartonStatusLabels[order.status] ?? '状态待确认',
        to: { name: 'carton-procurement', query: { tab: 'orders', ...factoryQuery(result.factoryId) } },
        actionLabel: '打开纸箱采购订单',
      })),
    }
  }
  if (result.kind === 'raw_material_master_list' && result.rawMaterialMaster) {
    const value = result.rawMaterialMaster
    return {
      summary: `全厂共享目录共 ${value.total} 条，本次返回 ${value.returned} 条`,
      emptyLabel: '当前筛选条件下没有原料主数据',
      total: value.total, returned: value.returned, offset: value.offset, limit: value.limit,
      items: value.materials.map((material) => ({
        id: material.materialId,
        title: `${material.materialCode} · ${material.materialName}`,
        description: `${material.category || '类别待补充'} · ${material.spec || '规格待补充'}`,
        meta: `单位 ${material.unit || '—'} · 安全库存 ${material.safetyStockKg ?? '待维护'} kg`,
        status: material.status,
        to: { name: 'raw-material-management', query: { tab: 'material', ...factoryQuery(result.factoryId) } },
        actionLabel: '打开原料主数据',
      })),
    }
  }
  if (result.kind === 'raw_material_inventory_list' && result.rawMaterialInventory) {
    const value = result.rawMaterialInventory
    return {
      summary: `共 ${value.total} 个批次，本次返回 ${value.returned} 个`,
      emptyLabel: '当前筛选条件下没有库存批次',
      total: value.total, returned: value.returned, offset: value.offset, limit: value.limit,
      items: value.batches.map((batch) => ({
        id: batch.batchId,
        title: `${batch.materialName} · ${batch.batchNo || '批次待补充'}`,
        description: `库位：${batch.location || '—'}`,
        meta: `初始 ${batch.initialWeightKg} kg · 可用 ${batch.availableWeightKg} kg · 更新时间：${batch.updatedAt || '—'}`,
        to: { name: 'raw-material-management', query: { tab: 'batch', ...factoryQuery(result.factoryId) } },
        actionLabel: '打开库存批次',
      })),
    }
  }
  if (result.kind === 'customer_order_capabilities' && result.customerOrderCapabilities) {
    const value = result.customerOrderCapabilities
    return {
      summary: `当前厂区已配置 ${value.customers.length} 个客户订单入口`,
      notice: '当前没有权威订单总台账，不能提供官方订单总数。',
      emptyLabel: '当前厂区尚未配置客户订单映射',
      total: value.customers.length, returned: value.customers.length, offset: 0, limit: value.customers.length || 1,
      items: value.customers.map((customer) => ({
        id: customer.customerCode,
        title: customer.customerName,
        description: customer.customerCode,
        meta: '支持批量预览与受控导出',
        to: { name: 'customer-order-center', query: factoryQuery(result.factoryId) },
        actionLabel: '打开客户订单中心',
      })),
    }
  }
  if (result.kind === 'customer_order_export_audit_list' && result.customerOrderExportAudits) {
    const value = result.customerOrderExportAudits
    return {
      summary: `本次返回 ${value.returned} 条导出审计；这不是订单总数`,
      emptyLabel: '当前筛选条件下没有导出审计',
      total: value.offset + value.returned, returned: value.returned, offset: value.offset, limit: value.limit,
      items: value.audits.map((audit) => ({
        id: audit.auditId,
        title: `${audit.customerCode} · ${audit.outputFileName || '输出文件待确认'}`,
        description: `模板：${audit.outputTemplate || '—'} · 来单日期：${audit.receivedDate || '—'}`,
        meta: `确认问题 ${audit.confirmedIssueCount} · 人工修改 ${audit.manualOverrideCount} · ${audit.createdAt || '—'}`,
        to: { name: 'customer-order-center', query: factoryQuery(result.factoryId) },
        actionLabel: '打开客户订单中心',
      })),
    }
  }
  return null
}
