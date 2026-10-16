import type { ClosingPreview } from './closingApi'
type OrderIdentity=Pick<ClosingPreview,'line_id'|'order_snapshot'>
export function periodOrderLabel(orders:OrderIdentity[],lineId:string){
  const order=orders.find(item=>item.line_id===lineId)?.order_snapshot
  return `${order?.customer_name||'客户未填写'} · ${order?.reference_no||lineId} · ${order?.product_no||'货号未填写'} · ${order?.product_name_zh||order?.product_name_en||'货名未填写'}`
}
export function periodMatches(orders:OrderIdentity[],lineId:string,query:string){
  return !query.trim()||periodOrderLabel(orders,lineId).toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())
}
