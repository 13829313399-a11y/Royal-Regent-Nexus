/** Presentation-only fields. No posting, validation or persistence contract. */
export type WarehousePreviewValues = Record<string, string | number | undefined>

export interface WarehousePreviewField {
  id: string
  label: string
  placeholder?: string
  type?: 'date' | 'month' | 'number' | 'select' | 'textarea'
  options?: string[]
}

export interface WarehouseDocumentSpec {
  title: string
  description: string
  groups: {
    title: string
    description?: string
    fields: WarehousePreviewField[]
    repeatable?: { id: string; itemLabel: string; addLabel: string }
  }[]
  trace: string[]
}
