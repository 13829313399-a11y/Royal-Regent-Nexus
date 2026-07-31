export interface ThreeDSettings {
  factory_id: 'huakang-a'
  machine_count: number
  electricity_per_machine_day: number
  labor_per_day: number
  material_loss_rate: number
  profit_rate_percent: number
  revision: number
  updated_at: string
}

export interface ThreeDMaterial {
  id: string
  factory_id: 'huakang-a'
  legacy_id: string
  name: string
  material_type: string
  price_per_kg: number
  is_active: boolean
  revision: number
  created_at: string
  updated_at: string
}

export interface ThreeDProduct {
  id: string
  factory_id: 'huakang-a'
  legacy_id: string
  name: string
  customer: string
  material_name: string
  weight_g: number
  duration_hours: number
  default_quantity: number
  quoted_price: number
  image_url: string
  image_size_bytes: number
  image_sha256: string
  is_active: boolean
  revision: number
  created_at: string
  updated_at: string
}

export interface ThreeDPrinter {
  id: string
  factory_id: 'huakang-a'
  machine_no: number
  name: string
  printer_type: string
  model: string
  enabled: boolean
  connected: boolean
  state: string
  current_file: string
  progress_percent: number
  remaining_minutes: number
  live_material: string
  nozzle_temperature: number
  bed_temperature: number
  error_text: string
  last_seen_at: string
}

export interface ThreeDProductionRecord {
  id: string
  factory_id: 'huakang-a'
  legacy_id: string
  business_date: string
  machine_no: number
  status: string
  product_id: string
  product_name: string
  material_name: string
  weight_g: number
  quantity: number
  duration_hours: number
  design_fee: number
  quoted_price: number
  customer: string
  remark: string
  auto_record: boolean
  print_start_at: string
  print_end_at: string
  gcode_file: string
  revision: number
  created_at: string
  updated_at: string
}

export interface ThreeDInventory {
  id: string
  factory_id: 'huakang-a'
  material_name: string
  stock_g: number
  min_stock_g: number
  revision: number
  is_low: boolean
  updated_at: string
}

export interface ThreeDInventoryMovement {
  id: string
  factory_id: 'huakang-a'
  material_name: string
  movement_type: string
  delta_g: number
  balance_after_g: number
  business_date: string
  vendor: string
  cost: number
  remark: string
  source_record_id: string
  created_at: string
}

export interface ThreeDSchedule {
  id: string
  factory_id: 'huakang-a'
  legacy_id: string
  business_date: string
  product_id: string
  product_name: string
  customer: string
  material_name: string
  weight_g: number
  quantity: number
  machine_no: number
  priority: 'high' | 'normal' | 'low'
  status: 'pending' | 'printing' | 'done' | 'cancelled'
  remark: string
  revision: number
  created_at: string
  updated_at: string
}

export interface ThreeDMaintenance {
  id: string
  factory_id: 'huakang-a'
  legacy_id: string
  business_date: string
  machine_no: number
  maintenance_type: string
  description: string
  cost: number
  vendor: string
  remark: string
  revision: number
  created_at: string
  updated_at: string
}

export interface ThreeDAuditEvent {
  id: string
  factory_id: 'huakang-a'
  entity_type: string
  entity_id: string
  action: string
  detail: Record<string, unknown>
  actor_name: string
  actor_type: string
  request_id: string
  created_at: string
}

export interface ThreeDDashboard {
  factory_id: 'huakang-a'
  generated_at: string
  settings: ThreeDSettings
  printers: ThreeDPrinter[]
  materials: ThreeDMaterial[]
  products: ThreeDProduct[]
  records: ThreeDProductionRecord[]
  inventory: ThreeDInventory[]
  inventory_movements: ThreeDInventoryMovement[]
  schedules: ThreeDSchedule[]
  maintenance: ThreeDMaintenance[]
  day_off_dates: string[]
  summary: {
    revenue?: number
    materialCost?: number
    electricityCost?: number
    laborCost?: number
    maintenanceCost?: number
    totalCost?: number
    balance?: number
    productionDays?: number
    recordCount?: number
    productCount?: number
    lowInventoryCount?: number
    [key: string]: unknown
  }
}

export type ThreeDProductPayload = Omit<
  ThreeDProduct,
  | 'id'
  | 'legacy_id'
  | 'image_url'
  | 'image_size_bytes'
  | 'image_sha256'
  | 'is_active'
  | 'revision'
  | 'created_at'
  | 'updated_at'
> & { revision?: number }

export type ThreeDMaterialPayload = Pick<
  ThreeDMaterial,
  'factory_id' | 'name' | 'material_type' | 'price_per_kg'
> & { revision?: number }

export type ThreeDRecordPayload = Omit<
  ThreeDProductionRecord,
  | 'id'
  | 'legacy_id'
  | 'auto_record'
  | 'print_start_at'
  | 'print_end_at'
  | 'gcode_file'
  | 'revision'
  | 'created_at'
  | 'updated_at'
> & { revision?: number }

export type ThreeDSchedulePayload = Omit<
  ThreeDSchedule,
  'id' | 'legacy_id' | 'revision' | 'created_at' | 'updated_at'
> & { revision?: number }

export type ThreeDMaintenancePayload = Omit<
  ThreeDMaintenance,
  'id' | 'legacy_id' | 'revision' | 'created_at' | 'updated_at'
> & { revision?: number }
