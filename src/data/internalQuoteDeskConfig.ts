import type { InternalQuoteSectionCode } from '@/types/internalQuoteDesk'

export const internalQuoteSectionDefinitions: Array<{
  code: InternalQuoteSectionCode
  label: string
  owner: string
  formulaHint: string
  dependencies: string[]
  departments: string[]
}> = [
  { code: 'sales', label: '业务部', owner: '业务核价', formulaHint: '填写包装材料、产品、彩盒、纸箱、平卡及运费资料；CUFT、纸箱成本与八个备选运输方案由服务端权威计算，客户自提时可关闭运费计算。', dependencies: ['全部参与分段计算结果', '汇率快照', '包装材料、纸箱、平卡与可选运费资料'], departments: ['sales-business'] },
  { code: 'engineering', label: '工程部', owner: '工程核价', formulaHint: '模具总价 ÷ 分摊数量；人民币价格按冻结汇率转换为港币。', dependencies: ['模具报价单', 'RMB/HKD 汇率', '分摊数量'], departments: ['engineering'] },
  { code: 'electronic', label: '电子部', owner: '电子核价', formulaHint: '零件与子项成本 + 邦定/SMT/人工/测试/包装，再计算利润与税负。', dependencies: ['电子报价单', '利润率', '抵税差额'], departments: ['electronic'] },
  { code: 'molding', label: '啤机部', owner: '啤机核价', formulaHint: '净重 × 3% 损耗 × 材料价 + 机型台班啤价；材质与料型必须精确匹配。', dependencies: ['工程模具 revision', '材料价快照', '机型价快照'], departments: ['production', 'molding'] },
  { code: 'painting', label: '喷油部', owner: '喷油核价', formulaHint: '夹模、移印、散枪、边模、油色、浸油、抹油七类工序数量 × 单价。', dependencies: ['工程模具 revision', '喷油核价表'], departments: ['painting'] },
  { code: 'slush', label: '搪胶部', owner: '搪胶核价', formulaHint: '行金额 = 单价 HKD × 数量；汇总后进入整单成本。', dependencies: ['搪胶数量'], departments: ['slush'] },
  { code: 'sewing', label: '车缝部', owner: '车缝核价', formulaHint: '用量 × 物料价 RMB × 码点 + 人工；人工明细已存在时禁止重复追加。', dependencies: ['车缝报价单', '产品组', '车衣/车发分类'], departments: ['sewing'] },
  { code: 'assembly', label: '装配部', owner: '装配核价', formulaHint: '260 HKD/人 × 人数 × 小组数 ÷ 生产量，组装与包装分别汇总；人工基数可调整。', dependencies: ['工程模具 revision', '生产排拉工序表'], departments: ['assembly'] },
]
