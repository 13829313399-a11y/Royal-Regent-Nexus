import type { Data } from '@/api/indonesiaMaterials'
import { quantity } from './warehouseMatching'
function text(value: bigint) { return `${value / 100000000n}.${(value % 100000000n).toString().padStart(8, '0')}`.replace(/\.?0+$/, '') }
export function packingBalance(form: Data): { id: string; message: string }[] {
  const issues: { id: string; message: string }[] = []
  for (const line of form.lines) {
    for (const [key, label] of [['normal_quantity', '正常量'], ['spare_quantity', '备品量']] as const) {
      const expected = quantity(line[key])
      const values = form.packages.flatMap((group: Data) => group.items.filter((item: Data) => item.allocation_id === line.allocation_id).map((item: Data) => quantity(item[key]))) as (bigint | null)[]
      if (expected === null || values.some(v => v === null)) { issues.push({ id: line.allocation_id, message: `${label}须填写有效数量` }); continue }
      const total = values.reduce<bigint>((sum, v) => sum + v!, 0n), difference = expected - total
      if (difference) issues.push({ id: line.allocation_id, message: `${label}${difference > 0 ? '还差' : '多装'} ${text(difference > 0 ? difference : -difference)}` })
    }
  }
  return issues
}
