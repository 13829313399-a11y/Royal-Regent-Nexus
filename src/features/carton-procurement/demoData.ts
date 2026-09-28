export type CartonTone = 'teal' | 'blue' | 'amber' | 'red' | 'slate' | 'green'

export interface CartonMaterialLine {
  id: string
  packagingType: string
  paperQuality: string
  specification: string
  unitsPerCarton: number | null
  unit: string
}

export interface CartonOrderRow {
  id: string
  orderDate: string
  customerDueDate?: string | null
  safetyLeadDays?: number
  customer: string
  contractNo: string
  itemNo: string
  orderQuantity: number | null
  materials: CartonMaterialLine[]
  dueDate: string
  status: string
  tone: CartonTone
  note: string
}

export interface WeeklyCheckRow {
  customerCode?: string
  scheduleSection?: 'PENDING' | 'CANCELLED' | 'SHIPPED'
  scheduleChange?: string
  scheduleIdentity?: string
  sourceSheet?: string
  sourceRow?: number
  manualOrdered?: boolean
  orderType?: string
  sourceReference?: string
  sourceLocation?: string
  customerDueDate?: string
  dateReviewRequired?: boolean
  procurementState?: string
  quantityMissing?: boolean
  businessCustomer?: string
  id: string
  reference: string
  poNumbers: string
  customer: string
  itemNo: string
  productName: string
  quantity: number
  cartonRule: string
  inspectionWindow: string
  result: string
  tone: CartonTone
  linkedOrder: string
  suggestion: string
}

export interface InspectionReminderRow extends WeeklyCheckRow {
  inspectionStartDate: string
  requiredDeliveryDate: string
  advanceDays: number
  daysUntilDelivery: number | null
  orderStatus: string
  reminderStatus: string
}

export interface ReceiptLineSeed {
  id: string
  orderNo: string
  description: string
  specification: string
  deliveryQuantity: number
  unitPrice: number
  receivedQuantity: number
  damagedQuantity: number
  rejectedQuantity: number
  unusableQuantity: number
}

export interface InventoryMovementRow {
  id: string
  date: string
  documentNo: string
  customer: string
  poNumber: string
  itemNo: string
  packagingType: string
  paperQuality: string
  specification: string
  movementType: '入库' | '出库' | '调整' | '冲销' | '期初'
  quantity: number
  balance: number
  location: string
  operator: string
  source: string
}

export interface ClosingRow {
  id: string
  customer: string
  period: string
  openingQuantity: number
  inboundQuantity: number
  outboundQuantity: number
  adjustmentQuantity: number
  endingQuantity: number
  endingAmount: number
  currency: string
  status: string
  tone: CartonTone
}

export interface CartonExceptionRow {
  id: string
  customer: string
  type: string
  title: string
  detail: string
  owner: string
  deadline: string
  status: string
  tone: CartonTone
}

export const cartonCustomers = ['全部客户', 'Dickie', '360', '施信', 'BuzzBee'] as const

export const cartonOrders: CartonOrderRow[] = [
  {
    id: 'CT-260805-006',
    orderDate: '2026-08-05',
    customer: 'Dickie',
    contractNo: 'SC700145365',
    itemNo: '203302044',
    orderQuantity: 3600,
    materials: [
      { id: 'CT-260805-006-01', packagingType: '外箱', paperQuality: 'A33+B', specification: '31.5 × 11.125 × 11.25 in', unitsPerCarton: 120, unit: '个' },
      { id: 'CT-260805-006-02', packagingType: '内箱', paperQuality: 'B3B', specification: '15.5 × 10.625 × 5.25 in', unitsPerCarton: 30, unit: '个' },
      { id: 'CT-260805-006-03', packagingType: '滑板纸', paperQuality: 'A9A', specification: '30.75 × 10.5 in', unitsPerCarton: 1, unit: '张' },
      { id: 'CT-260805-006-04', packagingType: '卡纸', paperQuality: '250g 灰底白', specification: '8.5 × 5.5 in', unitsPerCarton: 1, unit: '张' },
    ],
    dueDate: '2026-08-12',
    status: '待供应商确认',
    tone: 'amber',
    note: '按历史规格复用，需人工复核纸质与刀模。',
  },
  {
    id: 'CT-260804-011',
    orderDate: '2026-08-04',
    customer: '360',
    contractNo: 'SC700142616',
    itemNo: '203302028',
    orderQuantity: 3600,
    materials: [
      { id: 'CT-260804-011-01', packagingType: '外箱', paperQuality: 'A33+B', specification: '31.5 × 11.125 × 11.25 in', unitsPerCarton: 60, unit: '个' },
      { id: 'CT-260804-011-02', packagingType: '内箱', paperQuality: 'B3B', specification: '15.5 × 10.625 × 5.25 in', unitsPerCarton: 15, unit: '个' },
      { id: 'CT-260804-011-03', packagingType: '滑板纸', paperQuality: 'A9A', specification: '14.75 × 10.25 in', unitsPerCarton: 1, unit: '张' },
    ],
    dueDate: '2026-08-10',
    status: '部分收料',
    tone: 'blue',
    note: '送货单 DN26061301 已到一批，余数继续跟进。',
  },
  {
    id: 'CT-260802-004',
    orderDate: '2026-08-02',
    customer: '施信',
    contractNo: 'SC700144460',
    itemNo: '203302038',
    orderQuantity: 1800,
    materials: [
      { id: 'CT-260802-004-01', packagingType: '外箱', paperQuality: 'A33+B', specification: '31.5 × 11.125 × 11.25 in', unitsPerCarton: 40, unit: '个' },
      { id: 'CT-260802-004-02', packagingType: '卡纸', paperQuality: '300g 白卡', specification: '9.25 × 6.75 in', unitsPerCarton: 1, unit: '张' },
    ],
    dueDate: '2026-08-09',
    status: '已确认交期',
    tone: 'green',
    note: '供应商回覆 8 月 9 日送货。',
  },
  {
    id: 'CT-260731-018',
    orderDate: '2026-07-31',
    customer: 'BuzzBee',
    contractNo: 'SC700144488',
    itemNo: '203302058',
    orderQuantity: 2400,
    materials: [
      { id: 'CT-260731-018-01', packagingType: '外箱', paperQuality: 'A33+B', specification: '31.5 × 11.125 × 11.25 in', unitsPerCarton: 60, unit: '个' },
      { id: 'CT-260731-018-02', packagingType: '内箱', paperQuality: 'B3B', specification: '15.5 × 10.625 × 5.25 in', unitsPerCarton: 15, unit: '个' },
      { id: 'CT-260731-018-03', packagingType: '卡纸', paperQuality: '250g 灰底白', specification: '8.75 × 5.25 in', unitsPerCarton: 1, unit: '张' },
    ],
    dueDate: '2026-08-08',
    status: '逾期未齐',
    tone: 'red',
    note: '当前有效收料少于订单量，需确认补送日期。',
  },
]

export const weeklyChecks: WeeklyCheckRow[] = [
  {
    id: 'WK-260805-001',
    reference: 'SC700140444-100',
    poNumbers: '45012786 / 45012790',
    customer: 'Dickie',
    itemNo: '203302044',
    productName: '多文盒',
    quantity: 3600,
    cartonRule: '120 PCS / 外箱',
    inspectionWindow: '8月10日—8月13日',
    result: '已匹配',
    tone: 'green',
    linkedOrder: 'CT-260805-006',
    suggestion: '订单与验货窗口一致，无需处理。',
  },
  {
    id: 'WK-260805-002',
    reference: 'SC700145011-300',
    poNumbers: '45012803',
    customer: '360',
    itemNo: '203302028',
    productName: '彩盒套装',
    quantity: 3600,
    cartonRule: '60 PCS / 外箱',
    inspectionWindow: '8月11日—8月12日',
    result: '数量差异',
    tone: 'amber',
    linkedOrder: 'CT-260804-011',
    suggestion: '排期数量与当前已收数量不同，请人工确认余数。',
  },
  {
    id: 'WK-260805-003',
    reference: 'SC700145501-100',
    poNumbers: '45012816 / 45012817',
    customer: 'BuzzBee',
    itemNo: '203302061',
    productName: '展示盒',
    quantity: 2400,
    cartonRule: '60 PCS / 外箱',
    inspectionWindow: '8月14日—8月15日',
    result: '疑似漏单',
    tone: 'red',
    linkedOrder: '—',
    suggestion: '未找到正式纸箱订单，仅生成待核对事项。',
  },
  {
    id: 'WK-260805-004',
    reference: 'SC700144460-100',
    poNumbers: '45012742',
    customer: '施信',
    itemNo: '203302038',
    productName: '普通箱',
    quantity: 1800,
    cartonRule: '40 PCS / 外箱',
    inspectionWindow: '8月8日—8月9日',
    result: '交期变化',
    tone: 'blue',
    linkedOrder: 'CT-260802-004',
    suggestion: '验货窗口提前 1 天，请重新确认送货承诺。',
  },
]

export const receiptSeed: ReceiptLineSeed[] = [
  {
    id: 'RC-DN26061301-01',
    orderNo: 'SC700142616/Z00-203302028',
    description: '普通箱 B3B',
    specification: '15.5 × 10.625 × 5.25 inch',
    deliveryQuantity: 24,
    unitPrice: 0.96,
    receivedQuantity: 24,
    damagedQuantity: 0,
    rejectedQuantity: 0,
    unusableQuantity: 0,
  },
  {
    id: 'RC-DN26061301-02',
    orderNo: 'SC700145011/3600-203302044',
    description: '普通箱 A33+B',
    specification: '31.5 × 11.125 × 11.25 inch',
    deliveryQuantity: 6,
    unitPrice: 3.46,
    receivedQuantity: 6,
    damagedQuantity: 1,
    rejectedQuantity: 0,
    unusableQuantity: 0,
  },
  {
    id: 'RC-DN26061301-03',
    orderNo: 'SC700144488/Z00-203302058',
    description: '普通箱 A33+B',
    specification: '31.5 × 11.125 × 11.25 inch',
    deliveryQuantity: 20,
    unitPrice: 3.46,
    receivedQuantity: 20,
    damagedQuantity: 0,
    rejectedQuantity: 2,
    unusableQuantity: 0,
  },
]

export const inventoryMovements: InventoryMovementRow[] = [
  {
    id: 'MV-260805-021',
    date: '2026-08-05 10:35',
    documentNo: 'DN26061301',
    customer: '360',
    poNumber: 'SC700142616',
    itemNo: '203302028',
    packagingType: '内箱',
    paperQuality: 'B3B',
    specification: '15.5 × 10.625 × 5.25 in',
    movementType: '入库',
    quantity: 24,
    balance: 84,
    location: '纸箱仓 A-03',
    operator: '仓管·陈',
    source: '收料反馈',
  },
  {
    id: 'MV-260805-019',
    date: '2026-08-05 09:10',
    documentNo: 'OUT-260805-008',
    customer: 'Dickie',
    poNumber: 'SC700140444',
    itemNo: '203302044',
    packagingType: '外箱',
    paperQuality: 'A33+B',
    specification: '31.5 × 11.125 × 11.25 in',
    movementType: '出库',
    quantity: -18,
    balance: 42,
    location: '纸箱仓 B-01',
    operator: '仓管·李',
    source: '车间领料',
  },
  {
    id: 'MV-260804-034',
    date: '2026-08-04 16:28',
    documentNo: 'OUT-260804-014',
    customer: '施信',
    poNumber: 'SC700144460',
    itemNo: '203302038',
    packagingType: '卡纸',
    paperQuality: '300g 白卡',
    specification: '9.25 × 6.75 in',
    movementType: '出库',
    quantity: -12,
    balance: 33,
    location: '纸箱仓 A-08',
    operator: '仓管·陈',
    source: '车间领料',
  },
  {
    id: 'MV-260804-030',
    date: '2026-08-04 15:42',
    documentNo: 'ADJ-260804-002',
    customer: 'BuzzBee',
    poNumber: 'SC700144488',
    itemNo: '203302058',
    packagingType: '内箱',
    paperQuality: 'B3B',
    specification: '15.5 × 10.625 × 5.25 in',
    movementType: '调整',
    quantity: -2,
    balance: 16,
    location: '纸箱仓 C-02',
    operator: '仓管·李',
    source: '报损调整',
  },
]

export const cartonClosings: ClosingRow[] = [
  {
    id: 'CL-2607-DICKIE',
    customer: 'Dickie',
    period: '2026-07',
    openingQuantity: 188,
    inboundQuantity: 126,
    outboundQuantity: 246,
    adjustmentQuantity: -2,
    endingQuantity: 66,
    endingAmount: 228.36,
    currency: 'CNY',
    status: '待核对',
    tone: 'amber',
  },
  {
    id: 'CL-2607-360',
    customer: '360',
    period: '2026-07',
    openingQuantity: 240,
    inboundQuantity: 180,
    outboundQuantity: 312,
    adjustmentQuantity: 0,
    endingQuantity: 108,
    endingAmount: 286.44,
    currency: 'CNY',
    status: '已对平',
    tone: 'green',
  },
  {
    id: 'CL-2607-SHIXIN',
    customer: '施信',
    period: '2026-07',
    openingQuantity: 96,
    inboundQuantity: 88,
    outboundQuantity: 142,
    adjustmentQuantity: 1,
    endingQuantity: 43,
    endingAmount: 148.78,
    currency: 'CNY',
    status: '有差异',
    tone: 'red',
  },
  {
    id: 'CL-2607-BUZZBEE',
    customer: 'BuzzBee',
    period: '2026-07',
    openingQuantity: 72,
    inboundQuantity: 120,
    outboundQuantity: 168,
    adjustmentQuantity: -2,
    endingQuantity: 22,
    endingAmount: 76.12,
    currency: 'CNY',
    status: '待核对',
    tone: 'amber',
  },
]

export const cartonExceptions: CartonExceptionRow[] = [
  {
    id: 'EX-260805-011',
    customer: 'BuzzBee',
    type: '疑似漏单',
    title: '周排期未找到对应纸箱订单',
    detail: 'Reference SC700145501-100 · 验货窗口 8月14日—8月15日',
    owner: '纸箱下单',
    deadline: '今天 17:00',
    status: '待确认',
    tone: 'red',
  },
  {
    id: 'EX-260805-008',
    customer: '360',
    type: '数量差异',
    title: '排期需求与有效收料数量不一致',
    detail: 'SC700142616 · 仍需确认本批次不可用数量与补送计划',
    owner: '采购跟单',
    deadline: '明天 10:00',
    status: '处理中',
    tone: 'amber',
  },
  {
    id: 'EX-260804-016',
    customer: '施信',
    type: '月结差异',
    title: '7 月纸箱结存差 1 箱',
    detail: '系统试算 43 · 供应商对账 42 · 需核对调整流水',
    owner: '仓管',
    deadline: '8月6日',
    status: '待核对',
    tone: 'blue',
  },
  {
    id: 'EX-260731-003',
    customer: 'Dickie',
    type: '规格复核',
    title: '历史规格命中但刀模版本待确认',
    detail: '203302044 · A33+B · 31.5 × 11.125 × 11.25 in',
    owner: '纸箱下单',
    deadline: '已完成',
    status: '已关闭',
    tone: 'slate',
  },
]
