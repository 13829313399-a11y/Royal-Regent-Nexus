import type { AIBusinessResult, AIRawMaterialInventorySummary, AIRawMaterialMasterSummary } from '../types'
import { productionFactoryContextIds } from '@/data/enterpriseMock'
import { boundedInteger, boundedText, bool, finiteNumber, hasExactKeys, localId, record, safeLinks, text } from './contracts'


export function isRawMaterialResultCandidate(source: Record<string, unknown>) {
  const resultType = typeof source.result_type === 'string' ? source.result_type : ''
  const schemaVersion = typeof source.schema_version === 'string' ? source.schema_version : ''
  return resultType === 'raw_material'
    || resultType.startsWith('raw_material.')
    || schemaVersion === 'raw-material'
    || schemaVersion.startsWith('raw-material-')
}

function commonRawMaterialPage(source: Record<string, unknown>, itemsKey: 'materials' | 'batches') {
  const factoryId = boundedText(source.factory_id, 1, 64)
  const asOf = boundedText(source.as_of, 1, 40)
  const total = boundedInteger(source.total, 0, Number.MAX_SAFE_INTEGER)
  const returned = boundedInteger(source.returned, 0, 20)
  const limit = boundedInteger(source.limit, 1, 20)
  const offset = boundedInteger(source.offset, 0, 10_000)
  const items = Array.isArray(source[itemsKey]) ? source[itemsKey] as unknown[] : null
  if (
    !factoryId
    || !productionFactoryContextIds.includes(factoryId as (typeof productionFactoryContextIds)[number])
    || !asOf
    || total === null
    || returned === null
    || limit === null
    || offset === null
    || items === null
    || items.length > 20
    || returned !== items.length
    || total < returned
    || typeof source.truncated !== 'boolean'
    || source.truncated !== (offset + returned < total)
  ) return null
  return { factoryId, asOf, total, returned, limit, offset, items }
}

function extractRawMaterialMasterResult(source: Record<string, unknown>): AIBusinessResult | null {
  if (!hasExactKeys(source, [
    'schema_version', 'result_type', 'source_type', 'catalog_scope', 'factory_id',
    'as_of', 'total', 'limit', 'offset', 'returned', 'truncated', 'materials',
  ])) return null
  if (
    source.schema_version !== 'raw-material-master-summary-v1'
    || source.result_type !== 'raw_material.master_summary_list'
    || source.source_type !== 'FORMAL'
    || source.catalog_scope !== 'ALL_FACTORIES'
  ) return null
  const page = commonRawMaterialPage(source, 'materials')
  if (!page) return null
  const materials: AIRawMaterialMasterSummary[] = []
  for (const rawItem of page.items) {
    const item = record(rawItem)
    if (!item || !hasExactKeys(item, [
      'material_id', 'material_code', 'material_name', 'category', 'spec',
      'unit', 'safety_stock_kg', 'status', 'updated_at',
    ])) return null
    const materialId = boundedText(item.material_id, 1, 64)
    const materialCode = boundedText(item.material_code, 1, 128)
    const materialName = boundedText(item.material_name, 0, 255)
    const category = boundedText(item.category, 0, 128)
    const spec = boundedText(item.spec, 0, 255)
    const unit = boundedText(item.unit, 0, 64)
    const updatedAt = boundedText(item.updated_at, 0, 32)
    const safetyStockKg = item.safety_stock_kg === null ? null : finiteNumber(item.safety_stock_kg)
    if (
      !materialId
      || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(materialId)
      || !materialCode
      || materialName === null
      || category === null
      || spec === null
      || unit === null
      || (item.safety_stock_kg !== null && (
        safetyStockKg === undefined
        || safetyStockKg === null
        || safetyStockKg < 0
      ))
      || !['启用', '停用'].includes(String(item.status))
      || updatedAt === null
    ) return null
    materials.push({
      materialId, materialCode, materialName, category, spec, unit,
      safetyStockKg: safetyStockKg ?? null,
      status: item.status as '启用' | '停用',
      updatedAt,
    })
  }
  return {
    id: localId('result'),
    kind: 'raw_material_master_list',
    title: '原料主数据摘要',
    summary: `全厂共享目录本次返回 ${page.returned} 条，共 ${page.total} 条。`,
    sourceType: 'FORMAL',
    factoryId: page.factoryId,
    asOf: page.asOf,
    truncated: source.truncated as boolean,
    links: [],
    rawMaterialMaster: {
      total: page.total,
      returned: page.returned,
      limit: page.limit,
      offset: page.offset,
      materials,
    },
  }
}

function extractRawMaterialInventoryResult(source: Record<string, unknown>): AIBusinessResult | null {
  if (!hasExactKeys(source, [
    'schema_version', 'result_type', 'source_type', 'factory_id', 'as_of',
    'total', 'limit', 'offset', 'returned', 'truncated', 'batches',
  ])) return null
  if (
    source.schema_version !== 'raw-material-inventory-summary-v1'
    || source.result_type !== 'raw_material.inventory_summary_list'
    || source.source_type !== 'FORMAL'
  ) return null
  const page = commonRawMaterialPage(source, 'batches')
  if (!page) return null
  const batches: AIRawMaterialInventorySummary[] = []
  for (const rawItem of page.items) {
    const item = record(rawItem)
    if (!item || !hasExactKeys(item, [
      'batch_id', 'material_name', 'batch_no', 'location',
      'initial_weight_kg', 'available_weight_kg', 'updated_at',
    ])) return null
    const batchId = boundedText(item.batch_id, 1, 96)
    const materialName = boundedText(item.material_name, 0, 255)
    const batchNo = boundedText(item.batch_no, 0, 128)
    const location = boundedText(item.location, 0, 128)
    const initialWeightKg = finiteNumber(item.initial_weight_kg)
    const availableWeightKg = finiteNumber(item.available_weight_kg)
    const updatedAt = boundedText(item.updated_at, 0, 32)
    if (
      !batchId
      || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$/.test(batchId)
      || materialName === null
      || batchNo === null
      || location === null
      || initialWeightKg === undefined
      || initialWeightKg < 0
      || availableWeightKg === undefined
      || availableWeightKg < 0
      || updatedAt === null
    ) return null
    batches.push({
      batchId, materialName, batchNo, location, initialWeightKg, availableWeightKg, updatedAt,
    })
  }
  return {
    id: localId('result'),
    kind: 'raw_material_inventory_list',
    title: '原料库存摘要',
    summary: `本次返回 ${page.returned} 个批次，共 ${page.total} 个。`,
    sourceType: 'FORMAL',
    factoryId: page.factoryId,
    asOf: page.asOf,
    truncated: source.truncated as boolean,
    links: [],
    rawMaterialInventory: {
      total: page.total,
      returned: page.returned,
      limit: page.limit,
      offset: page.offset,
      batches,
    },
  }
}

export function extractRawMaterialResult(source: Record<string, unknown>) {
  if (source.result_type === 'raw_material.master_summary_list') {
    return extractRawMaterialMasterResult(source)
  }
  if (source.result_type === 'raw_material.inventory_summary_list') {
    return extractRawMaterialInventoryResult(source)
  }
  return null
}
