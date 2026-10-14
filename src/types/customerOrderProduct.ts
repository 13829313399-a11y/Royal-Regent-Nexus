export interface OrderProductValue {
  product_no: string
  item_sheet_name: string
  product_name_zh: string
  product_name_en: string
  default_pack: string
}
export interface OrderProductChoice extends OrderProductValue { reason: string }
export interface OrderProductRule extends OrderProductValue { active: boolean; rule_revision: number; actor: string; updated_at: string }
export interface OrderProductCatalog { available: boolean; revision: number; sha256: string; products: Record<string, OrderProductRule>; can_write?: boolean }
export interface OrderProductRegistration {
  available: boolean; revision: number; sha256: string; sheets: string[]; choices: OrderProductChoice[]
  applied: Array<{ row_id: string; product_no: string; origin: string; rule: OrderProductChoice | OrderProductRule }>
  conflicts: Array<{ product_no: string; message: string }>
}
export interface OrderProductChange { revision: number; product_key: string; actor: string; created_at: string; data: { before: OrderProductRule | null; after: OrderProductRule; reason: string } }
