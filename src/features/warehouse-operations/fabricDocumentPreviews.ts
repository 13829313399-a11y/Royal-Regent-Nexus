import type { WarehouseDocumentSpec, WarehousePreviewField } from '@/features/warehouse-foundation/documentPreview'
import type { WarehousePreviewKind } from './documentPreviews'

const text = (id: string, label: string, placeholder?: string): WarehousePreviewField => ({ id, label, placeholder })
const number = (id: string, label: string): WarehousePreviewField => ({ id, label, type: 'number' })
const date = (id: string, label: string): WarehousePreviewField => ({ id, label, type: 'date' })
const note = (id: string, label: string, placeholder?: string): WarehousePreviewField => ({ id, label, type: 'textarea', placeholder })
const choice = (id: string, label: string, options: string[]): WarehousePreviewField => ({ id, label, type: 'select', options })
const unit = (id = 'unit', label = '本次计量单位') => text(id, label, '按原单位填写，如码、千克、卷、Pcs')
const period: WarehousePreviewField = { id: 'period', label: '记账月份', type: 'month' }

function materialGroup(stock = false): WarehouseDocumentSpec['groups'][number] {
  return {
    title: '物料资料',
    description: '布料、辅料和线分别标识；保留原编码与计量单位。',
    fields: [choice('category', '物料分类', ['布料', '辅料', '线']), text('material', '物料编码'), text('legacyCode', '旧物料编码'), text('name', '名称规格'), text('color', '颜色 / 色号'), unit('unit', stock ? '库存单位' : '本次计量单位')],
  }
}

function batches(kind: WarehousePreviewKind): WarehouseDocumentSpec['groups'][number] {
  const issue = kind === 'issue'
  const stock = kind === 'stock'
  return {
    title: stock ? '批次与仓位' : issue ? '实际发出明细' : '批次分仓',
    description: stock
      ? '分别查看每个批次、缸号和卷支所在仓位。这里填写的是预览内容，尚未读取库存。'
      : '每行填写一个批次或卷支在一个仓位的实际数量。拆到多个仓位时可继续加行，单位不自动换算。',
    repeatable: { id: 'batches', itemLabel: stock ? '库存明细' : issue ? '发出明细' : '分仓明细', addLabel: stock ? '添加库存明细' : issue ? '添加发出明细' : '添加分仓明细' },
    fields: [text('batch', '批次编号'), text('dyeLot', '缸号'), text('roll', '卷号 / 包号'), text('location', issue ? '发出仓库 / 仓位' : stock ? '仓库 / 仓位' : '入库仓库 / 仓位'), number('quantity', stock ? '仓位账面数量' : issue ? '该行实发数量' : '该行实收数量'), unit('unit', '明细计量单位'), number('packages', '包装件数'), note('note', '卷支或仓位备注', '如余卷、拆包情况；包装件数与计量数量分别填写')],
  }
}

function allocations(stock = false): WarehouseDocumentSpec['groups'][number] {
  return {
    title: stock ? '用料归属' : '放产用料分配',
    description: stock
      ? '记录库存分给哪些用料需求；没有确认的占用规则时，不据此计算可用数量。'
      : '同一次实发可分配给多个放产任务。这里记录用途归属，不另形成一份出库。',
    repeatable: { id: 'allocations', itemLabel: '用料分配', addLabel: '添加用料分配' },
    fields: [text('demandLine', '需求明细编号', '保留上游明细编号，不用数量拼接'), text('order', '放产单号'), text('contract', '合同号'), text('product', '产品货号'), number('quantity', '本次分配数量'), unit('unit', '分配计量单位')],
  }
}

function prices(): WarehouseDocumentSpec['groups'][number] {
  return {
    title: '价格参考',
    description: '价格和计价单位单独保留；空白、零价和减值依据分别核对，预览不计算金额。',
    fields: [choice('priceStatus', '价格情况', ['待核对', '已有价格依据', '零价依据待确认']), number('price', '参考单价'), text('currency', '币种', '如人民币、港币'), unit('pricingUnit', '计价单位'), note('priceSource', '价格 / 减值依据', '填写采购报价、原单或减值处理依据')],
  }
}

export function fabricDocumentSpec(kind: WarehousePreviewKind): WarehouseDocumentSpec {
  if (kind === 'receipt') return {
    title: '收料单样式',
    description: '核对采购来源、本次实收和批次分仓。',
    groups: [
      { title: '来源与日期', description: '每次到货单独记录，采购订货量不随分批到货重复累加。', fields: [text('source', '采购单号'), text('sourceLine', '采购明细编号'), text('partner', '供应商'), text('delivery', '送货单号'), text('order', '放产单号'), text('contract', '合同号'), date('deliveryDate', '送货单日期'), date('date', '收货日期'), period] },
      materialGroup(),
      { title: '本次收料', description: '以下数量使用上面的本次计量单位。此前累计仅供核对；本次实收保留现场清点结果，预览不自动累计或计算欠数。', fields: [number('ordered', '采购订货数量'), number('previousReceived', '此前累计实收'), number('reported', '送货数量'), number('quantity', '本次实收数量')] },
      batches(kind),
      { title: '质量与差异', description: '质量结果与数量差异分别记录；正式放行规则待业务接入时确认。', fields: [choice('quality', '质量情况', ['待检', '已有检验结果', '存在质量异常']), text('qualitySource', '检验记录 / 依据'), note('note', '收货差异说明', '保留单据数量、实收差异及处理依据'), note('missingSource', '待补来源说明', '无法关联采购或送货资料时，记录缺失项与跟进情况')] },
      prices(),
    ],
    trace: ['采购明细', '本次送货与实收', '批次卷支与分仓', '检验与差异', '库存流水', '操作记录'],
  }
  if (kind === 'issue') return {
    title: '发料单样式',
    description: '核对领用去向、实际批次和放产用料分配。',
    groups: [
      { title: '领用与日期', description: '发料日期、来源到货日期和记账月份分别记录；同一去向的实际发出明细集中核对。', fields: [text('source', '领料申请 / 原单号'), choice('purpose', '发料用途', ['生产领用', '样板领用', '加工发出', '跨仓交接', '其他领用']), text('partner', '领用部门 / 加工方'), text('delivery', '领料人'), date('date', '发料日期'), date('arrivalDate', '来源到货日期'), period, text('processing', '目标工序 / 接收仓库')] },
      materialGroup(),
      { title: '本次发料', description: '申请、此前已发和本次实发分别保留。不同单位不直接相减，预览不扣减库存。', fields: [number('reported', '申请数量'), number('previousIssued', '此前累计实发'), number('quantity', '本次实发数量')] },
      batches(kind),
      allocations(),
      { title: '交接与差异', fields: [text('handover', '交接凭证 / 原发料记录'), note('note', '发料差异说明', '如部分领料、改用其他批次或交接数量不符'), note('missingSource', '待补来源说明', '记录暂缺的申请或放产关联，补关联不应再次扣库')] },
    ],
    trace: ['领料申请', '实际批次与仓位', '放产任务分配', '交接记录', '退料与更正', '库存流水'],
  }
  return {
    title: '库存详情样式',
    description: '核对物料、批次仓位、用料归属和各类状态。',
    groups: [
      materialGroup(true),
      { title: '数量与状态', description: '质量、暂停和订单归属分别表达；账面数仅为填写预览，正式结存应从流水生成。', fields: [number('quantity', '账面数量'), choice('quality', '质量情况', ['待检', '已有检验结果', '存在质量异常']), choice('hold', '暂停情况', ['未记录暂停', '暂停待确认', '已记录暂停']), choice('ownership', '订单归属情况', ['待核对', '已关联需求', '无订单余料', '共用物料']), note('note', '待处理说明', '记录余料、暂停、退料或处理依据，不直接改写库存')] },
      batches(kind),
      allocations(true),
      { title: '来源与期间', fields: [text('source', '来源单据'), text('partner', '来源供应商 / 退回方'), date('arrivalDate', '来源到货日期'), period, note('openingBasis', '期初 / 更正依据', '保留盘点、原台账版本、截止日及更正原因')] },
      prices(),
    ],
    trace: ['期初依据', '实际收发', '批次卷支记录', '用料归属', '退料与盘点更正', '月结记录'],
  }
}
