<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { X } from '@lucide/vue'
import { DialogRoot, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogDescription, DialogClose } from 'reka-ui'
import { WAREHOUSE_FACTORY, warehousePath, type WarehouseWorkspace } from './navigation'

const props = defineProps<{ warehouse: WarehouseWorkspace }>()
const open = defineModel<boolean>('open', { required: true })
const search = ref('')
const sections = computed(() => props.warehouse.sections.filter(section => [section.title, section.description, ...section.views.flatMap(view => [view.title, view.description, ...view.columns])].join(' ').includes(search.value.trim())))
</script>

<template>
  <DialogRoot v-model:open="open">
    <DialogPortal>
      <DialogOverlay class="warehouse-guide-overlay" />
      <DialogContent class="warehouse-guide">
        <header class="warehouse-guide-heading"><div><DialogTitle>{{ warehouse.title }}使用说明</DialogTitle><DialogDescription>{{ warehouse.id === 'fabric-warehouse' ? '布料仓支持采购追货、实际入库、质检结论、领发料、退料与移库；期初、盘点、计价和月结尚待建设。' : '半成品仓可登记加工任务、实际收货、分批加工发回和包装交接；外部接口、历史导入和月结尚待建设。' }}</DialogDescription></div><DialogClose class="warehouse-guide-close" aria-label="关闭使用说明"><X :size="20" /></DialogClose></header>
        <div class="warehouse-guide-body">
          <label class="warehouse-guide-search">查找说明<input v-model="search" type="search" aria-label="查找仓库使用说明" placeholder="栏目 / 业务分区 / 字段" /></label>
          <section v-if="warehouse.id === 'fabric-warehouse'" class="warehouse-guide-intro"><h3>在收料入库接收订单资料与收货</h3><p>采购负责下单，布料仓接收已下达的订单。订单导入、待收料、送货单扫描、入库记录、采购接口共五个入口，扫描及采购接口尚未接通，日常默认待收料。默认导入未回物料和补数未回物料，并检查已有来源是否移入已回料或补数已回。补数独立标记，不与正常采购合并。退货记录需要明确是否补回；罚款属于扣款跟进，本次不生成待入库。</p><p>未齐料包含部分到货；已报到货进入“采购报到货 · 待核对”，变化保留未读提醒。标记已读不确认实收。原表已回数量只作参考，缺数不按零，原单位不换算。采购历史不自动生成入库或期初库存。</p><p>仓库点“登记入库”，填写本次数量、仓位和送货依据，日期默认当天，记账月份跟收货日期。分类优先使用已确认且与来源匹配的物料资料，没有资料时手选，布料每项必填缸号，卷号为单卷编号、选填；辅料和线不填缸号、卷号。可增加明细分仓位、分缸收料。导入自动按订货减已回数量开始追货，数量空白时可按实物入库，欠数保持待核对；负责人在来源详情核对起始待收量，起始量须包含本系统已经登记的实收；不再询问是否首次收货或手填此前实收。已回参考不增加库存，后续表更新不重复扣减系统实收。送货单日期和备注在补充信息中。点击“保存并入库”即可；只有超过待收量才填超收说明。保存后可在入库记录、库存台账和库存流水查看本次待检库存，同一来源/送货依据防重复。库存台账从原采购实收与新增收发计算结余，不含未核实的期初。</p><p>每条来源保留文件、页签、行号和变更证据；多条明细变化须核对稳定编号。最近有效导入可预览撤销，填写原因并确认；涉及已有实际入库或起始数量核对的来源会阻止撤销。提醒随新文件导入产生，本页每分钟刷新，未连接金蝶自动同步。</p></section>
          <section class="warehouse-guide-intro"><h3>日常收发与加工交接</h3><p>工作看板可登记缺少采购来源的手工实收，必填原凭证和明细编号。这类实收不自动修改采购待收量；有采购来源的收料仍从待收料办理，不能重复登记。实收后可在库存台账找到对应批次。</p><p>库存台账按物料名称、数量和仓位显示已入库物料，正式仓位的库存每行可直接出库或调仓，也可勾选后批量出库。旧记录显示“仓位待核实”时，先由有更正权限的人员核实关联，原数量不变。出库填写领用方和本次数量，有领料申请时再关联；放产单分配选填，填写后合计须等于出库数量。普通用途和备注选填。质检由 QC 模块负责，仓库不再登记质检；已有暂停或不合格记录仍限制出库。退料关联原发出，调仓保留原批次信息、总量不变。</p><p>半成品每轮发出关联加工任务；回货分别填写实际产出与本轮核销发出量，跨单位不自动换算。包装发出与仓库代录接收回执分开，实际接收人必填，接收依据选填。返工可建立新任务并选择退回批次，旧加工轮次保留。</p><p>录错单据从异常处理申请冲销，需独立更正权限及原因；已有后续业务时阻止直接冲销。冲销后可按原来源重新登记。期初、盘点、计价和月结尚未开放，不能据当前数量判断现场完整库存。</p></section><section class="warehouse-guide-intro"><h3>查看单据字段样式</h3><p>工作看板提供收料单、发料单和库存详情预览；收料入库、库存管理也有对应入口。可以临时填写字段，再切换到详情核对。关闭或离开会清空预览内容，不保存单据、不增加库存；已有填写时会提示确认清空。</p><p v-if="warehouse.id === 'fabric-warehouse'">布料预览可选择布料、辅料或线，分开填写业务日期、来源到货日期和记账月份。收料可添加批次、缸号、卷支与仓位明细；发料可添加实际发出明细和多个放产任务的用料分配。库存详情区分质量、暂停、订单归属和价格依据。已有填写的明细在移除前会提醒。</p><p v-else>半成品预览保留加工任务、加工状态及本轮交接编号。</p><p>临时预览不自动换算、合计或生成金额；布料实际入库请使用待收料中的“登记入库”。实际发料可直接从库存台账办理，有领料申请时再关联；扫码尚未接通。</p></section>
          <section class="warehouse-guide-intro"><h3>准备基础资料，再衔接实际收发</h3><p>两仓入库、退料入仓和调入必须选择已启用的正式仓位；没有仓位时先在基础资料建档。停用仓位可发出或调走已有库存，不能新增入库。不能通过修改仓位资料移动实物。</p><p v-if="warehouse.id === 'fabric-warehouse'">物料、供应商、仓位、单位可在基础资料新增、修改和停用。导入负责人可从采购来源候选补齐资料，确认分类和单位后启用。已停用物料及仓位不用于新入库；历史入库内容不会随资料修改。单位换算必须明确适用物料及依据，当前不自动换算库存。</p><p>{{ warehouse.id === 'fabric-warehouse' ? '布料仓接收采购已下的订单和供应商送货信息，核对实物后办理收料，再按领料申请或纸质单分批发料。' : '半成品仓接收外发、车间和手工回货，区分加工状态；二次加工的发出、回收与包装交接分别记录。' }}</p><p>需求、送货、实收和实发分别保留。质量由 QC 核实，缺价保留待核依据；期初库存需先确认实物、账期和正式账。</p><p>每次实际收发应保留原单、批次、仓位与经办人。库存汇总和月报从同一份收发流水形成，更正保留原记录。</p></section>
          <section v-for="section in sections" :key="section.path" class="warehouse-guide-section"><h3>{{ section.title }}</h3><p>{{ section.description }}</p><ul><li v-for="view in section.views" :key="view.id"><RouterLink :to="{ path: warehousePath(warehouse, section.path), query: { factory: WAREHOUSE_FACTORY, view: view.id } }" @click="open = false">{{ view.title }}</RouterLink><p>{{ view.description }}</p></li></ul></section>
          <p v-if="!sections.length" role="status">没有匹配的说明，请换一个栏目或字段名称。</p>
        </div>
        <footer class="warehouse-guide-footer">点击业务分区可查看对应页面；打开或关闭说明不会登记业务。</footer>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>
