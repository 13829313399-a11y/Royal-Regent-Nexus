import type { CartonGuideSection } from './usageGuide'

export type CartonSupplierGuideDestination =
  | 'supplier-orders' | 'supplier-documents' | 'supplier-shipments'
  | 'supplier-settlements' | 'supplier-activity' | 'supplier-carton-mark' | 'supplier-feedback'

export const cartonSupplierGuideSections: CartonGuideSection<CartonSupplierGuideDestination>[] = [
  {
    "id": "supplier-start",
    "number": "01",
    "group": "首次启用",
    "title": "先选厂区，再看订单",
    "summary": "按订单目的厂区办理，避免送错地方。",
    "entry": "纸箱供应商协同 → 页面顶部 / 订单管理",
    "destination": "supplier-orders",
    "actionLabel": "打开订单管理",
    "steps": [
      "进入“订单管理”，核对厂区和订单类型。",
      "打开采购或订单明细，核对纸品、数量和交期。",
      "需要操作其他厂区时，先检查该厂区授权和对应单据。"
    ],
    "result": "看到的是有权限的当前订单。",
    "reminders": [
      "供应商负责接单和发货；仓库负责验收、仓位和入库。"
    ],
    "image": {
      "src": "/carton-guide/quick-supplier-start.svg",
      "alt": "先选厂区，再看订单：进入“订单管理”，核对厂区和订单类型。 → 打开采购或订单明细，核对纸品、数量和交期。 → 需要操作其他厂区时，先检查该厂区授权和对应单据。",
      "caption": "操作示意图；按图中 1 → 2 → 3 办理，按钮与数据以当前页面为准。"
    }
  },
  {
    "id": "supplier-accept",
    "number": "02",
    "group": "每天工作",
    "title": "核对后确认接单",
    "summary": "按当前采购版本安排生产和送货。",
    "entry": "订单管理 → 明细 / 确认接单 / 批量接单",
    "destination": "supplier-orders",
    "actionLabel": "打开订单管理",
    "steps": [
      "打开订单明细，检查纸品、数量和交期。",
      "确认可以供应后接单，按页面填写承诺日期；多单可批量办理。",
      "订单追加、减量或调整后，重新核对新版本再安排发货。"
    ],
    "result": "接单状态和承诺交期可供本厂查看。",
    "reminders": [
      "批量操作有失败项时先看结果，不要重复操作已成功的单。"
    ],
    "image": {
      "src": "/carton-guide/quick-supplier-accept.svg",
      "alt": "核对后确认接单：打开订单明细，检查纸品、数量和交期。 → 确认可以供应后接单，按页面填写承诺日期；多单可批量办理。 → 订单追加、减量或调整后，重新核对新版本再安排发货。",
      "caption": "操作示意图；按图中 1 → 2 → 3 办理，按钮与数据以当前页面为准。"
    }
  },
  {
    "id": "supplier-documents",
    "number": "03",
    "group": "每天工作",
    "title": "查看和下载采购单",
    "summary": "正单、样板和杂单都可以查看已生成采购。",
    "entry": "采购单与送货单 → 筛选 / 明细 / 导出东康导入模板",
    "destination": "supplier-documents",
    "actionLabel": "打开采购单与送货单",
    "steps": [
      "打开“采购单与送货单”，按厂区或单号查找。",
      "查看明细，核对采购版本和纸品数量。",
      "需要带入东康时，使用“导出东康导入模板”，检查文件后再导入。"
    ],
    "result": "采购内容和导出文件一致。",
    "reminders": [
      "导出采购单不等于已发货，也不会产生入库。"
    ],
    "image": {
      "src": "/carton-guide/quick-supplier-documents.svg",
      "alt": "查看和下载采购单：打开“采购单与送货单”，按厂区或单号查找。 → 查看明细，核对采购版本和纸品数量。 → 需要带入东康时，使用“导出东康导入模板”，检查文件后再导入。",
      "caption": "操作示意图；按图中 1 → 2 → 3 办理，按钮与数据以当前页面为准。"
    }
  },
  {
    "id": "supplier-dispatch",
    "number": "04",
    "group": "每天工作",
    "title": "导入原送货单",
    "summary": "按实际发货登记，价格以供应商原单为依据。",
    "entry": "订单管理 → 导入送货单；发货与仓库反馈",
    "destination": "supplier-orders",
    "actionLabel": "打开订单管理",
    "steps": [
      "在“订单管理”导入原始送货单，核对目的厂区和原单号。",
      "检查日期、纸品、数量、单位、单价及订单关联，修正错误。",
      "确认真实发货，再到“发货与仓库反馈”查看仓库处理情况。"
    ],
    "result": "送货单进入本厂待验收列表。",
    "reminders": [
      "仓库已经手工入库的同一批货，使用后补凭证关联已有入库，不能再形成一次实收。",
      "缺价需补价；零价只有明确免费才作为免费处理。"
    ],
    "image": {
      "src": "/carton-guide/quick-supplier-dispatch.svg",
      "alt": "导入原送货单：在“订单管理”导入原始送货单，核对目的厂区和原单号。 → 检查日期、纸品、数量、单位、单价及订单关联，修正错误。 → 确认真实发货，再到“发货与仓库反馈”查看仓库处理情况。",
      "caption": "操作示意图；按图中 1 → 2 → 3 办理，按钮与数据以当前页面为准。"
    }
  },
  {
    "id": "supplier-feedback",
    "number": "05",
    "group": "每天工作",
    "title": "看仓库实际验收结果",
    "summary": "到货数量包括拒收部分，入库只算有效数量。",
    "entry": "发货与仓库反馈 → 送货单明细 / 验收历史",
    "destination": "supplier-shipments",
    "actionLabel": "打开发货与仓库反馈",
    "steps": [
      "打开“发货与仓库反馈”，找到原送货单。",
      "展开明细，看累计到货、破损、拒收和有效入库数量。",
      "有短送、拒收或冲销时先核对原单和验收历史，再处理后续送货。"
    ],
    "result": "例如到货 100、拒收 100，有效入库为 0。",
    "reminders": [
      "未到不等于拒收；整项拒收不代表采购欠数已清零。"
    ],
    "image": {
      "src": "/carton-guide/quick-supplier-feedback.svg",
      "alt": "看仓库实际验收结果：打开“发货与仓库反馈”，找到原送货单。 → 展开明细，看累计到货、破损、拒收和有效入库数量。 → 有短送、拒收或冲销时先核对原单和验收历史，再处理后续送货。",
      "caption": "操作示意图；按图中 1 → 2 → 3 办理，按钮与数据以当前页面为准。"
    }
  },
  {
    "id": "supplier-monthly",
    "number": "06",
    "group": "需要时处理",
    "title": "本月对账：看金额和明细",
    "summary": "和本厂核对同一月份的送货、退货和应结。",
    "entry": "月结对账 → 本月对账 / 应付与收款",
    "destination": "supplier-settlements",
    "actionLabel": "打开月结对账",
    "steps": [
      "打开“月结对账 → 本月对账”，选择厂区、月份和币种。",
      "先看已验收送货、退货贷项和本月应结，再查具体送货或退货明细。",
      "数量或价格不对时联系本厂核实原单，处理后刷新；收款另看“应付与收款”。"
    ],
    "result": "本月应结＝已验收送货金额－退货贷项。",
    "reminders": [
      "本页只读，不需要在系统内确认或提异议；月结按原流程办理。",
      "不把仓库期初库存或车间领用当成新增供货或退货。"
    ],
    "image": {
      "src": "/carton-guide/quick-supplier-monthly.svg",
      "alt": "本月对账：看金额和明细：打开“月结对账 → 本月对账”，选择厂区、月份和币种。 → 先看已验收送货、退货贷项和本月应结，再查具体送货或退货明细。 → 数量或价格不对时联系本厂核实原单，处理后刷新；收款另看“应付与收款”。",
      "caption": "操作示意图；按图中 1 → 2 → 3 办理，按钮与数据以当前页面为准。"
    }
  },
  {
    "id": "supplier-help",
    "number": "07",
    "group": "需要时处理",
    "title": "上传并核对箱唛资料",
    "summary": "原文件与 PDF 要核对同一份内容。",
    "entry": "箱唛资料库 → 快速上传 / 共享厂区 / 状态",
    "destination": "supplier-carton-mark",
    "actionLabel": "打开箱唛资料库",
    "steps": [
      "打开“箱唛资料库”快速上传，选择初稿、待确认、已确认或历史版本，可关联多个订单。",
      "共享厂区默认不选；勾选服务厂区后，该厂业务和仓库可查看并更新资料状态。",
      "业务确认打板回稿后更新为已确认，供应商核对文件及关联订单后使用。"
    ],
    "result": "双方查看正确的原文件和对应 PDF。",
    "reminders": [
      "转换成功不代表内容正确，使用前仍需核对。"
    ],
    "image": {
      "src": "/carton-guide/quick-supplier-help.svg",
      "alt": "上传并核对箱唛资料：打开“箱唛资料库”快速上传，选择初稿、待确认、已确认或历史版本，可关联多个订单。 → 共享厂区默认不选；勾选服务厂区后，该厂业务和仓库可查看并更新资料状态。 → 业务确认打板回稿后更新为已确认，供应商核对文件及关联订单后使用。",
      "caption": "操作示意图；按图中 1 → 2 → 3 办理，按钮与数据以当前页面为准。"
    }
  },
  {
    "id": "supplier-failure",
    "number": "08",
    "group": "需要时处理",
    "title": "失败或超时先查原单",
    "summary": "先看结果，避免重复接单或发货。",
    "entry": "当前页面提示；采购单与送货单 / 操作日志",
    "destination": "supplier-activity",
    "actionLabel": "打开操作日志",
    "steps": [
      "记录厂区、原单号、时间和提示。",
      "到采购单与送货单、发货反馈或操作日志检查是否已经成功。",
      "确定未成功再重试；仍不明确时反馈问题并附提示截图。"
    ],
    "result": "已成功的记录不重复提交。",
    "reminders": [
      "“已保存但刷新失败”只需重新读取，不能当作没保存。"
    ],
    "image": {
      "src": "/carton-guide/quick-supplier-failure.svg",
      "alt": "失败或超时先查原单：记录厂区、原单号、时间和提示。 → 到采购单与送货单、发货反馈或操作日志检查是否已经成功。 → 确定未成功再重试；仍不明确时反馈问题并附提示截图。",
      "caption": "操作示意图；按图中 1 → 2 → 3 办理，按钮与数据以当前页面为准。"
    }
  },
  {
    "id": "supplier-report",
    "number": "09",
    "group": "需要时处理",
    "title": "反馈问题与查看更新",
    "summary": "说明问题发生在哪张单，便于处理。",
    "entry": "页面右上角 → 反馈与变更",
    "destination": "supplier-feedback",
    "actionLabel": "打开反馈与变更",
    "steps": [
      "打开右上角“反馈与变更”。",
      "写明厂区、单号、操作和提示，附截图。",
      "留意处理回复和功能更新说明。"
    ],
    "result": "反馈能对应到具体单据。",
    "reminders": [
      "截图避开密码和无关个人信息。"
    ],
    "image": {
      "src": "/carton-guide/quick-supplier-report.svg",
      "alt": "反馈问题与查看更新：打开右上角“反馈与变更”。 → 写明厂区、单号、操作和提示，附截图。 → 留意处理回复和功能更新说明。",
      "caption": "操作示意图；按图中 1 → 2 → 3 办理，按钮与数据以当前页面为准。"
    }
  },
  {
    "id": "supplier-special",
    "number": "10",
    "group": "每天工作",
    "title": "样板、杂单与免费赠送",
    "summary": "样板和杂单沿用订单接单、采购单和送货流程。",
    "entry": "订单管理 → 订单台账 → 类型筛选",
    "destination": "supplier-orders",
    "actionLabel": "打开订单管理",
    "steps": [
      "按类型筛选订单，核对纸品、数量和需用日期。",
      "按当前版本接单并登记实际送货，无需补填正单合同来源。",
      "免费赠送在送货时明确标注，仓库按实际验收后入库。"
    ],
    "result": "订单类型和送货性质清楚，历史记录可追溯。",
    "reminders": [
      "样板不等于免费；追加和修改后仍需核对新版本。"
    ],
    "image": {
      "src": "/carton-guide/quick-supplier-special.svg",
      "alt": "样板、杂单与免费赠送：按类型筛选订单，核对纸品、数量和需用日期。 → 按当前版本接单并登记实际送货，无需补填正单合同来源。 → 免费赠送在送货时明确标注，仓库按实际验收后入库。",
      "caption": "操作示意图；按图中 1 → 2 → 3 办理，按钮与数据以当前页面为准。"
    }
  }
]

export const cartonSupplierChecklist = [
  "核对厂区和当前采购版本。",
  "接单、交期承诺与实际安排一致。",
  "送货单数量和原价填写清楚。",
  "跟进仓库有效入库、拒收和短送反馈。",
  "核对本月送货、退货与应结，差异回原单处理。"
]
