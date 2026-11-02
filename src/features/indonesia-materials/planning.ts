import type { BoardOrder, MaterialRecord } from '@/api/indonesiaMaterials'
import { sameQuantity, quantity } from './warehouseMatching'

export function planningMaterials(order: BoardOrder, records: MaterialRecord[]) {
  const product = records.find(r => r.kind === 'product' && !r.data.deleted && r.data.customer === order.customer && r.data.code === order.item_no)
  const oldIds = new Set(order.demands.map(d => d.material_id))
  const addedIds: string[] = (product?.data.materials ?? []).map((r: { material_id: string }) => r.material_id).filter((id: string) => !oldIds.has(id))
  const ids = [...new Set([...oldIds, ...addedIds])]
  const materials = ids.map(id => records.find(r => r.id === id && r.kind === 'material' && !r.data.deleted))
  const cycleIds = order.demands.filter(demand => {
    const days = materials.find(m => m?.id === demand.material_id)?.data.procurement_days
    return days != null && (days !== demand.procurement_days || (!!order.plan?.required_date && !demand.purchase_start))
  }).map(demand => demand.material_id)
  return { product, addedIds, cycleIds, materials }
}

export function procurementDefault(order: BoardOrder, material: MaterialRecord) {
  return material.data.procurement_days ?? order.demands.find(d => d.material_id === material.id)?.procurement_days ?? ''
}

/** Pending rows are a labelled preview, never allocation or receipt identities. */
export function contractDemands(order: BoardOrder, records: MaterialRecord[]) {
  const { product, addedIds, cycleIds, materials } = planningMaterials(order, records)
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
  return [...order.demands.map(d => ({ ...d, pending: false })), ...pending].map(demand => {
    const currentDays = materials.find(m => m?.id === demand.material_id)?.data.procurement_days
    const cyclePending = cycleIds.includes(demand.material_id)
    return { ...demand,
      procurementLabel: demand.pending ? '新增物料待同步' : cyclePending ? '周期已填，待同步'
        : demand.purchase_start || (demand.procurement_days == null ? '待补采购周期' : '待补计划参数'),
      procurementNote: cyclePending ? `资料库 ${currentDays} 天${demand.procurement_days != null ? ` · 本合同 ${demand.procurement_days} 天` : ' · 本合同尚未同步'}`
        : demand.procurement_days != null ? `备料 ${demand.procurement_days} 个自然日` : '',
    }
  })
}

export function planningInfo(order: BoardOrder, records: MaterialRecord[]) {
  const saved = records.find(r => r.id === order.id)?.data
  const { product, materials, addedIds, cycleIds } = planningMaterials(order, records)
  if (!product || !materials.length || materials.some(m => !m)) return { label: '缺货号或物料资料', needs: true, missingMaster: true, product }
  if (addedIds.length) return { label: `新增 ${addedIds.length} 种物料待同步`, needs: true, missingMaster: false, product }
  const missing = [!product.data.daily_capacity ? '日产能' : '', ...materials.filter(m => procurementDefault(order, m!) === '').map(m => `${m!.data.code} 采购周期`)].filter(Boolean)
  if (missing.length) return { label: missing.length === 1 ? `缺${missing[0]}` : `缺 ${missing.length} 项参数`, needs: true, missingMaster: false, product }
  const source = saved?.planning_snapshot ?? saved?.product_snapshot?.data
  const stale = !order.plan || !sameQuantity(source?.daily_capacity, product.data.daily_capacity) || order.plan.transport_days !== product.data.transport_days || cycleIds.length > 0
  return { label: stale ? '资料已更新，待同步' : '计划齐全', needs: stale, missingMaster: false, product }
}
