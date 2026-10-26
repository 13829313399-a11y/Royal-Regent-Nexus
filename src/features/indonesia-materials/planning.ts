import type { BoardOrder, MaterialRecord } from '@/api/indonesiaMaterials'
import { sameQuantity } from './warehouseMatching'

export function planningInfo(order: BoardOrder, records: MaterialRecord[]) {
  const saved = records.find(r => r.id === order.id)?.data
  const product = records.find(r => r.kind === 'product' && !r.data.deleted && r.data.customer === order.customer && r.data.code === order.item_no)
  const materials = order.demands.map(d => records.find(r => r.id === d.material_id && r.kind === 'material' && !r.data.deleted))
  if (!product || !order.demands.length || materials.some(m => !m)) return { label: '缺货号或物料资料', needs: true, missingMaster: true, product }
  const missing = [!product.data.daily_capacity ? '日产能' : '', ...materials.filter(m => m!.data.procurement_days == null).map(m => `${m!.data.code} 采购周期`)].filter(Boolean)
  if (missing.length) return { label: missing.length === 1 ? `缺${missing[0]}` : `缺 ${missing.length} 项参数`, needs: true, missingMaster: false, product }
  const source = saved?.planning_snapshot ?? saved?.product_snapshot?.data
  const stale = !order.plan || !sameQuantity(source?.daily_capacity, product.data.daily_capacity) || order.plan.transport_days !== product.data.transport_days || order.demands.some((d, i) => d.procurement_days !== materials[i]!.data.procurement_days)
  return { label: stale ? '资料已更新，待同步' : '计划齐全', needs: stale, missingMaster: false, product }
}
