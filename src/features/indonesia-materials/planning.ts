import type { BoardOrder, MaterialRecord } from '@/api/indonesiaMaterials'
import { sameQuantity, quantity } from './warehouseMatching'

export function planningMaterials(order: BoardOrder, records: MaterialRecord[]) {
  const product = records.find(r => r.kind === 'product' && !r.data.deleted && r.data.customer === order.customer && r.data.code === order.item_no)
  const oldIds = new Set(order.demands.map(d => d.material_id))
  const addedIds: string[] = (product?.data.materials ?? []).map((r: { material_id: string }) => r.material_id).filter((id: string) => !oldIds.has(id))
  const ids = [...new Set([...oldIds, ...addedIds])]
  return { product, addedIds, materials: ids.map(id => records.find(r => r.id === id && r.kind === 'material' && !r.data.deleted)) }
}

/** Pending rows are a labelled preview, never allocation or receipt identities. */
export function contractDemands(order: BoardOrder, records: MaterialRecord[]) {
  const { product, addedIds, materials } = planningMaterials(order, records)
  const pending = addedIds.flatMap(id => {
    const material = materials.find(m => m?.id === id)
    const usage = product?.data.materials.find((r: { material_id: string }) => r.material_id === id)?.usage
    const amount = quantity(order.quantity), perPiece = quantity(usage)
    if (!material || amount === null || perPiece === null) return []
    const productAmount = amount * perPiece, scale = 10000000000000000n
    const fraction = (productAmount % scale).toString().padStart(16, '0').replace(/0+$/, '')
    const computed = `${productAmount / scale}${fraction ? `.${fraction}` : ''}`
    return [{ id: `pending:${id}`, material_id: id, code: material.data.code, name: material.data.name, unit: material.data.unit,
      quantity: computed, computed_quantity: computed, procurement_days: material.data.procurement_days ?? null,
      purchase_start: null, allocated: '0', coverage: '0', shipped: '0', shortage: computed, promised_date: null, actual_date: null, risk: 'awaiting_reply', pending: true }]
  })
  return [...order.demands.map(d => ({ ...d, pending: false })), ...pending]
}

export function planningInfo(order: BoardOrder, records: MaterialRecord[]) {
  const saved = records.find(r => r.id === order.id)?.data
  const { product, materials, addedIds } = planningMaterials(order, records)
  if (!product || !materials.length || materials.some(m => !m)) return { label: '缺货号或物料资料', needs: true, missingMaster: true, product }
  if (addedIds.length) return { label: `新增 ${addedIds.length} 种物料待同步`, needs: true, missingMaster: false, product }
  const missing = [!product.data.daily_capacity ? '日产能' : '', ...materials.filter(m => m!.data.procurement_days == null).map(m => `${m!.data.code} 采购周期`)].filter(Boolean)
  if (missing.length) return { label: missing.length === 1 ? `缺${missing[0]}` : `缺 ${missing.length} 项参数`, needs: true, missingMaster: false, product }
  const source = saved?.planning_snapshot ?? saved?.product_snapshot?.data
  const stale = !order.plan || !sameQuantity(source?.daily_capacity, product.data.daily_capacity) || order.plan.transport_days !== product.data.transport_days || order.demands.some((d, i) => d.procurement_days !== materials[i]!.data.procurement_days)
  return { label: stale ? '资料已更新，待同步' : '计划齐全', needs: stale, missingMaster: false, product }
}
