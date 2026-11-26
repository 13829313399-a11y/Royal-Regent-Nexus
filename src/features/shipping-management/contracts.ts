import type { Tone } from '@/data/enterpriseMock'

/**
 * 船务管理前端示例数据。
 *
 * 当前版本只提供界面与交互框架：任务、明细、分车与基础资料均为按厂区隔离的
 * 示例数据，未接入 VoyagePlex / 旧船务系统的任何接口。字段命名沿用船务业务
 * 文档里的术语（SO、SI、截关、交仓、CBM、卡板），便于后续替换为真实 API。
 *
 * 日期顺序遵循业务口径：SI 截止 < 截关 < 装船/交仓日。
 */

export type ShippingFactoryId = 'huaxing' | 'huadeng' | 'huakang-a' | 'huakang-b' | 'huakang-d'

export type ShipmentMode = 'container' | 'warehouse' | 'customer-load' | 'customer-truck' | 'qingxi'

export type ShipmentStatus = 'waiting' | 'review' | 'shipment' | 'completed' | 'cancelled'

export type QcState = 'pass' | 'failed' | 'pending' | 'missing' | 'exempt'

export interface ShippingItem {
  id: string
  productCode: string
  productName: string
  contractNo: string
  customerPo: string
  pieces: number
  quantity: number
  cbm: number
  pallets: number
  qc: QcState
  /** 缺少每箱毛重时，制表会被阻断（可强导）。 */
  weightMissing?: boolean
}

export interface VehicleTrip {
  key: string
  truckType: string
  warehouse: string
  items: number
  cbm: number
}

export interface ShipmentReadiness {
  qc: QcState
  inventory: 'confirmed' | 'pending'
  missingWeights: number
}

export interface ShipmentTask {
  id: string
  batchNo: string
  customer: string
  mode: ShipmentMode
  status: ShipmentStatus
  so: string
  containerType: string
  port: string
  country: string
  /** 做柜工厂（整柜才有意义）。 */
  mainFactory: string
  warehouse?: string
  truckType?: string
  shipDate: string
  siDeadline: string
  cutoff: string
  deliveryDate?: string
  coordinator: string
  updatedAt: string
  special: string
  readiness: ShipmentReadiness
  items: ShippingItem[]
  vehicles: VehicleTrip[]
}

export interface ShippingCustomer {
  name: string
  cabinetSeq: string
  consigneeCode: string
  note: string
}

export interface ShippingPort {
  port: string
  country: string
  note: string
}

export interface ShippingFactoryMapping {
  english: string
  chinese: string
  local: boolean
}

export type ShippingOrderStatus = '已创建' | '已确认' | '已装柜' | '已开船' | '已取消'

export const shippingOrderStatusMeta: Record<ShippingOrderStatus, { tone: Tone }> = {
  已创建: { tone: 'slate' },
  已确认: { tone: 'blue' },
  已装柜: { tone: 'teal' },
  已开船: { tone: 'green' },
  已取消: { tone: 'red' },
}

/** 工厂货期排单的列表实体：一票货一个柜/车次，按开航日期倒序展示。 */
export interface ShippingProduct {
  code: string
  name: string
}

export interface ShippingOrder {
  id: string
  containerNo: string
  so: string
  customer: string
  containerType: string
  /** 出场时间，与开航日期一致，用于排序与区间筛选。 */
  departureDate: string
  siDeadline: string
  cutoff: string
  port: string
  destination: string
  plCount: number
  cbm: number
  special: string
  status: ShippingOrderStatus
  contractNo?: string
  filingNo?: string
  orderDate?: string
  inspectionDate?: string
  requestedShipDate?: string
  salesOrderNo?: string
  packing?: number | null
  quantity?: number | null
  standard?: string
  remark?: string
  poNo?: string
  /** 本票货物摘要，用于按货号或货名搜索。 */
  products: ShippingProduct[]
}

export interface ShippingFactoryProfile {
  factoryId: ShippingFactoryId
  label: string
  note: string
  customers: ShippingCustomer[]
  ports: ShippingPort[]
  factoryMappings: ShippingFactoryMapping[]
  tasks: ShipmentTask[]
  orders: ShippingOrder[]
}

/** 船务单据进度：SO 排出货表、补料（SI）、舱单。 */
export type DocumentStage = 'done' | 'pending' | 'todo'

export interface TaskDocuments {
  so: DocumentStage
  supplement: DocumentStage
  manifest: DocumentStage
}

export const documentStageMeta: Record<DocumentStage, { label: string; tone: Tone }> = {
  done: { label: '已完成', tone: 'green' },
  pending: { label: '处理中', tone: 'amber' },
  todo: { label: '未开始', tone: 'slate' },
}

const taskDocumentProgress: Record<string, [DocumentStage, DocumentStage, DocumentStage]> = {
  'HX-128-1': ['done', 'pending', 'todo'],
  'HX-128-2': ['pending', 'pending', 'todo'],
  'HX-129-1': ['done', 'done', 'pending'],
  'HX-130-1': ['todo', 'todo', 'todo'],
  'HX-127-1': ['done', 'done', 'done'],
  'HD-064-1': ['pending', 'done', 'todo'],
  'HD-064-2': ['done', 'done', 'pending'],
  'HD-065-1': ['todo', 'todo', 'todo'],
  'HD-063-1': ['done', 'done', 'done'],
  'KA-012-1': ['done', 'pending', 'todo'],
  'KA-012-2': ['done', 'done', 'pending'],
  'KA-011-1': ['done', 'done', 'done'],
  'KB-008-1': ['pending', 'done', 'todo'],
  'KB-008-2': ['done', 'pending', 'todo'],
  'KB-007-1': ['done', 'done', 'done'],
  'KD-003-1': ['pending', 'pending', 'todo'],
  'KD-003-2': ['done', 'done', 'done'],
}

export function taskDocuments(task: ShipmentTask): TaskDocuments {
  const [so, supplement, manifest] = taskDocumentProgress[task.id] ?? ['todo', 'todo', 'todo']
  return { so, supplement, manifest }
}

/** 按当前厂区统计三类单据的完成数量，供「已完成」指标展开说明。 */
export function documentCompletion(tasks: ShipmentTask[]) {
  const documents = tasks.map(taskDocuments)
  return {
    so: documents.filter((item) => item.so === 'done').length,
    supplement: documents.filter((item) => item.supplement === 'done').length,
    manifest: documents.filter((item) => item.manifest === 'done').length,
  }
}

export const SHIPPING_FACTORY_IDS: ShippingFactoryId[] = [
  'huaxing',
  'huadeng',
  'huakang-a',
  'huakang-b',
  'huakang-d',
]

export function isShippingFactory(value: string): value is ShippingFactoryId {
  return (SHIPPING_FACTORY_IDS as string[]).includes(value)
}

export const shipmentStatusMeta: Record<ShipmentStatus, { label: string; tone: Tone; hint: string }> = {
  waiting: { label: '等待客户通知', tone: 'slate', hint: '剩余散货，收到客户通知后再安排走货' },
  review: { label: '待复核', tone: 'amber', hint: '核对邮件解析结果与货物明细后进入待走货' },
  shipment: { label: '待走货', tone: 'blue', hint: '已确定计划走货日，等待仓库完成装柜或交仓' },
  completed: { label: '走货完成', tone: 'green', hint: '仓务已完成，库存回写闭环' },
  cancelled: { label: '已取消', tone: 'slate', hint: '任务已取消，不再参与汇总' },
}

export const shipmentModeMeta: Record<ShipmentMode, { label: string; tone: Tone }> = {
  container: { label: '整柜', tone: 'teal' },
  warehouse: { label: '交仓', tone: 'blue' },
  'customer-load': { label: '客上柜', tone: 'amber' },
  'customer-truck': { label: '客上车', tone: 'amber' },
  qingxi: { label: '清溪物流园', tone: 'slate' },
}

export const qcStateMeta: Record<QcState, { label: string; tone: Tone }> = {
  pass: { label: '验货通过', tone: 'green' },
  failed: { label: '验货不通过', tone: 'red' },
  pending: { label: '验货待出结果', tone: 'amber' },
  missing: { label: '缺少验货记录', tone: 'slate' },
  exempt: { label: '无需验货', tone: 'slate' },
}

/** 交仓分车上限：裕泰仓单车 35 CBM（新系统口径）。 */
export const WAREHOUSE_CBM_LIMIT = 35

const TRUCK_TIERS = [
  { limit: 10, truck: '1*3T' },
  { limit: 16, truck: '1*5T' },
  { limit: 20, truck: '1*8T' },
  { limit: 30, truck: '1*10T' },
  { limit: 39, truck: '1*12T' },
  { limit: 50, truck: '1*18T' },
]

/** 按体积推荐吨车；超过 50 CBM 无推荐，必须人工确认。 */
export function recommendTruck(cbm: number): string {
  const tier = TRUCK_TIERS.find((item) => cbm <= item.limit)
  return tier?.truck ?? ''
}

function startOfToday() {
  const now = new Date()
  return new Date(now.getFullYear(), now.getMonth(), now.getDate())
}

/** 相对今天的日期，避免示例数据随日期推移全部过期。 */
function day(offset: number) {
  const value = startOfToday()
  value.setDate(value.getDate() + offset)
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const date = String(value.getDate()).padStart(2, '0')
  return `${value.getFullYear()}-${month}-${date}`
}

function at(offset: number, time: string) {
  return `${day(offset)} ${time}`
}

function items(rows: Array<[string, string, string, string, number, number, number, number, QcState, boolean?]>): ShippingItem[] {
  return rows.map(([productCode, productName, contractNo, customerPo, pieces, quantity, cbm, pallets, qc, weightMissing], index) => ({
    id: `${productCode}-${index + 1}`,
    productCode,
    productName,
    contractNo,
    customerPo,
    pieces,
    quantity,
    cbm,
    pallets,
    qc,
    weightMissing: Boolean(weightMissing),
  }))
}

const huaxingTasks: ShipmentTask[] = [
  {
    id: 'HX-128-1',
    batchNo: '128-1',
    customer: 'ZURU',
    mode: 'container',
    status: 'shipment',
    so: 'SHZ8265013',
    containerType: '1*40HQ',
    port: '盐田',
    country: '美国',
    mainFactory: '兴信做柜',
    shipDate: day(3),
    siDeadline: at(0, '14:00'),
    cutoff: at(1, '17:00'),
    coordinator: '廖平',
    updatedAt: at(0, '09:20'),
    special: '立放、拉网；柜门拍照留档，外箱不可压角。',
    readiness: { qc: 'pass', inventory: 'pending', missingWeights: 0 },
    items: items([
      ['15754', '链条枪 4个/箱', '4500189918', '0958543467', 1017, 4068, 15.5, 18, 'pass'],
      ['62437', '三弹枪 6个/箱', '4500189921', '0958543468', 640, 3840, 9.8, 11, 'pass'],
      ['15789', '恐龙蛋 4个/箱', '4500189935', '0958543511', 320, 1280, 5.2, 6, 'pending'],
      ['92107', '泡泡棒 12个/箱', '4500189940', '0958543520', 180, 2160, 3.1, 4, 'exempt'],
    ]),
    vehicles: [],
  },
  {
    id: 'HX-128-2',
    batchNo: '128-2',
    customer: 'ZURU',
    mode: 'container',
    status: 'review',
    so: 'SHZ8265014',
    containerType: '1*40HQ',
    port: '盐田',
    country: '美国',
    mainFactory: '兴信做柜',
    shipDate: day(4),
    siDeadline: at(1, '11:00'),
    cutoff: at(2, '17:00'),
    coordinator: '王军',
    updatedAt: at(0, '10:05'),
    special: '与 128-1 同批拼柜，注意不要重复计入总件数。',
    readiness: { qc: 'pending', inventory: 'pending', missingWeights: 1 },
    items: items([
      ['15756', '遥控车 6个/箱', '4500189951', '0958543561', 420, 2520, 8.4, 8, 'pending', true],
      ['9548', '沙滩桶 8个/箱', '4500189960', '0958543577', 260, 2080, 4.6, 5, 'missing'],
      ['15783', '恐龙套装 4个/箱', '4500189974', '0958543588', 310, 1240, 6.9, 6, 'pending'],
    ]),
    vehicles: [],
  },
  {
    id: 'HX-129-1',
    batchNo: '129-1',
    customer: 'ZURU',
    mode: 'warehouse',
    status: 'shipment',
    so: 'SZCFS2288',
    containerType: '散货交仓',
    port: '盐田',
    country: '美国',
    mainFactory: '兴信',
    warehouse: '裕泰仓',
    truckType: '1*10T / 1*5T',
    shipDate: day(2),
    siDeadline: at(0, '12:00'),
    cutoff: at(1, '08:30'),
    deliveryDate: at(2, '11:00'),
    coordinator: '王军',
    updatedAt: at(0, '08:40'),
    special: '按 35 CBM 上限分两车；司机需带送货单原件。',
    readiness: { qc: 'pass', inventory: 'confirmed', missingWeights: 0 },
    items: items([
      ['15754', '链条枪 4个/箱', '4500189918', '0958543467', 420, 1680, 6.4, 7, 'pass'],
      ['62437', '三弹枪 6个/箱', '4500189921', '0958543468', 380, 2280, 6.1, 6, 'pass'],
      ['15789', '恐龙蛋 4个/箱', '4500189935', '0958543511', 900, 3600, 18.5, 17, 'pass'],
    ]),
    vehicles: [
      { key: '车1', truckType: '1*10T', warehouse: '裕泰仓', items: 2, cbm: 18.4 },
      { key: '车2', truckType: '1*5T', warehouse: '裕泰仓', items: 1, cbm: 12.6 },
    ],
  },
  {
    id: 'HX-130-1',
    batchNo: '130-1',
    customer: 'ZURU',
    mode: 'container',
    status: 'waiting',
    so: 'SHZ8265301',
    containerType: '1*20GP',
    port: '盐田',
    country: '美国',
    mainFactory: '兴信做柜',
    shipDate: '',
    siDeadline: '',
    cutoff: '',
    coordinator: '廖平',
    updatedAt: at(-1, '16:10'),
    special: '剩余散货等待客户通知，收到通知后再补计划走货日。',
    readiness: { qc: 'missing', inventory: 'pending', missingWeights: 0 },
    items: items([
      ['15754', '链条枪 4个/箱', '4500190022', '0958543601', 210, 840, 3.2, 4, 'missing'],
      ['92107', '泡泡棒 12个/箱', '4500190031', '0958543610', 96, 1152, 1.7, 2, 'missing'],
    ]),
    vehicles: [],
  },
  {
    id: 'HX-127-1',
    batchNo: '127-1',
    customer: 'ZURU',
    mode: 'container',
    status: 'completed',
    so: 'SHZ8264998',
    containerType: '1*40HQ',
    port: '盐田',
    country: '美国',
    mainFactory: '兴信做柜',
    shipDate: day(-6),
    siDeadline: at(-8, '14:00'),
    cutoff: at(-7, '17:00'),
    coordinator: '王军',
    updatedAt: at(-6, '18:24'),
    special: '已完成，柜号 盐田 ZURU 1004 柜。',
    readiness: { qc: 'pass', inventory: 'confirmed', missingWeights: 0 },
    items: items([
      ['15756', '遥控车 6个/箱', '4500189701', '0958543100', 520, 3120, 10.4, 10, 'pass'],
      ['15783', '恐龙套装 4个/箱', '4500189715', '0958543122', 300, 1200, 6.8, 6, 'pass'],
    ]),
    vehicles: [],
  },
]

const huadengTasks: ShipmentTask[] = [
  {
    id: 'HD-064-1',
    batchNo: '064-1',
    customer: 'MOOSE',
    mode: 'container',
    status: 'review',
    so: 'HDX77120',
    containerType: '1*45HC',
    port: '蛇口',
    country: '加拿大',
    mainFactory: '华登做柜',
    shipDate: day(5),
    siDeadline: at(2, '10:00'),
    cutoff: at(4, '16:00'),
    coordinator: '陈嘉',
    updatedAt: at(0, '09:55'),
    special: '华登做柜，兴信货需在截关前送达华登拼柜。',
    readiness: { qc: 'pending', inventory: 'pending', missingWeights: 0 },
    items: items([
      ['15812', '遥控工程车 4个/箱', '4600120411', 'MO-77410', 380, 1520, 9.6, 9, 'pending'],
      ['15901', '合金车模 8个/箱', '4600120420', 'MO-77418', 240, 1920, 4.8, 5, 'pending'],
      ['15944', '轨道车 6个/箱', '4600120433', 'MO-77426', 300, 1800, 7.2, 7, 'missing'],
    ]),
    vehicles: [],
  },
  {
    id: 'HD-064-2',
    batchNo: '064-2',
    customer: 'MOOSE',
    mode: 'warehouse',
    status: 'shipment',
    so: 'HDSO5521',
    containerType: '散货交仓',
    port: '蛇口',
    country: '加拿大',
    mainFactory: '华登',
    warehouse: '普洛斯（东莞）仓',
    truckType: '1*8T',
    shipDate: day(2),
    siDeadline: at(0, '15:00'),
    cutoff: at(1, '09:00'),
    deliveryDate: at(2, '09:30'),
    coordinator: '陈嘉',
    updatedAt: at(0, '08:30'),
    special: '交仓单需注明 MOOSE 收货编号，司机带身份证登记。',
    readiness: { qc: 'pass', inventory: 'confirmed', missingWeights: 0 },
    items: items([
      ['15812', '遥控工程车 4个/箱', '4600120411', 'MO-77410', 320, 1280, 8.1, 7, 'pass'],
      ['15901', '合金车模 8个/箱', '4600120420', 'MO-77418', 260, 2080, 5.2, 5, 'pass'],
      ['15944', '轨道车 6个/箱', '4600120433', 'MO-77426', 280, 1680, 6.9, 6, 'pass'],
    ]),
    vehicles: [{ key: '车1', truckType: '1*8T', warehouse: '普洛斯（东莞）仓', items: 3, cbm: 20.2 }],
  },
  {
    id: 'HD-065-1',
    batchNo: '065-1',
    customer: 'TOMY',
    mode: 'container',
    status: 'waiting',
    so: 'HDX77208',
    containerType: '1*20GP',
    port: '蛇口',
    country: '英国',
    mainFactory: '华登做柜',
    shipDate: '',
    siDeadline: '',
    cutoff: '',
    coordinator: '林静',
    updatedAt: at(-1, '15:40'),
    special: '客户 11 月 20 日后再确认剩余散货安排。',
    readiness: { qc: 'missing', inventory: 'pending', missingWeights: 0 },
    items: items([
      ['15520', '拼装积木 10个/箱', '4600120501', 'TM-2210', 180, 1800, 3.4, 3, 'missing'],
    ]),
    vehicles: [],
  },
  {
    id: 'HD-063-1',
    batchNo: '063-1',
    customer: 'MOOSE',
    mode: 'container',
    status: 'completed',
    so: 'HDX77088',
    containerType: '1*40HQ',
    port: '蛇口',
    country: '加拿大',
    mainFactory: '华登做柜',
    shipDate: day(-3),
    siDeadline: at(-5, '10:00'),
    cutoff: at(-4, '16:00'),
    coordinator: '陈嘉',
    updatedAt: at(-3, '17:10'),
    special: '已完成，走柜表由华登固定模板导出。',
    readiness: { qc: 'pass', inventory: 'confirmed', missingWeights: 0 },
    items: items([
      ['15812', '遥控工程车 4个/箱', '4600119901', 'MO-77301', 460, 1840, 11.2, 11, 'pass'],
      ['15901', '合金车模 8个/箱', '4600119915', 'MO-77308', 320, 2560, 6.4, 6, 'pass'],
    ]),
    vehicles: [],
  },
]

const huakangATasks: ShipmentTask[] = [
  {
    id: 'KA-012-1',
    batchNo: '012-1',
    customer: 'TOMY',
    mode: 'container',
    status: 'shipment',
    so: 'KAX55102',
    containerType: '1*40HQ',
    port: '南沙',
    country: '英国',
    mainFactory: '华康A做柜',
    shipDate: day(3),
    siDeadline: at(1, '13:00'),
    cutoff: at(2, '17:00'),
    coordinator: '周敏',
    updatedAt: at(0, '09:10'),
    special: '英国线，需提供 UKCA 标签照片。',
    readiness: { qc: 'pass', inventory: 'pending', missingWeights: 0 },
    items: items([
      ['22110', '轨道套装 4个/箱', '4700115001', 'TM-55101', 540, 2160, 12.8, 12, 'pass'],
      ['22144', '合金车队 8个/箱', '4700115012', 'TM-55108', 260, 2080, 5.4, 5, 'pass'],
      ['22190', '拼装飞机 6个/箱', '4700115030', 'TM-55115', 300, 1800, 6.6, 6, 'pending'],
    ]),
    vehicles: [],
  },
  {
    id: 'KA-012-2',
    batchNo: '012-2',
    customer: 'TOMY',
    mode: 'warehouse',
    status: 'review',
    so: 'KASO7781',
    containerType: '散货交仓',
    port: '南沙',
    country: '英国',
    mainFactory: '华康A',
    warehouse: '盐田2号仓',
    truckType: '1*12T',
    shipDate: day(4),
    siDeadline: at(2, '12:00'),
    cutoff: at(3, '08:00'),
    deliveryDate: at(3, '10:30'),
    coordinator: '周敏',
    updatedAt: at(-1, '17:35'),
    special: '交仓资料需与 UKCA 照片一并归档。',
    readiness: { qc: 'pending', inventory: 'confirmed', missingWeights: 0 },
    items: items([
      ['22110', '轨道套装 4个/箱', '4700115001', 'TM-55101', 420, 1680, 9.9, 9, 'pending'],
      ['22144', '合金车队 8个/箱', '4700115012', 'TM-55108', 380, 3040, 8.2, 8, 'pending'],
    ]),
    vehicles: [{ key: '车1', truckType: '1*12T', warehouse: '盐田2号仓', items: 2, cbm: 18.1 }],
  },
  {
    id: 'KA-011-1',
    batchNo: '011-1',
    customer: 'TOMY',
    mode: 'container',
    status: 'completed',
    so: 'KAX55040',
    containerType: '1*20GP',
    port: '南沙',
    country: '英国',
    mainFactory: '华康A做柜',
    shipDate: day(-2),
    siDeadline: at(-4, '13:00'),
    cutoff: at(-3, '17:00'),
    coordinator: '周敏',
    updatedAt: at(-2, '18:02'),
    special: '已完成。',
    readiness: { qc: 'pass', inventory: 'confirmed', missingWeights: 0 },
    items: items([
      ['22144', '合金车队 8个/箱', '4700114801', 'TM-55010', 260, 2080, 5.3, 5, 'pass'],
    ]),
    vehicles: [],
  },
]

const huakangBTasks: ShipmentTask[] = [
  {
    id: 'KB-008-1',
    batchNo: '008-1',
    customer: 'CEPIA',
    mode: 'container',
    status: 'review',
    so: 'KBX31077',
    containerType: '1*40GP',
    port: '盐田',
    country: '美国',
    mainFactory: '华康B做柜',
    shipDate: day(6),
    siDeadline: at(4, '14:00'),
    cutoff: at(5, '17:00'),
    coordinator: '黄俊',
    updatedAt: at(0, '10:20'),
    special: '客户要求柜内拍照，箱门贴 CEPIA 标签。',
    readiness: { qc: 'pending', inventory: 'pending', missingWeights: 0 },
    items: items([
      ['33101', '手工套装 6个/箱', '4800120011', 'CE-8801', 340, 2040, 8.7, 8, 'pending'],
      ['33155', '彩泥套装 12个/箱', '4800120024', 'CE-8808', 280, 3360, 6.2, 6, 'pending'],
    ]),
    vehicles: [],
  },
  {
    id: 'KB-008-2',
    batchNo: '008-2',
    customer: 'CEPIA',
    mode: 'warehouse',
    status: 'shipment',
    so: 'KBSO9912',
    containerType: '散货交仓',
    port: '盐田',
    country: '美国',
    mainFactory: '华康B',
    warehouse: '裕泰仓',
    truckType: '',
    shipDate: day(3),
    siDeadline: at(1, '12:00'),
    cutoff: at(2, '09:00'),
    deliveryDate: at(3, '10:00'),
    coordinator: '黄俊',
    updatedAt: at(0, '08:05'),
    special: '体积超过 35 CBM，需拆车后重新确认吨车。',
    readiness: { qc: 'pass', inventory: 'pending', missingWeights: 0 },
    items: items([
      ['33101', '手工套装 6个/箱', '4800120011', 'CE-8801', 620, 3720, 16.4, 15, 'pass'],
      ['33155', '彩泥套装 12个/箱', '4800120024', 'CE-8808', 780, 9360, 22.1, 20, 'pass'],
    ]),
    vehicles: [{ key: '车1', truckType: '', warehouse: '裕泰仓', items: 2, cbm: 38.5 }],
  },
  {
    id: 'KB-007-1',
    batchNo: '007-1',
    customer: 'CEPIA',
    mode: 'container',
    status: 'completed',
    so: 'KBX31002',
    containerType: '1*40HQ',
    port: '盐田',
    country: '美国',
    mainFactory: '华康B做柜',
    shipDate: day(-5),
    siDeadline: at(-7, '14:00'),
    cutoff: at(-6, '17:00'),
    coordinator: '黄俊',
    updatedAt: at(-5, '18:40'),
    special: '已完成。',
    readiness: { qc: 'pass', inventory: 'confirmed', missingWeights: 0 },
    items: items([
      ['33101', '手工套装 6个/箱', '4800119701', 'CE-8701', 540, 3240, 13.2, 12, 'pass'],
    ]),
    vehicles: [],
  },
]

const huakangDTasks: ShipmentTask[] = [
  {
    id: 'KD-003-1',
    batchNo: '003-1',
    customer: 'AZAD',
    mode: 'container',
    status: 'review',
    so: 'KDX10245',
    containerType: '1*20GP',
    port: '盐田',
    country: '阿联酋',
    mainFactory: '华康D做柜',
    shipDate: day(7),
    siDeadline: at(5, '11:00'),
    cutoff: at(6, '15:00'),
    coordinator: '郑婷',
    updatedAt: at(0, '09:45'),
    special: '阿联酋线，需提供阿拉伯语标签确认图。',
    readiness: { qc: 'pending', inventory: 'pending', missingWeights: 0 },
    items: items([
      ['44101', '沙滩玩具 8个/箱', '4900130011', 'AZ-2201', 260, 2080, 5.8, 5, 'pending'],
      ['44155', '水枪套装 6个/箱', '4900130025', 'AZ-2209', 190, 1140, 3.4, 3, 'missing'],
    ]),
    vehicles: [],
  },
  {
    id: 'KD-003-2',
    batchNo: '003-2',
    customer: 'AZAD',
    mode: 'qingxi',
    status: 'shipment',
    so: 'KDSO3301',
    containerType: '散货',
    port: '盐田',
    country: '阿联酋',
    mainFactory: '华康D',
    warehouse: '清溪物流园',
    truckType: '1*5T',
    shipDate: day(2),
    siDeadline: at(0, '12:00'),
    cutoff: at(1, '08:00'),
    deliveryDate: at(2, '09:00'),
    coordinator: '郑婷',
    updatedAt: at(0, '08:50'),
    special: '送清溪物流园，按园区预约时段进场。',
    readiness: { qc: 'pass', inventory: 'confirmed', missingWeights: 0 },
    items: items([
      ['44101', '沙滩玩具 8个/箱', '4900130011', 'AZ-2201', 210, 1680, 4.6, 4, 'pass'],
      ['44155', '水枪套装 6个/箱', '4900130025', 'AZ-2209', 180, 1080, 3.2, 3, 'pass'],
    ]),
    vehicles: [{ key: '车1', truckType: '1*5T', warehouse: '清溪物流园', items: 2, cbm: 7.8 }],
  },
]

type OrderRow = [
  id: string,
  containerNo: string,
  so: string,
  containerType: string,
  departureDate: string,
  siDeadline: string,
  cutoff: string,
  port: string,
  destination: string,
  plCount: number,
  cbm: number,
  special: string,
  status: ShippingOrderStatus,
]

function orderRows(pool: ShippingProduct[], rows: OrderRow[]): ShippingOrder[] {
  const customers = ['ZURU', 'PLAYMATES', 'MOOSE', 'EDU', 'TIG']
  return rows.map(([id, containerNo, so, containerType, departureDate, siDeadline, cutoff, port, destination, plCount, cbm, special, status], index) => ({
    id, containerNo, so, customer: customers[index % customers.length]!, containerType, departureDate, siDeadline, cutoff, port, destination, plCount, cbm, special, status,
    products: [pool[index % pool.length]!, pool[(index + 3) % pool.length]!],
  }))
}

const huaxingProducts: ShippingProduct[] = [
  { code: '15754', name: '链条枪' },
  { code: '62437', name: '三弹枪' },
  { code: '15789', name: '恐龙蛋' },
  { code: '92107', name: '泡泡棒' },
  { code: '15756', name: '遥控车' },
  { code: '9548', name: '沙滩桶' },
  { code: '15783', name: '恐龙套装' },
]

const huadengProducts: ShippingProduct[] = [
  { code: '15812', name: '遥控工程车' },
  { code: '15901', name: '合金车模' },
  { code: '15944', name: '轨道车' },
  { code: '15520', name: '拼装积木' },
  { code: '15888', name: '遥控飞机' },
  { code: '15977', name: '合金车队' },
]

const huakangAProducts: ShippingProduct[] = [
  { code: '22110', name: '轨道套装' },
  { code: '22144', name: '合金车队' },
  { code: '22190', name: '拼装飞机' },
  { code: '22210', name: '遥控船' },
  { code: '22255', name: '积木城堡' },
  { code: '22301', name: '恐龙模型' },
]

const huakangBProducts: ShippingProduct[] = [
  { code: '33101', name: '手工套装' },
  { code: '33155', name: '彩泥套装' },
  { code: '33220', name: '拼装积木' },
  { code: '33290', name: '遥控车' },
]

const huakangDProducts: ShippingProduct[] = [
  { code: '44101', name: '沙滩玩具' },
  { code: '44155', name: '水枪套装' },
  { code: '44220', name: '拼装模型' },
  { code: '44290', name: '遥控越野车' },
]

const huaxingOrders = orderRows(huaxingProducts, [
  ['1001', 'C260304887', 'SHZ8265013', '1*40HQ', day(8), at(6, '14:00'), at(7, '17:00'), '盐田', '美国 · 洛杉矶', 4, 33.6, '立放、拉网；柜门拍照留档', '已创建'],
  ['1002', 'C260304891', 'SHZ8265014', '1*40HQ', day(6), at(4, '11:00'), at(5, '17:00'), '盐田', '美国 · 长滩', 3, 28.4, '与 1001 同批拼柜', '已创建'],
  ['1003', '', 'SZCFS2288', '散货交仓', day(5), at(3, '12:00'), at(4, '08:30'), '盐田', '美国 · 芝加哥', 1, 31.0, '按 35 CBM 分两车', '已确认'],
  ['1004', 'C260304760', 'SHZ8264998', '1*40HQ', day(-1), at(-2, '14:00'), at(-1, '17:00'), '盐田', '美国 · 纽约', 4, 52.3, '', '已装柜'],
  ['1005', '', 'SHZ8265301', '1*20GP', '', '', '', '盐田', '美国 · 休斯顿', 2, 12.6, '剩余散货等待客户通知', '已创建'],
  ['1006', 'C260304611', 'SHZ8264777', '1*40HQ', day(-3), at(-4, '09:00'), at(-3, '16:00'), '南沙', '美国 · 奥克兰', 3, 41.8, '', '已开船'],
  ['1007', 'C260304455', 'SHZ8264551', '1*20GP', day(-5), at(-6, '10:00'), at(-5, '15:00'), '南沙', '加拿大 · 温哥华', 2, 19.2, '', '已开船'],
  ['1008', 'C260304990', 'SHZ8265110', '1*40HQ', day(2), at(0, '14:00'), at(1, '17:00'), '盐田', '英国 · 费利克斯托', 3, 37.5, 'UKCA 标签照片随柜', '已确认'],
  ['1009', 'C260305012', 'SHZ8265188', '1*45HC', day(1), at(-1, '11:00'), at(0, '16:00'), '蛇口', '加拿大 · 多伦多', 2, 44.1, '华登做柜拼柜', '已创建'],
  ['1010', '', 'SHZ8265202', '散货交仓', day(3), at(1, '12:00'), at(2, '08:30'), '盐田', '美国 · 达拉斯', 1, 22.7, '', '已创建'],
  ['1011', 'C260304301', 'SHZ8264960', '1*40HQ', day(-7), at(-8, '14:00'), at(-7, '17:00'), '盐田', '美国 · 洛杉矶', 4, 58.2, '', '已开船'],
  ['1012', 'C260305101', 'SHZ8265388', '1*20GP', day(4), at(2, '09:00'), at(3, '16:00'), '南沙', '美国 · 迈阿密', 2, 15.9, '客户指定船公司', '已取消'],
])

const huadengOrders = orderRows(huadengProducts, [
  ['2001', 'HDCU771201', 'HDX77120', '1*45HC', day(7), at(5, '10:00'), at(6, '16:00'), '蛇口', '加拿大 · 多伦多', 3, 46.2, '华登做柜，兴信货截关前送达', '已创建'],
  ['2002', '', 'HDSO5521', '散货交仓', day(3), at(1, '15:00'), at(2, '09:00'), '蛇口', '加拿大 · 多伦多', 2, 20.2, '交仓单注明 MOOSE 收货编号', '已确认'],
  ['2003', 'HDCU770881', 'HDX77088', '1*40HQ', day(-2), at(-3, '10:00'), at(-2, '16:00'), '蛇口', '加拿大 · 多伦多', 3, 39.4, '', '已装柜'],
  ['2004', '', 'HDX77208', '1*20GP', '', '', '', '蛇口', '英国 · 费利克斯托', 1, 3.4, '剩余散货等待客户通知', '已创建'],
  ['2005', 'HDCU773011', 'HDX77301', '1*40HQ', day(5), at(3, '14:00'), at(4, '17:00'), '盐田', '美国 · 洛杉矶', 3, 34.8, '', '已确认'],
  ['2006', 'HDCU768801', 'HDX76880', '1*40HQ', day(-6), at(-7, '10:00'), at(-6, '15:00'), '蛇口', '加拿大 · 温哥华', 4, 55.1, '', '已开船'],
  ['2007', 'HDCU774021', 'HDX77402', '1*20GP', day(1), at(-1, '09:00'), at(0, '14:00'), '蛇口', '加拿大 · 多伦多', 2, 17.6, '', '已确认'],
  ['2008', '', 'HDX77455', '散货交仓', day(4), at(2, '12:00'), at(3, '08:30'), '盐田', '美国 · 芝加哥', 1, 26.3, '', '已创建'],
  ['2009', 'HDCU775001', 'HDX77500', '1*45HC', day(9), at(7, '11:00'), at(8, '16:00'), '蛇口', '加拿大 · 多伦多', 4, 48.7, '品牌行红字版走柜表', '已创建'],
  ['2010', 'HDCU765201', 'HDX76520', '1*40HQ', day(-9), at(-10, '14:00'), at(-9, '17:00'), '蛇口', '加拿大 · 温哥华', 2, 30.5, '', '已取消'],
])

const huakangAOrders = orderRows(huakangAProducts, [
  ['3001', 'KACU551021', 'KAX55102', '1*40HQ', day(6), at(4, '13:00'), at(5, '17:00'), '南沙', '英国 · 费利克斯托', 3, 37.2, 'UKCA 标签照片随柜', '已创建'],
  ['3002', '', 'KASO7781', '散货交仓', day(4), at(2, '12:00'), at(3, '08:00'), '南沙', '英国 · 费利克斯托', 2, 18.1, '交仓资料与照片一并归档', '已确认'],
  ['3003', 'KACU550401', 'KAX55040', '1*20GP', day(-2), at(-3, '13:00'), at(-2, '17:00'), '南沙', '英国 · 伦敦门户', 2, 14.6, '', '已装柜'],
  ['3004', 'KACU552211', 'KAX55221', '1*40HQ', day(2), at(0, '14:00'), at(1, '17:00'), '盐田', '美国 · 洛杉矶', 3, 42.5, '', '已创建'],
  ['3005', 'KACU549801', 'KAX54980', '1*40HQ', day(-6), at(-7, '10:00'), at(-6, '16:00'), '南沙', '英国 · 费利克斯托', 4, 51.7, '', '已开船'],
  ['3006', '', 'KASO7799', '散货交仓', day(1), at(-1, '12:00'), at(0, '09:00'), '盐田', '美国 · 芝加哥', 1, 21.4, '', '已创建'],
  ['3007', 'KACU552702', 'KAX55270', '1*20GP', day(8), at(6, '09:00'), at(7, '15:00'), '南沙', '英国 · 伦敦门户', 2, 16.3, '', '已确认'],
  ['3008', 'KACU548901', 'KAX54890', '1*40HQ', day(-8), at(-9, '14:00'), at(-8, '17:00'), '南沙', '英国 · 费利克斯托', 3, 44.9, '', '已取消'],
])

const huakangBOrders = orderRows(huakangBProducts, [
  ['4001', 'KBCU310771', 'KBX31077', '1*40GP', day(8), at(6, '14:00'), at(7, '17:00'), '盐田', '美国 · 洛杉矶', 2, 15.1, '柜内拍照，箱门贴 CEPIA 标签', '已创建'],
  ['4002', '', 'KBSO9912', '散货交仓', day(3), at(1, '12:00'), at(2, '09:00'), '盐田', '美国 · 达拉斯', 2, 38.5, '体积超过 35 CBM，需拆车', '已确认'],
  ['4003', 'KBCU310021', 'KBX31002', '1*40HQ', day(-5), at(-6, '14:00'), at(-5, '17:00'), '盐田', '美国 · 纽瓦克', 3, 45.8, '', '已装柜'],
  ['4004', 'KBCU311501', 'KBX31150', '1*20GP', day(1), at(-1, '10:00'), at(0, '16:00'), '南沙', '美国 · 奥克兰', 1, 9.7, '', '已创建'],
  ['4005', 'KBCU307701', 'KBX30770', '1*40HQ', day(-10), at(-11, '09:00'), at(-10, '15:00'), '盐田', '美国 · 洛杉矶', 4, 57.3, '', '已开船'],
  ['4006', '', 'KBX31201', '1*40GP', day(5), at(3, '11:00'), at(4, '16:00'), '南沙', '美国 · 迈阿密', 2, 24.6, '', '已取消'],
])

const huakangDOrders = orderRows(huakangDProducts, [
  ['5001', 'KDCU102451', 'KDX10245', '1*20GP', day(7), at(5, '11:00'), at(6, '15:00'), '盐田', '阿联酋 · 迪拜', 2, 9.2, '阿拉伯语标签确认图', '已创建'],
  ['5002', '', 'KDSO3301', '散货', day(2), at(0, '12:00'), at(1, '08:00'), '盐田', '阿联酋 · 杰贝阿里', 2, 7.8, '送清溪物流园，按预约时段进场', '已确认'],
  ['5003', 'KDCU101801', 'KDX10180', '1*20GP', day(-4), at(-5, '11:00'), at(-4, '15:00'), '盐田', '阿联酋 · 迪拜', 1, 6.4, '', '已装柜'],
  ['5004', 'KDCU103122', 'KDX10312', '1*40HQ', day(4), at(2, '14:00'), at(3, '17:00'), '南沙', '沙特 · 吉达', 3, 36.4, '', '已创建'],
  ['5005', 'KDCU100201', 'KDX10020', '1*40HQ', day(-9), at(-10, '10:00'), at(-9, '16:00'), '盐田', '阿联酋 · 迪拜', 3, 41.2, '', '已开船'],
])

export const shippingFactoryProfiles: Record<ShippingFactoryId, ShippingFactoryProfile> = {
  huaxing: {
    factoryId: 'huaxing',
    label: '华兴',
    note: '兴信做柜为主，ZURU 柜号序列与拼柜场景最完整。',
    customers: [
      { name: 'ZURU', cabinetSeq: '1001', consigneeCode: 'ZURU-US01', note: '品牌自动匹配，TJX 多柜' },
      { name: 'MOOSE', cabinetSeq: '3001', consigneeCode: 'MOOSE-CA', note: '加拿大线，需 UKCA/CCPSA 标签' },
      { name: 'Dickie', cabinetSeq: '5001', consigneeCode: 'DICKIE-UK', note: '英国线，客价按 P4 模板' },
    ],
    ports: [
      { port: '盐田', country: '美国', note: '主力航线，截关多为 17:00' },
      { port: '南沙', country: '美国', note: '与盐田并行，柜号独立' },
      { port: '蛇口', country: '加拿大', note: '华登拼柜常见' },
    ],
    factoryMappings: [
      { english: 'Dong Guan Xingxin Plastic Products Co., Ltd.', chinese: '兴信', local: true },
      { english: 'Dong Guan Huadeng Toys Co., Ltd.', chinese: '华登', local: true },
      { english: 'Dong Guan Hanson Plastic Product Ltd', chinese: '兴信（贸易抬头）', local: true },
    ],
    tasks: huaxingTasks,
    orders: huaxingOrders,
  },
  huadeng: {
    factoryId: 'huadeng',
    label: '华登',
    note: '华登做柜与交仓并行，导出使用华登固定模板。',
    customers: [
      { name: 'MOOSE', cabinetSeq: '2001', consigneeCode: 'MOOSE-CA', note: '华登主力客户' },
      { name: 'TOMY', cabinetSeq: '6001', consigneeCode: 'TOMY-UK', note: '英国线，等待通知较多' },
      { name: 'AZAD', cabinetSeq: '4001', consigneeCode: 'AZAD-AE', note: '中东线，标签需提前确认' },
    ],
    ports: [
      { port: '蛇口', country: '加拿大', note: '华登默认装港' },
      { port: '盐田', country: '美国', note: '拼柜转盐田时使用' },
      { port: '南沙', country: '英国', note: '少量英国线' },
    ],
    factoryMappings: [
      { english: 'Dong Guan Huadeng Toys Co., Ltd.', chinese: '华登', local: true },
      { english: 'Dong Guan Xingxin Plastic Products Co., Ltd.', chinese: '兴信', local: true },
      { english: 'Sky Castle Industrial Ltd.', chinese: 'Sky Castle', local: false },
    ],
    tasks: huadengTasks,
    orders: huadengOrders,
  },
  'huakang-a': {
    factoryId: 'huakang-a',
    label: '华康A',
    note: '华康 A 做柜为主，交仓走盐田 2 号仓。',
    customers: [
      { name: 'TOMY', cabinetSeq: '7001', consigneeCode: 'TOMY-UK', note: '英国线，需 UKCA 照片' },
      { name: 'BuzzBee', cabinetSeq: '8001', consigneeCode: 'BUZZ-US', note: '美国线' },
      { name: 'Dickie', cabinetSeq: '9001', consigneeCode: 'DICKIE-UK', note: '英国线' },
    ],
    ports: [
      { port: '南沙', country: '英国', note: '华康 A 默认装港' },
      { port: '盐田', country: '美国', note: '交仓与整柜并行' },
      { port: '蛇口', country: '加拿大', note: '少量拼柜' },
    ],
    factoryMappings: [
      { english: 'Huakang A Toys Manufacturing Ltd.', chinese: '华康A', local: true },
      { english: 'Dong Guan Xingxin Plastic Products Co., Ltd.', chinese: '兴信', local: true },
      { english: 'Dong Guan Huadeng Toys Co., Ltd.', chinese: '华登', local: true },
    ],
    tasks: huakangATasks,
    orders: huakangAOrders,
  },
  'huakang-b': {
    factoryId: 'huakang-b',
    label: '华康B',
    note: '华康 B 交仓需关注 35 CBM 上限与吨车确认。',
    customers: [
      { name: 'CEPIA', cabinetSeq: '1101', consigneeCode: 'CEPIA-US', note: '美国线，柜内拍照' },
      { name: 'Moose', cabinetSeq: '1201', consigneeCode: 'MOOSE-CA', note: '加拿大线' },
      { name: 'ZURU', cabinetSeq: '1301', consigneeCode: 'ZURU-US02', note: '临时调拨' },
    ],
    ports: [
      { port: '盐田', country: '美国', note: '主力航线' },
      { port: '南沙', country: '美国', note: '旺季分流' },
      { port: '蛇口', country: '加拿大', note: '少量' },
    ],
    factoryMappings: [
      { english: 'Huakang B Toys Manufacturing Ltd.', chinese: '华康B', local: true },
      { english: 'Dong Guan Xingxin Plastic Products Co., Ltd.', chinese: '兴信', local: true },
      { english: 'Prologis Dongguan Warehouse', chinese: '普洛斯（东莞）仓', local: false },
    ],
    tasks: huakangBTasks,
    orders: huakangBOrders,
  },
  'huakang-d': {
    factoryId: 'huakang-d',
    label: '华康D',
    note: '华康 D 以 AZAD 与清溪物流园出货为主。',
    customers: [
      { name: 'AZAD', cabinetSeq: '1401', consigneeCode: 'AZAD-AE', note: '阿联酋线，阿拉伯语标签' },
      { name: 'ZANZOON', cabinetSeq: '1501', consigneeCode: 'ZANZOON-SA', note: '沙特线' },
      { name: 'TOMY', cabinetSeq: '1601', consigneeCode: 'TOMY-UK', note: '英国线' },
    ],
    ports: [
      { port: '盐田', country: '阿联酋', note: '中东线主力' },
      { port: '南沙', country: '沙特', note: '少量' },
      { port: '蛇口', country: '英国', note: '拼柜' },
    ],
    factoryMappings: [
      { english: 'Huakang D Toys Manufacturing Ltd.', chinese: '华康D', local: true },
      { english: 'Dong Guan Xingxin Plastic Products Co., Ltd.', chinese: '兴信', local: true },
      { english: 'Qingxi Logistics Park', chinese: '清溪物流园', local: false },
    ],
    tasks: huakangDTasks,
    orders: huakangDOrders,
  },
}

export function shippingTotals(task: ShipmentTask) {
  return task.items.reduce(
    (total, item) => ({
      pieces: total.pieces + item.pieces,
      quantity: total.quantity + item.quantity,
      cbm: total.cbm + item.cbm,
      pallets: total.pallets + item.pallets,
    }),
    { pieces: 0, quantity: 0, cbm: 0, pallets: 0 },
  )
}

export function cbmText(value: number) {
  return value.toFixed(1)
}

/** 距截关还有多少小时；空日期或已过期返回 null / 负数。 */
export function hoursUntil(value: string, now = new Date()): number | null {
  if (!value) return null
  const parsed = new Date(value.replace(' ', 'T'))
  if (Number.isNaN(parsed.getTime())) return null
  return (parsed.getTime() - now.getTime()) / 3_600_000
}

/** 距某天还有几个自然日；今天 0，明天 1，已过为负数。 */
export function daysUntil(value: string, now = new Date()): number | null {
  if (!value) return null
  const parsed = new Date(value.replace(' ', 'T'))
  if (Number.isNaN(parsed.getTime())) return null
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const target = new Date(parsed.getFullYear(), parsed.getMonth(), parsed.getDate())
  return Math.round((target.getTime() - start.getTime()) / 86_400_000)
}

export function relativeDayText(value: string, now = new Date()): string {
  if (!value) return '待确认'
  const parsed = new Date(value.replace(' ', 'T'))
  if (Number.isNaN(parsed.getTime())) return value
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const target = new Date(parsed.getFullYear(), parsed.getMonth(), parsed.getDate())
  const days = Math.round((target.getTime() - start.getTime()) / 86_400_000)
  if (days === 0) return '今天'
  if (days === 1) return '明天'
  if (days === -1) return '昨天'
  if (days > 1) return `${days} 天后`
  return `${Math.abs(days)} 天前`
}

export function isUrgentCutoff(task: ShipmentTask, now = new Date()) {
  if (task.status === 'completed' || task.status === 'cancelled' || task.status === 'waiting') return false
  const hours = hoursUntil(task.cutoff, now)
  return hours !== null && hours <= 48
}

/** 按明细备案号拼接导出文件名（无备案号时回退默认名称）。 */
export function filingCodeFilename(
  lines: Array<{ filingCode?: string; declareCode?: string; itemNo?: string }> | undefined,
  ext: '.xls' | '.xlsx',
  fallback: string,
  headerCode?: string,
) {
  const codes = [...new Set(
    (lines ?? [])
      .map((line) => String(line.filingCode || line.declareCode || line.itemNo || '').trim())
      .filter(Boolean),
  )]
  if (!codes.length && headerCode?.trim()) {
    codes.push(headerCode.trim())
  }
  return `${codes.length ? codes.join('_') : fallback}${ext}`
}
