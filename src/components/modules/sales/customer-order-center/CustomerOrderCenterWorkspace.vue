<script setup lang="ts">
import {
  AlertTriangle,
  ArrowRight,
  Building2,
  CalendarClock,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  ClipboardCheck,
  Database,
  Download,
  FileCheck2,
  FileSpreadsheet,
  FileUp,
  Filter,
  GitBranch,
  History,
  Layers3,
  ListChecks,
  Plus,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  UploadCloud,
  UserRoundCheck,
  X,
} from '@lucide/vue'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { customerOrderApi } from '@/api/customerOrder'
import type { MappedCustomerCode } from '@/api/customerOrder'
import { customerOrderLedgerApi } from '@/api/customerOrderLedger'
import type { CustomerOrderLedgerLine } from '@/api/customerOrderLedger'
import CustomerOrderLedger from './CustomerOrderLedger.vue'
import CustomerOrderSchedule from './CustomerOrderSchedule.vue'
import { getApiErrorMessage } from '@/lib/http'
import type {
  CustomerOrderImportPreview,
  CustomerOrderIssue,
  CustomerOrderManualOverride,
  CustomerOrderPreviewRow,
} from '@/types/customerOrder'
import type { CustomerOrderCenterSection } from '@/views/CustomerOrderCenterView.vue'

type OrderStatus = 'valid' | 'warning' | 'blocked'
type DeliveryStatus = 'overdue' | 'due-soon' | 'upcoming' | 'planned'
type ExceptionSeverity = 'critical' | 'warning' | 'attention'
type CustomerOrderCustomerCode =
  | 'buzzbee'
  | 'dickie'
  | 'caixing'
  | MappedCustomerCode

interface CustomerOrderCustomerProfile {
  code: CustomerOrderCustomerCode
  name: string
  version: string
  poAccept: string
  poExtensions: string[]
  scheduleAccept: string
  scheduleExtensions: string[]
  poDescription: string
  templateDescription: string
  targetTemplate: string
  ruleDescription: string
}

const CUSTOMER_PROFILES_BY_FACTORY: Record<string, CustomerOrderCustomerProfile[]> = {
  huaxing: [
    {
      code: 'buzzbee',
      name: 'BuzzBee',
      version: 'V1',
      poAccept: '.xlsx,.xls',
      poExtensions: ['.xls', '.xlsx'],
      scheduleAccept: '.xlsx',
      scheduleExtensions: ['.xlsx'],
      poDescription: '普通合同、WMC 首页内嵌 PO 与 WMU 的 PO Attached 子订单',
      templateDescription: '2026年 BUZZ BEE 生产排期表',
      targetTemplate: 'BUZZBEE_PRODUCTION_SCHEDULE_V1',
      ruleDescription: 'WMC读取首页双语PO区；WMU从首页复用货号、品名及装箱数，并按PO Attached逐行生成S/C与Walmart PO子订单；WM客P/O#必填。仅明确标注印尼的资料另行处理。',
    },
    {
      code: 'dickie',
      name: 'Dickie',
      version: 'V1',
      poAccept: '.pdf',
      poExtensions: ['.pdf'],
      scheduleAccept: '.xlsx',
      scheduleExtensions: ['.xlsx'],
      poDescription: 'Simba Dickie Release Order 扫描版 PDF',
      templateDescription: '2026年 Dickie 生产情况排期',
      targetTemplate: 'DICKIE_PRODUCTION_SCHEDULE_V1',
      ruleDescription: '读取 Simba Dickie Release Order 扫描版 PDF，并按 Dickie 生产排期与 Item 表规则映射。',
    },
    {
      code: 'caixing',
      name: '彩星',
      version: 'V2',
      poAccept: '.pdf',
      poExtensions: ['.pdf'],
      scheduleAccept: '.xls,.xlsx',
      scheduleExtensions: ['.xls', '.xlsx'],
      poDescription: 'Playmates OE/OL/OG/OH/OK 系列文本型 PDF PO',
      templateDescription: '彩星生产排期（正单评审表 / 接单表 / ITEM表）',
      targetTemplate: 'CAIXING_PRODUCTION_SCHEDULE_REVIEW_ORDER_ITEM_V2',
      ruleDescription: '读取 Playmates 文本型 PDF PO，先列大货号总数量与总装箱数，再按 ASSORTMENT 展开小货号，并同步写入正单评审表、接单表及 ITEM表。',
    },
    {
      code: 'edu',
      name: 'EDU',
      version: 'V1',
      poAccept: '.xls,.xlsx,.xlsm',
      poExtensions: ['.xls', '.xlsx', '.xlsm'],
      scheduleAccept: '.xls,.xlsx,.xlsm',
      scheduleExtensions: ['.xls', '.xlsx', '.xlsm'],
      poDescription: 'EDU Excel PO（支持同 PO 修订版批量导入）',
      templateDescription: 'EDU 华兴排期底表',
      targetTemplate: 'HUAXING_EDU_NEW_ORDER_V1',
      ruleDescription: '按 PO 版本去重并续编 EDUHX 单号；验货期为走货期前 7 天，遇周末向前调整。',
    },
    {
      code: '360',
      name: '360',
      version: 'V1',
      poAccept: '.pdf,.xlsx,.xlsm',
      poExtensions: ['.pdf', '.xlsx', '.xlsm'],
      scheduleAccept: '.xlsx,.xlsm',
      scheduleExtensions: ['.xlsx', '.xlsm'],
      poDescription: '360 主合同与 Release PDF / Excel',
      templateDescription: '华兴 360 接单表 / 正单评审表 / Iteam表',
      targetTemplate: 'HUAXING_360_NEW_ORDER_V1',
      ruleDescription: '主合同用于补价格，Release 用于生成新单；新行同步写入接单表、正单评审表和 Iteam表，并保留原表公式与合计。',
    },
    {
      code: 'yinhui',
      name: '银辉',
      version: 'V1',
      poAccept: '.pdf,.xlsx,.xlsm',
      poExtensions: ['.pdf', '.xlsx', '.xlsm'],
      scheduleAccept: '.xlsx,.xlsm',
      scheduleExtensions: ['.xlsx', '.xlsm'],
      poDescription: '银辉文本 PDF、排期式 Excel 或扫描转换 Excel PO',
      templateDescription: '银辉 Iteam / ITEM 排期',
      targetTemplate: 'HUAXING_YINHUI_NEW_ORDER_V1',
      ruleDescription: 'USD 按 7.75 换算 HKD，验货期为走货期前 5 天，同时核对数量、单价、行金额及大写金额。',
    },
    {
      code: 'seasons',
      name: 'SEASONS（施信）',
      version: 'V1',
      poAccept: '.pdf,.xls,.xlsx,.xlsm',
      poExtensions: ['.pdf', '.xls', '.xlsx', '.xlsm'],
      scheduleAccept: '.xls,.xlsx,.xlsm',
      scheduleExtensions: ['.xls', '.xlsx', '.xlsm'],
      poDescription: 'SEASONS QF 预备单与正式 PO',
      templateDescription: 'SEASONS 正单评审表',
      targetTemplate: 'HUAXING_SEASONS_NEW_ORDER_V1',
      ruleDescription: '区分 QF 与正式 PO；同单同货号去重，当前排期数量不一致时按修改/补单拦截。',
    },
    {
      code: 'maxx',
      name: 'Maxx',
      version: 'V1',
      poAccept: '.pdf,.xlsx,.xlsm',
      poExtensions: ['.pdf', '.xlsx', '.xlsm'],
      scheduleAccept: '.xlsx',
      scheduleExtensions: ['.xlsx'],
      poDescription: 'Maxx PDF / Excel PO',
      templateDescription: 'Maxx KFC 公仔接单表',
      targetTemplate: 'HUAXING_MAXX_NEW_ORDER_V1',
      ruleDescription: '严格校验客户并按 PO 修订版、当前及已走货排期去重；完成与验货日期均为 Shipment 前 7 天。',
    },
    {
      code: 'shushupapa',
      name: 'Shushupapa',
      version: 'V1',
      poAccept: '.pdf,.xlsx,.xlsm',
      poExtensions: ['.pdf', '.xlsx', '.xlsm'],
      scheduleAccept: '.xlsx',
      scheduleExtensions: ['.xlsx'],
      poDescription: 'Shushupapa PDF / Excel PO',
      templateDescription: 'Shushupapa 接单表',
      targetTemplate: 'HUAXING_SHUSHUPAPA_NEW_ORDER_V1',
      ruleDescription: '严格隔离客户数据并按 PO 修订版、当前及已走货排期去重；验货日期为走货期前 7 天。',
    },
    {
      code: 'barter',
      name: 'Barter',
      version: 'V1·OCR复核',
      poAccept: '.pdf',
      poExtensions: ['.pdf'],
      scheduleAccept: '.xlsx',
      scheduleExtensions: ['.xlsx'],
      poDescription: 'Barter Purchase Contract 扫描 PDF（支持 TNT 连号多页合同）',
      templateDescription: '2026 BARTER 排期（Iteam表 / 接单表）',
      targetTemplate: 'HUAXING_BARTER_SCHEDULE_APPEND_V2',
      ruleDescription: '逐页 OCR 识别并按文件名合同范围校正页序；来单日期取客户确认邮件日期，同步写入 Iteam表和接单表，BV 验货日期留待确认，并保留源排期密码。',
    },
    {
      code: 'disney',
      name: '迪士尼',
      version: 'V1',
      poAccept: '.pdf',
      poExtensions: ['.pdf'],
      scheduleAccept: '.xlsx,.xlsm',
      scheduleExtensions: ['.xlsx', '.xlsm'],
      poDescription: 'DLR、WDW、TDSE、国际 F 单及日本 V 单 PDF',
      templateDescription: '华兴迪士尼 ITEM表 / 正单评审表 / 接单表',
      targetTemplate: 'HUAXING_DISNEY_SCHEDULE_APPEND_V2',
      ruleDescription: '按货号分组写入 ITEM表并生成分组合计，同步新增正单评审表和接单表公式行；验货期为走货期前 5 天，日期码及出厂价保留人工补录。',
    },
  ],
  'huakang-a': [
    {
      code: '360',
      name: '360',
      version: 'V1',
      poAccept: '.pdf,.xls,.xlsx,.xlsm',
      poExtensions: ['.pdf', '.xls', '.xlsx', '.xlsm'],
      scheduleAccept: '.xlsx,.xlsm',
      scheduleExtensions: ['.xlsx', '.xlsm'],
      poDescription: 'ThreeSixty PURCHASE ORDER RELEASE PDF 或 WPS 转换 Excel',
      templateDescription: '华康A 360客排期表',
      targetTemplate: 'HUAKANG_A_360_SCHEDULE_APPEND_V3',
      ruleDescription: '读取 RL 合同号、Revision Date、客户 PO、货号、数量、装箱、验货日、FCD、柜型及卸货港；每个货号先按现有产品标题行写入货号和名称，下一行再写 PO 明细。',
    },
    {
      code: 'green-toys',
      name: 'Green Toys',
      version: 'V1·OCR复核',
      poAccept: '.png,.jpg,.jpeg',
      poExtensions: ['.png', '.jpg', '.jpeg'],
      scheduleAccept: '.xlsx,.xlsm',
      scheduleExtensions: ['.xlsx', '.xlsm'],
      poDescription: 'Green Toys Purchase Order 图片（PNG / JPG）',
      templateDescription: '河源华康A Green Toys 客排货表',
      targetTemplate: 'HUAKANG_A_GREEN_TOYS_SCHEDULE_APPEND_V1',
      ruleDescription: "OCR读取PO号、货号、数量、Deliver By Date及USD单价；按同货号继承中文品名、箱规、国家和落货港，走货方式固定40'YT，USD按7.8换算HKD。",
    },
    {
      code: 'headstart',
      name: 'HeadStart',
      version: 'V1',
      poAccept: '.pdf',
      poExtensions: ['.pdf'],
      scheduleAccept: '.xlsx,.xlsm',
      scheduleExtensions: ['.xlsx', '.xlsm'],
      poDescription: 'HeadStart 文本型 PURCHASE ORDER PDF',
      templateDescription: 'HeadStart 客排期表',
      targetTemplate: 'HUAKANG_A_HEADSTART_SCHEDULE_APPEND_V1',
      ruleDescription: '读取Order No、货号、品名、数量、Delivery Date、APN、箱规、日期码及USD单价；走货期按验货日期后7天计算，USD按7.8换算HKD。',
    },
  ],
  'huakang-c': [
    {
      code: 'index',
      name: 'INDEX',
      version: 'V1',
      poAccept: '.pdf,.xls,.xlsx,.xlsm',
      poExtensions: ['.pdf', '.xls', '.xlsx', '.xlsm'],
      scheduleAccept: '.xls,.xlsx,.xlsm',
      scheduleExtensions: ['.xls', '.xlsx', '.xlsm'],
      poDescription: 'INDEX Promotions PDF 或 WPS 转换 Excel PO',
      templateDescription: '建文客排期表 / 生产排期',
      targetTemplate: 'HUAKANG_C_INDEX_NEW_ORDER_V1',
      ruleDescription: '读取PO号、PO日期、Ex-Factory、产品、数量、箱规和USD价格；按货号继承唯一排期品名并以7.75换算港币。',
    },
    {
      code: 'jazwares',
      name: 'JAZAWARES',
      version: 'V1',
      poAccept: '.pdf,.xls,.xlsx,.xlsm',
      poExtensions: ['.pdf', '.xls', '.xlsx', '.xlsm'],
      scheduleAccept: '.xls,.xlsx,.xlsm',
      scheduleExtensions: ['.xls', '.xlsx', '.xlsm'],
      poDescription: 'JAZWARES PDF 或 WPS 转换 Excel PO',
      templateDescription: 'JAZWARES 生产排期',
      targetTemplate: 'HUAKANG_C_JAZWARES_NEW_ORDER_V1',
      ruleDescription: '按旧版JAZWARES格式读取PO、版本、合同、产品、数量、PCS/CTN和走货日；同PO批量上传时保留最新修订版。',
    },
    {
      code: 'maxx',
      name: 'MAXX',
      version: 'V1',
      poAccept: '.pdf,.xls,.xlsx,.xlsm',
      poExtensions: ['.pdf', '.xls', '.xlsx', '.xlsm'],
      scheduleAccept: '.xls,.xlsx,.xlsm',
      scheduleExtensions: ['.xls', '.xlsx', '.xlsm'],
      poDescription: 'MAXX Marketing PDF 或 WPS 转换 Excel PO',
      templateDescription: 'MAXX排期 / MAXX放产表',
      targetTemplate: 'HUAKANG_C_MAXX_NEW_ORDER_V1',
      ruleDescription: '读取P.O.、S.C.合同、日期、货号、数量及USD价格；PO未提供装箱数时保持空白。',
    },
    {
      code: 'strottman',
      name: 'STROTTMAN',
      version: 'V1',
      poAccept: '.pdf,.xls,.xlsx,.xlsm',
      poExtensions: ['.pdf', '.xls', '.xlsx', '.xlsm'],
      scheduleAccept: '.xls,.xlsx,.xlsm',
      scheduleExtensions: ['.xls', '.xlsx', '.xlsm'],
      poDescription: 'STROTTMAN PDF 或 WPS 转换 Excel PO',
      templateDescription: '2026正单 / Strottman放产表',
      targetTemplate: 'HUAKANG_C_STROTTMAN_NEW_ORDER_V1',
      ruleDescription: '按Special Instructions把Case换算成PCS和每箱件数；多个走货日取最早日期写主列，其余保留在备注。',
    },
  ],
  huadeng: [
    {
      code: 'goliath',
      name: 'Goliath',
      version: 'V1',
      poAccept: '.pdf',
      poExtensions: ['.pdf'],
      scheduleAccept: '.xlsx',
      scheduleExtensions: ['.xlsx'],
      poDescription: 'Goliath Far East / BV（欧洲版）正式 Purchase Order PDF',
      templateDescription: 'Goliath 最新河源业务统一排期',
      targetTemplate: 'HEYUAN_BUSINESS_UNIFIED_REGIONAL_V3',
      ruleDescription: '按完整合同号、客户 PO 和完整货号映射，数量与走货期取原 PO，缺少箱规时只继承最新排期的唯一历史值。',
    },
    {
      code: 'casdon',
      name: 'Casdon',
      version: 'V1',
      poAccept: '.pdf,.xlsx,.xlsm',
      poExtensions: ['.pdf', '.xlsx', '.xlsm'],
      scheduleAccept: '.xlsx',
      scheduleExtensions: ['.xlsx'],
      poDescription: 'Casdon 电子 PDF 或 WPS 转换 Excel PO',
      templateDescription: 'Casdon 排货表总表',
      targetTemplate: 'HUADENG_CASDON_NEW_ORDER_V1',
      ruleDescription: '按 PO 修订版和字段完整度去重；USD 按 7.75 换算 HKD，验货期为走货期前 7 天并避开周末。',
    },
    {
      code: 'jakks',
      name: 'Jakks',
      version: 'V1',
      poAccept: '.pdf,.xlsx,.xlsm',
      poExtensions: ['.pdf', '.xlsx', '.xlsm'],
      scheduleAccept: '.xls,.xlsx',
      scheduleExtensions: ['.xls', '.xlsx'],
      poDescription: 'Jakks 正式 PO、补充合同（箱唛资料）PDF 或 WPS 转换 Excel PO',
      templateDescription: 'Jakks 排货总表',
      targetTemplate: 'HUADENG_JAKKS_NEW_ORDER_V1',
      ruleDescription: '支持补充合同先行排产，缺失价格保持空白；正式 PO 到齐后按确认号和货号查重。取消单仍拦截，产品名称仅继承排期唯一值。',
    },
    {
      code: 'simba',
      name: 'Simba',
      version: 'V1',
      poAccept: '.pdf,.xlsx,.xlsm',
      poExtensions: ['.pdf', '.xlsx', '.xlsm'],
      scheduleAccept: '.xlsx,.xlsm',
      scheduleExtensions: ['.xlsx', '.xlsm'],
      poDescription: 'Simba Release Order PDF / Excel',
      templateDescription: 'Simba 客户排期',
      targetTemplate: 'HUADENG_SIMBA_NEW_ORDER_V1',
      ruleDescription: '同名 PDF 与 WPS Excel 优先采用 Excel；按修订版、文件类型和完整度合并，并安全继承当前排期资料。',
    },
    {
      code: 'spin',
      name: 'Spin',
      version: 'V1',
      poAccept: '.pdf,.xlsx,.xlsm',
      poExtensions: ['.pdf', '.xlsx', '.xlsm'],
      scheduleAccept: '.xlsx',
      scheduleExtensions: ['.xlsx'],
      poDescription: 'Spin 电子 PDF 或 WPS 转换 Excel PO',
      templateDescription: 'Spin 排货表（中国）',
      targetTemplate: 'HUADENG_SPIN_NEW_ORDER_V1',
      ruleDescription: '按 PO 修订版去重，按客户与货号继承排期主数据；USD 按 7.75 换算 HKD，人工排期字段保持空白。',
    },
  ],
}

const UNIFIED_SCHEDULE_ACCEPT = '.xlsx'
const UNIFIED_SCHEDULE_EXTENSIONS = ['.xlsx']
const UNIFIED_SCHEDULE_DESCRIPTION = '河源业务统一排期（ITEM表 / 接单表 / 正单评审表）'
const UNIFIED_SCHEDULE_TEMPLATE = 'HEYUAN_BUSINESS_UNIFIED_SCHEDULE_V1'

Object.entries(CUSTOMER_PROFILES_BY_FACTORY).forEach(([factoryId, profiles]) => {
  profiles.forEach((profile) => {
    profile.scheduleAccept = UNIFIED_SCHEDULE_ACCEPT
    profile.scheduleExtensions = UNIFIED_SCHEDULE_EXTENSIONS
    profile.templateDescription = UNIFIED_SCHEDULE_DESCRIPTION
    profile.targetTemplate = UNIFIED_SCHEDULE_TEMPLATE
    profile.ruleDescription = `${profile.ruleDescription} 输出统一写入河源业务统一排期：三张表只使用“取消单”上方空行，接单表和正单评审表 C:G 同步 ITEM表 D:H；ITEM表只在 A:AB 写入可取得字段，缺失字段留空。`
    if (factoryId === 'huakang-a') {
      profile.targetTemplate = 'HEYUAN_BUSINESS_UNIFIED_HUAKANG_A_V4'
      profile.templateDescription = `华康A ${profile.name} 最新统一排期（含客户专属列）`
      profile.ruleDescription = '只校验公共区域字段，客户专属列可增减或调整顺序，已配置的专属字段按实际表头定位。三张表分别在取消单前追加，接单表和正单评审表 C:G 同步 ITEM表 D:H。历史 PO 按客户编号与货号查重，保留原有记录、公式及人工生产和出货字段。'
    }
    if (factoryId === 'huaxing' && profile.code !== 'seasons') {
      profile.targetTemplate = 'HEYUAN_BUSINESS_UNIFIED_HUAXING_V2'
      profile.templateDescription = `华兴 ${profile.name} 最新统一排期（含 ITEM 分类页）`
      profile.ruleDescription = '按主要公共字段匹配最新排期，BuzzBee 和迪奇按产品对应 ITEM 分类页。各表在自己的取消单前追加，接单表、正单评审表关联实际明细页和行；合同、SO、客户 PO 分别映射，保留历史订单、公式和人工字段。'
    }
  })
})

// External customer orders are now owned by Huakang D.  Keep the backend's
// Huakang C route compatible for saved historical previews, but do not offer
// those external profiles from the Huakang C customer-order workspace.
CUSTOMER_PROFILES_BY_FACTORY['huakang-d'] = CUSTOMER_PROFILES_BY_FACTORY['huakang-c'] ?? []
CUSTOMER_PROFILES_BY_FACTORY['huakang-c'] = []
for (const factoryId of ['huadeng', 'huakang-d']) {
  for (const profile of CUSTOMER_PROFILES_BY_FACTORY[factoryId] ?? []) {
    profile.targetTemplate = 'HEYUAN_BUSINESS_UNIFIED_REGIONAL_V3'
    profile.ruleDescription = '只校验主要公共字段，客户专属列按实际表头定位。三张表分别在取消单前追加，按客户订单识别号和产品编号核对历史；保留已有记录、公式、生产及实际出货字段。'
  }
}

const disneyProfile = CUSTOMER_PROFILES_BY_FACTORY.huaxing?.find((profile) => profile.code === 'disney')
CUSTOMER_PROFILES_BY_FACTORY['huakang-d']!.push({
  code: 'ubtech', name: '优必选', version: 'V1',
  poAccept: '.pdf', poExtensions: ['.pdf'],
  scheduleAccept: '.xlsx', scheduleExtensions: ['.xlsx'],
  poDescription: '优必选 UBTECH 人民币 Purchase Order PDF',
  templateDescription: '华康D 优必选河源业务统一排期',
  targetTemplate: 'HEYUAN_BUSINESS_UNIFIED_HUAKANG_D_UBTECH_V1',
  ruleDescription: '来单日期取确认邮件日期；走货期默认取PO需求日期，可人工更正。订单换算价按人民币÷0.85及÷7.75写入专属列，出厂价保留手工填写。装箱取当前排期唯一历史值，箱数向上取整；只进入华康D总排期。',
})
if (disneyProfile) {
  CUSTOMER_PROFILES_BY_FACTORY['huakang-d']!.push({
    ...disneyProfile,
    poExtensions: [...disneyProfile.poExtensions],
    scheduleExtensions: [...disneyProfile.scheduleExtensions],
    targetTemplate: 'HEYUAN_BUSINESS_UNIFIED_HUAKANG_D_DISNEY_V1',
    templateDescription: '华康D 迪士尼最新统一排期',
    ruleDescription: '复用迪士尼 PO 识别规则，只使用本次上传的华康D排期核对历史和写入新单。导入数据仅进入华康D总排期，日期码及出厂价保留人工补录。',
  })
}

const MAPPED_CUSTOMERS = new Set<MappedCustomerCode>([
  'disney', 'edu', '360', 'green-toys', 'headstart', 'yinhui', 'seasons', 'maxx', 'shushupapa', 'barter',
  'casdon', 'jakks', 'simba', 'spin', 'goliath',
  'index', 'jazwares', 'strottman', 'ubtech',
])

function isMappedCustomerCode(code: CustomerOrderCustomerCode): code is MappedCustomerCode {
  return MAPPED_CUSTOMERS.has(code as MappedCustomerCode)
}

interface ScheduleException {
  id: string
  row: OrderRow
  severity: ExceptionSeverity
  severityLabel: string
  category: '订单数据' | '交付风险' | '生产反馈' | '版本状态'
  title: string
  detail: string
  suggestedAction: string
  actionSection: CustomerOrderCenterSection
}

interface OrderRow {
  id: string
  factoryId: string
  status: OrderStatus
  statusLabel: string
  rowRole?: 'parent' | 'detail'
  parentProductNo?: string
  issue: string
  receivedDate: string
  poNo: string
  contractNo: string
  customerCountry: string
  productNo: string
  productNameZh: string
  productNameEn: string
  quantity: string
  unitsPerCarton: string
  cartonCount: string
  standard: string
  unitPriceHkd: string
  amountHkd: string
  packaging: string
  lineQ: string
  customerQ: string
  requestedShipDate: string
  source: string
  sourcePoFileName: string
  inputTemplate: string
  targetTemplate: string
  itemSheetName: string
  poSource: string
  contractSource: string
  productSource: string
  shipDateSource: string
  productionStatus: string
  productionProgress: number
  productionDepartment: string
  productionIssue: string
  feedbackAt: string
  lineage?: Record<string, string>
  issues?: CustomerOrderIssue[]
}

const props = defineProps<{
  activeSection: CustomerOrderCenterSection
  factoryId: string
  factoryName: string
}>()

const emit = defineEmits<{
  navigate: [section: CustomerOrderCenterSection]
}>()

const poInput = ref<HTMLInputElement | null>(null)
const scheduleInput = ref<HTMLInputElement | null>(null)
function formatLocalDate(date: Date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const selectedCustomerCode = ref<CustomerOrderCustomerCode | ''>('')
const poFiles = ref<File[]>([])
const scheduleFile = ref<File | null>(null)
const draggingUpload = ref<'po' | 'schedule' | null>(null)
const selectedScheduleFile = ref('尚未选择河源业务统一排期')
const receivedDate = ref(formatLocalDate(new Date()))
const previewBatch = ref<CustomerOrderImportPreview | null>(null)
const parseFailureMessage = ref('')
const exportFailureMessage = ref('')
const parsingFiles = ref(false)
const exportingSchedule = ref(false)
const generatedScheduleBlob = ref<Blob | null>(null)
const generatedScheduleFileName = ref('')
const generatedPasswordRequired = ref(false)
const skippedIssueKeys = ref<string[]>([])
const manualOverrideValues = ref<Record<string, string>>({})
const confirmationReason = ref('')
const sourceKind = ref<'formal' | 'supplementary'>('formal')
const savingOrder = ref(false)
const reconciliation = ref({ enabled: false, lineId: '', expectedRevision: 0, reason: '' })
const reconciliationCandidates = ref<CustomerOrderLedgerLine[]>([])
const reconciliationLoading = ref(false)
const reconciliationQuery = ref('')
const reconciliationPage = ref(1)
const reconciliationTotal = ref(0)
const testDuplicateIssueCodes = new Set([
  'duplicate_reference',
  'existing_order_line',
  'duplicate_batch_order_line',
  'duplicate_existing_order',
])

function isTestDuplicateIssue(issue: CustomerOrderIssue) {
  return testDuplicateIssueCodes.has(issue.code)
}

function isConfirmationIssue(issue: CustomerOrderIssue) {
  return issue.severity === 'confirmation'
    || (issue.severity === 'blocked' && issue.can_skip && isTestDuplicateIssue(issue))
}

function isIssueManuallyOverridden(issue: CustomerOrderIssue) {
  return Boolean(issue.skip_key && manualOverrideValues.value[issue.skip_key]?.trim())
}

function isIssueResolved(issue: CustomerOrderIssue) {
  return isIssueManuallyOverridden(issue)
    || (issue.can_skip && skippedIssueKeys.value.includes(issue.skip_key))
}

const manualRowFieldMap: Partial<Record<string, keyof OrderRow>> = {
  po_no: 'poNo',
  contract_no: 'contractNo',
  customer_country: 'customerCountry',
  product_no: 'productNo',
  product_name_zh: 'productNameZh',
  product_name_en: 'productNameEn',
  quantity: 'quantity',
  units_per_carton: 'unitsPerCarton',
  carton_count: 'cartonCount',
  standard: 'standard',
  unit_price_hkd: 'unitPriceHkd',
  amount_hkd: 'amountHkd',
  packaging: 'packaging',
  line_q: 'lineQ',
  customer_q: 'customerQ',
  requested_ship_date: 'requestedShipDate',
  item: 'productNo',
  item_no: 'productNo',
  product_name: 'productNameZh',
  description: 'productNameEn',
  po_number: 'poNo',
  customer_po: 'poNo',
  customer: 'customerCountry',
  ship_date: 'requestedShipDate',
  factory_commit_date: 'requestedShipDate',
  planned_inspection_date: 'lineQ',
  case_pack: 'unitsPerCarton',
  pack_qty: 'unitsPerCarton',
  master_carton_qty: 'unitsPerCarton',
  unit_price: 'unitPriceHkd',
}
const searchQuery = ref('')
const includeValid = ref(true)
const includeWarning = ref(true)
const includeBlocked = ref(true)
const selectedLedgerStatus = ref<'all' | OrderStatus>('all')
const selectedLedgerCustomer = ref('all')
const traceRow = ref<OrderRow | null>(null)
const blockingResolutionOpen = ref(false)
const scheduleGenerated = ref(false)
const selectedScheduleMonth = ref('all')
const selectedScheduleCustomer = ref('all')
const selectedProductionStatus = ref('all')
const selectedExceptionSeverity = ref('all')
const selectedExceptionCategory = ref('all')
const exceptionSearch = ref('')
const acknowledgedExceptionIds = ref<string[]>([])
const notice = ref('')
let noticeTimer: ReturnType<typeof setTimeout> | null = null
let parseRequestSequence = 0
let exportRequestSequence = 0
let saveRequestSequence = 0
let reconciliationRequestSequence = 0

const availableCustomers = computed(
  () => CUSTOMER_PROFILES_BY_FACTORY[props.factoryId] ?? [],
)
const selectedCustomer = computed(
  () => availableCustomers.value.find(
    (customer) => customer.code === selectedCustomerCode.value,
  ) ?? null,
)
const selectedCustomerName = computed(
  () => selectedCustomer.value?.name ?? '尚未选择客户',
)
const preflightConfirmationText = computed(
  () => previewBatch.value?.duplicate_confirmation_enabled
    ? previewBatch.value?.duplicate_confirmation_authorized
      ? '当前环境已启用测试阶段重复订单确认；请在预览中逐项确认并填写原因后导出'
      : '当前环境已启用重复订单确认，但当前账号没有确认权限'
    : '重复订单是否允许确认以当前环境策略和预览结果为准',
)

const orderRows = ref<OrderRow[]>([])

const factoryOrderRows = computed(() => (
  orderRows.value.filter((row) => row.factoryId === props.factoryId)
))

const activeOrderRows = computed(() => (
  props.activeSection === 'preview' && !previewBatch.value
    ? []
    : factoryOrderRows.value.map((sourceRow) => {
        const row = { ...sourceRow }
        const issues = row.issues ?? []
        for (const issue of issues) {
          const value = manualOverrideValues.value[issue.skip_key]?.trim()
          const target = issue.edit_field ? manualRowFieldMap[issue.edit_field] : undefined
          if (value && target) row[target] = value as never
        }
        if (issues.length === 0) return row
        const remainingBlockers = issues.filter(
          (issue) => issue.severity === 'blocked'
            && !isConfirmationIssue(issue)
            && !isIssueResolved(issue),
        )
        const unresolvedConfirmations = issues.filter(
          (issue) => isConfirmationIssue(issue)
            && !isIssueResolved(issue),
        )
        const skippedIssues = issues.filter(
          (issue) => issue.can_skip && skippedIssueKeys.value.includes(issue.skip_key),
        )
        const overriddenIssues = issues.filter(isIssueManuallyOverridden)
        if (remainingBlockers.length > 0) {
          return row
        }
        if (unresolvedConfirmations.length > 0) {
          return { ...row, status: 'warning' as const, statusLabel: '待确认' }
        }
        if (issues.some((issue) => issue.severity === 'warning') || skippedIssues.length > 0 || overriddenIssues.length > 0) {
          const confirmedDuplicates = skippedIssues.filter(isTestDuplicateIssue)
          const skippedDataIssues = skippedIssues.filter((issue) => !isTestDuplicateIssue(issue))
          return {
            ...row,
            status: 'warning' as const,
            statusLabel: overriddenIssues.length > 0
              ? '已人工补录'
              : confirmedDuplicates.length > 0 && skippedDataIssues.length === 0
                ? '已确认通过'
                : skippedIssues.length > 0 ? '已确认放行' : '警告',
            issue: [
              row.issue,
              ...overriddenIssues.map((issue) => `人工补录${issue.edit_label || issue.field}`),
              ...confirmedDuplicates.map((issue) => `确认通过：${issue.skip_label}`),
              ...skippedDataIssues.map((issue) => `人工跳过：${issue.skip_label}`),
            ].filter(Boolean).join('；'),
          }
        }
        return { ...row, status: 'valid' as const, statusLabel: '有效' }
      })
))

const manualOverrides = computed<CustomerOrderManualOverride[]>(() => (
  (previewBatch.value?.rows ?? []).flatMap((row) => row.issues.flatMap((issue) => {
    const value = manualOverrideValues.value[issue.skip_key]?.trim() ?? ''
    if (!value || !issue.can_edit || !issue.edit_field) return []
    return [{
      row_id: row.id,
      issue_key: issue.skip_key,
      field: issue.edit_field,
      value,
    }]
  }))
))
const resolvedIssueKeys = computed(() => [...new Set([
  ...skippedIssueKeys.value,
  ...manualOverrides.value.map((item) => item.issue_key),
])])
const skippedIssueCount = computed(() => resolvedIssueKeys.value.length)
const confirmationReasonMissing = computed(() => (
  skippedIssueCount.value > 0 && confirmationReason.value.trim().length < 4
))
const canReconcilePreview = computed(() => Boolean(
  previewBatch.value
  && previewBatch.value.rows.length === 1
  && sourceKind.value === 'formal',
))
const reconciliationProductNo = computed(() => previewBatch.value?.rows[0]?.product_no ?? '')
const reconciliationPageCount = computed(() => Math.max(1, Math.ceil(reconciliationTotal.value / 50)))
const selectedReconciliationLine = computed(() => reconciliationCandidates.value.find(
  (line) => line.id === reconciliation.value.lineId,
) ?? null)
const selectedPoFile = computed(() => {
  if (poFiles.value.length === 0) return '尚未选择 PO 文件'
  if (poFiles.value.length === 1) return poFiles.value[0]!.name
  return `已选择 ${poFiles.value.length} 份 PO`
})
const selectedPoFileTitle = computed(() => poFiles.value.map((file) => file.name).join('\n'))
const poImportQueue = computed(() => poFiles.value.map((file, index) => ({
  key: `${file.name}-${file.size}-${file.lastModified}-${index}`,
  fileName: file.name,
  inputTemplate: previewBatch.value?.rows.find(
    (row) => row.source_po_file_name === file.name,
  )?.input_template || '解析后识别',
})))

const filteredRows = computed(() => {
  const query = searchQuery.value.trim().toLowerCase()
  return activeOrderRows.value.filter((row) => {
    if (row.status === 'valid' && !includeValid.value) return false
    if (row.status === 'warning' && !includeWarning.value) return false
    if (row.status === 'blocked' && !includeBlocked.value) return false
    if (!query) return true
    return [
      row.poNo,
      row.contractNo,
      row.customerCountry,
      row.productNo,
      row.productNameZh,
      row.productNameEn,
    ].some((value) => value.toLowerCase().includes(query))
  })
})

const ledgerCustomers = computed(() => [...new Set(
  activeOrderRows.value.map((row) => row.customerCountry),
)])

const filteredLedgerRows = computed(() => {
  const query = searchQuery.value.trim().toLowerCase()
  return activeOrderRows.value.filter((row) => {
    if (selectedLedgerStatus.value !== 'all' && row.status !== selectedLedgerStatus.value) return false
    if (selectedLedgerCustomer.value !== 'all' && row.customerCountry !== selectedLedgerCustomer.value) return false
    if (!query) return true
    return [
      row.poNo,
      row.contractNo,
      row.customerCountry,
      row.productNo,
      row.productNameZh,
      row.productNameEn,
    ].some((value) => value.toLowerCase().includes(query))
  })
})

const orderSummary = computed(() => ({
  total: activeOrderRows.value.length,
  valid: activeOrderRows.value.filter((row) => row.status === 'valid').length,
  warning: activeOrderRows.value.filter((row) => row.status === 'warning').length,
  blocked: activeOrderRows.value.filter((row) => row.status === 'blocked').length,
}))

const unconfirmedDuplicateIssueCount = computed(() => (
  (previewBatch.value?.rows ?? []).flatMap((row) => row.issues)
    .filter((issue) => isConfirmationIssue(issue)
      && issue.can_skip
      && isTestDuplicateIssue(issue)
      && !isIssueResolved(issue))
    .length
))

const blockingIssueDetails = computed(() => {
  const seen = new Set<string>()
  return (previewBatch.value?.rows ?? []).flatMap((row) => row.issues
    .filter((issue) => (
      issue.severity === 'blocked'
      && !isConfirmationIssue(issue)
      && !isIssueResolved(issue)
    ) || (
      isConfirmationIssue(issue)
      && !isIssueResolved(issue)
    ))
    .flatMap((issue) => {
      const key = [row.source_po_file_name, issue.code, issue.field, issue.message].join('|')
      if (seen.has(key)) return []
      seen.add(key)
      return [{ key, fileName: row.source_po_file_name, message: issue.message }]
    }))
})

const blockingResolutionItems = computed(() => (
  (previewBatch.value?.rows ?? []).flatMap((row) => row.issues
    .filter((issue) => issue.severity === 'blocked' || isConfirmationIssue(issue) || issue.can_edit)
    .map((issue) => ({ row, issue })))
))
const bulkSkippableIssueKeys = computed(() => [...new Set(
  blockingResolutionItems.value
    .map(({ issue }) => issue)
    .filter((issue) => issue.severity !== 'warning' && issue.can_skip && !isIssueManuallyOverridden(issue))
    .map((issue) => issue.skip_key),
)])
const allSkippableIssuesSelected = computed(() => (
  bulkSkippableIssueKeys.value.length > 0
  && bulkSkippableIssueKeys.value.every((key) => skippedIssueKeys.value.includes(key))
))

const scheduleReferenceDate = (() => {
  const today = new Date()
  return Date.UTC(today.getFullYear(), today.getMonth(), today.getDate())
})()

function getDeliveryMeta(requestedShipDate: string): {
  daysUntil: number
  deliveryStatus: DeliveryStatus
  deliveryStatusLabel: string
} {
  const targetDate = Date.parse(`${requestedShipDate}T00:00:00Z`)
  if (!Number.isFinite(targetDate)) {
    return {
      daysUntil: Number.MAX_SAFE_INTEGER,
      deliveryStatus: 'planned',
      deliveryStatusLabel: '走货期待补',
    }
  }
  const daysUntil = Math.ceil((targetDate - scheduleReferenceDate) / 86_400_000)
  if (daysUntil < 0) return { daysUntil, deliveryStatus: 'overdue', deliveryStatusLabel: `已逾期 ${Math.abs(daysUntil)} 天` }
  if (daysUntil <= 7) return { daysUntil, deliveryStatus: 'due-soon', deliveryStatusLabel: `${daysUntil} 天内到期` }
  if (daysUntil <= 30) return { daysUntil, deliveryStatus: 'upcoming', deliveryStatusLabel: `${daysUntil} 天后走货` }
  return { daysUntil, deliveryStatus: 'planned', deliveryStatusLabel: `计划中 · ${daysUntil} 天后` }
}

const factoryScheduleRows = computed(() => activeOrderRows.value.map((row) => ({
  ...row,
  deliveryMonth: row.requestedShipDate.slice(0, 7) || '待补日期',
  demandVersion: 'V1',
  publishableToDownstream: row.status === 'valid',
  ...getDeliveryMeta(row.requestedShipDate),
})))

const scheduleMonths = computed(() => [...new Set(factoryScheduleRows.value.map((row) => row.deliveryMonth))].sort())

const filteredFactoryScheduleRows = computed(() => factoryScheduleRows.value.filter((row) => {
  if (selectedScheduleMonth.value !== 'all' && row.deliveryMonth !== selectedScheduleMonth.value) return false
  if (selectedScheduleCustomer.value !== 'all' && row.customerCountry !== selectedScheduleCustomer.value) return false
  if (selectedProductionStatus.value === 'incomplete' && row.productionProgress >= 100) return false
  if (selectedProductionStatus.value === 'complete' && row.productionProgress < 100) return false
  return true
}))

const scheduleSummary = computed(() => ({
  poCount: new Set(filteredFactoryScheduleRows.value.map((row) => row.poNo)).size,
  totalQuantity: filteredFactoryScheduleRows.value.reduce(
    (sum, row) => sum + Number(row.quantity.replaceAll(',', '')),
    0,
  ),
  riskCount: filteredFactoryScheduleRows.value.filter(
    (row) => row.deliveryStatus === 'overdue' || row.deliveryStatus === 'due-soon',
  ).length,
  productionIncomplete: filteredFactoryScheduleRows.value.filter((row) => row.productionProgress < 100).length,
  publishableCount: filteredFactoryScheduleRows.value.filter((row) => row.publishableToDownstream).length,
}))

const dashboardSummary = computed(() => ({
  importBatchCount: factoryOrderRows.value.length > 0 ? 1 : 0,
  poCount: new Set(factoryOrderRows.value.map((row) => row.poNo)).size,
  confirmationCount: activeOrderRows.value.filter((row) => row.status !== 'valid').length,
  productionIncomplete: factoryScheduleRows.value.filter((row) => row.productionProgress < 100).length,
}))

const recentFactoryActivities = computed(() => factoryOrderRows.value.slice(0, 3).map((row) => ({
  id: row.id,
  time: row.feedbackAt === '—' ? row.receivedDate : row.feedbackAt.slice(11, 16),
  action: row.status === 'valid' ? '订单排期确认' : '字段映射复核',
  subject: `${row.customerCountry} / P/O# ${row.poNo}`,
  result: row.status === 'valid' ? '已确认' : row.statusLabel,
  status: row.status,
  stage: row.status === 'valid' ? '流程01完成' : '预览与确认',
})))

const monthlyScheduleSummary = computed(() => scheduleMonths.value.map((month) => {
  const rows = factoryScheduleRows.value.filter((row) => row.deliveryMonth === month)
  return {
    month,
    poCount: new Set(rows.map((row) => row.poNo)).size,
    customerCount: new Set(rows.map((row) => row.customerCountry)).size,
    quantity: rows.reduce((sum, row) => sum + Number(row.quantity.replaceAll(',', '')), 0),
    riskCount: rows.filter((row) => row.deliveryStatus === 'overdue' || row.deliveryStatus === 'due-soon').length,
  }
}))

const scheduleCustomers = computed(() => [...new Set(factoryScheduleRows.value.map((row) => row.customerCountry))])

const customerMonthlySummary = computed(() => scheduleCustomers.value
  .map((customer) => {
    const rows = filteredFactoryScheduleRows.value.filter((row) => row.customerCountry === customer)
    if (rows.length === 0) return null
    return {
      customer,
      poCount: new Set(rows.map((row) => row.poNo)).size,
      quantity: rows.reduce((sum, row) => sum + Number(row.quantity.replaceAll(',', '')), 0),
      nearestShipDate: [...rows].sort(
        (a, b) => (a.requestedShipDate || '9999-12-31').localeCompare(
          b.requestedShipDate || '9999-12-31',
        ),
      )[0]!.requestedShipDate || '待补充',
      riskCount: rows.filter((row) => row.deliveryStatus === 'overdue' || row.deliveryStatus === 'due-soon').length,
      productionIncomplete: rows.filter((row) => row.productionProgress < 100).length,
      publishableCount: rows.filter((row) => row.publishableToDownstream).length,
    }
  })
  .filter((summary): summary is NonNullable<typeof summary> => summary !== null))

// Risk and production feedback require authoritative downstream data.  They are
// intentionally not inferred from a transient PO preview or shown as mock facts.
const scheduleExceptions = computed<ScheduleException[]>(() => [])

const filteredScheduleExceptions = computed(() => {
  const query = exceptionSearch.value.trim().toLowerCase()
  return scheduleExceptions.value.filter((exception) => {
    if (selectedExceptionSeverity.value !== 'all' && exception.severity !== selectedExceptionSeverity.value) return false
    if (selectedExceptionCategory.value !== 'all' && exception.category !== selectedExceptionCategory.value) return false
    if (!query) return true
    return [
      exception.row.poNo,
      exception.row.contractNo,
      exception.row.customerCountry,
      exception.row.productNo,
      exception.row.productNameZh,
      exception.title,
    ].some((value) => value.toLowerCase().includes(query))
  })
})

const exceptionSummary = computed(() => ({
  total: scheduleExceptions.value.length,
  critical: scheduleExceptions.value.filter((exception) => exception.severity === 'critical').length,
  dueRisk: factoryScheduleRows.value.filter(
    (row) => row.deliveryStatus === 'overdue' || row.deliveryStatus === 'due-soon',
  ).length,
  dataBlocked: factoryScheduleRows.value.filter((row) => row.status === 'blocked').length,
  production: 0,
  versionLag: scheduleExceptions.value.filter((exception) => exception.category === '版本状态').length,
}))

const outputScheduleFile = computed(() => {
  if (generatedScheduleFileName.value) return generatedScheduleFileName.value
  if (previewBatch.value?.output_file_name) return previewBatch.value.output_file_name
  return scheduleFile.value?.name || `${selectedCustomerName.value}生产排期表.xlsx`
})

const previewCustomerName = computed(() => {
  const customerCode = previewBatch.value?.customer_code
  if (!customerCode) return selectedCustomerName.value
  return availableCustomers.value.find((customer) => customer.code === customerCode)?.name
    ?? customerCode
})

const previewCustomerMarkets = computed(() => Array.from(new Set(
  factoryOrderRows.value
    .map((row) => row.customerCountry.trim())
    .filter(Boolean),
)))

const previewRuleNotice = computed(() => {
  const customerCode = previewBatch.value?.customer_code ?? selectedCustomer.value?.code
  const profile = availableCustomers.value.find((customer) => customer.code === customerCode)
  const title = customerCode === 'caixing'
    ? '当前彩星输入规则已启用'
    : customerCode === 'dickie'
      ? '当前 Dickie 输入规则已启用'
      : customerCode === 'buzzbee'
        ? '当前 BuzzBee 三套输入规则已区分'
        : `当前${profile?.name ?? '客户'}输入规则已启用`
  return {
    title,
    description: profile?.ruleDescription ?? '请选择客户并完成解析后查看当前映射规则。',
  }
})

const generatedOutputDescription = computed(() => {
  const customerName = previewCustomerName.value || selectedCustomerName.value
  const targetTemplate = previewBatch.value?.target_template || selectedCustomer.value?.targetTemplate || UNIFIED_SCHEDULE_TEMPLATE
  const confirmationText = skippedIssueCount.value > 0
    ? `本批已人工确认/跳过 ${skippedIssueCount.value} 项。`
    : '本批没有人工确认或跳过项。'
  const passwordText = generatedPasswordRequired.value ? '工作簿打开密码为 2026。' : ''
  return `已按 ${customerName} 映射处理 ${previewBatch.value?.po_file_count || poFiles.value.length} 份 PO，生成 ${targetTemplate}；源排期文件未被覆盖。${confirmationText}${passwordText}`
})

const canParseFiles = computed(() => Boolean(
  selectedCustomer.value
  && poFiles.value.length > 0
  && scheduleFile.value
  && receivedDate.value
  && !parsingFiles.value
  && !exportingSchedule.value,
))

const traceFields = computed(() => {
  const row = traceRow.value
  if (!row) return []
  const isDickie = row.inputTemplate.includes('DICKIE')
  const isCaixing = row.inputTemplate.includes('CAIXING')
  const isWmu = row.inputTemplate.includes('WMU_ATTACHED')
  const sheetName = isDickie
    ? 'Dickie PDF'
    : isCaixing
      ? 'Playmates PDF'
      : isWmu
        ? 'PO Attached'
      : row.inputTemplate.includes('WMC')
        ? 'Sheet1'
        : 'SHEET'
  const inputKind = isDickie
    ? 'Simba Dickie Release Order PDF规则'
    : isCaixing
      ? '彩星 Playmates PDF规则'
      : isWmu
        ? 'WMU PO Attached子订单规则'
      : row.inputTemplate.includes('WMC')
        ? 'WMC首页内嵌规则'
        : '普通合同标签规则'
  const lineage = row.lineage ?? {}

  return [
    { label: '来单日期', value: row.receivedDate, source: lineage.received_date || '业务登记 · 来单日期' },
    { label: 'P/O#', value: row.poNo, source: lineage.po_no || row.poSource },
    { label: 'Contract No.', value: row.contractNo, source: lineage.contract_no || row.contractSource },
    { label: '客名/国家', value: row.customerCountry, source: lineage.customer_country || `${inputKind} · 客户与市场识别` },
    { label: '产品编号', value: row.productNo, source: lineage.product_no || row.productSource },
    { label: '中文名称', value: row.productNameZh, source: lineage.product_name_zh || `河源业务统一排期 · 货号 ${row.productNo}` },
    { label: '产品名称', value: row.productNameEn, source: lineage.product_name_en || `${sheetName} · 产品名称区域` },
    { label: '数量', value: row.quantity, source: lineage.quantity || `${inputKind} · Quantity` },
    { label: '装箱数', value: row.unitsPerCarton, source: lineage.units_per_carton || `${inputKind} · Shipping Carton Packing` },
    { label: '箱数', value: row.cartonCount, source: lineage.carton_count || '系统计算 · 数量 ÷ 装箱数' },
    { label: '国家标准', value: row.standard, source: lineage.standard || '模板规则 · 按客户/国家映射' },
    { label: '单价HK', value: row.unitPriceHkd, source: lineage.unit_price_hkd || '河源业务统一排期 · 产品最近有效单价' },
    { label: '金额HK', value: row.amountHkd, source: lineage.amount_hkd || '系统计算 · 数量 × 单价HK' },
    { label: '包装', value: row.packaging, source: lineage.packaging || `${inputKind} · 包装REF` },
    { label: '行Q', value: row.lineQ, source: lineage.line_q || `${inputKind} · 验货/交付日期规则` },
    { label: '客Q', value: row.customerQ, source: lineage.customer_q || `${inputKind} · 客户验货说明` },
    { label: '客要求走货期', value: row.requestedShipDate, source: lineage.requested_ship_date || row.shipDateSource },
  ]
})

function notify(message: string) {
  notice.value = message
  if (noticeTimer) window.clearTimeout(noticeTimer)
  noticeTimer = window.setTimeout(() => {
    notice.value = ''
  }, 3400)
}

function navigate(section: CustomerOrderCenterSection) {
  emit('navigate', section)
}

function getCustomerScheduleLabel(row: OrderRow) {
  const customerName = row.customerCountry.split('/')[0]?.trim() || row.customerCountry
  return `${customerName}排期_V1.xlsx`
}

function clearPreviewState() {
  parseRequestSequence += 1
  exportRequestSequence += 1
  saveRequestSequence += 1
  parsingFiles.value = false
  exportingSchedule.value = false
  previewBatch.value = null
  parseFailureMessage.value = ''
  exportFailureMessage.value = ''
  scheduleGenerated.value = false
  generatedScheduleBlob.value = null
  generatedScheduleFileName.value = ''
  generatedPasswordRequired.value = false
  skippedIssueKeys.value = []
  manualOverrideValues.value = {}
  confirmationReason.value = ''
  savingOrder.value = false
  reconciliationRequestSequence += 1
  reconciliation.value = { enabled: false, lineId: '', expectedRevision: 0, reason: '' }
  reconciliationCandidates.value = []
  reconciliationLoading.value = false
  reconciliationQuery.value = ''
  reconciliationPage.value = 1
  reconciliationTotal.value = 0
  orderRows.value = []
  traceRow.value = null
  blockingResolutionOpen.value = false
}

function resetImportBatch() {
  clearPreviewState()
  poFiles.value = []
  scheduleFile.value = null
  selectedScheduleFile.value = '尚未选择河源业务统一排期'
}

function selectCustomer(customerCode: CustomerOrderCustomerCode) {
  if (selectedCustomerCode.value === customerCode) return
  selectedCustomerCode.value = customerCode
  resetImportBatch()
  const customer = availableCustomers.value.find((item) => item.code === customerCode)
  notify(`已选择 ${customer?.name ?? customerCode}；请导入该客户的 PO 与排期文件。`)
}

function selectUpload(kind: 'po' | 'schedule') {
  if (!selectedCustomer.value) {
    notify('请先选择当前厂区的客户。')
    return
  }
  if (kind === 'po') poInput.value?.click()
  else scheduleInput.value?.click()
}

function isMacMetadataFile(file: File) {
  const normalizedPath = (file.webkitRelativePath || file.name).replace(/\\/g, '/')
  const pathParts = normalizedPath.toLowerCase().split('/').filter(Boolean)
  const baseName = pathParts.at(-1) ?? ''
  return pathParts.includes('__macosx') || baseName.startsWith('._') || baseName === '.ds_store'
}

function applySelectedFiles(kind: 'po' | 'schedule', files: File[]) {
  if (files.length === 0) return
  if (!selectedCustomer.value) {
    notify('请先选择当前厂区的客户，再导入文件。')
    return
  }

  const ignoredMacFiles = files.filter(isMacMetadataFile)
  const usableFiles = files.filter((file) => !isMacMetadataFile(file))
  if (usableFiles.length === 0) {
    clearPreviewState()
    if (kind === 'po') {
      poFiles.value = []
    } else {
      scheduleFile.value = null
      selectedScheduleFile.value = '尚未选择河源业务统一排期'
    }
    const fileName = ignoredMacFiles[0]?.name ?? '所选文件'
    notify(`已忽略 ${fileName}：这是 Mac 解压产生的隐藏资源文件，不是真实${kind === 'po' ? ' PO' : '排期'}。请选择同名且不带“._”前缀的文件。`)
    return
  }

  const acceptedExtensions = kind === 'po'
    ? selectedCustomer.value.poExtensions
    : selectedCustomer.value.scheduleExtensions
  const invalidFiles = usableFiles.filter(
    (file) => !acceptedExtensions.some((extension) => file.name.toLowerCase().endsWith(extension)),
  )
  if (invalidFiles.length > 0) {
    notify(
      kind === 'po'
        ? `${selectedCustomer.value.name} PO仅支持 ${acceptedExtensions.join(' / ')}：${invalidFiles[0]!.name}`
        : `${selectedCustomer.value.name} 排期仅支持 ${acceptedExtensions.join(' / ')}：${invalidFiles[0]!.name}`,
    )
    return
  }
  if (kind === 'po' && usableFiles.length > 30) {
    notify(`单批最多导入30份PO，当前拖入 ${usableFiles.length} 份。`)
    return
  }
  if (kind === 'schedule' && usableFiles.length > 1) {
    notify('客户排期每次只能导入1份，请重新拖入。')
    return
  }

  if (kind === 'po') {
    poFiles.value = usableFiles
  } else {
    const file = usableFiles[0]!
    scheduleFile.value = file
    selectedScheduleFile.value = file.name
  }
  clearPreviewState()
  const ignoredMessage = ignoredMacFiles.length > 0
    ? `已自动忽略 ${ignoredMacFiles.length} 个 Mac 隐藏资源文件；`
    : ''
  notify(
    kind === 'po'
      ? `${ignoredMessage}已选择 ${usableFiles.length} 份真实 PO；客户排期齐全后可批量解析。`
      : `${ignoredMessage}已选择 ${usableFiles[0]!.name}；PO文件齐全后可批量解析。`,
  )
}

function handleSelectedFile(kind: 'po' | 'schedule', event: Event) {
  const input = event.target as HTMLInputElement
  applySelectedFiles(kind, Array.from(input.files ?? []))
  input.value = ''
}

function handleUploadDragOver(kind: 'po' | 'schedule', event: DragEvent) {
  if (!selectedCustomer.value) return
  draggingUpload.value = kind
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy'
}

function handleUploadDragLeave(kind: 'po' | 'schedule', event: DragEvent) {
  const card = event.currentTarget as HTMLElement
  const nextTarget = event.relatedTarget
  if (!(nextTarget instanceof Node) || !card.contains(nextTarget)) {
    if (draggingUpload.value === kind) draggingUpload.value = null
  }
}

function handleDroppedFiles(kind: 'po' | 'schedule', event: DragEvent) {
  draggingUpload.value = null
  applySelectedFiles(kind, Array.from(event.dataTransfer?.files ?? []))
}

function mapPreviewRow(row: CustomerOrderPreviewRow, factoryId: string): OrderRow {
  return {
    id: row.id,
    factoryId,
    status: row.status,
    statusLabel: row.status_label,
    rowRole: row.row_role ?? 'detail',
    parentProductNo: row.parent_product_no ?? '',
    issue: row.issues.map((issue) => issue.message).join('；') || '17个统一字段已通过当前模板校验。',
    receivedDate: row.received_date,
    poNo: row.po_no,
    contractNo: row.contract_no,
    customerCountry: row.customer_country,
    productNo: row.product_no,
    productNameZh: row.product_name_zh,
    productNameEn: row.product_name_en,
    quantity: row.quantity,
    unitsPerCarton: row.units_per_carton,
    cartonCount: row.carton_count,
    standard: row.standard,
    unitPriceHkd: row.unit_price_hkd,
    amountHkd: row.amount_hkd,
    packaging: row.packaging,
    lineQ: row.line_q,
    customerQ: row.customer_q,
    requestedShipDate: row.requested_ship_date,
    source: Object.values(row.lineage).filter(Boolean).slice(0, 6).join(' / '),
    inputTemplate: row.input_template,
    targetTemplate: row.target_template,
    itemSheetName: row.item_sheet_name,
    poSource: row.lineage.po_no || '—',
    contractSource: row.lineage.contract_no || '—',
    productSource: row.lineage.product_no || '—',
    shipDateSource: row.lineage.requested_ship_date || '—',
    productionStatus: '尚未下发',
    productionProgress: 0,
    productionDepartment: '—',
    productionIssue: '当前批次只生成客户排期，尚未进入下游生产模块。',
    feedbackAt: '—',
    lineage: row.lineage,
    issues: row.issues,
    sourcePoFileName: row.source_po_file_name,
  }
}

async function parseSelectedFiles() {
  if (!selectedCustomer.value) {
    notify('请先选择当前厂区的客户。')
    return
  }
  if (poFiles.value.length === 0 || !scheduleFile.value) {
    notify(`请先选择一份或多份 ${selectedCustomer.value.name} PO 和河源业务统一排期。`)
    return
  }
  const requestId = ++parseRequestSequence
  const customerCode = selectedCustomer.value.code
  const requestedPoFiles = [...poFiles.value]
  const requestedScheduleFile = scheduleFile.value
  const requestedReceivedDate = receivedDate.value
  const requestedFactoryId = props.factoryId
  parsingFiles.value = true
  parseFailureMessage.value = ''
  exportFailureMessage.value = ''
  previewBatch.value = null
  orderRows.value = []
  skippedIssueKeys.value = []
  manualOverrideValues.value = {}
  confirmationReason.value = ''
  scheduleGenerated.value = false
  generatedScheduleBlob.value = null
  generatedScheduleFileName.value = ''
  generatedPasswordRequired.value = false
  try {
    const preview = customerCode === 'dickie'
      ? await customerOrderApi.previewDickieBatch(
          requestedPoFiles,
          requestedScheduleFile,
          requestedReceivedDate,
          requestedFactoryId,
        )
      : customerCode === 'caixing'
        ? await customerOrderApi.previewCaixingBatch(
            requestedPoFiles,
            requestedScheduleFile,
            requestedReceivedDate,
            requestedFactoryId,
          )
      : isMappedCustomerCode(customerCode)
        ? await customerOrderApi.previewMappedBatch(
            customerCode,
            requestedPoFiles,
            requestedScheduleFile,
            requestedReceivedDate,
            requestedFactoryId,
          )
      : await customerOrderApi.previewBuzzbeeBatch(
          requestedPoFiles,
          requestedScheduleFile,
          requestedReceivedDate,
          requestedFactoryId,
        )
    if (requestId !== parseRequestSequence) return
    if (preview.factory_id !== requestedFactoryId) {
      throw new Error(`服务端返回厂区 ${preview.factory_id || '未知'}，与当前厂区 ${requestedFactoryId} 不一致，已拒绝展示。`)
    }
    previewBatch.value = preview
    orderRows.value = preview.rows.map((row) => mapPreviewRow(row, requestedFactoryId))
    skippedIssueKeys.value = []
    manualOverrideValues.value = {}
    notify(`批量解析完成：${preview.po_file_count} 份PO、${preview.summary.total} 条明细，待确认 ${preview.confirmation_count ?? 0} 条，警告 ${preview.summary.warning} 条，阻断 ${preview.summary.blocked} 条。`)
    navigate('preview')
  } catch (error) {
    if (requestId !== parseRequestSequence) return
    const message = `解析失败：${getApiErrorMessage(error)}`
    parseFailureMessage.value = message
    notify(message)
  } finally {
    if (requestId === parseRequestSequence) parsingFiles.value = false
  }
}

function isIssueSkipped(issue: CustomerOrderIssue) {
  return issue.can_skip && skippedIssueKeys.value.includes(issue.skip_key)
}

function toggleIssueSkip(issue: CustomerOrderIssue) {
  if (!issue.can_skip) return
  if (!isIssueSkipped(issue)) {
    const nextOverrides = { ...manualOverrideValues.value }
    delete nextOverrides[issue.skip_key]
    manualOverrideValues.value = nextOverrides
  }
  skippedIssueKeys.value = isIssueSkipped(issue)
    ? skippedIssueKeys.value.filter((key) => key !== issue.skip_key)
    : [...skippedIssueKeys.value, issue.skip_key]
  if (skippedIssueKeys.value.length === 0) confirmationReason.value = ''
  scheduleGenerated.value = false
  generatedScheduleBlob.value = null
  generatedScheduleFileName.value = ''
  generatedPasswordRequired.value = false
  exportFailureMessage.value = ''
}

function toggleAllSkippableIssues() {
  const keys = new Set(bulkSkippableIssueKeys.value)
  skippedIssueKeys.value = allSkippableIssuesSelected.value
    ? skippedIssueKeys.value.filter((key) => !keys.has(key))
    : [...new Set([...skippedIssueKeys.value, ...keys])]
  if (skippedIssueKeys.value.length === 0) confirmationReason.value = ''
  scheduleGenerated.value = false
  generatedScheduleBlob.value = null
  generatedScheduleFileName.value = ''
  generatedPasswordRequired.value = false
  exportFailureMessage.value = ''
}

function updateManualOverride(issue: CustomerOrderIssue, event: Event) {
  if (!issue.can_edit || !issue.edit_field) return
  const value = (event.target as HTMLInputElement).value
  manualOverrideValues.value = {
    ...manualOverrideValues.value,
    [issue.skip_key]: value,
  }
  if (value.trim()) {
    skippedIssueKeys.value = skippedIssueKeys.value.filter((key) => key !== issue.skip_key)
  }
  if (resolvedIssueKeys.value.length === 0) confirmationReason.value = ''
  scheduleGenerated.value = false
  generatedScheduleBlob.value = null
  generatedScheduleFileName.value = ''
  generatedPasswordRequired.value = false
  exportFailureMessage.value = ''
}

function resolveBlockedRow() {
  if (blockingResolutionItems.value.length === 0) {
    notify('当前批次没有需要人工处理的阻断项。')
    return
  }
  blockingResolutionOpen.value = true
}

function finishBlockingResolution() {
  if (blockingIssueDetails.value.length > 0) {
    notify(`仍有 ${blockingIssueDetails.value.length} 类阻断未处理，请逐项补录或确认放行。`)
    return
  }
  if (confirmationReasonMissing.value) {
    notify('请填写至少 4 个字的人工处理原因。')
    return
  }
  blockingResolutionOpen.value = false
  notify('人工处理结果已保留，可以生成客户排期。')
}

async function confirmAndGenerateSchedule() {
  if (unconfirmedDuplicateIssueCount.value > 0) {
    notify(`仍有 ${unconfirmedDuplicateIssueCount.value} 项重复订单待确认，请在“确认/阻断处理”列勾选后再生成。`)
    return
  }
  if (orderSummary.value.blocked > 0) {
    notify('仍有未处理的阻断项；请人工补录，或确认资料暂缺并放行。')
    return
  }
  if (!previewBatch.value || poFiles.value.length === 0 || !scheduleFile.value) {
    notify('请先从“PO 与客户排期导入”完成真实解析。')
    return
  }
  if (confirmationReasonMissing.value) {
    notify('本批存在人工确认或跳过项，请填写至少 4 个字的确认原因。')
    return
  }
  const requestId = ++exportRequestSequence
  const requestedPreview = previewBatch.value
  const requestedPoFiles = [...poFiles.value]
  const requestedScheduleFile = scheduleFile.value
  const requestedReceivedDate = receivedDate.value
  const requestedFactoryId = props.factoryId
  const requestedSkippedIssueKeys = [...resolvedIssueKeys.value]
  const requestedManualOverrides = [...manualOverrides.value]
  const requestedConfirmationReason = confirmationReason.value.trim()
  exportingSchedule.value = true
  exportFailureMessage.value = ''
  try {
    const customerCode = requestedPreview.customer_code as CustomerOrderCustomerCode
    const result = customerCode === 'dickie'
      ? await customerOrderApi.exportDickieBatch(
          requestedPoFiles,
          requestedScheduleFile,
          requestedReceivedDate,
          requestedPreview.output_file_name,
          requestedFactoryId,
          requestedSkippedIssueKeys,
          requestedPreview.preview_fingerprint,
          requestedConfirmationReason,
          requestedManualOverrides,
        )
      : customerCode === 'caixing'
        ? await customerOrderApi.exportCaixingBatch(
            requestedPoFiles,
            requestedScheduleFile,
            requestedReceivedDate,
            requestedPreview.output_file_name,
            requestedFactoryId,
            requestedSkippedIssueKeys,
            requestedPreview.preview_fingerprint,
            requestedConfirmationReason,
            requestedManualOverrides,
          )
      : isMappedCustomerCode(customerCode)
        ? await customerOrderApi.exportMappedBatch(
            customerCode,
            requestedPoFiles,
            requestedScheduleFile,
            requestedReceivedDate,
            requestedPreview.output_file_name,
            requestedFactoryId,
            requestedSkippedIssueKeys,
            requestedPreview.preview_fingerprint,
            requestedConfirmationReason,
            requestedManualOverrides,
          )
      : await customerOrderApi.exportBuzzbeeBatch(
          requestedPoFiles,
          requestedScheduleFile,
          requestedReceivedDate,
          requestedPreview.output_file_name,
          requestedFactoryId,
          requestedSkippedIssueKeys,
          requestedPreview.preview_fingerprint,
          requestedConfirmationReason,
          requestedManualOverrides,
        )
    if (requestId !== exportRequestSequence) return
    generatedScheduleBlob.value = result.blob
    generatedScheduleFileName.value = result.fileName
    generatedPasswordRequired.value = result.passwordRequired
    scheduleGenerated.value = true
    downloadGeneratedSchedule()
    notify(
      result.passwordRequired
        ? `已生成并下载 ${result.fileName}；工作簿打开密码为 2026。`
        : `已生成并下载 ${result.fileName}；原客户排期未被覆盖。`,
    )
  } catch (error) {
    if (requestId !== exportRequestSequence) return
    const message = `生成失败：${getApiErrorMessage(error)}`
    exportFailureMessage.value = message
    notify(message)
  } finally {
    if (requestId === exportRequestSequence) exportingSchedule.value = false
  }
}

async function toggleReconciliation() {
  if (!reconciliation.value.enabled) {
    reconciliation.value = { enabled: false, lineId: '', expectedRevision: 0, reason: '' }
    reconciliationCandidates.value = []
    reconciliationQuery.value = ''
    reconciliationPage.value = 1
    reconciliationTotal.value = 0
    return
  }
  if (!previewBatch.value || !canReconcilePreview.value) return
  reconciliationQuery.value = ''
  reconciliationPage.value = 1
  reconciliationTotal.value = 0
  await loadReconciliationCandidates()
}

async function loadReconciliationCandidates() {
  if (!previewBatch.value || !canReconcilePreview.value) return
  const requestId = ++reconciliationRequestSequence
  const requestedFactoryId = props.factoryId
  const requestedCustomerCode = previewBatch.value.customer_code
  const requestedProductNo = reconciliationProductNo.value
  const requestedPage = reconciliationPage.value
  const requestedQuery = reconciliationQuery.value.trim()
  reconciliationLoading.value = true
  try {
    const result = await customerOrderLedgerApi.list(requestedFactoryId, {
      customerCode: requestedCustomerCode,
      view: 'all',
      q: requestedQuery,
      page: requestedPage,
      pageSize: 50,
    })
    if (requestId !== reconciliationRequestSequence || requestedFactoryId !== props.factoryId) return
    reconciliationTotal.value = result.total
    reconciliationCandidates.value = result.items.filter((line) => (
      line.factory_id === requestedFactoryId
      && line.customer_code === requestedCustomerCode
      && line.status === 'active'
      && line.product_no === requestedProductNo
    ))
    if (!reconciliationCandidates.value.some((line) => line.id === reconciliation.value.lineId)) {
      reconciliation.value = { ...reconciliation.value, lineId: '', expectedRevision: 0 }
    }
  } catch (error) {
    if (requestId !== reconciliationRequestSequence || requestedFactoryId !== props.factoryId) return
    reconciliation.value = { enabled: false, lineId: '', expectedRevision: 0, reason: '' }
    reconciliationCandidates.value = []
    reconciliationTotal.value = 0
    notify(`无法读取可关联订单：${getApiErrorMessage(error)}`)
  } finally {
    if (requestId === reconciliationRequestSequence) reconciliationLoading.value = false
  }
}

function searchReconciliationCandidates() {
  reconciliationPage.value = 1
  void loadReconciliationCandidates()
}

function goToReconciliationPage(nextPage: number) {
  if (nextPage < 1 || nextPage > reconciliationPageCount.value || nextPage === reconciliationPage.value) return
  reconciliationPage.value = nextPage
  void loadReconciliationCandidates()
}

function selectReconciliationLine() {
  const line = selectedReconciliationLine.value
  reconciliation.value = {
    ...reconciliation.value,
    expectedRevision: line?.revision ?? 0,
  }
}

async function confirmAndSaveOrder() {
  if (unconfirmedDuplicateIssueCount.value > 0 || orderSummary.value.blocked > 0) {
    notify('请先完成所有重复订单确认和阻断项处理。')
    return
  }
  if (!previewBatch.value || poFiles.value.length === 0 || !scheduleFile.value) {
    notify('请先从“PO 与客户排期导入”完成真实解析。')
    return
  }
  if (confirmationReasonMissing.value) {
    notify('本批存在人工确认或跳过项，请填写至少 4 个字的确认原因。')
    return
  }
  if (reconciliation.value.enabled && (!reconciliation.value.lineId || reconciliation.value.expectedRevision < 1 || reconciliation.value.reason.trim().length < 4)) {
    notify('关联已有订单时，请选择订单并填写至少 4 个字的核对原因。')
    return
  }
  const requestId = ++saveRequestSequence
  const requestedPreview = previewBatch.value
  const requestedFactoryId = props.factoryId
  const payload = new FormData()
  payload.append('factory_id', requestedFactoryId)
  payload.append('received_date', receivedDate.value)
  poFiles.value.forEach((file) => payload.append('po_files', file))
  payload.append('schedule_file', scheduleFile.value)
  payload.append('confirmed', 'true')
  payload.append('skipped_issue_keys', JSON.stringify(resolvedIssueKeys.value))
  payload.append('manual_overrides', JSON.stringify(manualOverrides.value))
  payload.append('preview_fingerprint', requestedPreview.preview_fingerprint)
  payload.append('confirmation_reason', confirmationReason.value.trim())
  payload.append('source_kind', sourceKind.value)
  if (reconciliation.value.enabled) {
    payload.append('reconcile_line_id', reconciliation.value.lineId)
    payload.append('expected_revision', String(reconciliation.value.expectedRevision))
    payload.append('reconciliation_reason', reconciliation.value.reason.trim())
  }
  savingOrder.value = true
  try {
    const result = await customerOrderLedgerApi.importConfirmed(requestedPreview.customer_code, payload)
    if (requestId !== saveRequestSequence || requestedFactoryId !== props.factoryId) return
    notify(result.reconciled_count > 0
      ? '订单已关联并更新原订单，原走货与版本记录已保留。'
      : `订单已确认并保存：新增 ${result.created_count} 条，已存在 ${result.existing_count} 条。`)
    navigate('ledger')
  } catch (error) {
    if (requestId !== saveRequestSequence || requestedFactoryId !== props.factoryId) return
    notify(`保存订单失败：${getApiErrorMessage(error)}`)
  } finally {
    if (requestId === saveRequestSequence) savingOrder.value = false
  }
}

function downloadGeneratedSchedule() {
  if (!generatedScheduleBlob.value) {
    notify('尚未生成可下载的客户排期。')
    return
  }
  const url = URL.createObjectURL(generatedScheduleBlob.value)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = outputScheduleFile.value
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1_000)
}

function toggleExceptionAcknowledged(exceptionId: string) {
  acknowledgedExceptionIds.value = acknowledgedExceptionIds.value.includes(exceptionId)
    ? acknowledgedExceptionIds.value.filter((id) => id !== exceptionId)
    : [...acknowledgedExceptionIds.value, exceptionId]
}

function handleExceptionAction(exception: ScheduleException) {
  navigate(exception.actionSection)
  notify(`静态演示：已前往“${exception.actionSection === 'preview' ? '预览与确认' : '厂区总排期'}”处理相关业务。`)
}

watch(
  () => props.factoryId,
  () => {
    if (noticeTimer) window.clearTimeout(noticeTimer)
    notice.value = ''
    selectedCustomerCode.value = ''
    resetImportBatch()
    searchQuery.value = ''
    includeValid.value = true
    includeWarning.value = true
    includeBlocked.value = true
    selectedLedgerStatus.value = 'all'
    selectedLedgerCustomer.value = 'all'
    selectedScheduleMonth.value = 'all'
    selectedScheduleCustomer.value = 'all'
    selectedProductionStatus.value = 'all'
    selectedExceptionSeverity.value = 'all'
    selectedExceptionCategory.value = 'all'
    exceptionSearch.value = ''
    acknowledgedExceptionIds.value = []
  },
)

watch(sourceKind, (kind) => {
  if (kind === 'formal' || !reconciliation.value.enabled) return
  reconciliationRequestSequence += 1
  reconciliation.value = { enabled: false, lineId: '', expectedRevision: 0, reason: '' }
  reconciliationCandidates.value = []
  reconciliationLoading.value = false
  reconciliationQuery.value = ''
  reconciliationPage.value = 1
  reconciliationTotal.value = 0
})

watch(receivedDate, (currentDate, previousDate) => {
  if (currentDate === previousDate) return
  if (previewBatch.value || parsingFiles.value || scheduleGenerated.value || exportingSchedule.value) {
    clearPreviewState()
    notify('来单日期已变更，原预览已失效；请按新日期重新解析。')
  }
})

onBeforeUnmount(() => {
  if (noticeTimer) window.clearTimeout(noticeTimer)
})
</script>

<template>
  <div class="order-workspace" data-testid="customer-order-center-workspace">
    <Transition name="order-panel" mode="out-in">
      <section v-if="activeSection === 'dashboard'" key="dashboard" class="order-view" data-testid="order-dashboard">
        <header class="view-heading">
          <div>
            <span class="eyebrow"><Sparkles aria-hidden="true" /> 预览辅助工作区</span>
            <h2>客户订单中心</h2>
            <p>这里仅辅助导入和预览。已确认订单、发送记录与走货数量以“订单数据台账”为准；不维护生产、物料、库存或排产数据。</p>
          </div>
          <div class="view-heading__actions">
            <button type="button" class="button button--ghost" @click="navigate('ledger')">
              <Database aria-hidden="true" /> 查看订单台账
            </button>
            <button type="button" class="button button--primary" @click="navigate('import')">
              <Plus aria-hidden="true" /> 新建导入
            </button>
          </div>
        </header>

        <div class="metric-grid">
          <article class="metric-card">
            <span class="metric-card__icon metric-card__icon--blue"><FileUp aria-hidden="true" /></span>
            <div><p>当前导入批次</p><strong>{{ dashboardSummary.importBatchCount }}</strong><small>{{ dashboardSummary.poCount }}个PO · 当前厂区</small></div>
          </article>
          <article class="metric-card">
            <span class="metric-card__icon metric-card__icon--amber"><ClipboardCheck aria-hidden="true" /></span>
            <div><p>待确认数据</p><strong>{{ dashboardSummary.confirmationCount }}</strong><small>仅统计当前厂区订单</small></div>
          </article>
          <article class="metric-card metric-card--error">
            <span class="metric-card__icon metric-card__icon--red"><AlertTriangle aria-hidden="true" /></span>
            <div><p>阻断项</p><strong>{{ orderSummary.blocked }}</strong><small>当前厂区数据校验</small></div>
          </article>
        </div>

        <div class="dashboard-grid">
          <div class="flow-column">
            <article class="flow-card flow-card--primary">
              <div class="flow-card__head">
                <span class="flow-number">流程 01</span>
                <span class="status-chip status-chip--active">当前可用</span>
              </div>
              <div class="flow-card__title">
                <span class="flow-card__icon"><FileSpreadsheet aria-hidden="true" /></span>
                <div>
                  <h3>PO 入客户排期并输出</h3>
                  <p>同时导入客户PO与客户年度排期，预览17个统一字段后生成填好数据的客户排期。</p>
                </div>
              </div>
              <ol class="flow-steps">
                <li><b>1</b><span>选择客户与模板</span></li>
                <li><b>2</b><span>导入PO及客户排期</span></li>
                <li><b>3</b><span>预览、校验、确认</span></li>
                <li><b>4</b><span>输出客户排期</span></li>
              </ol>
              <button type="button" class="flow-enter" @click="navigate('import')">
                进入PO导入 <ArrowRight aria-hidden="true" />
              </button>
            </article>

            <article class="flow-card">
              <div class="flow-card__head">
                <span class="flow-number">流程 02</span>
                <span class="status-chip status-chip--active">当前可用</span>
              </div>
              <div class="flow-card__title">
                <span class="flow-card__icon flow-card__icon--green"><GitBranch aria-hidden="true" /></span>
                <div>
                  <h3>已保存订单与走货台账</h3>
                  <p>按客户、订单状态和走货状态查看本厂已保存订单；厂区总排期只显示这些公共字段。</p>
                </div>
              </div>
              <ol class="flow-steps">
                <li><b>1</b><span>保存确认订单</span></li>
                <li><b>2</b><span>按客户筛选</span></li>
                <li><b>3</b><span>查看发送状态</span></li>
                <li><b>4</b><span>确认分批走货</span></li>
              </ol>
              <button type="button" class="flow-enter" @click="navigate('schedule')">
                查看厂区总排期 <ArrowRight aria-hidden="true" />
              </button>
            </article>
          </div>

          <aside class="dashboard-aside">
            <article class="panel-card">
              <header class="panel-card__head">
                <div><h3>快捷操作</h3><p>当前工作区</p></div>
              </header>
              <div class="quick-action-grid">
                <button type="button" @click="navigate('import')"><FileUp aria-hidden="true" /><span>导入PO与排期</span></button>
                <button type="button" @click="navigate('exceptions')"><ListChecks aria-hidden="true" /><span>查看异常提醒</span></button>
                <button type="button" @click="navigate('ledger')"><Database aria-hidden="true" /><span>查看订单台账</span></button>
                <button type="button" @click="navigate('schedule')"><GitBranch aria-hidden="true" /><span>查看厂区总排期</span></button>
              </div>
            </article>

            <article class="scope-card">
              <ShieldCheck aria-hidden="true" />
              <div>
                <h3>本阶段范围已锁定</h3>
                <p>流程01已支持{{ factoryName }} {{ availableCustomers.length }} 个已配置客户的真实 PO 解析与排期下载；仍不提交PMC、不计算库存，也不进入啤机、喷油或装配排产。</p>
              </div>
            </article>
          </aside>
        </div>

        <article class="panel-card activity-card">
          <header class="panel-card__head">
            <div><h3>当前预览记录</h3><p>只显示本次未保存的 PO 预览，不是订单台账。</p></div>
            <button type="button" class="text-button"><RefreshCw aria-hidden="true" /> 刷新</button>
          </header>
          <div class="table-scroll">
            <table class="activity-table">
              <thead><tr><th>时间</th><th>业务动作</th><th>客户 / 文件</th><th>处理结果</th><th>当前阶段</th></tr></thead>
              <tbody>
                <tr v-for="activity in recentFactoryActivities" :key="`activity-${activity.id}`">
                  <td>{{ activity.time }}</td>
                  <td>{{ activity.action }}</td>
                  <td>{{ activity.subject }}</td>
                  <td><span :class="['status-chip', `status-chip--${activity.status}`]">{{ activity.result }}</span></td>
                  <td>{{ activity.stage }}</td>
                </tr>
                <tr v-if="recentFactoryActivities.length === 0"><td colspan="5">当前厂区暂无处理记录</td></tr>
              </tbody>
            </table>
          </div>
        </article>
      </section>

      <section v-else-if="activeSection === 'import'" key="import" class="order-view" data-testid="order-import">
        <header class="view-heading">
          <div>
            <span class="eyebrow"><FileUp aria-hidden="true" /> 流程 01</span>
            <h2>PO 与客户排期导入</h2>
            <p>同时选择客户原始PO和该客户当前排期模板，系统将按客户模板映射统一字段。</p>
          </div>
          <span class="prototype-badge">真实文件试用 · {{ selectedCustomer ? `${selectedCustomer.name} ${selectedCustomer.version}` : '先选择客户' }}</span>
        </header>

        <section class="customer-selector" data-testid="factory-customer-selector">
          <header>
            <span><Building2 aria-hidden="true" /></span>
            <div>
              <h3>先选择 {{ factoryName }} 的客户</h3>
              <p>每个客户使用独立 PO 识别和排期写入规则；切换客户会清空当前未确认批次。</p>
            </div>
          </header>
          <div v-if="availableCustomers.length" class="customer-selector__options">
            <button
              v-for="customer in availableCustomers"
              :key="customer.code"
              type="button"
              :class="['customer-choice', { active: selectedCustomerCode === customer.code }]"
              :aria-pressed="selectedCustomerCode === customer.code"
              :data-testid="`customer-choice-${customer.code}`"
              @click="selectCustomer(customer.code)"
            >
              <span><UserRoundCheck aria-hidden="true" /></span>
              <div>
                <b>{{ customer.name }}</b>
                <small>{{ customer.poDescription }}</small>
              </div>
              <em>{{ selectedCustomerCode === customer.code ? '已选择' : '选择客户' }}</em>
            </button>
          </div>
          <p v-else class="customer-selector__empty">当前厂区尚未配置客户映射，暂不能导入。</p>
        </section>

        <ol class="wizard-steps">
          <li :class="{ active: !selectedCustomer }"><b>1</b><span>选择客户</span></li>
          <li :class="{ active: selectedCustomer && !poFiles.length }"><b>2</b><span>选择文件</span></li>
          <li><b>3</b><span>解析与映射</span></li>
          <li><b>4</b><span>预览与确认</span></li>
          <li><b>5</b><span>输出客户排期</span></li>
        </ol>

        <div class="import-layout">
          <div class="import-main">
            <div class="upload-grid">
              <article
                :class="['upload-card', { 'upload-card--dragging': draggingUpload === 'po', 'upload-card--disabled': !selectedCustomer }]"
                data-testid="po-drop-zone"
                aria-label="客户原始PO拖放区"
                @dragover.prevent="handleUploadDragOver('po', $event)"
                @dragleave="handleUploadDragLeave('po', $event)"
                @drop.prevent="handleDroppedFiles('po', $event)"
              >
                <span class="upload-card__type">文件 01 · 客户订单来源</span>
                <div class="upload-card__icon"><FileSpreadsheet aria-hidden="true" /></div>
                <h3>批量导入客户原始 PO</h3>
                <p>{{ selectedCustomer ? `${selectedCustomer.poDescription}；单批最多30份，也可直接拖入此区域。` : '请先选择客户，系统才会开放对应的 PO 文件类型。' }}</p>
                <strong :title="selectedPoFileTitle">{{ selectedPoFile }}</strong>
                <button type="button" class="button button--primary" :disabled="!selectedCustomer" @click="selectUpload('po')"><UploadCloud aria-hidden="true" /> 批量选择PO</button>
                <input ref="poInput" class="visually-hidden" type="file" :accept="selectedCustomer?.poAccept || ''" multiple @change="handleSelectedFile('po', $event)">
              </article>

              <article
                :class="['upload-card', 'upload-card--schedule', { 'upload-card--dragging': draggingUpload === 'schedule', 'upload-card--disabled': !selectedCustomer }]"
                data-testid="schedule-drop-zone"
                aria-label="客户排期拖放区"
                @dragover.prevent="handleUploadDragOver('schedule', $event)"
                @dragleave="handleUploadDragLeave('schedule', $event)"
                @drop.prevent="handleDroppedFiles('schedule', $event)"
              >
                <span class="upload-card__type">文件 02 · 客户输出模板</span>
                <div class="upload-card__icon upload-card__icon--green"><Layers3 aria-hidden="true" /></div>
                <h3>导入客户现有排期</h3>
                <p>{{ selectedCustomer ? `目标：${selectedCustomer.templateDescription}；仅在“取消单”上方追加，写入可取得的映射字段。` : '请先选择客户，再导入河源业务统一排期。' }}</p>
                <strong>{{ selectedScheduleFile }}</strong>
                <button type="button" class="button button--secondary" :disabled="!selectedCustomer" @click="selectUpload('schedule')"><UploadCloud aria-hidden="true" /> 选择排期文件</button>
                <input ref="scheduleInput" class="visually-hidden" type="file" :accept="selectedCustomer?.scheduleAccept || '.xlsx'" @change="handleSelectedFile('schedule', $event)">
              </article>
            </div>

            <div class="parse-banner">
              <span><Sparkles aria-hidden="true" /></span>
              <div>
                <h3>{{ selectedCustomer ? `已锁定当前 ${selectedCustomer.name} 映射范围` : '等待选择客户映射' }}</h3>
                <p>{{ selectedCustomer ? `输入：${selectedCustomer.poDescription} · 输出：${selectedCustomer.templateDescription}` : `当前厂区：${factoryName}；请选择已配置映射的客户。` }}</p>
                <label class="received-date-field">
                  <b>来单日期</b>
                  <input v-model="receivedDate" type="date" aria-label="来单日期">
                </label>
                <label class="received-date-field">
                  <b>资料类型</b>
                  <select v-model="sourceKind" aria-label="订单资料类型"><option value="formal">正式 PO</option><option value="supplementary">补充资料</option></select>
                </label>
              </div>
              <button type="button" class="button button--primary" :disabled="!canParseFiles" @click="parseSelectedFiles">
                {{ parsingFiles ? '正在解析…' : '解析并进入预览' }} <ArrowRight aria-hidden="true" />
              </button>
            </div>

            <article
              v-if="parseFailureMessage || exportFailureMessage || blockingIssueDetails.length"
              class="persistent-parse-alert"
              data-testid="import-parse-alert"
              role="alert"
            >
              <span class="persistent-parse-alert__icon"><AlertTriangle aria-hidden="true" /></span>
              <div class="persistent-parse-alert__content">
                <h3>{{ parseFailureMessage ? '解析未完成' : exportFailureMessage ? '排期生成未完成' : `发现 ${blockingIssueDetails.length} 项待确认/阻断` }}</h3>
                <p v-if="parseFailureMessage">{{ parseFailureMessage }}</p>
                <p v-else-if="exportFailureMessage">{{ exportFailureMessage }}</p>
                <ul v-else>
                  <li v-for="item in blockingIssueDetails" :key="item.key">
                    <b>{{ item.fileName }}</b>
                    <span>{{ item.message }}</span>
                  </li>
                </ul>
              </div>
              <button
                v-if="previewBatch"
                type="button"
                class="button button--ghost"
                @click="navigate('preview')"
              >
                查看阻断明细
              </button>
            </article>

            <article class="panel-card">
              <header class="panel-card__head">
                <div><h3>实时导入队列</h3><p>参考HTML中的批量导入状态设计</p></div>
                <button type="button" class="text-button"><History aria-hidden="true" /> 查看历史</button>
              </header>
              <div class="table-scroll">
                <table class="import-queue-table">
                  <thead><tr><th>文件名</th><th>文件角色</th><th>客户</th><th>识别模板</th><th>状态</th><th>时间</th></tr></thead>
                  <tbody>
                    <tr v-for="item in poImportQueue" :key="item.key"><td><FileSpreadsheet aria-hidden="true" /> {{ item.fileName }}</td><td>客户PO</td><td>{{ selectedCustomerName }}</td><td>{{ item.inputTemplate }}</td><td><span class="status-chip status-chip--active">已选择</span></td><td>本批</td></tr>
                    <tr v-if="poImportQueue.length === 0"><td><FileSpreadsheet aria-hidden="true" /> 尚未选择 PO 文件</td><td>客户PO</td><td>{{ selectedCustomerName }}</td><td>解析后识别</td><td><span class="status-chip status-chip--warning">待选择</span></td><td>本批</td></tr>
                    <tr><td><FileSpreadsheet aria-hidden="true" /> {{ selectedScheduleFile }}</td><td>河源统一排期</td><td>{{ selectedCustomerName }} / {{ factoryName }}</td><td>{{ previewBatch?.target_template || selectedCustomer?.targetTemplate || '待选择客户' }}</td><td><span :class="['status-chip', scheduleFile ? 'status-chip--active' : 'status-chip--warning']">{{ scheduleFile ? '已选择' : '待选择' }}</span></td><td>本次</td></tr>
                  </tbody>
                </table>
              </div>
            </article>
          </div>

          <aside class="import-aside">
            <article class="panel-card guide-card">
              <header class="panel-card__head"><div><h3>本次导入检查</h3><p>进入预览前</p></div></header>
              <ul>
                <li><component :is="selectedCustomer ? CheckCircle2 : CircleAlert" :class="{ warning: !selectedCustomer }" aria-hidden="true" /><div><b>客户{{ selectedCustomer ? '已选择' : '待选择' }}</b><span>{{ selectedCustomerName }} · {{ factoryName }}</span></div></li>
                <li><component :is="poFiles.length && scheduleFile ? CheckCircle2 : CircleAlert" :class="{ warning: !poFiles.length || !scheduleFile }" aria-hidden="true" /><div><b>批量PO与排期{{ poFiles.length && scheduleFile ? '齐全' : '待选择' }}</b><span>{{ poFiles.length }} 份PO + 1份客户排期</span></div></li>
                <li><component :is="previewBatch ? CheckCircle2 : CircleAlert" :class="{ warning: !previewBatch }" aria-hidden="true" /><div><b>模板{{ previewBatch ? '已识别' : '待解析' }}</b><span>{{ previewBatch?.input_template || selectedCustomer?.poDescription || '先选择客户' }}</span></div></li>
                <li><CircleAlert aria-hidden="true" class="warning" /><div><b>生成前检查</b><span>{{ preflightConfirmationText }}</span></div></li>
              </ul>
            </article>

            <article class="mapping-card">
              <Settings2 aria-hidden="true" />
              <h3>字段映射</h3>
              <p>当前批次将映射到17个统一业务字段，并保留原文件、工作表与单元格来源。</p>
              <button type="button" :disabled="!previewBatch" @click="navigate('preview')">查看映射结果</button>
            </article>

            <article class="panel-card load-card">
              <header><h3>解析进度</h3><strong>{{ parsingFiles ? '处理中' : previewBatch ? '100%' : '0%' }}</strong></header>
              <div class="progress-track"><span :style="{ width: parsingFiles ? '55%' : previewBatch ? '100%' : '0%' }" /></div>
              <p v-if="previewBatch">{{ previewBatch.summary.total }} 条订单明细 · 17个字段 · {{ unconfirmedDuplicateIssueCount }} 项待确认 · {{ orderSummary.blocked }} 项阻断</p>
              <p v-else>选择一份或多份PO及一份客户排期后开始真实解析</p>
            </article>
          </aside>
        </div>
      </section>

      <section v-else-if="activeSection === 'preview'" key="preview" class="order-view" data-testid="order-preview">
        <header class="view-heading view-heading--compact">
          <div>
            <span class="eyebrow"><ClipboardCheck aria-hidden="true" /> 预览与校验</span>
            <h2>{{ previewBatch ? `${previewCustomerName} PO 映射预览` : '尚未建立真实预览批次' }}</h2>
            <p>来源：<b>{{ previewBatch?.input_template || '请先导入 PO 与排期' }}</b> · 输出目标：<b>{{ previewBatch?.target_template || selectedCustomer?.targetTemplate || '待选择客户' }}</b></p>
          </div>
          <div class="view-heading__actions">
            <button v-if="blockingResolutionItems.length" type="button" class="button button--ghost" data-testid="open-field-resolution" @click="resolveBlockedRow">
              {{ blockingIssueDetails.length ? '打开待确认/阻断处理' : blockingResolutionItems.some(({ issue }) => issue.severity === 'warning' && issue.can_edit) ? '更正日期/补录字段' : '查看已处理阻断项' }}
            </button>
            <button type="button" class="button button--secondary" :disabled="!previewBatch || unconfirmedDuplicateIssueCount > 0 || orderSummary.blocked > 0 || confirmationReasonMissing || savingOrder" @click="confirmAndSaveOrder">{{ savingOrder ? '正在保存…' : '确认并保存订单' }}</button>
            <button type="button" class="button button--primary" :disabled="!previewBatch || unconfirmedDuplicateIssueCount > 0 || orderSummary.blocked > 0 || confirmationReasonMissing || exportingSchedule" @click="confirmAndGenerateSchedule"><Download aria-hidden="true" /> {{ exportingSchedule ? '正在生成…' : unconfirmedDuplicateIssueCount > 0 ? '确认重复订单后生成' : orderSummary.blocked > 0 ? '处理阻断后生成' : confirmationReasonMissing ? '填写确认原因后生成' : orderSummary.warning > 0 ? '确认警告并生成客户排期' : '确认并生成客户排期' }}</button>
          </div>
        </header>

        <article
          v-if="blockingIssueDetails.length"
          class="persistent-parse-alert persistent-parse-alert--preview"
          data-testid="preview-blocker-alert"
          role="alert"
        >
          <span class="persistent-parse-alert__icon"><AlertTriangle aria-hidden="true" /></span>
          <div class="persistent-parse-alert__content">
            <h3>当前批次有 {{ blockingIssueDetails.length }} 项待人工处理，补录或确认放行后可生成排期</h3>
            <ul>
              <li v-for="item in blockingIssueDetails" :key="item.key">
                <b>{{ item.fileName }}</b>
                <span>{{ item.message }}</span>
              </li>
            </ul>
          </div>
        </article>

        <article
          v-if="skippedIssueCount > 0"
          class="confirmation-reason-card"
          data-testid="confirmation-reason-card"
        >
          <div>
            <strong>人工确认原因</strong>
            <p>本批已处理 {{ skippedIssueCount }} 项，其中 {{ manualOverrides.length }} 项使用人工补录值。补录内容、原因、操作者和文件哈希会一起写入审计记录。</p>
          </div>
          <label>
            <span>确认原因（必填，4–500 字）</span>
            <textarea
              v-model="confirmationReason"
              maxlength="500"
              rows="2"
              placeholder="例如：测试阶段验证客户映射，已核对订单号、货号和数量一致"
            />
            <small :class="{ invalid: confirmationReasonMissing }">{{ confirmationReason.trim().length }} / 500</small>
          </label>
        </article>

        <article v-if="previewBatch" class="reconciliation-card" data-testid="order-reconciliation-card">
          <label class="reconciliation-card__toggle">
            <input v-model="reconciliation.enabled" type="checkbox" :disabled="!canReconcilePreview" @change="toggleReconciliation">
            <span><b>关联已有订单（正式 PO 补齐/修订）</b><small v-if="canReconcilePreview">保留原订单、走货与版本记录，并以本次正式 PO 形成修订。</small><small v-else>仅单条正式 PO 的预览批次可关联已有订单；补充资料和批量保存保持独立新建。</small></span>
          </label>
          <div v-if="reconciliation.enabled" class="reconciliation-card__body">
            <div class="reconciliation-card__search">
              <label>搜索已有订单
                <input v-model="reconciliationQuery" type="search" placeholder="参考号、P/O 或产品编号" @keyup.enter="searchReconciliationCandidates">
              </label>
              <button type="button" class="button button--ghost" :disabled="reconciliationLoading" @click="searchReconciliationCandidates">搜索已有订单</button>
            </div>
            <p class="reconciliation-card__scope">只显示当前客户、货号 {{ reconciliationProductNo }} 且未取消的订单。第 {{ reconciliationPage }} / {{ reconciliationPageCount }} 页（查询共 {{ reconciliationTotal }} 条）。</p>
            <label>选择当前客户的已有订单
              <select v-model="reconciliation.lineId" :disabled="reconciliationLoading" @change="selectReconciliationLine">
                <option value="">{{ reconciliationLoading ? '正在读取已有订单…' : '请选择已有订单' }}</option>
                <option v-for="line in reconciliationCandidates" :key="line.id" :value="line.id">{{ line.reference_no }} · {{ line.product_no }} · 数量 {{ line.quantity }}</option>
              </select>
            </label>
            <p v-if="!reconciliationLoading && reconciliationCandidates.length === 0" class="reconciliation-card__scope">当前页没有可关联订单；可搜索参考号、P/O 或产品编号，或翻页继续查找。</p>
            <div class="reconciliation-card__pager">
              <button type="button" class="button button--ghost" :disabled="reconciliationLoading || reconciliationPage <= 1" @click="goToReconciliationPage(reconciliationPage - 1)">上一页</button>
              <button type="button" class="button button--ghost" :disabled="reconciliationLoading || reconciliationPage >= reconciliationPageCount" @click="goToReconciliationPage(reconciliationPage + 1)">下一页</button>
            </div>
            <p v-if="selectedReconciliationLine" class="reconciliation-card__selected">将关联：{{ selectedReconciliationLine.reference_no }} / {{ selectedReconciliationLine.product_no }} / 数量 {{ selectedReconciliationLine.quantity }} / 当前修订 {{ selectedReconciliationLine.revision }}</p>
            <label>正式 PO 核对原因（4–500 字）<textarea v-model="reconciliation.reason" maxlength="500" rows="2" placeholder="例如：正式 PO 补齐合同号，已核对货号、数量和交期" /></label>
          </div>
        </article>

        <ol class="wizard-steps wizard-steps--preview">
          <li class="done"><b>✓</b><span>选择客户</span></li>
          <li class="done"><b>✓</b><span>选择文件</span></li>
          <li class="done"><b>✓</b><span>解析与映射</span></li>
          <li :class="{ active: !scheduleGenerated, done: scheduleGenerated }"><b>{{ scheduleGenerated ? '✓' : '4' }}</b><span>预览与确认</span></li>
          <li :class="{ active: scheduleGenerated }"><b>5</b><span>输出客户排期</span></li>
        </ol>

        <article
          v-if="previewBatch && !scheduleGenerated"
          class="preview-next-step"
          data-testid="preview-next-step"
        >
          <span><FileCheck2 aria-hidden="true" /></span>
          <div>
            <strong>解析已完成，当前尚未输出排期</strong>
            <p>请核对下方明细；红色项可直接补录正确内容，确实无法取得时也可人工确认放行，再写入新排期。</p>
          </div>
          <button
            type="button"
            class="button button--primary"
            :disabled="unconfirmedDuplicateIssueCount > 0 || orderSummary.blocked > 0 || confirmationReasonMissing || exportingSchedule"
            @click="confirmAndGenerateSchedule"
          >
            <Download aria-hidden="true" />
            {{ exportingSchedule ? '正在生成…' : unconfirmedDuplicateIssueCount > 0 ? '确认重复订单后生成' : orderSummary.blocked > 0 ? '处理阻断后生成' : confirmationReasonMissing ? '填写确认原因后生成' : '生成并下载客户排期' }}
          </button>
          <button
            type="button"
            class="button button--secondary"
            :disabled="unconfirmedDuplicateIssueCount > 0 || orderSummary.blocked > 0 || confirmationReasonMissing || savingOrder"
            @click="confirmAndSaveOrder"
          >{{ savingOrder ? '正在保存…' : '确认并保存订单' }}</button>
        </article>

        <div class="summary-strip">
          <article><span>总行数</span><strong>{{ orderSummary.total }}</strong><small>订单明细</small></article>
          <article class="valid"><span>有效项</span><strong>{{ orderSummary.valid }}</strong><small>可直接写入</small></article>
          <article class="warning"><span>警告/待确认</span><strong>{{ orderSummary.warning }}</strong><small>不形成阻断</small></article>
          <article class="blocked"><span>待人工处理</span><strong>{{ orderSummary.blocked }}</strong><small>补录或确认放行</small></article>
        </div>

        <div class="preview-layout">
          <aside class="filter-panel">
            <h3><Filter aria-hidden="true" /> 活动筛选</h3>
            <label><input v-model="includeBlocked" type="checkbox"> 阻断性错误</label>
            <label><input v-model="includeWarning" type="checkbox"> 警告/待确认</label>
            <label><input v-model="includeValid" type="checkbox"> 已校验通过</label>
            <div class="filter-divider" />
            <label class="filter-field">客户 / 市场<select><option>全部 {{ previewCustomerName }}</option><option v-for="market in previewCustomerMarkets" :key="market">{{ market }}</option></select></label>
            <label class="filter-field">模板版本<select><option>V1.0 当前版本</option></select></label>
            <div class="logic-note">
              <Sparkles aria-hidden="true" />
              <div><b>{{ previewRuleNotice.title }}</b><p>{{ previewRuleNotice.description }}</p></div>
            </div>
          </aside>

          <article class="data-grid-card">
            <header class="data-grid-card__toolbar">
              <div>
                <ListChecks aria-hidden="true" />
                <span>17字段完整性网格</span>
                <small>显示 {{ filteredRows.length }} / {{ activeOrderRows.length }} 条</small>
              </div>
              <label class="inline-search"><Search aria-hidden="true" /><input v-model="searchQuery" type="search" placeholder="搜索PO、合同或产品"></label>
            </header>
            <div class="table-scroll table-scroll--preview">
              <table class="unified-table">
                <thead>
                  <tr>
                    <th class="sticky-left">状态</th><th class="resolution-column">人工处理</th>
                    <th>来单日期</th><th>P/O#</th><th>Contract No.</th><th>客名/国家</th><th>产品编号</th>
                    <th>中文名称</th><th>产品名称</th><th>数量</th><th>装箱数</th><th>箱数</th>
                    <th>国家标准</th><th>单价HK</th><th>金额HK</th><th>包装</th><th>行Q</th><th>客Q</th><th>客要求走货期</th><th>溯源</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="row in filteredRows"
                    :key="row.id"
                    :class="[`row-${row.status}`, { 'row-parent-product': row.rowRole === 'parent' }]"
                  >
                    <td class="sticky-left preview-row-status">
                      <span :class="['status-chip', `status-chip--${row.status}`]">{{ row.statusLabel }}</span>
                      <ul v-if="row.issues?.length" class="preview-row-issue-summary">
                        <li v-for="issue in row.issues" :key="`${row.id}-status-${issue.code}-${issue.field}`">{{ issue.message }}</li>
                      </ul>
                    </td>
                    <td class="resolution-column">
                      <div v-if="row.issues?.some((issue) => issue.severity === 'blocked' || isConfirmationIssue(issue) || issue.can_edit)" class="issue-resolution-list">
                        <template v-for="issue in (row.issues ?? []).filter((item) => item.severity === 'blocked' || isConfirmationIssue(item))" :key="`${row.id}-${issue.code}-${issue.field}`">
                          <div class="issue-resolution-item">
                            <p class="issue-resolution-message">{{ issue.message }}</p>
                            <label v-if="issue.can_edit" class="manual-override-field">
                              <span><b>人工补录 {{ issue.edit_label }}</b><small>该值会写入新排期，不修改客户原 PO</small></span>
                              <input
                                :type="issue.edit_input_type || 'text'"
                                :step="issue.edit_input_type === 'number' ? 'any' : undefined"
                                :value="manualOverrideValues[issue.skip_key] || ''"
                                :placeholder="`填写${issue.edit_label || '正确内容'}`"
                                @input="updateManualOverride(issue, $event)"
                              >
                            </label>
                          <label v-if="issue.can_skip && issue.severity !== 'warning'" class="skip-issue-option">
                            <input
                              type="checkbox"
                              :checked="isIssueSkipped(issue)"
                              :disabled="isIssueManuallyOverridden(issue)"
                              @change="toggleIssueSkip(issue)"
                            >
                            <span><b>{{ isTestDuplicateIssue(issue) ? '确认重复订单' : '确认缺失并放行' }}</b>{{ issue.skip_label }}</span>
                          </label>
                          <p v-if="!issue.can_edit && !issue.can_skip" class="required-issue"><b>必须补齐</b>{{ issue.message }}</p>
                          </div>
                        </template>
                      </div>
                      <span v-else class="no-resolution-needed">—</span>
                    </td>
                    <td>{{ row.receivedDate }}</td><td class="mono">{{ row.poNo }}</td><td class="mono">{{ row.contractNo }}</td><td>{{ row.customerCountry }}</td>
                    <td :class="['mono', 'product-hierarchy-cell', { 'product-hierarchy-cell--child': row.rowRole === 'detail' && row.parentProductNo }]">
                      <span v-if="row.rowRole === 'parent'" class="product-role-badge product-role-badge--parent">大货号</span>
                      <span v-else-if="row.parentProductNo" class="product-role-badge product-role-badge--child">小货号</span>
                      <b>{{ row.productNo }}</b>
                    </td>
                    <td :class="{ 'cell-issue': row.productNameZh === '待映射' }">{{ row.productNameZh }}</td><td>{{ row.productNameEn }}</td><td class="number">{{ row.quantity }}</td><td class="number">{{ row.unitsPerCarton }}</td><td class="number">{{ row.cartonCount }}</td>
                    <td>{{ row.standard }}</td><td class="number">{{ row.unitPriceHkd }}</td><td class="number">{{ row.amountHkd }}</td><td>{{ row.packaging }}</td><td>{{ row.lineQ }}</td><td>{{ row.customerQ }}</td><td>{{ row.requestedShipDate || '待补充' }}</td>
                    <td><button type="button" class="trace-button" @click="traceRow = row">查看来源</button></td>
                  </tr>
                </tbody>
              </table>
            </div>
            <footer class="table-footer">
              <span><CircleAlert aria-hidden="true" /> {{ previewRuleNotice.description }}</span>
              <div><button type="button"><ChevronLeft aria-hidden="true" /></button><b>1</b><button type="button"><ChevronRight aria-hidden="true" /></button></div>
            </footer>
          </article>
        </div>

        <article v-if="scheduleGenerated" class="generated-output-card" data-testid="generated-schedule-output">
          <span class="generated-output-card__icon"><FileCheck2 aria-hidden="true" /></span>
          <div class="generated-output-card__main">
            <span class="status-chip status-chip--valid">真实输出已生成</span>
            <h3>{{ outputScheduleFile }}</h3>
            <p>{{ generatedOutputDescription }}</p>
            <dl>
              <div><dt>输入模板</dt><dd>{{ previewBatch?.input_template }}</dd></div>
              <div><dt>输出模板</dt><dd>{{ previewBatch?.target_template }}</dd></div>
              <div><dt>订单明细</dt><dd>{{ orderSummary.total }} 条 · 17个统一字段</dd></div>
              <div><dt>文件名</dt><dd>按本批次生成独立文件 · 不覆盖原排期</dd></div>
            </dl>
          </div>
          <div class="generated-output-card__actions">
            <button type="button" class="button button--ghost" @click="downloadGeneratedSchedule"><Download aria-hidden="true" /> 再次下载排期</button>
            <button type="button" class="button button--primary" @click="navigate('schedule')">下一步：查看厂区总排期 <ArrowRight aria-hidden="true" /></button>
          </div>
        </article>
      </section>

      <section v-else-if="activeSection === 'ledger'" key="ledger" class="order-view" data-testid="order-ledger">
        <CustomerOrderLedger :factory-id="factoryId" :factory-name="factoryName" @import="navigate('import')" />
      </section>

      <section v-else-if="activeSection === 'exceptions'" key="exceptions" class="order-view" data-testid="order-exceptions">
        <header class="view-heading">
          <div>
            <span class="eyebrow"><AlertTriangle aria-hidden="true" /> 交付风险工作区</span>
            <h2>异常与提醒中心</h2>
            <p>此页暂不从订单台账推导风险或生产状态；请在预览中处理本次文件校验，并在台账中维护已保存订单。</p>
          </div>
          <span class="prototype-badge">预览辅助页 · 非订单台账</span>
        </header>

        <div class="exception-kpis">
          <article><span>全部待关注</span><strong>{{ exceptionSummary.total }}</strong><small>当前活动订单</small></article>
          <article class="critical"><span>紧急</span><strong>{{ exceptionSummary.critical }}</strong><small>需要优先处理</small></article>
          <article class="data"><span>预览阻断</span><strong>{{ exceptionSummary.dataBlocked }}</strong><small>只在当前未保存预览中计算</small></article>
        </div>

        <div class="exception-toolbar">
          <label class="exception-search"><Search aria-hidden="true" /><input v-model="exceptionSearch" type="search" placeholder="搜索PO、合同、客户或产品"></label>
          <label><span>优先级</span><select v-model="selectedExceptionSeverity"><option value="all">全部优先级</option><option value="critical">紧急</option><option value="warning">警告</option><option value="attention">关注</option></select></label>
          <label><span>异常分类</span><select v-model="selectedExceptionCategory"><option value="all">全部分类</option><option value="订单数据">订单数据</option></select></label>
          <button type="button" class="button button--ghost" @click="notify('当前没有可独立计算的台账风险；请查看订单台账。')"><Database aria-hidden="true" /> 查看台账规则</button>
        </div>

        <div class="exception-layout">
          <article class="exception-list-card">
            <header class="data-grid-card__toolbar">
              <div><CircleAlert aria-hidden="true" /><span>待关注事项</span><small>显示 {{ filteredScheduleExceptions.length }} / {{ scheduleExceptions.length }} 项</small></div>
            </header>
            <div class="exception-list">
              <article
                v-for="exception in filteredScheduleExceptions"
                :key="exception.id"
                :class="['exception-item', `exception-item--${exception.severity}`, { acknowledged: acknowledgedExceptionIds.includes(exception.id) }]"
              >
                <div class="exception-item__severity">
                  <span :class="['exception-severity', `exception-severity--${exception.severity}`]">{{ exception.severityLabel }}</span>
                  <small>{{ exception.category }}</small>
                </div>
                <div class="exception-item__main">
                  <div class="exception-item__title">
                    <h3>{{ exception.title }}</h3>
                    <span>{{ exception.row.customerCountry }}</span>
                  </div>
                  <p>{{ exception.detail }}</p>
                  <dl>
                    <div><dt>P/O#</dt><dd>{{ exception.row.poNo }}</dd></div>
                    <div><dt>Contract No.</dt><dd>{{ exception.row.contractNo }}</dd></div>
                    <div><dt>产品</dt><dd>{{ exception.row.productNo }} · {{ exception.row.productNameZh }}</dd></div>
                    <div><dt>走货期</dt><dd>{{ exception.row.requestedShipDate || '待补充' }}</dd></div>
                  </dl>
                  <div class="exception-item__recommendation"><Sparkles aria-hidden="true" /><span><b>建议动作</b>{{ exception.suggestedAction }}</span></div>
                </div>
                <div class="exception-item__actions">
                  <button type="button" class="trace-button" @click="traceRow = exception.row">查看订单</button>
                  <button type="button" class="exception-action" @click="handleExceptionAction(exception)">前往处理</button>
                  <button type="button" class="exception-acknowledge" @click="toggleExceptionAcknowledged(exception.id)">
                    {{ acknowledgedExceptionIds.includes(exception.id) ? '取消关注标记' : '标记已关注' }}
                  </button>
                </div>
              </article>
              <div v-if="filteredScheduleExceptions.length === 0" class="empty-exception">
                <CheckCircle2 aria-hidden="true" />
                <b>当前没有独立风险数据</b>
                <span>订单台账不包含生产、物料、库存或排产数据；预览校验请回到“预览与确认”。</span>
              </div>
            </div>
          </article>

          <aside class="exception-aside">
            <article class="panel-card exception-rule-card">
              <header class="panel-card__head"><div><h3>当前提醒规则</h3><p>公司级草案，不属于客户模板</p></div></header>
              <ol>
                <li><b>预览</b><span>文件校验问题在“预览与确认”处理</span></li>
                <li><b>台账</b><span>已保存订单、发送及走货在台账维护</span></li>
              </ol>
            </article>

            <article class="panel-card exception-boundary-card">
              <header class="panel-card__head"><div><h3>处理边界</h3><p>提醒中心不成为第二套业务台账</p></div></header>
              <ul>
                <li><ShieldCheck aria-hidden="true" /><span>订单字段回到“预览与确认”处理</span></li>
                <li><ShieldCheck aria-hidden="true" /><span>已保存订单回到“订单数据台账”处理</span></li>
                <li><ShieldCheck aria-hidden="true" /><span>生产、物料、库存和排产不在本订单中心维护</span></li>
              </ul>
            </article>
          </aside>
        </div>
      </section>

      <section v-else-if="activeSection === 'customer-schedule'" key="customer-schedule" class="order-view" data-testid="order-customer-schedule">
        <CustomerOrderSchedule :factory-id="factoryId" :factory-name="factoryName" @import="navigate('import')" />
      </section>

      <section v-else-if="activeSection === 'schedule'" key="schedule-live" class="order-view" data-testid="order-schedule">
        <CustomerOrderLedger :factory-id="factoryId" :factory-name="factoryName" initial-view="all" display-mode="schedule" @import="navigate('import')" />
      </section>

      <section v-else-if="false" key="schedule" class="order-view" data-testid="order-schedule-static">
        <header class="view-heading">
          <div>
            <span class="eyebrow"><CalendarClock aria-hidden="true" /> 订单交付数据视图</span>
            <h2>{{ factoryName }}总排期</h2>
            <p>基于已进入客户订单中心的统一订单数据，按客户和走货月份查看PO、临期风险以及生产模块回传的未完成情况。</p>
          </div>
          <span class="prototype-badge">系统数据视图 · 不输出总排期Excel</span>
        </header>

        <div class="schedule-definition-card">
          <Database aria-hidden="true" />
          <div>
            <b>这张总排期是系统数据，不是第三张Excel</b>
            <span>订单数据台账保存全部标准订单及版本；厂区总排期只投影交付相关数据，供生产部门读取。生产进度由下游模块维护，这里只读汇总。</span>
          </div>
        </div>

        <div class="schedule-toolbar-card">
          <label>
            <span>走货月份</span>
            <select v-model="selectedScheduleMonth">
              <option value="all">全部月份</option>
              <option v-for="month in scheduleMonths" :key="month" :value="month">{{ month.replace('-', '年') }}月</option>
            </select>
          </label>
          <label>
            <span>客户</span>
            <select v-model="selectedScheduleCustomer">
              <option value="all">全部客户</option>
              <option v-for="customer in scheduleCustomers" :key="customer" :value="customer">{{ customer }}</option>
            </select>
          </label>
          <label>
            <span>生产反馈</span>
            <select v-model="selectedProductionStatus">
              <option value="all">全部状态</option>
              <option value="incomplete">未完成</option>
              <option value="complete">已完成</option>
            </select>
          </label>
          <button type="button" class="button button--ghost" @click="notify('静态演示：已刷新订单交付与生产反馈摘要。')">
            <RefreshCw aria-hidden="true" /> 刷新数据
          </button>
        </div>

        <div class="factory-schedule-kpis">
          <article><span>待走货PO</span><strong>{{ scheduleSummary.poCount }}</strong><small>当前筛选范围</small></article>
          <article><span>订单数量</span><strong>{{ scheduleSummary.totalQuantity.toLocaleString() }}</strong><small>PCS</small></article>
          <article class="risk"><span>临期 / 逾期</span><strong>{{ scheduleSummary.riskCount }}</strong><small>需跟客关注</small></article>
          <article class="production"><span>生产未完成</span><strong>{{ scheduleSummary.productionIncomplete }}</strong><small>下游只读反馈</small></article>
          <article class="publishable"><span>可供生产调用</span><strong>{{ scheduleSummary.publishableCount }}</strong><small>当前有效确认版本</small></article>
        </div>

        <section class="month-schedule-section">
          <header>
            <div><h3>按月走货概览</h3><p>快速查看每个月涉及多少客户、PO和数量</p></div>
            <span>统计日期：2026-07-27 · 静态样例</span>
          </header>
          <div class="month-card-grid">
            <button
              v-for="month in monthlyScheduleSummary"
              :key="month.month"
              type="button"
              :class="{ active: selectedScheduleMonth === month.month }"
              @click="selectedScheduleMonth = selectedScheduleMonth === month.month ? 'all' : month.month"
            >
              <span>{{ month.month.replace('-', '年') }}月</span>
              <strong>{{ month.poCount }} 个PO</strong>
              <small>{{ month.customerCount }} 个客户 · {{ month.quantity.toLocaleString() }} PCS</small>
              <em v-if="month.riskCount > 0">{{ month.riskCount }} 项临期/逾期</em>
              <em v-else>走货计划正常</em>
            </button>
          </div>
        </section>

        <section class="customer-month-section">
          <header>
            <div><h3>客户月度PO汇总</h3><p>回答“这个月每个客户有哪些PO要走货”</p></div>
            <span>随上方月份和客户筛选同步</span>
          </header>
          <div class="customer-summary-grid">
            <article v-for="summary in customerMonthlySummary" :key="summary.customer">
              <div class="customer-summary-grid__head">
                <span>{{ summary.customer }}</span>
                <button type="button" @click="selectedScheduleCustomer = summary.customer">只看该客户</button>
              </div>
              <strong>{{ summary.poCount }} 个PO · {{ summary.quantity.toLocaleString() }} PCS</strong>
              <dl>
                <div><dt>最近走货</dt><dd>{{ summary.nearestShipDate }}</dd></div>
                <div><dt>临期/逾期</dt><dd :class="{ danger: summary.riskCount > 0 }">{{ summary.riskCount }}</dd></div>
                <div><dt>生产未完成</dt><dd :class="{ warning: summary.productionIncomplete > 0 }">{{ summary.productionIncomplete }}</dd></div>
                <div><dt>可供下游</dt><dd>{{ summary.publishableCount }}</dd></div>
              </dl>
            </article>
            <div v-if="customerMonthlySummary.length === 0" class="empty-customer-summary">当前筛选范围没有客户PO</div>
          </div>
        </section>

        <div class="factory-schedule-layout">
          <article class="factory-schedule-table-card">
            <header class="data-grid-card__toolbar">
              <div><CalendarClock aria-hidden="true" /><span>客户PO交付排期</span><small>显示 {{ filteredFactoryScheduleRows.length }} 条</small></div>
              <button type="button" class="button button--ghost" @click="navigate('ledger')"><Database aria-hidden="true" /> 查看订单数据台账</button>
            </header>
            <div class="table-scroll table-scroll--schedule">
              <table class="factory-schedule-table">
                <thead>
                  <tr>
                    <th>走货状态</th><th>客要求走货期</th><th>客名/国家</th><th>P/O#</th><th>Contract No.</th>
                    <th>产品编号</th><th>中文名称</th><th>数量</th><th>订单数据状态</th><th>生产调用</th><th>需求版本</th><th>生产状态</th>
                    <th>完成进度</th><th>未完成说明</th><th>最后反馈</th><th>详情</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in filteredFactoryScheduleRows" :key="`schedule-${row.id}`">
                    <td><span :class="['delivery-chip', `delivery-chip--${row.deliveryStatus}`]">{{ row.deliveryStatusLabel }}</span></td>
                    <td class="mono strong">{{ row.requestedShipDate || '待补充' }}</td>
                    <td>{{ row.customerCountry }}</td>
                    <td class="mono">{{ row.poNo }}</td>
                    <td class="mono">{{ row.contractNo }}</td>
                    <td class="mono">{{ row.productNo }}</td>
                    <td>{{ row.productNameZh }}</td>
                    <td class="number">{{ row.quantity }}</td>
                    <td><span :class="['status-chip', `status-chip--${row.status}`]">{{ row.status === 'valid' ? '已确认' : row.statusLabel }}</span></td>
                    <td><span :class="['downstream-chip', { 'downstream-chip--blocked': !row.publishableToDownstream }]">{{ row.publishableToDownstream ? '可调用' : '不可调用' }}</span></td>
                    <td class="mono">{{ row.demandVersion }}</td>
                    <td><span :class="['production-chip', { 'production-chip--pending': row.productionProgress < 100 }]">{{ row.productionStatus }}</span></td>
                    <td>
                      <div class="production-progress">
                        <span><i :style="{ width: `${row.productionProgress}%` }" /></span>
                        <b>{{ row.productionProgress }}%</b>
                      </div>
                    </td>
                    <td>{{ row.productionDepartment }} · {{ row.productionIssue }}</td>
                    <td class="mono">{{ row.feedbackAt }}</td>
                    <td><button type="button" class="trace-button" @click="traceRow = row">查看订单</button></td>
                  </tr>
                  <tr v-if="filteredFactoryScheduleRows.length === 0"><td colspan="16" class="empty-schedule">当前筛选条件下暂无走货PO</td></tr>
                </tbody>
              </table>
            </div>
          </article>

          <aside class="factory-schedule-aside">
            <article class="panel-card data-feed-card">
              <header class="panel-card__head"><div><h3>供生产部门调用</h3><p>未来接口数据范围</p></div></header>
              <ul>
                <li><CheckCircle2 aria-hidden="true" /><span><b>稳定标识与版本</b>订单行ID、交付需求ID、订单版本</span></li>
                <li><CheckCircle2 aria-hidden="true" /><span><b>17个基础字段</b>PO、货号、数量、包装及交付日期</span></li>
                <li><CheckCircle2 aria-hidden="true" /><span><b>排期派生状态</b>走货月份、剩余天数、临期与逾期</span></li>
                <li><CircleAlert aria-hidden="true" /><span><b>接口尚未接入</b>当前只展示前端静态数据合同</span></li>
              </ul>
            </article>

            <article class="panel-card feedback-boundary-card">
              <header class="panel-card__head"><div><h3>生产反馈边界</h3><p>下游权威、中心只读</p></div></header>
              <p>啤机、喷油和装配模块以后分别回传任务状态、完成数量、未完成原因和反馈时间。</p>
              <div><ShieldCheck aria-hidden="true" /><span>客户订单中心不能修改生产任务或完成数量，只负责汇总展示和交付风险提醒。</span></div>
            </article>
          </aside>
        </div>

        <div class="downstream-note">
          <ShieldCheck aria-hidden="true" />
          <div><b>厂区总排期是订单需求数据层，不是生产排产模块</b><span>生产部门读取已确认订单需求并在自己的模块排产；这里以后只接收只读进度反馈，用于提示业务哪些订单临期但生产尚未完成。</span></div>
        </div>
      </section>
    </Transition>

    <Transition name="drawer">
      <div
        v-if="blockingResolutionOpen"
        class="blocker-resolution-backdrop"
        @click.self="blockingResolutionOpen = false"
      >
        <section
          class="blocker-resolution-dialog"
          data-testid="blocker-resolution-dialog"
          role="dialog"
          aria-modal="true"
          aria-labelledby="blocker-resolution-title"
        >
          <header>
            <div>
              <span>客户订单人工处理</span>
              <h3 id="blocker-resolution-title">补录缺失内容或人工确认放行</h3>
              <p>共 {{ blockingResolutionItems.length }} 项；人工值写入新排期，客户原始 PO 不会被修改。</p>
            </div>
            <button type="button" aria-label="关闭人工处理窗口" @click="blockingResolutionOpen = false"><X aria-hidden="true" /></button>
          </header>

          <div class="blocker-resolution-dialog__body">
            <div class="blocker-resolution-progress">
              <span :class="{ done: blockingIssueDetails.length === 0 }">
                {{ blockingIssueDetails.length === 0 ? '全部处理完成' : `仍有 ${blockingIssueDetails.length} 类问题待处理` }}
              </span>
              <small>可批量确认允许放行的项目；必须补录的业务字段仍需逐行填写</small>
              <button
                v-if="bulkSkippableIssueKeys.length"
                type="button"
                class="button button--ghost blocker-resolution-select-all"
                data-testid="select-all-skippable-issues"
                @click="toggleAllSkippableIssues"
              >
                {{ allSkippableIssuesSelected ? '取消全选可放行项' : `全选可放行项（${bulkSkippableIssueKeys.length}）` }}
              </button>
            </div>

            <div class="blocker-resolution-list">
              <article
                v-for="item in blockingResolutionItems"
                :key="`${item.row.id}-${item.issue.skip_key}`"
                :class="{ resolved: isIssueResolved(item.issue) }"
              >
                <div class="blocker-resolution-item__heading">
                  <div>
                    <b>{{ item.row.source_po_file_name }}</b>
                    <span>PO {{ item.row.po_no || '—' }} · 产品 {{ item.row.product_no || '—' }}</span>
                  </div>
                  <em v-if="isIssueManuallyOverridden(item.issue)">已人工补录</em>
                  <em v-else-if="isIssueResolved(item.issue)">已确认放行</em>
                  <em v-else>{{ item.issue.severity === 'warning' ? '可选更正' : '待处理' }}</em>
                </div>
                <p class="blocker-resolution-item__message">{{ item.issue.message }}</p>

                <label v-if="item.issue.can_edit" class="manual-override-field manual-override-field--dialog">
                  <span><b>人工补录 {{ item.issue.edit_label }}</b><small>{{ item.issue.severity === 'warning' ? '不填写则使用PO原值；填写后写入新排期' : '填写正确内容后，本项立即解除阻断并写入新排期' }}</small></span>
                  <input
                    :type="item.issue.edit_input_type || 'text'"
                    :step="item.issue.edit_input_type === 'number' ? 'any' : undefined"
                    :value="manualOverrideValues[item.issue.skip_key] || ''"
                    :placeholder="`填写${item.issue.edit_label || '正确内容'}`"
                    @input="updateManualOverride(item.issue, $event)"
                  >
                </label>

                <label v-if="item.issue.can_skip && item.issue.severity !== 'warning'" class="skip-issue-option skip-issue-option--dialog">
                  <input
                    type="checkbox"
                    :checked="isIssueSkipped(item.issue)"
                    :disabled="isIssueManuallyOverridden(item.issue)"
                    @change="toggleIssueSkip(item.issue)"
                  >
                  <span><b>{{ isTestDuplicateIssue(item.issue) ? '确认重复订单' : '确认缺失并放行' }}</b>{{ item.issue.skip_label }}</span>
                </label>
                <p v-if="!item.issue.can_edit && !item.issue.can_skip" class="required-issue"><b>当前不能放行</b>{{ item.issue.message }}</p>
              </article>
            </div>

            <label v-if="skippedIssueCount > 0" class="blocker-resolution-reason">
              <span>人工处理原因（必填，4–500 字）</span>
              <textarea
                v-model="confirmationReason"
                maxlength="500"
                rows="3"
                placeholder="例如：客户 PDF 无法修改，已与客户核对装箱数量并人工补录"
              />
              <small :class="{ invalid: confirmationReasonMissing }">{{ confirmationReason.trim().length }} / 500</small>
            </label>
          </div>

          <footer>
            <button type="button" class="button button--ghost" @click="blockingResolutionOpen = false">关闭，稍后处理</button>
            <button
              type="button"
              class="button button--primary"
              :disabled="blockingIssueDetails.length > 0 || confirmationReasonMissing"
              @click="finishBlockingResolution"
            >
              {{ blockingIssueDetails.length > 0 ? '请先处理全部阻断' : confirmationReasonMissing ? '请填写处理原因' : '完成处理并返回预览' }}
            </button>
          </footer>
        </section>
      </div>
    </Transition>

    <Transition name="toast">
      <div v-if="notice" class="order-toast" role="status">
        <CheckCircle2 aria-hidden="true" />
        {{ notice }}
        <button type="button" aria-label="关闭提示" @click="notice = ''"><X aria-hidden="true" /></button>
      </div>
    </Transition>

    <Transition name="drawer">
      <div v-if="traceRow" class="trace-backdrop" @click.self="traceRow = null">
        <aside class="trace-drawer" data-testid="trace-drawer">
          <header>
            <div><span>字段级追溯</span><h3>{{ traceRow.poNo }} / {{ traceRow.productNo }}</h3></div>
            <button type="button" aria-label="关闭追溯面板" @click="traceRow = null"><X aria-hidden="true" /></button>
          </header>
          <div class="trace-status">
            <span :class="['status-chip', `status-chip--${traceRow.status}`]">{{ traceRow.statusLabel }}</span>
            <p>{{ traceRow.issue }}</p>
          </div>
          <dl>
            <div><dt>原始文件</dt><dd>{{ traceRow.sourcePoFileName || selectedPoFile }}</dd></div>
            <div><dt>来源位置</dt><dd>{{ traceRow.source }}</dd></div>
            <div><dt>输入模板</dt><dd>{{ traceRow.inputTemplate }}</dd></div>
            <div><dt>目标模板</dt><dd>{{ traceRow.targetTemplate }}</dd></div>
            <div><dt>ITEM去向</dt><dd>{{ traceRow.itemSheetName }}</dd></div>
            <div><dt>订单版本</dt><dd>V1 · 静态样例</dd></div>
          </dl>
          <section>
            <h4>17字段逐一映射</h4>
            <p v-for="field in traceFields" :key="field.label">
              <b>{{ field.label }}</b><span>{{ field.value }}</span><small>{{ field.source }}</small>
            </p>
          </section>
          <section class="trace-production-feedback">
            <h4>生产反馈摘要（静态示例）</h4>
            <p><b>反馈部门</b><span>{{ traceRow.productionDepartment }}</span><small>权威来源：对应生产模块</small></p>
            <p><b>生产状态</b><span>{{ traceRow.productionStatus }}</span><small>客户订单中心只读</small></p>
            <p><b>完成进度</b><span>{{ traceRow.productionProgress }}%</span><small>以后由生产模块回传完成数量计算</small></p>
            <p><b>未完成说明</b><span>{{ traceRow.productionIssue }}</span><small>{{ traceRow.feedbackAt }}</small></p>
          </section>
          <button type="button" class="button button--primary drawer-action" @click="notify('静态演示：追溯记录下载将在后续实现。')"><Download aria-hidden="true" /> 下载追溯记录</button>
        </aside>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.order-workspace {
  width: min(100%, 1640px);
  margin: 0 auto;
  color: var(--order-text, #191b23);
}

.order-view {
  min-width: 0;
}

.view-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 24px;
}

.view-heading--compact {
  margin-bottom: 16px;
}

.view-heading h2,
.view-heading p,
.panel-card h3,
.panel-card p {
  margin: 0;
}

.view-heading h2 {
  margin-top: 7px;
  color: #191b23;
  font-size: clamp(25px, 2.5vw, 34px);
  font-weight: 900;
  letter-spacing: -.035em;
}

.view-heading p {
  max-width: 850px;
  margin-top: 7px;
  color: #596070;
  font-size: 13px;
  line-height: 1.65;
}

.eyebrow,
.prototype-badge {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: #003d9b;
  font-size: 11px;
  font-weight: 900;
  letter-spacing: .08em;
}

.eyebrow svg,
.prototype-badge svg {
  width: 15px;
  height: 15px;
}

.prototype-badge {
  border: 1px solid #b2c5ff;
  border-radius: 6px;
  background: #dae2ff;
  padding: 7px 10px;
  color: #0040a2;
}

.view-heading__actions {
  display: flex;
  flex: 0 0 auto;
  gap: 8px;
}

.button {
  display: inline-flex;
  min-height: 38px;
  align-items: center;
  justify-content: center;
  gap: 7px;
  border: 1px solid transparent;
  border-radius: 6px;
  padding: 0 14px;
  font-size: 12px;
  font-weight: 900;
  transition: transform 160ms ease, background-color 160ms ease, border-color 160ms ease, box-shadow 160ms ease;
}

.button:not(:disabled):hover {
  transform: translateY(-1px);
}

.button:disabled {
  cursor: not-allowed;
  opacity: .46;
  box-shadow: none;
}

.button svg {
  width: 16px;
  height: 16px;
}

.button--primary {
  background: #003d9b;
  color: #fff;
  box-shadow: 0 6px 15px rgb(0 61 155 / 15%);
}

.button--primary:hover {
  background: #0052cc;
}

.button--secondary {
  background: #006c47;
  color: #fff;
}

.button--ghost {
  border-color: #c3c6d6;
  background: #fff;
  color: #434654;
}

.button--ghost:hover {
  border-color: #003d9b;
  color: #003d9b;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 18px;
}

.metric-card {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 14px;
  border: 1px solid #cfd2df;
  border-radius: 8px;
  background: #fff;
  padding: 17px;
  box-shadow: 0 7px 18px rgb(38 42 55 / 4%);
}

.metric-card--error {
  border-left: 4px solid #ba1a1a;
}

.metric-card__icon {
  display: grid;
  width: 44px;
  height: 44px;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 7px;
}

.metric-card__icon svg {
  width: 22px;
  height: 22px;
}

.metric-card__icon--blue { background: #dae2ff; color: #003d9b; }
.metric-card__icon--amber { background: #ffddb3; color: #7d5200; }
.metric-card__icon--green { background: #d5f9e6; color: #006c47; }
.metric-card__icon--red { background: #ffdad6; color: #ba1a1a; }

.metric-card p,
.metric-card strong,
.metric-card small {
  display: block;
  margin: 0;
}

.metric-card p {
  color: #596070;
  font-size: 12px;
  font-weight: 700;
}

.metric-card strong {
  margin-top: 2px;
  color: #191b23;
  font-size: 26px;
  line-height: 1.1;
}

.metric-card small {
  margin-top: 5px;
  overflow: hidden;
  color: #737685;
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dashboard-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 330px;
  gap: 16px;
}

.flow-column,
.dashboard-aside,
.import-main,
.import-aside,
.schedule-aside {
  display: grid;
  align-content: start;
  gap: 14px;
}

.flow-card,
.panel-card,
.ledger-card,
.data-grid-card,
.merge-table-card {
  border: 1px solid #cfd2df;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 7px 18px rgb(38 42 55 / 4%);
}

.flow-card {
  padding: 20px;
}

.flow-card--primary {
  border-top: 3px solid #003d9b;
}

.flow-card__head,
.flow-card__title,
.panel-card__head,
.data-grid-card__toolbar,
.ledger-toolbar,
.table-footer,
.load-card header,
.schedule-files article,
.output-card ul,
.trace-drawer header {
  display: flex;
  align-items: center;
}

.flow-card__head,
.panel-card__head,
.data-grid-card__toolbar,
.table-footer,
.load-card header,
.trace-drawer header {
  justify-content: space-between;
}

.flow-number {
  color: #737685;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 10px;
  font-weight: 900;
  letter-spacing: .09em;
}

.status-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid transparent;
  border-radius: 999px;
  padding: 3px 8px;
  font-size: 10px;
  font-weight: 900;
  white-space: nowrap;
}

.status-chip--active,
.status-chip--valid { border-color: #71dba6; background: #d5f9e6; color: #005235; }
.status-chip--warning { border-color: #ffb950; background: #ffddb3; color: #624000; }
.status-chip--blocked { border-color: #ffb4ab; background: #ffdad6; color: #93000a; }

.preview-row-status {
  min-width: 210px;
  white-space: normal;
}

.preview-row-issue-summary {
  display: grid;
  gap: 4px;
  margin: 8px 0 0;
  padding-left: 16px;
  color: #6b3d00;
  font-size: 12px;
  line-height: 1.4;
}

.row-blocked .preview-row-issue-summary {
  color: #8c1d18;
}

.flow-card__title {
  align-items: flex-start;
  gap: 14px;
  margin-top: 16px;
}

.flow-card__icon {
  display: grid;
  width: 46px;
  height: 46px;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 8px;
  background: #dae2ff;
  color: #003d9b;
}

.flow-card__icon--green {
  background: #d5f9e6;
  color: #006c47;
}

.flow-card__icon svg {
  width: 23px;
  height: 23px;
}

.flow-card h3,
.flow-card p {
  margin: 0;
}

.flow-card h3 {
  font-size: 17px;
  font-weight: 900;
}

.flow-card p {
  margin-top: 4px;
  color: #596070;
  font-size: 12px;
  line-height: 1.6;
}

.flow-steps {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin: 18px 0;
  padding: 0;
  list-style: none;
}

.flow-steps li {
  position: relative;
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
  color: #434654;
  font-size: 10px;
  font-weight: 700;
}

.flow-steps li:not(:last-child)::after {
  position: absolute;
  top: 50%;
  right: 8px;
  width: 14px;
  height: 1px;
  background: #c3c6d6;
  content: "";
}

.flow-steps b {
  display: grid;
  width: 23px;
  height: 23px;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 50%;
  background: #e7e7f2;
  color: #003d9b;
  font-size: 10px;
}

.flow-enter {
  display: inline-flex;
  min-height: 36px;
  align-items: center;
  gap: 7px;
  border: 0;
  background: transparent;
  color: #003d9b;
  font-size: 12px;
  font-weight: 900;
}

.flow-enter:hover {
  text-decoration: underline;
}

.flow-enter svg {
  width: 15px;
  height: 15px;
}

.panel-card {
  padding: 16px;
}

.panel-card__head {
  gap: 12px;
  margin-bottom: 14px;
}

.panel-card__head h3 {
  font-size: 14px;
  font-weight: 900;
}

.panel-card__head p {
  margin-top: 2px;
  color: #737685;
  font-size: 10px;
}

.quick-action-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.quick-action-grid button {
  display: grid;
  min-height: 82px;
  place-items: center;
  gap: 4px;
  border: 1px solid #d7d9e3;
  border-radius: 7px;
  background: #faf8ff;
  padding: 10px;
  color: #434654;
  font-size: 10px;
  font-weight: 800;
}

.quick-action-grid button:hover {
  border-color: #b2c5ff;
  background: #f3f3fd;
  color: #003d9b;
}

.quick-action-grid svg {
  width: 21px;
  height: 21px;
}

.scope-card {
  display: flex;
  align-items: flex-start;
  gap: 11px;
  border-radius: 8px;
  background: #2e3038;
  padding: 16px;
  color: #f0f0fb;
}

.scope-card > svg {
  width: 21px;
  height: 21px;
  flex: 0 0 auto;
  color: #8df7c1;
}

.scope-card h3,
.scope-card p {
  margin: 0;
}

.scope-card h3 {
  font-size: 12px;
  font-weight: 900;
}

.scope-card p {
  margin-top: 5px;
  opacity: .76;
  font-size: 10px;
  line-height: 1.55;
}

.activity-card {
  margin-top: 16px;
  padding: 0;
  overflow: hidden;
}

.activity-card .panel-card__head {
  margin: 0;
  padding: 15px 18px;
}

.text-button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 0;
  background: transparent;
  color: #003d9b;
  font-size: 10px;
  font-weight: 900;
}

.text-button svg {
  width: 14px;
  height: 14px;
}

.table-scroll {
  width: 100%;
  overflow: auto;
  scrollbar-color: #c3c6d6 transparent;
  scrollbar-width: thin;
}

table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
}

th {
  background: #f3f3fd;
  color: #737685;
  font-size: 10px;
  font-weight: 900;
  letter-spacing: .04em;
  white-space: nowrap;
}

th,
td {
  border-bottom: 1px solid #e0e1e9;
  padding: 10px 12px;
  vertical-align: middle;
}

td {
  color: #343742;
  font-size: 11px;
}

tbody tr:hover td {
  background: #f8f8ff;
}

.activity-table {
  min-width: 760px;
}

.activity-table td:first-child,
.mono {
  font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, Consolas, monospace;
}

.wizard-steps {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  margin: 0 0 20px;
  border: 1px solid #cfd2df;
  border-radius: 8px;
  background: #fff;
  padding: 14px 20px;
  list-style: none;
}

.customer-selector {
  display: grid;
  grid-template-columns: minmax(260px, .8fr) minmax(420px, 1.2fr);
  align-items: center;
  gap: 18px;
  margin-bottom: 14px;
  border: 1px solid #b8c7e5;
  border-radius: 10px;
  background: linear-gradient(135deg, #f8faff, #f2fff9);
  padding: 15px 17px;
}

.customer-selector > header {
  display: flex;
  align-items: flex-start;
  gap: 11px;
}

.customer-selector > header > span {
  display: grid;
  width: 38px;
  height: 38px;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 9px;
  background: #e1e9ff;
  color: #003d9b;
}

.customer-selector > header svg {
  width: 20px;
  height: 20px;
}

.customer-selector h3,
.customer-selector p {
  margin: 0;
}

.customer-selector h3 {
  font-size: 15px;
}

.customer-selector p {
  margin-top: 3px;
  color: #596070;
  line-height: 1.5;
}

.customer-selector__options {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.customer-choice {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  min-width: 0;
  border: 1px solid #cfd5e4;
  border-radius: 9px;
  background: #fff;
  padding: 11px 12px;
  color: #343742;
  text-align: left;
  transition:
    transform var(--order-motion-fast) var(--order-motion-ease),
    border-color var(--order-motion-fast) ease,
    background-color var(--order-motion-fast) ease,
    box-shadow var(--order-motion-normal) var(--order-motion-ease);
}

.customer-choice:hover {
  border-color: #7e9bd2;
  box-shadow: 0 9px 22px rgb(31 55 102 / 10%);
  transform: translateY(-1px);
}

.customer-choice.active {
  border-color: #007a58;
  background: #edfff7;
  box-shadow: inset 0 0 0 1px rgb(0 122 88 / 18%);
}

.customer-choice > span {
  display: grid;
  width: 32px;
  height: 32px;
  place-items: center;
  border-radius: 50%;
  background: #edf0ff;
  color: #003d9b;
}

.customer-choice.active > span {
  background: #d5f9e6;
  color: #006c47;
}

.customer-choice svg {
  width: 17px;
  height: 17px;
}

.customer-choice b,
.customer-choice small {
  display: block;
}

.customer-choice b {
  font-size: 14px;
}

.customer-choice small {
  margin-top: 2px;
  overflow: hidden;
  color: #737685;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.customer-choice em {
  border-radius: 999px;
  background: #edf0ff;
  padding: 4px 7px;
  color: #0040a2;
  font-style: normal;
  font-weight: 900;
  white-space: nowrap;
}

.customer-choice.active em {
  background: #d5f9e6;
  color: #005235;
}

.customer-selector__empty {
  border-radius: 7px;
  background: #fff0c7;
  padding: 11px;
  color: #674c00 !important;
}

.wizard-steps li {
  position: relative;
  display: grid;
  justify-items: center;
  gap: 7px;
  color: #737685;
  font-size: 10px;
  font-weight: 800;
}

.wizard-steps li:not(:last-child)::after {
  position: absolute;
  top: 17px;
  left: calc(50% + 30px);
  width: calc(100% - 60px);
  height: 1px;
  background: #c3c6d6;
  content: "";
}

.wizard-steps b {
  display: grid;
  width: 34px;
  height: 34px;
  place-items: center;
  border: 1px solid #c3c6d6;
  border-radius: 50%;
  background: #e7e7f2;
  font-size: 11px;
}

.wizard-steps li.active {
  color: #003d9b;
}

.wizard-steps li.active b {
  border-color: #003d9b;
  background: #003d9b;
  color: #fff;
}

.wizard-steps li.done {
  color: #006c47;
}

.wizard-steps li.done b {
  border-color: #71dba6;
  background: #d5f9e6;
  color: #006c47;
}

.import-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 310px;
  gap: 16px;
}

.import-main,
.import-aside {
  min-width: 0;
}

.upload-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.upload-card {
  display: flex;
  min-width: 0;
  min-height: 294px;
  overflow: hidden;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border: 2px dashed #c3c6d6;
  border-radius: 8px;
  background: #fff;
  padding: 22px;
  text-align: center;
  transition: border-color 160ms ease, background-color 160ms ease;
}

.upload-card:hover {
  border-color: #003d9b;
  background: #f8f9ff;
}

.upload-card--dragging {
  border-color: #003d9b;
  background: #eef3ff;
  box-shadow: inset 0 0 0 2px rgb(0 61 155 / 9%);
}

.upload-card--schedule.upload-card--dragging {
  border-color: #007a50;
  background: #effcf6;
  box-shadow: inset 0 0 0 2px rgb(0 122 80 / 9%);
}

.upload-card--disabled {
  cursor: not-allowed;
  opacity: .62;
}

.upload-card--disabled:hover {
  box-shadow: none;
  transform: none;
}

.upload-card--dragging .upload-card__icon {
  transform: scale(1.06);
}

.upload-card__type {
  align-self: flex-start;
  color: #737685;
  font-size: 9px;
  font-weight: 900;
  letter-spacing: .07em;
  text-transform: uppercase;
}

.upload-card__icon {
  display: grid;
  width: 62px;
  height: 62px;
  margin: 12px 0;
  place-items: center;
  border-radius: 50%;
  background: #dae2ff;
  color: #003d9b;
  transition: transform 160ms ease;
}

.upload-card__icon--green {
  background: #d5f9e6;
  color: #006c47;
}

.upload-card__icon svg {
  width: 29px;
  height: 29px;
}

.upload-card h3,
.upload-card p,
.upload-card strong {
  margin: 0;
}

.upload-card h3 {
  font-size: 15px;
  font-weight: 900;
}

.upload-card p {
  margin-top: 5px;
  color: #737685;
  font-size: 10px;
  line-height: 1.5;
}

.upload-card strong {
  display: block;
  width: 100%;
  max-width: 100%;
  margin: 14px 0;
  overflow: hidden;
  color: #434654;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  clip-path: inset(50%);
  white-space: nowrap;
}

.parse-banner {
  display: flex;
  align-items: center;
  gap: 12px;
  border: 1px solid #71dba6;
  border-radius: 8px;
  background: #e6fbf0;
  padding: 13px 14px;
}

.parse-banner > span {
  display: grid;
  width: 34px;
  height: 34px;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 6px;
  background: #8df7c1;
  color: #005235;
}

.parse-banner svg {
  width: 17px;
  height: 17px;
}

.parse-banner div {
  min-width: 0;
  flex: 1;
}

.parse-banner h3,
.parse-banner p {
  margin: 0;
}

.parse-banner h3 {
  color: #005235;
  font-size: 12px;
  font-weight: 900;
}

.parse-banner p {
  margin-top: 3px;
  color: #006c47;
  font-size: 9px;
  line-height: 1.45;
}

.persistent-parse-alert {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  border: 1px solid #ef8f85;
  border-radius: 8px;
  background: #fff1ef;
  padding: 13px 14px;
  color: #7d2018;
}

.persistent-parse-alert--preview {
  margin-bottom: 14px;
}

.persistent-parse-alert__icon {
  display: grid;
  width: 34px;
  height: 34px;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 6px;
  background: #ffd8d3;
}

.persistent-parse-alert__icon svg {
  width: 18px;
  height: 18px;
}

.persistent-parse-alert__content {
  min-width: 0;
  flex: 1;
}

.persistent-parse-alert h3,
.persistent-parse-alert p {
  margin: 0;
}

.persistent-parse-alert h3 {
  font-size: 12px;
  font-weight: 900;
}

.persistent-parse-alert p,
.persistent-parse-alert li {
  font-size: 10px;
  line-height: 1.55;
}

.persistent-parse-alert p {
  margin-top: 4px;
  overflow-wrap: anywhere;
}

.confirmation-reason-card {
  display: grid;
  grid-template-columns: minmax(220px, 0.8fr) minmax(320px, 1.2fr);
  gap: 18px;
  margin-bottom: 14px;
  border: 1px solid #d8b55f;
  border-radius: 8px;
  background: #fffaf0;
  padding: 14px;
  color: #5f4507;
}

.confirmation-reason-card strong,
.confirmation-reason-card p {
  margin: 0;
}

.confirmation-reason-card strong {
  font-size: 12px;
  font-weight: 900;
}

.confirmation-reason-card p {
  margin-top: 5px;
  font-size: 10px;
  line-height: 1.55;
}

.confirmation-reason-card label {
  display: grid;
  gap: 5px;
  font-size: 10px;
  font-weight: 800;
}

.confirmation-reason-card textarea {
  width: 100%;
  min-height: 58px;
  resize: vertical;
  border: 1px solid #c9b06f;
  border-radius: 6px;
  background: #fff;
  padding: 8px 10px;
  color: #232323;
  font: inherit;
  line-height: 1.45;
}

.confirmation-reason-card small {
  justify-self: end;
  color: #806920;
  font-weight: 700;
}

.confirmation-reason-card small.invalid {
  color: #b42318;
}

.persistent-parse-alert ul {
  display: grid;
  max-height: 180px;
  gap: 6px;
  margin: 8px 0 0;
  padding: 0;
  overflow-y: auto;
  list-style: none;
}

.persistent-parse-alert li {
  display: grid;
  grid-template-columns: minmax(140px, 220px) 1fr;
  gap: 8px;
}

.persistent-parse-alert li b,
.persistent-parse-alert li span {
  overflow-wrap: anywhere;
}

.received-date-field {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  color: #005235;
  font-size: 10px;
}

.received-date-field input {
  height: 30px;
  border: 1px solid #71dba6;
  border-radius: 5px;
  background: #fff;
  padding: 0 8px;
  color: #24312d;
  font: inherit;
  outline: none;
}

.received-date-field input:focus {
  border-color: #006c47;
  box-shadow: 0 0 0 3px rgb(0 108 71 / 10%);
}

.reconciliation-card {
  display: grid;
  gap: 12px;
  margin: 14px 0;
  border: 1px solid #b2c5ff;
  border-radius: 8px;
  background: #f6f8ff;
  padding: 14px;
}

.reconciliation-card__toggle,
.reconciliation-card__body,
.reconciliation-card__body label {
  display: grid;
  gap: 7px;
}

.reconciliation-card__toggle {
  grid-template-columns: auto 1fr;
  align-items: start;
  color: #1d315a;
  font-size: 12px;
}

.reconciliation-card__toggle b,
.reconciliation-card__toggle small {
  display: block;
}

.reconciliation-card__toggle small,
.reconciliation-card__selected {
  margin-top: 3px;
  color: #596070;
  font-size: 11px;
  line-height: 1.5;
}

.reconciliation-card__body {
  padding-left: 23px;
}

.reconciliation-card__search,
.reconciliation-card__pager {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  gap: 8px;
}

.reconciliation-card__search label {
  flex: 1 1 240px;
}

.reconciliation-card__scope {
  margin: 0;
  color: #596070;
  font-size: 11px;
  line-height: 1.5;
}

.reconciliation-card__body label {
  color: #434654;
  font-size: 12px;
  font-weight: 800;
}

.reconciliation-card__body select,
.reconciliation-card__body textarea {
  border: 1px solid #b2c5ff;
  border-radius: 6px;
  background: #fff;
  padding: 8px;
  color: #191b23;
  font: inherit;
}

.import-queue-table {
  min-width: 820px;
}

.import-queue-table td:first-child {
  display: flex;
  align-items: center;
  gap: 7px;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
}

.import-queue-table td svg {
  width: 15px;
  height: 15px;
  color: #737685;
}

.guide-card ul,
.output-card ul {
  margin: 0;
  padding: 0;
  list-style: none;
}

.guide-card ul {
  display: grid;
  gap: 13px;
}

.guide-card li {
  display: flex;
  align-items: flex-start;
  gap: 9px;
}

.guide-card li > svg {
  width: 18px;
  height: 18px;
  flex: 0 0 auto;
  color: #006c47;
}

.guide-card li > svg.warning {
  color: #7d5200;
}

.guide-card b,
.guide-card span {
  display: block;
}

.guide-card b {
  font-size: 11px;
}

.guide-card span {
  margin-top: 2px;
  color: #737685;
  font-size: 9px;
}

.mapping-card {
  position: relative;
  overflow: hidden;
  border-radius: 8px;
  background: #2e3038;
  padding: 19px;
  color: #f0f0fb;
}

.mapping-card > svg {
  width: 23px;
  height: 23px;
  color: #b2c5ff;
}

.mapping-card h3,
.mapping-card p {
  margin: 0;
}

.mapping-card h3 {
  margin-top: 10px;
  font-size: 14px;
  font-weight: 900;
}

.mapping-card p {
  margin-top: 6px;
  opacity: .75;
  font-size: 10px;
  line-height: 1.55;
}

.mapping-card button {
  width: 100%;
  min-height: 34px;
  margin-top: 14px;
  border: 0;
  border-radius: 5px;
  background: #0052cc;
  color: #fff;
  font-size: 10px;
  font-weight: 900;
}

.mapping-card button:disabled {
  cursor: not-allowed;
  opacity: .45;
}

.load-card header h3,
.load-card header strong {
  margin: 0;
  font-size: 11px;
}

.load-card header strong {
  color: #006c47;
}

.progress-track {
  height: 6px;
  margin-top: 10px;
  overflow: hidden;
  border-radius: 999px;
  background: #e7e7f2;
}

.progress-track span {
  display: block;
  width: 100%;
  height: 100%;
  background: #006c47;
}

.load-card > p {
  margin-top: 8px;
  color: #737685;
  font-size: 9px;
}

.summary-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}

.summary-strip article {
  border: 1px solid #cfd2df;
  border-left: 4px solid #737685;
  border-radius: 7px;
  background: #fff;
  padding: 11px 13px;
}

.summary-strip article.valid { border-left-color: #006c47; }
.summary-strip article.warning { border-left-color: #7d5200; }
.summary-strip article.blocked { border-left-color: #ba1a1a; }

.summary-strip span,
.summary-strip strong,
.summary-strip small {
  display: block;
}

.summary-strip span {
  color: #737685;
  font-size: 9px;
  font-weight: 900;
  text-transform: uppercase;
}

.summary-strip strong {
  margin-top: 3px;
  font-size: 22px;
}

.summary-strip small {
  margin-top: 2px;
  color: #737685;
  font-size: 9px;
}

.preview-layout {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  gap: 12px;
}

.preview-next-step {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 14px;
  margin-bottom: 12px;
  padding: 13px 15px;
  border: 1px solid #8fc8ff;
  border-radius: 10px;
  background: linear-gradient(135deg, #eef7ff 0%, #f8fbff 100%);
  box-shadow: 0 8px 18px rgb(0 76 165 / 8%);
}

.preview-next-step > span {
  display: grid;
  width: 38px;
  height: 38px;
  place-items: center;
  border-radius: 10px;
  background: #dcecff;
  color: #004ca5;
}

.preview-next-step > span svg {
  width: 20px;
  height: 20px;
}

.preview-next-step strong,
.preview-next-step p {
  margin: 0;
}

.preview-next-step strong {
  color: #12345b;
  font-size: 14px;
}

.preview-next-step p {
  margin-top: 3px;
  color: #52667e;
  font-size: 11px;
}

.generated-output-card {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 16px;
  margin-top: 14px;
  border: 1px solid #71dba6;
  border-radius: 8px;
  background: linear-gradient(135deg, #f3fff8 0%, #fff 72%);
  padding: 16px;
  box-shadow: 0 10px 28px rgb(0 106 71 / 8%);
}

.generated-output-card__icon {
  display: grid;
  width: 48px;
  height: 48px;
  place-items: center;
  border-radius: 10px;
  background: #c4eed8;
  color: #006c47;
}

.generated-output-card__icon svg {
  width: 24px;
  height: 24px;
}

.generated-output-card h3,
.generated-output-card p,
.generated-output-card dl,
.generated-output-card dt,
.generated-output-card dd {
  margin: 0;
}

.generated-output-card h3 {
  margin-top: 7px;
  overflow-wrap: anywhere;
  color: #173329;
  font-size: 15px;
}

.generated-output-card p {
  margin-top: 4px;
  color: #50635b;
  font-size: 10px;
}

.generated-output-card dl {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 18px;
  margin-top: 10px;
}

.generated-output-card dl div {
  display: flex;
  gap: 5px;
  font-size: 9px;
}

.generated-output-card dt {
  color: #6b7d75;
  font-weight: 800;
}

.generated-output-card dd {
  color: #243a31;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
}

.generated-output-card__actions {
  display: grid;
  gap: 8px;
}

.filter-panel {
  align-self: start;
  border: 1px solid #cfd2df;
  border-radius: 8px;
  background: #f3f3fd;
  padding: 14px;
}

.filter-panel h3 {
  display: flex;
  align-items: center;
  gap: 7px;
  margin: 0 0 13px;
  color: #737685;
  font-size: 10px;
  font-weight: 900;
  letter-spacing: .07em;
  text-transform: uppercase;
}

.filter-panel h3 svg {
  width: 14px;
  height: 14px;
}

.filter-panel > label:not(.filter-field) {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 0;
  color: #434654;
  font-size: 10px;
  font-weight: 700;
}

.filter-panel input[type="checkbox"],
.check-option input {
  accent-color: #003d9b;
}

.filter-divider {
  height: 1px;
  margin: 12px 0;
  background: #c3c6d6;
}

.filter-field,
.rule-card > label:not(.check-option) {
  display: grid;
  gap: 5px;
  margin-top: 11px;
  color: #596070;
  font-size: 9px;
  font-weight: 900;
}

.filter-field select,
.rule-card select,
.ledger-toolbar select {
  width: 100%;
  height: 34px;
  border: 1px solid #c3c6d6;
  border-radius: 5px;
  background: #fff;
  padding: 0 8px;
  color: #343742;
  font-size: 10px;
}

.logic-note {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  margin-top: 15px;
  border: 1px solid #b2c5ff;
  border-radius: 6px;
  background: #e8edff;
  padding: 10px;
  color: #0040a2;
}

.logic-note > svg {
  width: 15px;
  height: 15px;
  flex: 0 0 auto;
}

.logic-note b,
.logic-note p {
  margin: 0;
}

.logic-note b {
  font-size: 9px;
}

.logic-note p {
  margin-top: 3px;
  font-size: 8px;
  line-height: 1.45;
}

.data-grid-card,
.merge-table-card,
.ledger-card {
  min-width: 0;
  overflow: hidden;
}

.data-grid-card__toolbar {
  min-height: 54px;
  gap: 12px;
  border-bottom: 1px solid #d7d9e3;
  padding: 10px 13px;
}

.data-grid-card__toolbar > div {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.data-grid-card__toolbar svg {
  width: 17px;
  height: 17px;
  flex: 0 0 auto;
  color: #003d9b;
}

.data-grid-card__toolbar span {
  font-size: 11px;
  font-weight: 900;
}

.data-grid-card__toolbar small {
  color: #737685;
  font-size: 9px;
}

.inline-search,
.ledger-search {
  display: flex;
  height: 34px;
  align-items: center;
  gap: 7px;
  border: 1px solid #c3c6d6;
  border-radius: 5px;
  background: #f8f8ff;
  padding: 0 9px;
  color: #737685;
}

.inline-search {
  width: 230px;
  flex: 0 0 auto;
}

.inline-search svg,
.ledger-search svg {
  width: 14px;
  height: 14px;
}

.inline-search input,
.ledger-search input {
  min-width: 0;
  flex: 1;
  border: 0;
  background: transparent;
  font-size: 10px;
  outline: none;
}

.table-scroll--preview {
  max-height: 520px;
}

.unified-table {
  min-width: 2440px;
}

.unified-table th,
.unified-table td {
  padding: 8px 10px;
}

.unified-table thead {
  position: sticky;
  top: 0;
  z-index: 4;
}

.unified-table .sticky-left {
  position: sticky;
  left: 0;
  z-index: 3;
  background: #f3f3fd;
}

.unified-table td.sticky-left {
  background: #fff;
}

.unified-table .resolution-column {
  min-width: 230px;
  max-width: 280px;
  white-space: normal;
}

.issue-resolution-list {
  display: grid;
  gap: 6px;
}

.issue-resolution-item {
  display: grid;
  gap: 6px;
}

.issue-resolution-message {
  margin: 0;
  color: #93000a;
  font-size: 10px;
  font-weight: 700;
  line-height: 1.45;
}

.manual-override-field {
  display: grid;
  gap: 6px;
  border: 1px solid #9bc5b2;
  border-radius: 6px;
  background: #effbf5;
  padding: 8px;
  color: #005235;
}

.manual-override-field span,
.manual-override-field b,
.manual-override-field small {
  display: block;
}

.manual-override-field b {
  font-size: 9px;
}

.manual-override-field small {
  margin-top: 2px;
  color: #3f6b59;
  font-size: 8px;
  font-weight: 600;
}

.manual-override-field input {
  width: 100%;
  min-width: 0;
  border: 1px solid #91b6a5;
  border-radius: 5px;
  background: #fff;
  padding: 7px 8px;
  color: #18392c;
  font-size: 10px;
  outline: none;
}

.manual-override-field input:focus {
  border-color: #007a58;
  box-shadow: 0 0 0 2px rgb(0 122 88 / 12%);
}

.skip-issue-option,
.required-issue {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  margin: 0;
  border-radius: 6px;
  padding: 6px 7px;
  font-size: 9px;
  line-height: 1.45;
}

.skip-issue-option {
  cursor: pointer;
  border: 1px solid #f1c36b;
  background: #fff8e8;
  color: #624000;
}

.skip-issue-option input {
  margin-top: 2px;
  accent-color: #006c4c;
}

.skip-issue-option:has(input:disabled) {
  cursor: default;
  opacity: .58;
}

.skip-issue-option span,
.required-issue {
  min-width: 0;
}

.skip-issue-option b,
.required-issue b {
  display: block;
  margin-bottom: 1px;
  font-size: 8px;
  letter-spacing: .04em;
}

.required-issue {
  border: 1px solid #ffb4ab;
  background: #ffebe8;
  color: #93000a;
}

.no-resolution-needed {
  color: #8a93a5;
}

.unified-table .row-warning td {
  background: #fffdf6;
}

.unified-table .row-blocked td {
  background: #fff8f7;
}

.unified-table .row-warning td.sticky-left {
  background: #fffdf6;
}

.unified-table .row-blocked td.sticky-left {
  background: #fff8f7;
}

.unified-table .row-parent-product td {
  border-top: 2px solid #8dcbb7;
  background: #edf9f4;
  font-weight: 800;
}

.unified-table .row-parent-product td.sticky-left {
  background: #edf9f4;
}

.product-hierarchy-cell {
  min-width: 150px;
  white-space: nowrap;
}

.product-hierarchy-cell--child {
  padding-left: 25px !important;
}

.product-role-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-right: 7px;
  border: 1px solid;
  border-radius: 999px;
  padding: 2px 6px;
  font-family: inherit;
  font-size: 9px;
  font-weight: 900;
  line-height: 1.2;
}

.product-role-badge--parent {
  border-color: #70c7aa;
  background: #d8f5e9;
  color: #005238;
}

.product-role-badge--child {
  border-color: #bdc8de;
  background: #f2f5fb;
  color: #44536f;
}

.number {
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.cell-issue {
  color: #93000a !important;
  font-weight: 900;
}

.trace-button,
.version-button {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  padding: 4px 6px;
  color: #003d9b;
  font-size: 9px;
  font-weight: 900;
  white-space: nowrap;
}

.trace-button:hover,
.version-button:hover {
  background: #dae2ff;
}

.version-button svg {
  width: 12px;
  height: 12px;
}

.table-footer {
  min-height: 42px;
  gap: 12px;
  border-top: 1px solid #d7d9e3;
  padding: 8px 12px;
  color: #737685;
  font-size: 9px;
}

.table-footer > span {
  display: flex;
  align-items: center;
  gap: 6px;
}

.table-footer svg {
  width: 13px;
  height: 13px;
}

.table-footer > div {
  display: flex;
  align-items: center;
  gap: 4px;
}

.table-footer button,
.table-footer b {
  display: grid;
  width: 25px;
  height: 25px;
  place-items: center;
  border: 0;
  border-radius: 4px;
}

.table-footer button {
  background: transparent;
  color: #737685;
}

.table-footer b {
  background: #003d9b;
  color: #fff;
}

.ledger-kpis {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 14px;
}

.ledger-kpis article {
  display: flex;
  align-items: center;
  gap: 13px;
  border: 1px solid #cfd2df;
  border-radius: 8px;
  background: #fff;
  padding: 15px;
}

.ledger-kpis article > span {
  display: grid;
  width: 42px;
  height: 42px;
  place-items: center;
  border-radius: 7px;
  background: #dae2ff;
  color: #003d9b;
}

.ledger-kpis article > span.amber { background: #ffddb3; color: #7d5200; }
.ledger-kpis article > span.green { background: #d5f9e6; color: #006c47; }

.ledger-kpis svg {
  width: 21px;
  height: 21px;
}

.ledger-kpis p,
.ledger-kpis strong,
.ledger-kpis small {
  display: block;
  margin: 0;
}

.ledger-kpis p {
  color: #596070;
  font-size: 10px;
}

.ledger-kpis strong {
  margin-top: 2px;
  font-size: 21px;
}

.ledger-kpis small {
  margin-top: 2px;
  color: #737685;
  font-size: 9px;
}

.ledger-toolbar {
  gap: 8px;
  min-height: 58px;
  border-bottom: 1px solid #d7d9e3;
  padding: 10px 13px;
}

.ledger-search {
  width: min(410px, 42%);
}

.ledger-toolbar select {
  width: 150px;
}

.icon-square {
  display: grid;
  width: 34px;
  height: 34px;
  place-items: center;
  border: 1px solid #c3c6d6;
  border-radius: 5px;
  background: #fff;
  color: #434654;
}

.icon-square svg {
  width: 15px;
  height: 15px;
}

.ledger-count {
  margin-left: auto;
  color: #737685;
  font-size: 9px;
}

.table-scroll--ledger {
  max-height: 600px;
}

.ledger-table {
  min-width: 1840px;
}

.strong {
  color: #003d9b;
  font-weight: 900;
}

.schedule-files {
  display: grid;
  grid-template-columns: 1fr 44px 1fr;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
}

.schedule-files article {
  position: relative;
  gap: 13px;
  border: 1px solid #cfd2df;
  border-radius: 8px;
  background: #fff;
  padding: 16px;
}

.schedule-files article > svg {
  width: 28px;
  height: 28px;
  flex: 0 0 auto;
  color: #003d9b;
}

.schedule-files article > div {
  min-width: 0;
  flex: 1;
}

.schedule-files h3,
.schedule-files p,
.schedule-files small {
  display: block;
  margin: 0;
}

.schedule-files h3 {
  font-size: 12px;
  font-weight: 900;
}

.schedule-files p {
  margin-top: 3px;
  overflow: hidden;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.schedule-files small {
  margin-top: 4px;
  color: #737685;
  font-size: 9px;
}

.file-role {
  position: absolute;
  top: -8px;
  left: 12px;
  border: 1px solid #b2c5ff;
  border-radius: 4px;
  background: #dae2ff;
  padding: 2px 6px;
  color: #0040a2;
  font-size: 8px;
  font-weight: 900;
}

.merge-arrow {
  display: grid;
  width: 34px;
  height: 34px;
  place-items: center;
  border-radius: 50%;
  background: #003d9b;
  color: #fff;
}

.merge-arrow svg {
  width: 17px;
  height: 17px;
}

.merge-summary-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin-bottom: 14px;
}

.merge-summary-grid article {
  border: 1px solid #cfd2df;
  border-left: 4px solid #737685;
  border-radius: 7px;
  background: #fff;
  padding: 11px 13px;
}

.merge-summary-grid article.new { border-left-color: #003d9b; }
.merge-summary-grid article.update { border-left-color: #006c47; }
.merge-summary-grid article.conflict { border-left-color: #ba1a1a; }

.merge-summary-grid span,
.merge-summary-grid strong,
.merge-summary-grid small {
  display: block;
}

.merge-summary-grid span { color: #737685; font-size: 9px; font-weight: 900; }
.merge-summary-grid strong { margin-top: 2px; font-size: 22px; }
.merge-summary-grid small { margin-top: 2px; color: #737685; font-size: 8px; }

.schedule-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  gap: 14px;
}

.merge-table {
  min-width: 1120px;
}

.merge-status {
  display: inline-flex;
  min-width: 48px;
  justify-content: center;
  border-radius: 4px;
  padding: 4px 6px;
  font-size: 9px;
  font-weight: 900;
}

.merge-status--new { background: #dae2ff; color: #0040a2; }
.merge-status--update { background: #d5f9e6; color: #005235; }
.merge-status--conflict { background: #ffdad6; color: #93000a; }
.merge-status--unchanged { background: #e7e7f2; color: #596070; }

.rule-card > label:not(.check-option) {
  margin-top: 10px;
}

.check-option {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-top: 11px;
  color: #434654;
  font-size: 9px;
  font-weight: 700;
}

.output-card {
  border-radius: 8px;
  background: #2e3038;
  padding: 18px;
  color: #f0f0fb;
}

.output-card > svg {
  width: 25px;
  height: 25px;
  color: #8df7c1;
}

.output-card h3,
.output-card p,
.output-card small {
  margin: 0;
}

.output-card h3 {
  margin-top: 10px;
  font-size: 14px;
  font-weight: 900;
}

.output-card p {
  margin-top: 5px;
  overflow-wrap: anywhere;
  opacity: .76;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 9px;
}

.output-card ul {
  gap: 12px;
  margin: 13px 0;
}

.output-card li {
  font-size: 9px;
}

.output-card button {
  display: flex;
  width: 100%;
  min-height: 38px;
  align-items: center;
  justify-content: center;
  gap: 7px;
  border: 0;
  border-radius: 5px;
  background: #0052cc;
  color: #fff;
  font-size: 10px;
  font-weight: 900;
}

.output-card button:disabled {
  background: #596070;
  color: #c3c6d6;
  cursor: not-allowed;
}

.output-card button svg {
  width: 15px;
  height: 15px;
}

.output-card small {
  display: block;
  margin-top: 7px;
  color: #ffb4ab;
  font-size: 8px;
  text-align: center;
}

.schedule-source-alert,
.draft-rule-label {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  border-radius: 7px;
  padding: 12px 14px;
}

.schedule-source-alert {
  margin-bottom: 14px;
  border: 1px solid #ffb95f;
  background: #fff4e4;
  color: #784b00;
}

.draft-rule-label {
  margin-bottom: 12px;
  border: 1px solid #b2c5ff;
  background: #edf0ff;
  color: #0040a2;
}

.schedule-source-alert > svg,
.draft-rule-label > svg {
  width: 18px;
  height: 18px;
  flex: 0 0 auto;
}

.schedule-source-alert b,
.schedule-source-alert span,
.draft-rule-label b,
.draft-rule-label span {
  display: block;
}

.schedule-source-alert b,
.draft-rule-label b {
  margin-bottom: 3px;
  font-size: 10px;
}

.schedule-source-alert span,
.draft-rule-label span {
  font-size: 9px;
  line-height: 1.55;
}

.exception-kpis {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 9px;
  margin-bottom: 12px;
}

.exception-kpis article {
  border: 1px solid #cfd2df;
  border-left: 4px solid #737685;
  border-radius: 7px;
  background: #fff;
  padding: 11px;
}

.exception-kpis article.critical {
  border-left-color: #ba1a1a;
}

.exception-kpis article.delivery {
  border-left-color: #d87900;
}

.exception-kpis article.data {
  border-left-color: #7f1d1d;
}

.exception-kpis article.production {
  border-left-color: #006c47;
}

.exception-kpis span,
.exception-kpis strong,
.exception-kpis small {
  display: block;
}

.exception-kpis span {
  color: #737685;
  font-size: 8px;
  font-weight: 900;
}

.exception-kpis strong {
  margin-top: 2px;
  font-size: 21px;
}

.exception-kpis small {
  margin-top: 2px;
  color: #737685;
  font-size: 8px;
}

.exception-toolbar {
  display: grid;
  grid-template-columns: minmax(240px, 1fr) 180px 180px auto;
  align-items: end;
  gap: 9px;
  margin-bottom: 12px;
  border: 1px solid #cfd2df;
  border-radius: 8px;
  background: #fff;
  padding: 11px;
}

.exception-toolbar > label:not(.exception-search) {
  display: grid;
  gap: 5px;
}

.exception-toolbar > label > span {
  color: #596070;
  font-size: 9px;
  font-weight: 900;
}

.exception-toolbar select {
  width: 100%;
  height: 36px;
  border: 1px solid #c3c6d6;
  border-radius: 5px;
  background: #fff;
  padding: 0 9px;
  color: #343742;
  font-size: 10px;
}

.exception-search {
  display: flex;
  height: 36px;
  align-items: center;
  gap: 7px;
  border: 1px solid #c3c6d6;
  border-radius: 5px;
  padding: 0 10px;
}

.exception-search svg {
  width: 15px;
  height: 15px;
  color: #737685;
}

.exception-search input {
  width: 100%;
  border: 0;
  outline: 0;
  background: transparent;
  color: #343742;
  font-size: 10px;
}

.exception-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 290px;
  gap: 12px;
}

.exception-list-card {
  min-width: 0;
  overflow: hidden;
  border: 1px solid #cfd2df;
  border-radius: 8px;
  background: #fff;
}

.exception-list {
  display: grid;
}

.exception-item {
  display: grid;
  grid-template-columns: 70px minmax(0, 1fr) 110px;
  gap: 12px;
  border-bottom: 1px solid #e0e1e9;
  border-left: 4px solid #737685;
  padding: 14px;
  transition: opacity 160ms ease, background-color 160ms ease;
}

.exception-item:last-child {
  border-bottom: 0;
}

.exception-item--critical {
  border-left-color: #ba1a1a;
}

.exception-item--warning {
  border-left-color: #d87900;
}

.exception-item--attention {
  border-left-color: #006c47;
}

.exception-item.acknowledged {
  background: #f6f6fb;
  opacity: .7;
}

.exception-item__severity {
  display: grid;
  align-content: start;
  justify-items: start;
  gap: 6px;
}

.exception-severity {
  display: inline-flex;
  border-radius: 4px;
  padding: 4px 7px;
  font-size: 9px;
  font-weight: 900;
}

.exception-severity--critical {
  background: #ffdad6;
  color: #93000a;
}

.exception-severity--warning {
  background: #fff0c7;
  color: #674c00;
}

.exception-severity--attention {
  background: #d5f9e6;
  color: #005235;
}

.exception-item__severity small {
  color: #737685;
  font-size: 8px;
}

.exception-item__title {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.exception-item__title h3,
.exception-item__main > p {
  margin: 0;
}

.exception-item__title h3 {
  color: #252832;
  font-size: 12px;
}

.exception-item__title > span {
  color: #596070;
  font-size: 9px;
  white-space: nowrap;
}

.exception-item__main > p {
  margin-top: 5px;
  color: #596070;
  font-size: 9px;
  line-height: 1.55;
}

.exception-item dl {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 6px;
  margin: 10px 0 0;
}

.exception-item dl div {
  min-width: 0;
  border-radius: 5px;
  background: #f3f3fd;
  padding: 6px;
}

.exception-item dt,
.exception-item dd {
  margin: 0;
  font-size: 8px;
}

.exception-item dt {
  color: #737685;
}

.exception-item dd {
  margin-top: 2px;
  overflow: hidden;
  color: #343742;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.exception-item__recommendation {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  margin-top: 9px;
  border-radius: 5px;
  background: #edf0ff;
  padding: 7px 8px;
  color: #0040a2;
}

.exception-item__recommendation svg {
  width: 13px;
  height: 13px;
  flex: 0 0 auto;
}

.exception-item__recommendation span,
.exception-item__recommendation b {
  font-size: 8px;
}

.exception-item__recommendation b {
  margin-right: 5px;
}

.exception-item__actions {
  display: grid;
  align-content: start;
  gap: 6px;
}

.exception-item__actions button {
  min-height: 30px;
  border-radius: 4px;
  font-size: 9px;
  font-weight: 900;
}

.exception-action {
  border: 0;
  background: #003d9b;
  color: #fff;
}

.exception-acknowledge {
  border: 1px solid #c3c6d6;
  background: #fff;
  color: #596070;
}

.empty-exception {
  display: grid;
  justify-items: center;
  gap: 5px;
  padding: 40px;
  color: #596070;
  text-align: center;
}

.empty-exception svg {
  width: 28px;
  height: 28px;
  color: #006c47;
}

.empty-exception b {
  font-size: 11px;
}

.empty-exception span {
  font-size: 9px;
}

.exception-aside {
  display: grid;
  align-content: start;
  gap: 12px;
}

.exception-rule-card ol,
.exception-boundary-card ul {
  display: grid;
  gap: 9px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.exception-rule-card li {
  display: grid;
  grid-template-columns: 74px 1fr;
  align-items: center;
  gap: 8px;
  border-radius: 5px;
  background: #f3f3fd;
  padding: 8px;
}

.exception-rule-card li b {
  color: #003d9b;
  font-size: 9px;
}

.exception-rule-card li span,
.exception-boundary-card li {
  color: #596070;
  font-size: 8px;
  line-height: 1.45;
}

.exception-boundary-card li {
  display: flex;
  align-items: flex-start;
  gap: 7px;
}

.exception-boundary-card li svg {
  width: 14px;
  height: 14px;
  flex: 0 0 auto;
  color: #006c47;
}

.schedule-definition-card {
  display: flex;
  align-items: flex-start;
  gap: 11px;
  margin-bottom: 14px;
  border: 1px solid #71dba6;
  border-radius: 8px;
  background: #effcf5;
  padding: 13px 15px;
  color: #005235;
}

.schedule-definition-card > svg {
  width: 20px;
  height: 20px;
  flex: 0 0 auto;
}

.schedule-definition-card b,
.schedule-definition-card span {
  display: block;
}

.schedule-definition-card b {
  font-size: 11px;
}

.schedule-definition-card span {
  margin-top: 3px;
  font-size: 9px;
  line-height: 1.55;
}

.schedule-toolbar-card {
  display: grid;
  grid-template-columns: repeat(3, minmax(150px, 1fr)) auto;
  align-items: end;
  gap: 10px;
  margin-bottom: 12px;
  border: 1px solid #cfd2df;
  border-radius: 8px;
  background: #fff;
  padding: 12px;
}

.schedule-toolbar-card label {
  display: grid;
  gap: 5px;
}

.schedule-toolbar-card label > span {
  color: #596070;
  font-size: 9px;
  font-weight: 900;
}

.schedule-toolbar-card select {
  width: 100%;
  height: 36px;
  border: 1px solid #c3c6d6;
  border-radius: 5px;
  background: #fff;
  padding: 0 9px;
  color: #343742;
  font-size: 10px;
}

.factory-schedule-kpis {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}

.factory-schedule-kpis article {
  border: 1px solid #cfd2df;
  border-left: 4px solid #003d9b;
  border-radius: 7px;
  background: #fff;
  padding: 11px 13px;
}

.factory-schedule-kpis article.risk {
  border-left-color: #ba1a1a;
}

.factory-schedule-kpis article.production {
  border-left-color: #d87900;
}

.factory-schedule-kpis article.publishable {
  border-left-color: #006c47;
}

.factory-schedule-kpis span,
.factory-schedule-kpis strong,
.factory-schedule-kpis small {
  display: block;
}

.factory-schedule-kpis span {
  color: #737685;
  font-size: 9px;
  font-weight: 900;
}

.factory-schedule-kpis strong {
  margin-top: 2px;
  font-size: 22px;
}

.factory-schedule-kpis small {
  margin-top: 2px;
  color: #737685;
  font-size: 8px;
}

.month-schedule-section {
  margin-bottom: 12px;
  border: 1px solid #cfd2df;
  border-radius: 8px;
  background: #fff;
  padding: 13px;
}

.month-schedule-section > header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.month-schedule-section h3,
.month-schedule-section p {
  margin: 0;
}

.month-schedule-section h3 {
  font-size: 12px;
}

.month-schedule-section p,
.month-schedule-section > header > span {
  margin-top: 3px;
  color: #737685;
  font-size: 9px;
}

.month-card-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 9px;
}

.month-card-grid button {
  display: grid;
  gap: 4px;
  border: 1px solid #d7d9e3;
  border-radius: 7px;
  background: #f8f8ff;
  padding: 11px;
  color: #343742;
  text-align: left;
  transition: border-color 160ms ease, background-color 160ms ease;
}

.month-card-grid button.active,
.month-card-grid button:hover {
  border-color: #003d9b;
  background: #edf0ff;
}

.month-card-grid span {
  color: #596070;
  font-size: 9px;
  font-weight: 900;
}

.month-card-grid strong {
  font-size: 15px;
}

.month-card-grid small {
  color: #737685;
  font-size: 8px;
}

.month-card-grid em {
  color: #006c47;
  font-size: 8px;
  font-style: normal;
  font-weight: 800;
}

.customer-month-section {
  margin-bottom: 12px;
  border: 1px solid #cfd2df;
  border-radius: 8px;
  background: #fff;
  padding: 13px;
}

.customer-month-section > header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.customer-month-section h3,
.customer-month-section p {
  margin: 0;
}

.customer-month-section h3 {
  font-size: 12px;
}

.customer-month-section p,
.customer-month-section > header > span {
  margin-top: 3px;
  color: #737685;
  font-size: 9px;
}

.customer-summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 9px;
}

.customer-summary-grid > article {
  border: 1px solid #d7d9e3;
  border-radius: 7px;
  background: #f8f8ff;
  padding: 11px;
}

.customer-summary-grid__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.customer-summary-grid__head > span {
  color: #003d9b;
  font-size: 10px;
  font-weight: 900;
}

.customer-summary-grid__head button {
  border: 0;
  background: transparent;
  color: #006c47;
  font-size: 8px;
  font-weight: 900;
}

.customer-summary-grid > article > strong {
  display: block;
  margin-top: 8px;
  font-size: 13px;
}

.customer-summary-grid dl {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 7px;
  margin: 10px 0 0;
}

.customer-summary-grid dl div {
  border-radius: 5px;
  background: #fff;
  padding: 7px;
}

.customer-summary-grid dt,
.customer-summary-grid dd {
  margin: 0;
  font-size: 8px;
}

.customer-summary-grid dt {
  color: #737685;
}

.customer-summary-grid dd {
  margin-top: 2px;
  color: #343742;
  font-weight: 900;
}

.customer-summary-grid dd.danger {
  color: #ba1a1a;
}

.customer-summary-grid dd.warning {
  color: #9b5a00;
}

.empty-customer-summary {
  grid-column: 1 / -1;
  padding: 24px;
  color: #737685;
  font-size: 10px;
  text-align: center;
}

.factory-schedule-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  gap: 12px;
}

.factory-schedule-table-card {
  min-width: 0;
  overflow: hidden;
  border: 1px solid #cfd2df;
  border-radius: 8px;
  background: #fff;
}

.table-scroll--schedule {
  max-height: 560px;
}

.factory-schedule-table {
  min-width: 1840px;
}

.delivery-chip,
.production-chip {
  display: inline-flex;
  border-radius: 4px;
  padding: 4px 7px;
  font-size: 9px;
  font-weight: 900;
  white-space: nowrap;
}

.downstream-chip {
  display: inline-flex;
  border-radius: 4px;
  background: #d5f9e6;
  padding: 4px 7px;
  color: #005235;
  font-size: 9px;
  font-weight: 900;
  white-space: nowrap;
}

.downstream-chip--blocked {
  background: #ffdad6;
  color: #93000a;
}

.delivery-chip--planned {
  background: #dae2ff;
  color: #0040a2;
}

.delivery-chip--upcoming {
  background: #fff0c7;
  color: #674c00;
}

.delivery-chip--due-soon,
.delivery-chip--overdue {
  background: #ffdad6;
  color: #93000a;
}

.production-chip {
  background: #d5f9e6;
  color: #005235;
}

.production-chip--pending {
  background: #fff0c7;
  color: #674c00;
}

.production-progress {
  display: grid;
  grid-template-columns: 82px auto;
  align-items: center;
  gap: 7px;
}

.production-progress > span {
  height: 6px;
  overflow: hidden;
  border-radius: 999px;
  background: #e0e1e9;
}

.production-progress i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: #006c47;
}

.production-progress b {
  font-size: 9px;
}

.empty-schedule {
  padding: 34px;
  color: #737685;
  text-align: center;
}

.factory-schedule-aside {
  display: grid;
  align-content: start;
  gap: 12px;
}

.data-feed-card ul {
  display: grid;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.data-feed-card li {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  color: #434654;
  font-size: 9px;
  line-height: 1.45;
}

.data-feed-card li svg {
  width: 15px;
  height: 15px;
  flex: 0 0 auto;
  color: #006c47;
}

.data-feed-card li:last-child svg {
  color: #d87900;
}

.data-feed-card li b {
  display: block;
  margin-bottom: 2px;
}

.feedback-boundary-card > p {
  color: #596070;
  font-size: 9px;
  line-height: 1.55;
}

.feedback-boundary-card > div {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-top: 11px;
  border-radius: 6px;
  background: #edf0ff;
  padding: 10px;
  color: #0040a2;
  font-size: 9px;
  line-height: 1.5;
}

.feedback-boundary-card > div svg {
  width: 16px;
  height: 16px;
  flex: 0 0 auto;
}

.downstream-note {
  display: flex;
  align-items: center;
  gap: 11px;
  margin-top: 14px;
  border: 1px solid #b2c5ff;
  border-radius: 7px;
  background: #edf0ff;
  padding: 12px 14px;
  color: #0040a2;
}

.downstream-note > svg {
  width: 20px;
  height: 20px;
  flex: 0 0 auto;
}

.downstream-note b,
.downstream-note span {
  display: block;
}

.downstream-note b {
  font-size: 10px;
}

.downstream-note span {
  margin-top: 2px;
  font-size: 9px;
  line-height: 1.45;
}

.order-toast {
  position: fixed;
  right: 22px;
  bottom: 22px;
  z-index: 110;
  display: flex;
  max-width: min(430px, calc(100vw - 32px));
  align-items: center;
  gap: 9px;
  border: 1px solid #71dba6;
  border-radius: 7px;
  background: #fff;
  padding: 11px 13px;
  color: #005235;
  font-size: 11px;
  font-weight: 800;
  box-shadow: 0 15px 35px rgb(25 27 35 / 18%);
}

.order-toast > svg {
  width: 18px;
  height: 18px;
  flex: 0 0 auto;
}

.order-toast button {
  display: grid;
  width: 24px;
  height: 24px;
  margin-left: auto;
  place-items: center;
  border: 0;
  background: transparent;
  color: #596070;
}

.order-toast button svg {
  width: 14px;
  height: 14px;
}

.trace-backdrop {
  position: fixed;
  inset: 0;
  z-index: 100;
  background: rgb(25 27 35 / 24%);
}

.blocker-resolution-backdrop {
  position: fixed;
  inset: 0;
  z-index: 110;
  display: grid;
  place-items: center;
  background: rgb(25 27 35 / 42%);
  padding: 24px;
}

.blocker-resolution-dialog {
  display: grid;
  width: min(860px, 100%);
  max-height: min(820px, calc(100vh - 48px));
  grid-template-rows: auto minmax(0, 1fr) auto;
  overflow: hidden;
  border: 1px solid #d7d9e3;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 24px 70px rgb(25 27 35 / 24%);
}

.blocker-resolution-dialog > header,
.blocker-resolution-dialog > footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 22px;
}

.blocker-resolution-dialog > header {
  border-bottom: 1px solid #e0e1e9;
  background: #fff8f7;
}

.blocker-resolution-dialog > header span,
.blocker-resolution-dialog > header h3,
.blocker-resolution-dialog > header p {
  display: block;
  margin: 0;
}

.blocker-resolution-dialog > header span {
  color: #93000a;
  font-size: 9px;
  font-weight: 900;
  letter-spacing: .08em;
}

.blocker-resolution-dialog > header h3 {
  margin-top: 4px;
  font-size: 18px;
}

.blocker-resolution-dialog > header p {
  margin-top: 5px;
  color: #596070;
  font-size: 10px;
}

.blocker-resolution-dialog > header > button {
  display: grid;
  width: 34px;
  height: 34px;
  flex: 0 0 auto;
  place-items: center;
  border: 0;
  border-radius: 50%;
  background: #f3f3fd;
  color: #596070;
}

.blocker-resolution-dialog > header > button svg {
  width: 16px;
  height: 16px;
}

.blocker-resolution-dialog__body {
  overflow-y: auto;
  padding: 18px 22px;
}

.blocker-resolution-progress {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.blocker-resolution-progress span {
  border-radius: 999px;
  background: #ffdad6;
  padding: 5px 9px;
  color: #93000a;
  font-size: 10px;
  font-weight: 900;
}

.blocker-resolution-progress span.done {
  background: #d5f9e6;
  color: #005235;
}

.blocker-resolution-progress small {
  color: #737685;
  font-size: 9px;
}

.blocker-resolution-select-all {
  flex: 0 0 100%;
  justify-content: center;
  margin-top: 4px;
}

.blocker-resolution-list {
  display: grid;
  gap: 10px;
}

.blocker-resolution-list > article {
  display: grid;
  gap: 10px;
  border: 1px solid #ffb4ab;
  border-left: 4px solid #ba1a1a;
  border-radius: 8px;
  background: #fffafa;
  padding: 13px;
}

.blocker-resolution-list > article.resolved {
  border-color: #9bc5b2;
  border-left-color: #007a58;
  background: #f6fcf9;
}

.blocker-resolution-item__heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.blocker-resolution-item__heading b,
.blocker-resolution-item__heading span {
  display: block;
}

.blocker-resolution-item__heading b {
  font-size: 11px;
}

.blocker-resolution-item__heading span {
  margin-top: 3px;
  color: #596070;
  font-size: 9px;
}

.blocker-resolution-item__heading em {
  flex: 0 0 auto;
  border-radius: 999px;
  background: #ffdad6;
  padding: 4px 7px;
  color: #93000a;
  font-size: 8px;
  font-style: normal;
  font-weight: 900;
}

.blocker-resolution-list > article.resolved .blocker-resolution-item__heading em {
  background: #d5f9e6;
  color: #005235;
}

.blocker-resolution-item__message {
  margin: 0;
  color: #93000a;
  font-size: 10px;
  font-weight: 700;
}

.manual-override-field--dialog,
.skip-issue-option--dialog {
  font-size: 10px;
}

.blocker-resolution-reason {
  display: grid;
  gap: 6px;
  margin-top: 14px;
  border: 1px solid #b2c5ff;
  border-radius: 8px;
  background: #f7f8ff;
  padding: 12px;
}

.blocker-resolution-reason > span {
  color: #003d9b;
  font-size: 10px;
  font-weight: 900;
}

.blocker-resolution-reason textarea {
  width: 100%;
  resize: vertical;
  border: 1px solid #aeb8d7;
  border-radius: 6px;
  background: #fff;
  padding: 9px;
  font: inherit;
  font-size: 10px;
  line-height: 1.5;
  outline: none;
}

.blocker-resolution-reason textarea:focus {
  border-color: #0052cc;
  box-shadow: 0 0 0 2px rgb(0 82 204 / 12%);
}

.blocker-resolution-reason small {
  color: #737685;
  font-size: 8px;
  text-align: right;
}

.blocker-resolution-reason small.invalid {
  color: #ba1a1a;
  font-weight: 900;
}

.blocker-resolution-dialog > footer {
  justify-content: flex-end;
  border-top: 1px solid #e0e1e9;
  background: #f8f8ff;
}

.trace-drawer {
  position: absolute;
  inset: 0 0 0 auto;
  width: min(520px, 100%);
  overflow-y: auto;
  border-left: 1px solid #c3c6d6;
  background: #fff;
  padding: 20px;
  box-shadow: -15px 0 35px rgb(25 27 35 / 12%);
}

.trace-drawer header {
  gap: 12px;
  border-bottom: 1px solid #e0e1e9;
  padding-bottom: 14px;
}

.trace-drawer header span {
  color: #737685;
  font-size: 9px;
  font-weight: 900;
  letter-spacing: .08em;
}

.trace-drawer h3 {
  margin: 3px 0 0;
  font-size: 17px;
}

.trace-drawer header button {
  display: grid;
  width: 32px;
  height: 32px;
  place-items: center;
  border: 0;
  border-radius: 50%;
  background: #f3f3fd;
  color: #596070;
}

.trace-drawer header button svg {
  width: 16px;
  height: 16px;
}

.trace-status {
  margin: 15px 0;
  border-radius: 7px;
  background: #f3f3fd;
  padding: 12px;
}

.trace-status p {
  margin: 8px 0 0;
  color: #434654;
  font-size: 10px;
  line-height: 1.5;
}

.trace-drawer dl {
  display: grid;
  gap: 0;
  margin: 0;
  border: 1px solid #d7d9e3;
  border-radius: 7px;
  overflow: hidden;
}

.trace-drawer dl div {
  display: grid;
  grid-template-columns: 90px 1fr;
  border-bottom: 1px solid #e0e1e9;
}

.trace-drawer dl div:last-child {
  border-bottom: 0;
}

.trace-drawer dt,
.trace-drawer dd {
  margin: 0;
  padding: 9px 10px;
  font-size: 9px;
}

.trace-drawer dt {
  background: #f3f3fd;
  color: #737685;
  font-weight: 900;
}

.trace-drawer dd {
  overflow-wrap: anywhere;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
}

.trace-drawer section {
  margin-top: 16px;
}

.trace-drawer h4 {
  margin: 0 0 8px;
  font-size: 11px;
}

.trace-drawer section p {
  display: grid;
  grid-template-columns: 90px 1fr;
  gap: 4px 8px;
  margin: 0;
  border-bottom: 1px solid #e0e1e9;
  padding: 9px 0;
  font-size: 9px;
}

.trace-drawer section p b {
  color: #596070;
}

.trace-drawer section p span {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
}

.trace-drawer section p small {
  grid-column: 2;
  color: #737685;
  font-size: 8px;
}

.drawer-action {
  width: 100%;
  margin-top: 18px;
}

.order-panel-enter-active,
.order-panel-leave-active,
.toast-enter-active,
.toast-leave-active,
.drawer-enter-active,
.drawer-leave-active {
  transition: opacity 180ms ease, transform 200ms ease;
}

.order-panel-enter-from {
  opacity: 0;
  transform: translateY(6px);
}

.order-panel-leave-to {
  opacity: 0;
  transform: translateY(-3px);
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateY(8px);
}

.drawer-enter-from,
.drawer-leave-to {
  opacity: 0;
}

.drawer-enter-from .trace-drawer,
.drawer-leave-to .trace-drawer {
  transform: translateX(100%);
}

@media (max-width: 1280px) {
  .metric-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .dashboard-grid,
  .import-layout,
  .customer-selector,
  .schedule-layout,
  .factory-schedule-layout,
  .exception-layout {
    grid-template-columns: 1fr;
  }

  .dashboard-aside,
  .import-aside,
  .schedule-aside,
  .factory-schedule-aside,
  .exception-aside {
    grid-template-columns: repeat(3, 1fr);
  }

  .exception-kpis {
    grid-template-columns: repeat(3, 1fr);
  }

  .preview-layout {
    grid-template-columns: 190px minmax(0, 1fr);
  }
}

@media (max-width: 900px) {
  .view-heading {
    align-items: flex-start;
    flex-direction: column;
  }

  .summary-strip,
  .merge-summary-grid,
  .ledger-kpis,
  .factory-schedule-kpis {
    grid-template-columns: repeat(2, 1fr);
  }

  .schedule-toolbar-card,
  .month-card-grid,
  .customer-summary-grid,
  .exception-toolbar {
    grid-template-columns: repeat(2, 1fr);
  }

  .exception-search {
    grid-column: 1 / -1;
  }

  .exception-item {
    grid-template-columns: 64px minmax(0, 1fr);
  }

  .exception-item__actions {
    grid-column: 1 / -1;
    grid-template-columns: repeat(3, 1fr);
  }

  .exception-item dl {
    grid-template-columns: repeat(3, 1fr);
  }

  .preview-layout {
    grid-template-columns: 1fr;
  }

  .generated-output-card {
    grid-template-columns: auto minmax(0, 1fr);
  }

  .preview-next-step {
    grid-template-columns: auto minmax(0, 1fr);
  }

  .preview-next-step .button {
    grid-column: 1 / -1;
  }

  .generated-output-card__actions {
    grid-column: 1 / -1;
    grid-template-columns: 1fr 1fr;
  }

  .filter-panel {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 7px 12px;
  }

  .filter-panel h3,
  .logic-note {
    grid-column: 1 / -1;
  }

  .filter-divider {
    display: none;
  }

  .dashboard-aside,
  .import-aside,
  .schedule-aside,
  .factory-schedule-aside,
  .exception-aside {
    grid-template-columns: 1fr;
  }

  .schedule-files {
    grid-template-columns: 1fr;
  }

  .merge-arrow {
    justify-self: center;
    transform: rotate(90deg);
  }
}

@media (max-width: 680px) {
  .view-heading__actions,
  .parse-banner,
  .persistent-parse-alert {
    width: 100%;
    align-items: stretch;
    flex-direction: column;
  }

  .view-heading__actions .button,
  .parse-banner .button,
  .persistent-parse-alert .button {
    width: 100%;
  }

  .persistent-parse-alert li {
    grid-template-columns: 1fr;
    gap: 2px;
  }

  .metric-grid,
  .summary-strip,
  .merge-summary-grid,
  .ledger-kpis,
  .upload-grid,
  .factory-schedule-kpis,
  .schedule-toolbar-card,
  .month-card-grid,
  .customer-summary-grid,
  .exception-kpis,
  .exception-toolbar {
    grid-template-columns: 1fr;
  }

  .customer-selector__options {
    grid-template-columns: 1fr;
  }

  .exception-search {
    grid-column: auto;
  }

  .exception-item {
    grid-template-columns: 1fr;
  }

  .exception-item__actions {
    grid-column: auto;
    grid-template-columns: 1fr;
  }

  .exception-item dl {
    grid-template-columns: 1fr 1fr;
  }

  .flow-steps {
    grid-template-columns: 1fr 1fr;
    gap: 9px;
  }

  .flow-steps li::after {
    display: none;
  }

  .wizard-steps {
    padding-inline: 7px;
  }

  .wizard-steps li:not(:last-child)::after {
    left: calc(50% + 22px);
    width: calc(100% - 44px);
  }

  .wizard-steps span {
    font-size: 8px;
  }

  .ledger-toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .ledger-search,
  .ledger-toolbar select {
    width: 100%;
  }

  .ledger-count {
    margin-left: 0;
  }

  .filter-panel {
    grid-template-columns: 1fr;
  }

  .filter-panel h3,
  .logic-note {
    grid-column: auto;
  }

  .data-grid-card__toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .generated-output-card {
    grid-template-columns: 1fr;
  }

  .preview-next-step {
    grid-template-columns: 1fr;
  }

  .preview-next-step > span {
    display: none;
  }

  .preview-next-step .button {
    grid-column: auto;
  }

  .generated-output-card__icon {
    display: none;
  }

  .generated-output-card__actions {
    grid-column: auto;
    grid-template-columns: 1fr;
  }

  .inline-search {
    width: 100%;
  }
}

/* Readability and interaction layer aligned with the Internal Quote Desk. */
.order-workspace {
  --order-motion-fast: 160ms;
  --order-motion-normal: 220ms;
  --order-motion-ease: cubic-bezier(.2, .8, .2, 1);

  font-size: 13px;
  line-height: 1.5;
}

.order-workspace :is(p, li, label, dt, dd, th, td, input, select, textarea, span, b, em) {
  font-size: 12px !important;
}

.order-workspace small {
  font-size: 11px !important;
}

.order-workspace :is(button, .button) {
  font-size: 13px !important;
}

.order-workspace h3 {
  font-size: 15px !important;
  line-height: 1.4;
}

.order-workspace h4 {
  font-size: 13px !important;
}

.view-heading h2 {
  font-size: clamp(28px, 2.7vw, 38px);
}

.view-heading p {
  font-size: 14px !important;
}

.upload-card h3 {
  font-size: 18px !important;
}

.upload-card p,
.upload-card strong,
.upload-card__type {
  font-size: 12px !important;
}

.order-workspace :is(
  .metric-card,
  .flow-card,
  .panel-card,
  .upload-card,
  .summary-strip article,
  .ledger-kpis article,
  .merge-summary-grid article,
  .exception-kpis article,
  .factory-schedule-kpis article,
  .schedule-files article,
  .customer-summary-grid > article,
  .month-schedule-section,
  .customer-month-section,
  .generated-output-card,
  .logic-note,
  .mapping-card,
  .output-card,
  .scope-card,
  .schedule-definition-card,
  .downstream-note
) {
  transition:
    transform var(--order-motion-normal) var(--order-motion-ease),
    border-color var(--order-motion-fast) ease,
    background-color var(--order-motion-fast) ease,
    box-shadow var(--order-motion-normal) var(--order-motion-ease);
}

.order-workspace :is(
  .metric-card,
  .flow-card,
  .panel-card,
  .summary-strip article,
  .ledger-kpis article,
  .merge-summary-grid article,
  .exception-kpis article,
  .factory-schedule-kpis article,
  .schedule-files article,
  .customer-summary-grid > article
):hover {
  border-color: #aeb4c8;
  box-shadow: 0 12px 28px rgb(31 38 57 / 10%);
  transform: translateY(-2px);
}

.order-workspace :is(
  .button,
  .flow-enter,
  .text-button,
  .version-button,
  .icon-square,
  .exception-item__actions button,
  .customer-summary-grid__head button,
  .table-footer button,
  .month-card-grid button
) {
  transition:
    transform var(--order-motion-fast) var(--order-motion-ease),
    border-color var(--order-motion-fast) ease,
    background-color var(--order-motion-fast) ease,
    color var(--order-motion-fast) ease,
    box-shadow var(--order-motion-normal) var(--order-motion-ease);
}

.order-workspace :is(
  .button,
  .flow-enter,
  .text-button,
  .version-button,
  .icon-square,
  .exception-item__actions button,
  .customer-summary-grid__head button,
  .table-footer button,
  .month-card-grid button
):not(:disabled):active {
  transform: translateY(0) scale(.975);
}

.order-workspace button svg {
  transition: transform var(--order-motion-fast) var(--order-motion-ease);
}

.order-workspace button:hover svg {
  transform: translateX(2px);
}

.order-workspace tbody tr td {
  transition: background-color var(--order-motion-fast) ease, color var(--order-motion-fast) ease;
}

.upload-card {
  transition:
    transform var(--order-motion-normal) var(--order-motion-ease),
    border-color var(--order-motion-fast) ease,
    background-color var(--order-motion-fast) ease,
    box-shadow var(--order-motion-normal) var(--order-motion-ease);
}

.upload-card:hover {
  box-shadow: 0 12px 28px rgb(31 38 57 / 9%);
  transform: translateY(-2px);
}

.upload-card--dragging {
  animation: order-drop-pulse 720ms ease-in-out infinite alternate;
  transform: translateY(-2px) scale(1.005);
}

.wizard-steps li.active b {
  animation: order-step-pop 220ms var(--order-motion-ease);
}

.order-panel-enter-active .view-heading {
  animation: order-rise-in 260ms var(--order-motion-ease) both;
}

.order-panel-enter-active :is(.wizard-steps, .metric-grid, .summary-strip, .ledger-kpis, .exception-kpis, .factory-schedule-kpis) {
  animation: order-rise-in 300ms 45ms var(--order-motion-ease) both;
}

.order-panel-enter-active :is(.dashboard-grid, .import-layout, .preview-layout, .schedule-layout, .factory-schedule-layout, .exception-layout, .ledger-card) {
  animation: order-rise-in 340ms 90ms var(--order-motion-ease) both;
}

@keyframes order-rise-in {
  from {
    opacity: 0;
    transform: translateY(10px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes order-step-pop {
  50% {
    transform: scale(1.12);
  }
}

@keyframes order-drop-pulse {
  from {
    box-shadow: inset 0 0 0 2px rgb(0 61 155 / 9%), 0 8px 20px rgb(0 61 155 / 8%);
  }

  to {
    box-shadow: inset 0 0 0 3px rgb(0 61 155 / 15%), 0 14px 30px rgb(0 61 155 / 14%);
  }
}

@media (prefers-reduced-motion: reduce) {
  .order-workspace *,
  .order-workspace *::before,
  .order-workspace *::after {
    animation-duration: .01ms !important;
    animation-iteration-count: 1 !important;
    scroll-behavior: auto !important;
    transition-duration: .01ms !important;
  }
}
</style>
