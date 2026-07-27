import type { InternalQuoteSectionCode } from '@/types/internalQuoteDesk'

export const internalQuoteSectionDefinitions: Array<{
  code: InternalQuoteSectionCode
  label: string
  owner: string
  formulaHint: string
  dependencies: string[]
  departments: string[]
}> = [
  { code: 'sales', label: '业务部', owner: '业务核价', formulaHint: '填写包装材料、产品、彩盒、纸箱、平卡及运输资料；CUFT、纸箱成本与各备选运输方案由服务端权威计算，运费和吊柜费可分别启用或关闭。', dependencies: ['冻结汇率快照', '业务部包装材料、纸箱、平卡与可选运输费用资料'], departments: ['sales-business'] },
  { code: 'engineering', label: '工程部', owner: '工程核价', formulaHint: '模具总价 ÷ 分摊数量；人民币价格按冻结汇率转换为港币。', dependencies: ['模具报价单', 'RMB/HKD 汇率', '分摊数量'], departments: ['engineering'] },
  { code: 'electronic', label: '电子部', owner: '电子核价', formulaHint: '人民币零件与邦定/贴片/人工/测试/包装成本，自动计算利润、抵税差额、税负及含税港币报价。', dependencies: ['电子报价单', '利润率', '冻结汇率'], departments: ['electronic'] },
  { code: 'molding', label: '啤机部', owner: '啤机核价', formulaHint: '注塑：净重 ×（1 + 损耗%）× 冻结材料价 ÷ 454 + 冻结机型台班价 ÷ 套数 ÷ 目标数；吹气按料价、吹工、披锋及利润倍率计算。', dependencies: ['工程模具资料', '材料价快照', '机型价快照'], departments: ['production', 'molding'] },
  { code: 'painting', label: '喷油部', owner: '喷油核价', formulaHint: '夹模、移印、散枪、边模、油色、浸油、抹油、擦PP水八类工序数量 × 单价。', dependencies: ['喷油报价单'], departments: ['production', 'painting'] },
  { code: 'slush', label: '搪胶部', owner: '搪胶核价', formulaHint: '行总价 HKD = 用量 PC × 单价 HKD；合计 RMB 按冻结汇率换算。', dependencies: ['产品编号', '胶件名称', '材料', '料重', '日产量 24H', '用量'], departments: ['slush'] },
  { code: 'sewing', label: '车缝部', owner: '车缝核价', formulaHint: '价钱 RMB = 用量/码 × 物料价；总价钱再乘码点，裁片数只作记录。历史车发分类继续兼容，新报价请使用独立车发部。', dependencies: ['产品组', '布料名称', '部位', '工艺', '裁片数', '用量/码'], departments: ['sewing'] },
  { code: 'hair', label: '车发部', owner: '车发核价', formulaHint: '每行单价 HKD 直接计入成品车发成本；重量、工艺与单位作为报价依据记录。', dependencies: ['名称', '工艺', '重量（g）', '单价（HKD）', '单位'], departments: ['hair'] },
  { code: 'assembly', label: '装配部', owner: '装配核价', formulaHint: '人工基数 × 总人数 × 小组数 ÷ 生产量；人工基数和标准工时均可调整，组装与包装分别汇总。', dependencies: ['生产排拉工序表'], departments: ['assembly'] },
]
