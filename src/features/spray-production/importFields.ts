// Import mapping is an explicit operator decision. A cell is never executed as
// a formula and a historical subtotal is never inferred to be a transaction.
export interface ImportField { key:string; label:string; type?:'date'|'number'; collection?:string; options?:{value:string;label:string}[]; optional?:boolean }
const field=(key:string,label:string,extra:Omit<ImportField,'key'|'label'>={}):ImportField=>({key,label,...extra})
const quantity=field('quantity','数量',{type:'number'}), date=field('business_date','业务日期',{type:'date'}), document=field('document_no','单据编号'), party=field('counterparty','委托方'), unit=field('unit','单位'), reason=field('reason','处理依据')
const currency=field('currency','币种',{options:['CNY','HKD','USD'].map(value=>({value,label:value}))})
const material=field('material_id','材料 SKU',{collection:'materials'}), poLine=field('purchase_line_id','采购明细',{collection:'purchase-lines'}), deliveryLine=field('delivery_line_id','原送货明细',{collection:'delivery-lines'})
export const importLabels:Record<string,string>={opening:'期初实物结余',reference:'保留参考证据',demand:'接单需求',batch:'白件来料',delivery:'成品送货',return:'实物退货',container:'周转容器',report:'生产日报',expense:'费用 / 回收',purchase:'采购订单',material_receipt:'采购到货',saving:'采购减价分析',settlement:'验收月结'}
export const importFields:Record<string,ImportField[]>={
 opening:[document,date,field('line_id','订单部位',{collection:'demand-lines'}),quantity,unit,field('state','期初实物状态',{options:[{value:'white',label:'合格白件'},{value:'wip',label:'在制品'},{value:'finished',label:'合格成品'}]}),field('completed_codes','已完成工序编码（逗号分隔）',{optional:true}),field('evidence','盘点和工艺状态依据')],
 reference:[field('note','参考说明')],
 demand:[document,date,party,field('item_no','货号'),field('part','部位'),field('color','颜色'),quantity,unit,field('due_date','承诺交期',{type:'date'}),field('route_id','确认工艺路线',{collection:'routes',optional:true})],
 batch:[document,date,field('line_id','需求明细',{collection:'demand-lines',optional:true}),field('item_no','货号'),field('part','部位'),quantity,field('accepted','合格数',{type:'number'}),field('held','待判数',{type:'number'}),field('rejected','拒收数',{type:'number'}),unit],
 delivery:[document,date,party,field('stock_id','合格成品批次',{collection:'stock'}),quantity,field('warehouse_ref','仓库单据',{optional:true})],
 return:[date,deliveryLine,quantity,reason],
 container:[date,party,field('item','容器名称'),quantity,field('owner','物权',{options:[{value:'ours',label:'本部门'},{value:'theirs',label:'对方'}]}),field('direction','方向',{options:[{value:'in',label:'收回 / 收入'},{value:'out',label:'发出'}]})],
 report:[document,date,field('task_id','已开工任务',{collection:'tasks'}),field('processed','实做数',{type:'number'}),field('good','合格数',{type:'number'}),field('hold','待判数',{type:'number'}),field('scrap','报废数',{type:'number'}),field('normal','正常班数',{type:'number'}),field('overtime','加班数',{type:'number'}),field('employee_id','员工',{collection:'employees'}),field('normal_hours','正常工时',{type:'number'}),field('overtime_hours','加班工时',{type:'number'}),field('nonproductive_hours','非生产工时',{type:'number'}),reason],
 expense:[document,date,field('category','费用分类'),field('kind','收支方向',{options:[{value:'expense',label:'支出'},{value:'recovery',label:'回收'}]}),field('amount','金额',{type:'number'}),currency,field('included','是否纳入口径',{options:[{value:'unknown',label:'待负责人确认'},{value:'yes',label:'纳入'},{value:'no',label:'不纳入'}]}),field('evidence','确认依据')],
 purchase:[document,date,field('supplier','供应商'),currency,field('tax_basis','税费口径'),material,quantity,unit,field('price','单价',{type:'number',optional:true}),field('due_date','承诺到货日',{type:'date'})],
 material_receipt:[document,date,field('supplier','供应商'),poLine,quantity,unit,field('conversion_rule_id','换算版本',{collection:'rules',optional:true})],
 saving:[date,field('purchase_line_id','采购明细',{collection:'purchase-lines',optional:true}),quantity,field('old_price','原单价',{type:'number'}),field('new_price','新单价',{type:'number'}),currency,field('source_ref','减价凭据')],
 settlement:[document,date,party,field('month','结算月份'),currency,deliveryLine,quantity],
}
export function importValues(target:string,values:Record<string,string>,linked?:Record<string,unknown>){
 const v:Record<string,unknown>={...values};for(const key of Object.keys(v))if(v[key]==='')v[key]=null
 const pick=(keys:string[])=>Object.fromEntries(keys.map(key=>[key,v[key]]))
 if(target==='reference')return {note:values.note}
 if(target==='opening'){
  const codes=values.completed_codes?.split(/[,，]/).map(s=>s.trim()).filter(Boolean)??[]
  const steps=(linked?.steps??[]) as {id:string;code:string}[]
  if(codes.some(code=>!steps.some(step=>step.code===code)))throw new Error('完成工序编码不在此订单的工艺版本内')
  return {...pick(['document_no','business_date','line_id','quantity','unit','state','evidence']),completed_step_ids:steps.filter(step=>codes.includes(step.code)).map(step=>step.id)}
 }
 if(target==='demand')return {...pick(['document_no','business_date','counterparty']),source_type:'excel',lines:[pick(['item_no','part','color','quantity','unit','due_date','route_id'])]}
 if(target==='delivery')return {...pick(['document_no','business_date','counterparty']),warehouse_ref:values.warehouse_ref??'',lines:[pick(['stock_id','quantity'])]}
 if(target==='purchase')return {...pick(['document_no','business_date','supplier','currency','tax_basis']),lines:[pick(['material_id','quantity','unit','price','due_date'])]}
 if(target==='material_receipt')return {...pick(['document_no','business_date','supplier']),lines:[pick(['purchase_line_id','quantity','unit','conversion_rule_id'])]}
 if(target==='settlement')return {...pick(['document_no','business_date','counterparty','month','currency']),lines:[pick(['delivery_line_id','quantity'])]}
 if(target==='report'){
  const allocations=(linked?.allocations??[]) as {id:string}[]
  if(allocations.length!==1)throw new Error('合并任务请在现场日报逐单分配数量，再将此来源保留为参考证据')
  const quantities=pick(['processed','good','hold','scrap','normal','overtime'])
  return {...pick(['document_no','business_date']),shift:'来源核对',confirm:false,rows:[{task_id:v.task_id,...quantities,reason:values.reason,allocations:[{task_allocation_id:allocations[0]!.id,...quantities}],labor:[{...pick(['employee_id','overtime_hours','nonproductive_hours']),hours:v.normal_hours,reason:values.reason,weight:'1'}]}]}
 }
 if(target==='expense')v.included=values.included==='unknown'?null:values.included==='yes'
 if(target==='return')v.expected_version=linked?.version??0
 return v
}
