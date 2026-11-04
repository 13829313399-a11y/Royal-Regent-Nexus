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
      "进入“订单管理”，先核对目的厂区和订单类型。",
      "打开订单或采购明细，核对纸品、数量和交期。",
      "需要办其他厂区的单，先核对授权和原单据。"
    ],
    "result": "看到的是有权限的当前订单。",
    "reminders": [
      "供应商负责接单和发货；仓库负责验收、仓位和入库。"
    ],
    "image": {
      "src": "/carton-guide/quick-supplier-start.svg",
      "alt": "先选厂区，再看订单：进入“订单管理”，先核对目的厂区和订单类型。 → 打开订单或采购明细，核对纸品、数量和交期。 → 需要办其他厂区的单，先核对授权和原单据。",
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
      "打开明细，核对当前采购版本、纸品、数量和交期。",
      "确认能供应后接单，填承诺日期；多单可批量办理。",
      "订单追加、减量或调整后，重核新版本再发货。"
    ],
    "result": "接单状态和承诺交期可供本厂查看。",
    "reminders": [
      "批量操作先看成功和失败结果，不要重做已成功的单。"
    ],
    "image": {
      "src": "/carton-guide/quick-supplier-accept.svg",
      "alt": "核对后确认接单：打开明细，核对当前采购版本、纸品、数量和交期。 → 确认能供应后接单，填承诺日期；多单可批量办理。 → 订单追加、减量或调整后，重核新版本再发货。",
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
      "到“采购单与送货单”，按厂区或单号查找。",
      "看明细，核对当前采购版本和纸品数量。",
      "需要导入东康时，导出对应模板，检查文件后再导入。"
    ],
    "result": "采购内容和导出文件一致。",
    "reminders": [
      "导出采购单不等于已发货，也不会产生入库。"
    ],
    "image": {
      "src": "/carton-guide/quick-supplier-documents.svg",
      "alt": "查看和下载采购单：到“采购单与送货单”，按厂区或单号查找。 → 看明细，核对当前采购版本和纸品数量。 → 需要导入东康时，导出对应模板，检查文件后再导入。",
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
      "在“订单管理”导入原送货单，先核对目的厂区和原单号。",
      "核对日期、纸品、数量、单位、单价和关联订单，改好错误。",
      "确认真实发货，再到“发货与仓库反馈”看仓库处理结果。"
    ],
    "result": "送货单进入本厂待验收列表。",
    "reminders": [
      "仓库已手工入过库的同批货，要后补凭证关联原入库，不能再收一次。",
      "样板、杂单在客户单号填真实 SP 订单号，按当前已接单版本匹配纸品。",
      "同一张真实送货单可含正单、样板和杂单；有一行待核对，整单先不提交。",
      "缺价不是免费。普通单空价或未确认免费的 0 元仍待核价；明确确认才作免费。样板、杂单零价须确认免费。",
      "正式合同缺货号，先补齐原文件再导入；资料齐全却没订单的货交仓库核实。"
    ],
    "image": {
      "src": "/carton-guide/quick-supplier-dispatch.svg",
      "alt": "导入原送货单：在“订单管理”导入原送货单，先核对目的厂区和原单号。 → 核对日期、纸品、数量、单位、单价和关联订单，改好错误。 → 确认真实发货，再到“发货与仓库反馈”看仓库处理结果。",
      "caption": "操作示意图；按图中 1 → 2 → 3 办理，按钮与数据以当前页面为准。"
    }
  },
  {
    "id": "supplier-feedback",
    "number": "05",
    "group": "每天工作",
    "title": "看仓库实际验收结果",
    "summary": "看有效入库、拒收和短送，不只看发货数。",
    "entry": "发货与仓库反馈 → 送货单明细 / 验收历史",
    "destination": "supplier-shipments",
    "actionLabel": "打开发货与仓库反馈",
    "steps": [
      "打开“发货与仓库反馈”，找到原送货单。",
      "展开明细，看累计到货、破损、拒收和有效入库数量。",
      "有短送、拒收或冲销时，先对照原单和验收历史，再安排后续送货。"
    ],
    "result": "例如到货 100、拒收 100，有效入库为 0。",
    "reminders": [
      "未到不等于拒收；全拒收时有效入库为 0，采购欠数不会因此清零。"
    ],
    "image": {
      "src": "/carton-guide/quick-supplier-feedback.svg",
      "alt": "看仓库实际验收结果：打开“发货与仓库反馈”，找到原送货单。 → 展开明细，看累计到货、破损、拒收和有效入库数量。 → 有短送、拒收或冲销时，先对照原单和验收历史，再安排后续送货。",
      "caption": "操作示意图；按图中 1 → 2 → 3 办理，按钮与数据以当前页面为准。"
    }
  },
  {
    "id": "supplier-monthly",
    "number": "06",
    "group": "需要时处理",
    "title": "本月对账：看金额和明细",
    "summary": "选同一厂区、月份和币种，和本厂核对明细。",
    "entry": "月结对账 → 本月对账 / 应付与收款",
    "destination": "supplier-settlements",
    "actionLabel": "打开月结对账",
    "steps": [
      "打开“月结对账 → 本月对账”，选对厂区、月份和币种。",
      "看已验收送货、退货、退款和本月应结，展开原单明细。",
      "有差异先联系本厂核实，再刷新；收款另看“应付与收款”。"
    ],
    "result": "核对送货、退货和退款明细，再按原流程对账。",
    "reminders": [
      "本页只读，无需在系统内确认或提异议；看完不代表已经收款。",
      "没数据先核对筛选和厂区、月份、币种，再联系本厂查实际收料。",
      "期初库存、车间领料不算新增供货或退货；缺价不是免费。"
    ],
    "image": {
      "src": "/carton-guide/quick-supplier-monthly.svg",
      "alt": "本月对账：看金额和明细：打开“月结对账 → 本月对账”，选对厂区、月份和币种。 → 看已验收送货、退货、退款和本月应结，展开原单明细。 → 有差异先联系本厂核实，再刷新；收款另看“应付与收款”。",
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
      "到“箱唛资料库”快速上传，选状态并核对关联订单。",
      "共享厂区默认不选；只勾选应共享的服务厂区。",
      "业务确认打板回稿后改为已确认；使用前核对原文件和对应 PDF。"
    ],
    "result": "双方查看正确的原文件和对应 PDF。",
    "reminders": [
      "勾选共享厂区后，该厂业务和仓库可查看并更新资料状态。",
      "已发给自己的订单可读其共享箱唛；上传、改状态、改关联另需资料权限。",
      "转换成功不等于内容正确，使用前仍要核对。"
    ],
    "image": {
      "src": "/carton-guide/quick-supplier-help.svg",
      "alt": "上传并核对箱唛资料：到“箱唛资料库”快速上传，选状态并核对关联订单。 → 共享厂区默认不选；只勾选应共享的服务厂区。 → 业务确认打板回稿后改为已确认；使用前核对原文件和对应 PDF。",
      "caption": "操作示意图；按图中 1 → 2 → 3 办理，按钮与数据以当前页面为准。"
    }
  },
  {
    "id": "supplier-failure",
    "number": "08",
    "group": "需要时处理",
    "title": "失败或超时先查原单",
    "summary": "先查有没有成功，避免重复接单或发货。",
    "entry": "当前页面提示；采购单与送货单 / 操作日志",
    "destination": "supplier-activity",
    "actionLabel": "打开操作日志",
    "steps": [
      "记下厂区、原单号、时间和完整提示，保留截图。",
      "查采购单与送货单、发货反馈或操作日志，看是否已经成功。",
      "确认未成功再重试；不确定就找本厂负责人，附上截图和单号。"
    ],
    "result": "已成功的记录不重复提交。",
    "reminders": [
      "“已保存但刷新失败”只需重新读取，不能当作没保存。",
      "不要反复点提交。当前没有“AI 自动修复”，问题须先核实。"
    ],
    "image": {
      "src": "/carton-guide/quick-supplier-failure.svg",
      "alt": "失败或超时先查原单：记下厂区、原单号、时间和完整提示，保留截图。 → 查采购单与送货单、发货反馈或操作日志，看是否已经成功。 → 确认未成功再重试；不确定就找本厂负责人，附上截图和单号。",
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
      "写清厂区、单号、刚做的操作和提示，附截图。",
      "看回复和更新说明，再核对原单结果。"
    ],
    "result": "反馈能对应到具体单据。",
    "reminders": [
      "截图避开密码和无关个人信息。"
    ],
    "image": {
      "src": "/carton-guide/quick-supplier-report.svg",
      "alt": "反馈问题与查看更新：打开右上角“反馈与变更”。 → 写清厂区、单号、刚做的操作和提示，附截图。 → 看回复和更新说明，再核对原单结果。",
      "caption": "操作示意图；按图中 1 → 2 → 3 办理，按钮与数据以当前页面为准。"
    }
  },
  {
    "id": "supplier-special",
    "number": "10",
    "group": "每天工作",
    "title": "样板、杂单与免费赠送",
    "summary": "样板、杂单是订单类型；免费要单独明确。",
    "entry": "订单管理 → 订单台账 → 类型筛选",
    "destination": "supplier-orders",
    "actionLabel": "打开订单管理",
    "steps": [
      "按类型找订单，核对纸品、数量和需用日期。",
      "按当前版本接单、登记实发数量，不编造正单合同来源。",
      "有明确赠送时注明免费，由仓库按实际有效数量验收入库。"
    ],
    "result": "订单类型和送货性质清楚，历史记录可追溯。",
    "reminders": [
      "样板不等于免费；追加和修改后仍需核对新版本。"
    ],
    "image": {
      "src": "/carton-guide/quick-supplier-special.svg",
      "alt": "样板、杂单与免费赠送：按类型找订单，核对纸品、数量和需用日期。 → 按当前版本接单、登记实发数量，不编造正单合同来源。 → 有明确赠送时注明免费，由仓库按实际有效数量验收入库。",
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
