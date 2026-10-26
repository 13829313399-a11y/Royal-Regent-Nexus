import type { MaterialCategory } from '@/api/fabricReceiving'
import unitCategories from '../../../shared/materialCategoryUnits.json'

// Convenience defaults only. Confirmed master data and staff selections take priority.
export function suggestMaterialCategory(unit?: string): MaterialCategory | '' {
  const normalized = (unit ?? '').normalize('NFKC').trim().toLowerCase()
  if (unitCategories.FABRIC.includes(normalized)) return 'FABRIC'
  if (unitCategories.ACCESSORY.includes(normalized)) return 'ACCESSORY'
  return ''
}
