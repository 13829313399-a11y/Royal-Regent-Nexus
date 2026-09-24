export const quantityFields=['processed','good','rework','scrap','pending'] as const
export type Quantities=Record<typeof quantityFields[number],number>
export function quantityError(row:Quantities) {
  if(quantityFields.some(key=>!Number.isSafeInteger(row[key])||row[key]<0))return '数量必须为非负整数'
  if(row.processed<=0)return '加工数必须大于 0'
  if(row.processed!==row.good+row.rework+row.scrap+row.pending)return '加工数与四个品质分桶之和不一致'
  return ''
}
export function pasteQuantities(text:string): {values:Quantities;error:string}[] {
  return text.trim().split(/\r?\n/).slice(0,200).map(line=>{
    const parts=line.split(/\t|,/),values=Object.fromEntries(quantityFields.map((key,index)=>[key,parts[index]?.trim()?Number(parts[index]):NaN])) as Quantities
    return {values,error:parts.length!==5?'每行需要 5 列数量':quantityError(values)}
  })
}
