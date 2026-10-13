import type { WarehousePreviewField, WarehouseDocumentSpec } from '@/features/warehouse-foundation/documentPreview'
import { fabricDocumentSpec } from './fabricDocumentPreviews'

export type WarehousePreviewKind = 'receipt' | 'issue' | 'stock'
export type { WarehousePreviewField, WarehouseDocumentSpec } from '@/features/warehouse-foundation/documentPreview'

const field = (id: string, label: string, placeholder?: string): WarehousePreviewField => ({ id, label, placeholder })

export function warehouseDocumentSpec(semi: boolean, kind: WarehousePreviewKind): WarehouseDocumentSpec {
  if (!semi) return fabricDocumentSpec(kind)
  const stock = kind === 'stock'
  const issue = kind === 'issue'
  const material = semi ? '产品 / 款式' : '物料编码'
  return {
    title: stock ? '库存详情样式' : issue ? '发料单样式' : '收料单样式',
    description: stock ? '核对库存的识别信息、数量和来源分区。' : issue ? '核对来源、实际发出明细和领用去向。' : '核对来源、实收信息、批次和仓位。',
    groups: [
      {
        title: stock ? '库存识别' : '来源与交接',
        fields: stock
          ? [field('material', material), field('name', semi ? '产品名称' : '名称规格'), field('batch', '批次编号'), field('location', '仓库 / 仓位')]
          : [field('source', issue ? '领料申请 / 原单号' : semi ? '加工任务 / 原发出单' : '采购单号'), field('partner', issue ? '领用部门 / 加工方' : semi ? '回货单位' : '供应商'), field('delivery', issue ? '领料人' : '送货单号'), field('order', semi ? '生产单号' : '放产单号'), { id: 'date', label: issue ? '发料日期' : '收货日期', type: 'date' }],
      },
      {
        title: stock ? '数量与状态' : '本次明细',
        fields: stock
          ? [{ id: 'quantity', label: '账面数量', type: 'number' }, field('unit', '库存单位', '按实际单位填写，不自动换算'), field('state', semi ? '加工状态' : '物料颜色 / 规格'), field('quality', '质量状态')]
          : [field('material', material), field('name', semi ? '加工状态' : '名称规格'), { id: 'reported', label: issue ? '申请数量' : '送货数量', type: 'number' }, { id: 'quantity', label: issue ? '本次实发数量' : '本次实收数量', type: 'number' }, field('unit', '本次计量单位', '按实际填写，不自动换算'), field('batch', '批次编号'), ...(semi ? [field('cycle', '本轮交接编号')] : [field('color', '颜色'), field('dyeLot', '缸号'), field('roll', '卷号 / 包号')])],
      },
      {
        title: stock ? '来源与归属' : issue ? '仓位与去向' : '存放与质量',
        fields: stock
          ? [field('source', '来源单据'), field('order', semi ? '生产单号' : '关联订单'), field('partner', semi ? '来源加工方' : '供应商'), field('note', '备注')]
          : [field('location', issue ? '发出仓库 / 仓位' : '入库仓库 / 仓位'), field('allocation', '本仓位分配数量', '正式收发将支持多个仓位分配'), field('quality', issue ? '用途 / 目标工序' : '质量状态 / 待检说明'), field('note', '差异说明 / 备注')],
      },
    ],
    trace: stock
      ? ['来源单据', '收发流水', semi ? '加工与返修记录' : '批次与卷支记录', '盘点与更正']
      : ['来源资料', issue ? '实际发出' : '实收与质检', semi ? '加工交接关联' : '批次与分仓', '库存流水', '操作记录'],
  }
}
