import type { PortalPaper, PortalShipment, ShipmentLine } from '@/api/cartonSupplierPortal'

/** Original supplier evidence carried into a separately reviewed ordinary order. */
export interface SupplierOrderSource {
  factoryId: string
  shipmentId: string
  sourceLineId: string
  deliveryNoteNo: string
  supplierId: string
  contractNo: string
  itemNo: string
  customerPo: string
  customerCode?: string
  papers: ShipmentLine[]
  createdOrderNo?: string
}

const identity = (value: string) => value.toLowerCase().replace(/[^a-z0-9\u4e00-\u9fff]/g, '')
const dimensions = (value: string) => (value.match(/\d+(?:[.,]\d+)?/g) ?? []).map(part => Number(part.replace(',', '.')))
const dimensionUnit = (value: string) => {
  const unit = value.match(/(inches|inch|in|英寸|cm|厘米|mm|毫米)\s*$/i)?.[1]?.toLowerCase()
  return unit && ['inches', 'inch', 'in', '英寸'].includes(unit) ? 'inch' : unit && ['mm', '毫米'].includes(unit) ? 'mm' : unit ? 'cm' : ''
}

export function supplierOrderPapers(shipment: PortalShipment, source: ShipmentLine): ShipmentLine[] {
  return shipment.lines.filter(line => line.source_type === 'AD_HOC_REVIEW'
    && identity(line.contract_no) === identity(source.contract_no)
    && identity(line.item_no) === identity(source.item_no)
    && identity(line.customer_po) === identity(source.customer_po)).map(line => ({ ...line }))
}

/** Dongkang's approved one-way alias; counting units are resolved by the formal paper. */
export function supplierPaperCompatible(source: ShipmentLine, target: PortalPaper): boolean {
  const sourceType = identity(source.packaging_type)
  const typeMatches = sourceType === identity(target.packaging_type)
    || sourceType === identity('普通箱') && identity(target.packaging_type) === identity('外箱')
  if (!typeMatches || !identity(source.paper_quality) || identity(source.paper_quality) !== identity(target.paper_quality)) return false
  const sourceDimensions = dimensions(source.specification), targetDimensions = dimensions(target.specification)
  if (![2, 3].includes(sourceDimensions.length) || sourceDimensions.length !== targetDimensions.length
    || sourceDimensions.some((value, index) => value !== targetDimensions[index])) return false
  const explicitSource = dimensionUnit(source.dimension_unit ?? ''), embeddedSource = dimensionUnit(source.specification)
  const explicitTarget = dimensionUnit(target.dimension_unit), embeddedTarget = dimensionUnit(target.specification)
  if (explicitSource && embeddedSource && explicitSource !== embeddedSource
    || explicitTarget && embeddedTarget && explicitTarget !== embeddedTarget) return false
  const sourceUnit = explicitSource || embeddedSource, targetUnit = explicitTarget || embeddedTarget || 'cm'
  return !sourceUnit || sourceUnit === targetUnit
}

export function isSupplierOrderSource(value: unknown): value is SupplierOrderSource {
  if (!value || typeof value !== 'object') return false
  const source = value as Record<string, unknown>
  const nonempty = ['factoryId', 'shipmentId', 'sourceLineId', 'deliveryNoteNo', 'contractNo', 'itemNo']
  if (!nonempty.every(key => typeof source[key] === 'string' && source[key].length > 0 && source[key].length <= 200)
    || !['supplierId', 'customerPo'].every(key => typeof source[key] === 'string' && source[key].length <= 200)
    || !['customerCode', 'createdOrderNo'].every(key => source[key] === undefined || typeof source[key] === 'string' && source[key].length <= 200)
    || !Array.isArray(source.papers) || !source.papers.length || source.papers.length > 1000) return false
  const strings = ['id', 'order_no', 'contract_no', 'customer_po', 'item_no', 'customer_name', 'child_no', 'packaging_type', 'paper_quality', 'specification', 'unit', 'quantity']
  const valid = source.papers.every(paper => paper && typeof paper === 'object'
    && strings.every(key => typeof paper[key] === 'string' && paper[key].length <= 2000)
    && paper.id && paper.source_type === 'AD_HOC_REVIEW' && paper.order_line_id === null
    && Number.isFinite(Number(paper.quantity)) && Number(paper.quantity) > 0
    && identity(paper.contract_no) === identity(source.contractNo as string)
    && identity(paper.item_no) === identity(source.itemNo as string)
    && identity(paper.customer_po) === identity(source.customerPo as string)
    && ['dimension_unit', 'original_unmatched_line_id', 'unit_price', 'delivery_unit_price', 'currency']
      .every(key => paper[key] === undefined || paper[key] === null || typeof paper[key] === 'string' && paper[key].length <= 200))
  return valid && source.papers.some(paper => paper.id === source.sourceLineId)
    && new Set(source.papers.map(paper => paper.id)).size === source.papers.length
}
