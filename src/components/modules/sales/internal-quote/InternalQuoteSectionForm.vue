<script setup lang="ts">
import { Plus, Trash2 } from '@lucide/vue'
import { computed } from 'vue'
import { calculateCartonCuft, calculateCartonPriceHkd, calculateCartonUnitCostHkd, calculateEngineeringMaterialAmountHkd, calculateEngineeringMaterialUnitHkd, calculateEngineeringMoldAllocation, calculateEngineeringMoldPriceHkd, calculateFlatCardPriceHkd, calculatePackagingMaterialAmountHkd, calculatePackagingMaterialUnitHkd, calculateSalesFreightOptions, paintingOperationLabels, salesFreightCapacityDefinitions, type AssemblyPayload, type ElectronicPayload, type EngineeringMaterialRow, type EngineeringPayload, type MoldingPayload, type PaintingOperationCode, type PaintingPayload, type SalesPayload, type SewingPayload, type SlushPayload } from '@/lib/internalQuoteSectionPayload'
import type { InternalQuoteSectionCode } from '@/types/internalQuoteDesk'

const props = defineProps<{ code: InternalQuoteSectionCode; disabled?: boolean; customer?: string; rmbHkdRate?: number }>()
const model = defineModel<Record<string, unknown>>({ required: true })

const sales = computed(() => model.value as unknown as SalesPayload)
const flatCardPriceFactor = computed<number>({
  get: () => {
    const override = Number(sales.value.flat_card_price_factor)
    if (Number.isFinite(override) && override > 0) return override
    const cartonFactor = Number(sales.value.paper_price_factor)
    return Number.isFinite(cartonFactor) && cartonFactor > 0 ? cartonFactor : 2.75
  },
  set: (value) => {
    const parsed = Number(value)
    if (Number.isFinite(parsed) && parsed > 0) sales.value.flat_card_price_factor = parsed
    else delete sales.value.flat_card_price_factor
  },
})
const engineering = computed(() => model.value as unknown as EngineeringPayload)
const electronic = computed(() => model.value as unknown as ElectronicPayload)
const molding = computed(() => model.value as unknown as MoldingPayload)
const painting = computed(() => model.value as unknown as PaintingPayload)
const slush = computed(() => model.value as unknown as SlushPayload)
const sewing = computed(() => model.value as unknown as SewingPayload)
const assembly = computed(() => model.value as unknown as AssemblyPayload)
// 内部报价统一采用 Huaxing Demo 基础填入格式。客户名称只在最终报客价
// 转换时选择对应输出模板，不再改变内部协作表的字段和布局。
const isBuzzBee = computed(() => false)
const isDisney = computed(() => false)
const isDickie = computed(() => false)
const isCaixing = computed(() => false)
const operationCodes = Object.keys(paintingOperationLabels) as PaintingOperationCode[]
const engineeringMaterialCategories: EngineeringMaterialRow['auxiliary_category'][] = ['吸塑', '胶袋', '彩盒/内卡', '电池', '利宝', '电镀', '其他外购']
const hardwareRows = computed(() => engineering.value.materials.filter((row) => row.category === 'hardware'))
const auxiliaryRows = computed(() => engineering.value.materials.filter((row) => row.category === 'auxiliary'))
const hardwareTotal = computed(() => hardwareRows.value.reduce((total, row) => total + calculateEngineeringMaterialAmountHkd(row, props.rmbHkdRate), 0))
const auxiliaryTotal = computed(() => auxiliaryRows.value.reduce((total, row) => total + calculateEngineeringMaterialAmountHkd(row, props.rmbHkdRate), 0))
const moldQuoteTotalRmb = computed(() => engineering.value.molds.reduce((total, row) => total + Number(row.cost_rmb || 0), 0))
const moldQuoteTotalHkd = computed(() => engineering.value.molds.reduce((total, row) => total + calculateEngineeringMoldPriceHkd(row, props.rmbHkdRate), 0))
const moldAllocation = computed(() => calculateEngineeringMoldAllocation(engineering.value))

function remove<T>(items: T[], index: number) { items.splice(index, 1) }
function engineeringMaterialRow(category: 'hardware' | 'auxiliary'): EngineeringMaterialRow {
  return { item: '', category, purpose: '', specification: '', quantity: 0, unit: '', unit_price_rmb: 0, material: '', surface_treatment: '', supplier: '', contact: '', auxiliary_category: '其他外购', tax_rate_percent: 0, remark: '', disney_description: '', disney_section: 'product', disney_unit_price_usd: 0, disney_included: 1 }
}
function addEngineeringHardware() { engineering.value.materials.push(engineeringMaterialRow('hardware')) }
function addEngineeringAuxiliary() { engineering.value.materials.push(engineeringMaterialRow('auxiliary')) }
function removeEngineeringMaterial(row: EngineeringMaterialRow) {
  const index = engineering.value.materials.indexOf(row)
  if (index >= 0) engineering.value.materials.splice(index, 1)
}
function addEngineeringMold() {
  engineering.value.molds.push({
    item: '', mold_no: '', mold_base_type: '', structure: '', material: '', color: '', cavity: '', quantity: 1,
    net_weight_g: 0, cycle_time_seconds: 0, mold_size: '', image_reference: '', cost_rmb: 0, remark: '', machine_code: '', target_output: 0, source_row: 0,
    disney_mold_no: '', disney_parts: '', disney_material: '', disney_cavities: 0, disney_parts_per_shot: 0, disney_tool_cost_usd: 0,
    dickie_project_name_en: '', dickie_mold_no: '', dickie_parts_en: '', dickie_resin: '', dickie_mold_size: '', dickie_mold_material: '', dickie_cavities: 0, dickie_parts_per_shot: 0, dickie_mold_cost_hkd: 0, dickie_remark_en: '',
    caixing_tool_plan_ref: '', caixing_mold_cost_hkd: 0, caixing_customer_mold_cost_hkd: 0,
  })
}
function addProductionMoldCost() { engineering.value.production_mold_costs.push({ item: '', cost_rmb: 0 }) }
function addSalesPackagingMaterial() { sales.value.packaging_materials.push({ item: '', specification: '', category: 'blister', quantity: 0, unit_price_rmb: 0, tax_rate_percent: 0, remark: '' }) }
function addSalesCarton() { sales.value.cartons.push({ item: '主纸箱', length_in: 0, width_in: 0, height_in: 0, qty_per_carton: 1, flat_cards: [] }) }
function addSalesFlatCard(cartonIndex: number) { sales.value.cartons[cartonIndex].flat_cards.push({ name: `平卡${sales.value.cartons[cartonIndex].flat_cards.length + 1}`, length_in: 0, width_in: 0, quantity: 1 }) }
function flatCardTotal(index: number) { return sales.value.cartons[index].flat_cards.reduce((total, row) => total + calculateFlatCardPriceHkd(row, flatCardPriceFactor.value), 0) }
const packagingMaterialTotal = computed(() => sales.value.packaging_materials.reduce((total, row) => total + calculatePackagingMaterialAmountHkd(row, props.rmbHkdRate), 0))
const primaryCarton = computed(() => sales.value.cartons[0])
const freightOptions = computed(() => calculateSalesFreightOptions(sales.value.freight_calc, primaryCarton.value))
const freightSourceCuft = computed(() => primaryCarton.value ? calculateCartonCuft(primaryCarton.value) : 0)
function calculated(value: number) { return value.toFixed(4) }
function whole(value: number) { return Math.round(value).toString() }
function normalizeFreightCapacity(key: keyof Pick<SalesPayload['freight_calc'], 'cap_10t' | 'cap_5t' | 'cap_40' | 'cap_20'>) {
  const value = Number(sales.value.freight_calc[key])
  sales.value.freight_calc[key] = Number.isFinite(value) && value > 0 ? Math.max(Math.round(value), 1) : 0
}
function addElectronicComponent() { electronic.value.components.push({ item: '', quantity: 0, unit_price_hkd: 0, children: [] }) }
function addElectronicChild(index: number) { electronic.value.components[index].children.push({ item: '', quantity: 0, unit_price_hkd: 0, children: [] }) }
function addInjection() { molding.value.injection_lines.push({ item: '', material: '', grade: '', net_weight_g: 0, loss_rate_percent: 3, machine_code: '', sets: 1, target_output: 0, quantity: 1, disney_mold_no: '', disney_resin_cost_usd_kg: 0, disney_cycle_time_seconds: 0, disney_labor_rate_usd_hr: 0 }) }
function addCaixingToolPlanRow() { molding.value.caixing_tool_plan_rows.push({ ref_no: '', process_type: 'IN', tool_no: '', tooling_cost_hkd: 0, description: '', sku_no: '', cavities: 1, up: 1, net_weight_g: 0, material_code: 0, material: '', color: '', material_cost_hkd: 0, machine_size: '', cycle_time_seconds: 0, process_cost_hkd: 0 }) }
function addBlow() { molding.value.blow_lines.push({ item: '', material: '', grade: '', estimated_weight_g: 0, labor_hkd: 0, burr_hkd: 0, profit_multiplier: 1.05, quantity: 1 }) }
function addPainting() {
  painting.value.rows.push({ item: '', operations: Object.fromEntries(operationCodes.map((code) => [code, { quantity: 0, unit_price_hkd: 0 }])) as PaintingPayload['rows'][number]['operations'] })
}
function addDisneyDecoration() { painting.value.disney_decorations.push({ application_type: '', rate_per_op_usd: 0, operations: 0 }) }
function addSlush() { slush.value.lines.push({ item: '', quantity: 0, unit_price_hkd: 0 }) }
function addSewingGroup() { sewing.value.groups.push({ name: '', category: 'clothes', labor_rmb: 0, materials: [] }) }
function addSewingMaterial(index: number) { sewing.value.groups[index].materials.push({ item: '', usage: 0, unit_price_rmb: 0, markup: 1 }) }
function addAssemblyGroup() { assembly.value.groups.push({ name: '', category: 'assembly', processes: [] }) }
function addAssemblyProcess(index: number) { assembly.value.groups[index].processes.push({ name: '', persons: 0, teams: 0, production_qty: 0 }) }
function addBuzzBeeColorBoxTier() {
  if (sales.value.customer_quote_fields.buzzbee.color_box_tiers.length >= 2) return
  sales.value.customer_quote_fields.buzzbee.color_box_tiers.push({ quote_price_hkd: 0, fsc_price_hkd: 0, moq: '' })
}
function addDickieProductRow() {
  if (sales.value.customer_quote_fields.dickie.product_rows.length >= 8) return
  sales.value.customer_quote_fields.dickie.product_rows.push({ line_no: sales.value.customer_quote_fields.dickie.product_rows.length + 1, item_text_en: '', units_per_carton: '', carton_cbm: 0, color_box_size_cm: '', carton_size_cm: '', production_moq: '', price_40h_hkd: 0, price_20h_hkd: 0, price_lcl_hkd: 0 })
}
function addDickieRemarkLine() { sales.value.customer_quote_fields.dickie.remark_lines.push({ line_no: 0, text_en: '' }) }
function addDickieMaterialPrice() {
  if (sales.value.customer_quote_fields.dickie.material_prices_hkd.length >= 4) return
  sales.value.customer_quote_fields.dickie.material_prices_hkd.push({ material: '', price_hkd_lb: 0 })
}
function addCaixingCostRow() { sales.value.customer_quote_fields.caixing.cost_rows.push({ group: 'purchase', tax_tag: '', category: '', description: '', base_cost_hkd: 0, customer_cost_hkd: 0 }) }
</script>

<template>
  <div class="section-payload-form" :class="{ disabled }">
    <section class="payload-standard-notice">
      <strong>统一填入格式：Huaxing Demo</strong>
      <span>所有客户均使用同一套内部核价字段；客户名称仅决定最终报客价的输出模板。</span>
    </section>
    <template v-if="props.code === 'engineering'">
      <section class="payload-block">
        <header><div><strong>五金</strong><span>录入字段与辅助材料一致；“五金1.xlsx”仅导入相应字段，其他模板列不作映射。</span></div><button type="button" :disabled="disabled" @click="addEngineeringHardware"><Plus />新增五金</button></header>
        <div class="payload-table-scroll"><table class="engineeringHardware"><thead><tr><th>#</th><th>零件名称</th><th>规格</th><th>类别</th><th>用量</th><th>单价 RMB</th><th>单价 HKD（自动）</th><th>金额 HKD（自动）</th><th>税点 %</th><th>备注</th><th /></tr></thead><tbody><tr v-for="(row,index) in hardwareRows" :key="index"><td>{{ index + 1 }}</td><td><input v-model="row.item" :disabled="disabled" aria-label="五金零件名称"></td><td><input v-model="row.specification" :disabled="disabled" aria-label="五金规格"></td><td><select v-model="row.auxiliary_category" :disabled="disabled" aria-label="五金类别"><option v-for="category in engineeringMaterialCategories" :key="category" :value="category">{{ category }}</option></select></td><td><input v-model.number="row.quantity" :disabled="disabled" type="number" min="0" step="0.0001" aria-label="五金用量"></td><td><input v-model.number="row.unit_price_rmb" :disabled="disabled" type="number" min="0" step="0.0001" aria-label="五金单价 RMB"></td><td class="calculated-cell">{{ calculated(calculateEngineeringMaterialUnitHkd(row, props.rmbHkdRate)) }}</td><td class="calculated-cell">{{ calculated(calculateEngineeringMaterialAmountHkd(row, props.rmbHkdRate)) }}</td><td><input v-model.number="row.tax_rate_percent" :disabled="disabled" type="number" min="0" max="100" step="0.01" aria-label="五金税点"></td><td><input v-model="row.remark" :disabled="disabled" aria-label="五金备注"></td><td><button type="button" class="icon" :disabled="disabled" @click="removeEngineeringMaterial(row)"><Trash2 /></button></td></tr><tr v-if="!hardwareRows.length"><td colspan="11" class="empty">暂无五金明细，可新增或从五金报价单预览导入</td></tr></tbody><tfoot><tr><td colspan="7">五金成本汇总</td><td>HKD {{ calculated(hardwareTotal) }}</td><td colspan="3" /></tr></tfoot></table></div>
      </section>
      <section class="payload-block">
        <header><div><strong>辅助材料</strong><span>按类别记录零件、规格、用量、人民币单价和税点；港币金额不计损耗。</span></div><button type="button" :disabled="disabled" @click="addEngineeringAuxiliary"><Plus />新增辅助材料</button></header>
        <div class="payload-table-scroll"><table class="engineeringAuxiliary"><thead><tr><th>#</th><th>零件名称</th><th>规格</th><th>类别</th><th>用量</th><th>单价 RMB</th><th>单价 HKD（自动）</th><th>金额 HKD（自动）</th><th>税点 %</th><th>备注</th><th /></tr></thead><tbody><tr v-for="(row,index) in auxiliaryRows" :key="index"><td>{{ index + 1 }}</td><td><input v-model="row.item" :disabled="disabled" aria-label="辅助材料零件名称"></td><td><input v-model="row.specification" :disabled="disabled" aria-label="辅助材料规格"></td><td><select v-model="row.auxiliary_category" :disabled="disabled" aria-label="辅助材料类别"><option v-for="category in engineeringMaterialCategories" :key="category" :value="category">{{ category }}</option></select></td><td><input v-model.number="row.quantity" :disabled="disabled" type="number" min="0" step="0.0001" aria-label="辅助材料用量"></td><td><input v-model.number="row.unit_price_rmb" :disabled="disabled" type="number" min="0" step="0.0001" aria-label="辅助材料单价 RMB"></td><td class="calculated-cell">{{ calculated(calculateEngineeringMaterialUnitHkd(row, props.rmbHkdRate)) }}</td><td class="calculated-cell">{{ calculated(calculateEngineeringMaterialAmountHkd(row, props.rmbHkdRate)) }}</td><td><input v-model.number="row.tax_rate_percent" :disabled="disabled" type="number" min="0" max="100" step="0.01" aria-label="辅助材料税点"></td><td><input v-model="row.remark" :disabled="disabled" aria-label="辅助材料备注"></td><td><button type="button" class="icon" :disabled="disabled" @click="removeEngineeringMaterial(row)"><Trash2 /></button></td></tr><tr v-if="!auxiliaryRows.length"><td colspan="11" class="empty">暂无辅助材料明细</td></tr></tbody><tfoot><tr><td colspan="7">辅助材料成本汇总</td><td>HKD {{ calculated(auxiliaryTotal) }}</td><td colspan="3" /></tr></tfoot></table></div>
      </section>
      <section class="payload-block engineering-molds">
        <header><div><strong>模具资料</strong><span>字段按原内部报价模具表统一；模具价格为整套总价，模价 HKD 按本报价冻结汇率自动换算。</span></div><button type="button" :disabled="disabled" @click="addEngineeringMold"><Plus />新增模具</button></header>
        <div class="payload-table-scroll">
          <table class="extraWide engineeringMolds">
            <thead><tr><th>#</th><th>模具名称</th><th>模号</th><th>模胚类型</th><th>模具结构</th><th>材质</th><th>颜色</th><th>出模数</th><th>套数</th><th>净重 (g)</th><th>周期 (秒)</th><th>模具尺寸</th><th>图片</th><th>模具价格 RMB</th><th>模价 HKD（自动）</th><th>备注</th><th /></tr></thead>
            <tbody>
              <tr v-for="(row,index) in engineering.molds" :key="index">
                <td>{{ index + 1 }}</td>
                <td><textarea v-model="row.item" :disabled="disabled" rows="2" aria-label="模具名称" /></td>
                <td><input v-model="row.mold_no" :disabled="disabled" aria-label="模号"></td>
                <td><textarea v-model="row.mold_base_type" :disabled="disabled" rows="2" aria-label="模胚类型" /></td>
                <td><input v-model="row.structure" :disabled="disabled" aria-label="模具结构"></td>
                <td><input v-model="row.material" :disabled="disabled" aria-label="模具材质"></td>
                <td><input v-model="row.color" :disabled="disabled" aria-label="模具颜色"></td>
                <td><input v-model="row.cavity" :disabled="disabled" aria-label="出模数"></td>
                <td><input v-model.number="row.quantity" :disabled="disabled" type="number" min="0" step="1" aria-label="模具套数"></td>
                <td><input v-model.number="row.net_weight_g" :disabled="disabled" type="number" min="0" step="0.0001" aria-label="模具净重"></td>
                <td><input v-model.number="row.cycle_time_seconds" :disabled="disabled" type="number" min="0" step="0.01" aria-label="模具周期"></td>
                <td><input v-model="row.mold_size" :disabled="disabled" aria-label="模具尺寸"></td>
                <td><input v-model="row.image_reference" :disabled="disabled" placeholder="附件名称；图片在分段附件上传" aria-label="模具图片附件说明"></td>
                <td><input v-model.number="row.cost_rmb" :disabled="disabled" type="number" min="0" step="0.01" aria-label="模具价格 RMB"></td>
                <td class="calculated-cell">{{ calculated(calculateEngineeringMoldPriceHkd(row, props.rmbHkdRate)) }}</td>
                <td><textarea v-model="row.remark" :disabled="disabled" rows="2" aria-label="模具备注" /></td>
                <td><button type="button" class="icon" :disabled="disabled" @click="remove(engineering.molds,index)"><Trash2 /></button></td>
              </tr>
              <tr v-if="!engineering.molds.length"><td colspan="17" class="empty">暂无模具明细，可新增或从模具报价单预览导入</td></tr>
            </tbody>
            <tfoot v-if="engineering.molds.length"><tr><td colspan="13">模具报价小计（RMB→HKD {{ Number(props.rmbHkdRate || 0).toFixed(2) }}）</td><td>RMB {{ calculated(moldQuoteTotalRmb) }}</td><td>HKD {{ calculated(moldQuoteTotalHkd) }}</td><td colspan="2" /></tr></tfoot>
          </table>
        </div>
      </section>
      <section class="payload-block production-mold-costs">
        <header><div><strong>生产模具费用与分摊</strong><span>生产模费、手板费和测试费分别按套数分摊；服务端将三项每件 USD 分摊合并进入报价成本。</span></div><button type="button" :disabled="disabled" @click="addProductionMoldCost"><Plus />增加费用行</button></header>
        <div class="payload-table-scroll">
          <table class="productionMoldCosts">
            <thead><tr><th>模具名称</th><th>模价 RMB</th><th>模价 USD（自动）</th><th /></tr></thead>
            <tbody>
              <tr v-for="(row,index) in engineering.production_mold_costs" :key="index"><td><input v-model="row.item" :disabled="disabled" aria-label="生产模具费用名称"></td><td><input v-model.number="row.cost_rmb" :disabled="disabled" type="number" min="0" step="0.01" aria-label="生产模具费用 RMB"></td><td class="calculated-cell">{{ calculated(Number(row.cost_rmb || 0) / moldAllocation.rate) }}</td><td><button type="button" class="icon" :disabled="disabled" @click="remove(engineering.production_mold_costs,index)"><Trash2 /></button></td></tr>
              <tr v-if="!engineering.production_mold_costs.length"><td colspan="4" class="empty">暂无生产模具费用</td></tr>
            </tbody>
            <tfoot><tr><td>模具总计</td><td>RMB {{ calculated(moldAllocation.productionTotalRmb) }}</td><td>USD {{ calculated(moldAllocation.productionTotalUsd) }}</td><td /></tr></tfoot>
          </table>
        </div>
        <div class="inline-fields four mold-allocation-inputs">
          <label><span>客户补贴模费 USD</span><input v-model.number="engineering.customer_mold_subsidy_usd" :disabled="disabled" type="number" min="0" step="0.01" aria-label="客户补贴模费 USD"></label>
          <label><span>模费分摊套数</span><input v-model.number="engineering.amortization_qty" :disabled="disabled" type="number" min="1" step="1" aria-label="模费分摊套数"></label>
          <label><span>手板费总额 USD</span><input v-model.number="engineering.prototype_total_usd" :disabled="disabled" type="number" min="0" step="0.01" aria-label="手板费总额 USD"></label>
          <label><span>手板费分摊套数</span><input v-model.number="engineering.prototype_amortization_qty" :disabled="disabled" type="number" min="1" step="1" aria-label="手板费分摊套数"></label>
          <label><span>测试费总额 USD</span><input v-model.number="engineering.testing_total_usd" :disabled="disabled" type="number" min="0" step="0.01" aria-label="测试费总额 USD"></label>
          <label><span>测试费分摊套数</span><input v-model.number="engineering.testing_amortization_qty" :disabled="disabled" type="number" min="1" step="1" aria-label="测试费分摊套数"></label>
          <label><span>RMB→USD 汇率</span><input v-model.number="engineering.mold_fx_rmb_usd" :disabled="disabled" type="number" min="0.01" step="0.01" aria-label="生产模具 RMB USD 汇率"></label>
        </div>
        <div class="payload-table-scroll">
          <table class="moldAllocationSummary">
            <thead><tr><th>分摊项目</th><th>公式</th><th>每件 RMB</th><th>每件 USD</th></tr></thead>
            <tbody>
              <tr><td>生产模费</td><td>RMB 总额 ÷ {{ engineering.amortization_qty || 0 }}；USD =（RMB 总额 ÷ {{ moldAllocation.rate }} − 客补贴 USD）÷ 套数</td><td>{{ calculated(moldAllocation.moldShareRmb) }}</td><td>{{ calculated(moldAllocation.moldShareUsd) }}</td></tr>
              <tr><td>手板费</td><td>USD {{ engineering.prototype_total_usd || 0 }} ÷ {{ engineering.prototype_amortization_qty || 0 }} 套；RMB 按汇率反算</td><td>{{ calculated(moldAllocation.prototypeShareRmb) }}</td><td>{{ calculated(moldAllocation.prototypeShareUsd) }}</td></tr>
              <tr><td>测试费</td><td>USD {{ engineering.testing_total_usd || 0 }} ÷ {{ engineering.testing_amortization_qty || 0 }} 套；RMB 按汇率反算</td><td>{{ calculated(moldAllocation.testingShareRmb) }}</td><td>{{ calculated(moldAllocation.testingShareUsd) }}</td></tr>
            </tbody>
            <tfoot><tr><td colspan="2">每件分摊合计</td><td>RMB {{ calculated(moldAllocation.totalShareRmb) }}</td><td>USD {{ calculated(moldAllocation.totalShareUsd) }}</td></tr></tfoot>
          </table>
        </div>
      </section>
    </template>

    <template v-else-if="props.code === 'electronic'">
      <section class="payload-block"><header><div><strong>电子零件与子项</strong><span>父项和子项均按用量 × 港币单价计算</span></div><button type="button" :disabled="disabled" @click="addElectronicComponent"><Plus />新增零件</button></header><article v-for="(row,index) in electronic.components" :key="index" class="nested-card"><div class="nested-head"><strong>零件 {{ index+1 }}</strong><button type="button" class="icon" :disabled="disabled" @click="remove(electronic.components,index)"><Trash2 /></button></div><div class="inline-fields"><label><span>零件名称</span><input v-model="row.item" :disabled="disabled"></label><label><span>用量</span><input v-model.number="row.quantity" :disabled="disabled" type="number" min="0" step="0.0001"></label><label><span>单价 HKD</span><input v-model.number="row.unit_price_hkd" :disabled="disabled" type="number" min="0" step="0.0001"></label></div><div class="subhead"><span>绑定子项</span><button type="button" :disabled="disabled" @click="addElectronicChild(index)"><Plus />新增子项</button></div><div class="payload-table-scroll"><table><thead><tr><th>子项</th><th>用量</th><th>单价 HKD</th><th /></tr></thead><tbody><tr v-for="(child,childIndex) in row.children" :key="childIndex"><td><input v-model="child.item" :disabled="disabled"></td><td><input v-model.number="child.quantity" :disabled="disabled" type="number" min="0"></td><td><input v-model.number="child.unit_price_hkd" :disabled="disabled" type="number" min="0"></td><td><button type="button" class="icon" :disabled="disabled" @click="remove(row.children,childIndex)"><Trash2 /></button></td></tr></tbody></table></div></article></section>
      <section class="payload-block"><header><div><strong>加工、利润与税项</strong><span>利润率单位为百分比</span></div></header><div class="inline-fields four"><label><span>邦定 HKD</span><input v-model.number="electronic.bonding_hkd" :disabled="disabled" type="number" min="0"></label><label><span>SMT / 贴片 HKD</span><input v-model.number="electronic.smt_hkd" :disabled="disabled" type="number" min="0"></label><label><span>人工 HKD</span><input v-model.number="electronic.labor_hkd" :disabled="disabled" type="number" min="0"></label><label><span>测试维修 HKD</span><input v-model.number="electronic.testing_hkd" :disabled="disabled" type="number" min="0"></label><label><span>包装运输 HKD</span><input v-model.number="electronic.packaging_hkd" :disabled="disabled" type="number" min="0"></label><label><span>利润率 %</span><input v-model.number="electronic.profit_rate_percent" :disabled="disabled" type="number" min="0"></label><label><span>抵税差额 HKD</span><input v-model.number="electronic.tax_credit_difference_hkd" :disabled="disabled" type="number" min="0"></label></div></section>
    </template>

    <template v-else-if="props.code === 'molding'">
      <section class="payload-block"><header><div><strong>注塑明细</strong><span>材料与牌号须精确匹配参考快照，机型使用 A 码；迪士尼直转还须关联工程模号并填写 Cycle Time</span></div><button type="button" :disabled="disabled" @click="addInjection"><Plus />新增注塑</button></header><div class="payload-table-scroll"><table class="wide"><thead><tr><th>项目</th><th>材料</th><th>牌号</th><th>净重 g</th><th>损耗 %</th><th>机型 A码</th><th>套数</th><th>目标数</th><th>成品用量</th><template v-if="isDisney"><th>模号</th><th>Resin USD/kg</th><th>Cycle Time (s)</th><th>Labor USD/hr</th></template><th /></tr></thead><tbody><tr v-for="(row,index) in molding.injection_lines" :key="index"><td><input v-model="row.item" :disabled="disabled"></td><td><input v-model="row.material" :disabled="disabled"></td><td><input v-model="row.grade" :disabled="disabled"></td><td><input v-model.number="row.net_weight_g" :disabled="disabled" type="number" min="0"></td><td><input v-model.number="row.loss_rate_percent" :disabled="disabled" type="number" min="0"></td><td><input v-model="row.machine_code" :disabled="disabled" placeholder="例如 20A"></td><td><input v-model.number="row.sets" :disabled="disabled" type="number" min="0"></td><td><input v-model.number="row.target_output" :disabled="disabled" type="number" min="0"></td><td><input v-model.number="row.quantity" :disabled="disabled" type="number" min="0"></td><template v-if="isDisney"><td><input v-model="row.disney_mold_no" :disabled="disabled" aria-label="迪士尼注塑模号"></td><td><input v-model.number="row.disney_resin_cost_usd_kg" :disabled="disabled" type="number" min="0" step="0.01" aria-label="迪士尼树脂单价 USD/kg"></td><td><input v-model.number="row.disney_cycle_time_seconds" :disabled="disabled" type="number" min="0" aria-label="迪士尼 Cycle Time"></td><td><input v-model.number="row.disney_labor_rate_usd_hr" :disabled="disabled" type="number" min="0" step="0.01" aria-label="迪士尼机台小时费 USD"></td></template><td><button type="button" class="icon" :disabled="disabled" @click="remove(molding.injection_lines,index)"><Trash2 /></button></td></tr><tr v-if="!molding.injection_lines.length"><td :colspan="isDisney ? 14 : 10" class="empty">暂无注塑明细</td></tr></tbody></table></div></section>
      <section v-if="isCaixing" class="payload-block"><header><div><strong>彩星 Tool Plan</strong><span>客户字段原样进入塑胶/毛绒模板；Cycle、Cav.、Up、材料/啤工成本不可从内部总价反推</span></div><button type="button" :disabled="disabled" @click="addCaixingToolPlanRow"><Plus />新增 Tool Plan</button></header><div class="payload-table-scroll"><table class="extraWide caixingToolPlan"><thead><tr><th>Ref</th><th>Type</th><th>Tool No.</th><th>Tooling HKD</th><th>Description</th><th>SKU</th><th>Cav.</th><th>Up</th><th>Net Wt. g</th><th>Material Code</th><th>Material</th><th>Color</th><th>Material Cost</th><th>M/C Size</th><th>Cycle s</th><th>Process Cost</th><th /></tr></thead><tbody><tr v-for="(row,index) in molding.caixing_tool_plan_rows" :key="index"><td><input v-model="row.ref_no" :disabled="disabled" aria-label="彩星 Tool Plan Ref"></td><td><select v-model="row.process_type" :disabled="disabled" aria-label="彩星 Tool Plan Type"><option value="IN">IN</option><option value="BL">BL</option><option value="CP">CP</option><option value="DC">DC</option><option value="RC">RC</option></select></td><td><input v-model="row.tool_no" :disabled="disabled" aria-label="彩星 Tool Number"></td><td><input v-model.number="row.tooling_cost_hkd" :disabled="disabled" type="number" min="0" step="0.01" aria-label="彩星 Tooling Cost"></td><td><input v-model="row.description" :disabled="disabled" aria-label="彩星 Tool Description"></td><td><input v-model="row.sku_no" :disabled="disabled" aria-label="彩星 Tool SKU"></td><td><input v-model.number="row.cavities" :disabled="disabled" type="number" min="0" aria-label="彩星 Cavities"></td><td><input v-model.number="row.up" :disabled="disabled" type="number" min="0" aria-label="彩星 Up"></td><td><input v-model.number="row.net_weight_g" :disabled="disabled" type="number" min="0" step="0.001" aria-label="彩星 Net Weight"></td><td><input v-model.number="row.material_code" :disabled="disabled" type="number" min="0" aria-label="彩星 Material Code"></td><td><input v-model="row.material" :disabled="disabled" aria-label="彩星 Material"></td><td><input v-model="row.color" :disabled="disabled" aria-label="彩星 Color"></td><td><input v-model.number="row.material_cost_hkd" :disabled="disabled" type="number" min="0" step="0.0001" aria-label="彩星 Material Cost"></td><td><input v-model="row.machine_size" :disabled="disabled" aria-label="彩星 Machine Size"></td><td><input v-model.number="row.cycle_time_seconds" :disabled="disabled" type="number" min="0" step="0.01" aria-label="彩星 Cycle Time"></td><td><input v-model.number="row.process_cost_hkd" :disabled="disabled" type="number" min="0" step="0.0001" aria-label="彩星 Process Cost"></td><td><button type="button" class="icon" :disabled="disabled" @click="remove(molding.caixing_tool_plan_rows,index)"><Trash2 /></button></td></tr><tr v-if="!molding.caixing_tool_plan_rows.length"><td colspan="17" class="empty">未填写 Tool Plan 将阻断彩星 P4 接收</td></tr></tbody></table></div></section>
      <section class="payload-block"><header><div><strong>吹气明细</strong><span>材料价来自同一冻结参考快照</span></div><button type="button" :disabled="disabled" @click="addBlow"><Plus />新增吹气</button></header><div class="payload-table-scroll"><table class="wide"><thead><tr><th>项目</th><th>材料</th><th>牌号</th><th>预估料重 g</th><th>人工 HKD</th><th>披锋 HKD</th><th>利润倍率</th><th>成品用量</th><th /></tr></thead><tbody><tr v-for="(row,index) in molding.blow_lines" :key="index"><td><input v-model="row.item" :disabled="disabled"></td><td><input v-model="row.material" :disabled="disabled"></td><td><input v-model="row.grade" :disabled="disabled"></td><td><input v-model.number="row.estimated_weight_g" :disabled="disabled" type="number" min="0"></td><td><input v-model.number="row.labor_hkd" :disabled="disabled" type="number" min="0"></td><td><input v-model.number="row.burr_hkd" :disabled="disabled" type="number" min="0"></td><td><input v-model.number="row.profit_multiplier" :disabled="disabled" type="number" min="0" step="0.01"></td><td><input v-model.number="row.quantity" :disabled="disabled" type="number" min="0"></td><td><button type="button" class="icon" :disabled="disabled" @click="remove(molding.blow_lines,index)"><Trash2 /></button></td></tr><tr v-if="!molding.blow_lines.length"><td colspan="9" class="empty">暂无吹气明细</td></tr></tbody></table></div></section>
    </template>

    <template v-else-if="props.code === 'painting'">
      <section class="payload-block"><header><div><strong>七类喷油工序</strong><span>每类工序分别输入数量和港币单价</span></div><button type="button" :disabled="disabled" @click="addPainting"><Plus />新增喷油项目</button></header><div class="payload-table-scroll"><table class="painting"><thead><tr><th rowspan="2">项目</th><template v-for="code in operationCodes" :key="code"><th colspan="2">{{ paintingOperationLabels[code] }}</th></template><th rowspan="2" /></tr><tr><template v-for="code in operationCodes" :key="`${code}-sub`"><th>数量</th><th>单价</th></template></tr></thead><tbody><tr v-for="(row,index) in painting.rows" :key="index"><td><input v-model="row.item" :disabled="disabled"></td><template v-for="code in operationCodes" :key="code"><td><input v-model.number="row.operations[code].quantity" :disabled="disabled" type="number" min="0"></td><td><input v-model.number="row.operations[code].unit_price_hkd" :disabled="disabled" type="number" min="0"></td></template><td><button type="button" class="icon" :disabled="disabled" @click="remove(painting.rows,index)"><Trash2 /></button></td></tr><tr v-if="!painting.rows.length"><td colspan="16" class="empty">暂无喷油工序</td></tr></tbody></table></div></section>
      <section v-if="isDisney" class="payload-block"><header><div><strong>迪士尼 Decoration 工序</strong><span>客户模板按 Application Type、Rate per Op 和 # of Ops 输出；不得从内部喷油小计反推</span></div><button type="button" :disabled="disabled" @click="addDisneyDecoration"><Plus />新增装饰工序</button></header><div class="payload-table-scroll"><table><thead><tr><th>Application Type</th><th>Rate per Op USD</th><th># of Ops</th><th /></tr></thead><tbody><tr v-for="(row,index) in painting.disney_decorations" :key="index"><td><input v-model="row.application_type" :disabled="disabled" aria-label="迪士尼装饰工序"></td><td><input v-model.number="row.rate_per_op_usd" :disabled="disabled" type="number" min="0" step="0.0001" aria-label="迪士尼装饰单价 USD"></td><td><input v-model.number="row.operations" :disabled="disabled" type="number" min="0" aria-label="迪士尼装饰次数"></td><td><button type="button" class="icon" :disabled="disabled" @click="remove(painting.disney_decorations,index)"><Trash2 /></button></td></tr><tr v-if="!painting.disney_decorations.length"><td colspan="4" class="empty">存在喷油成本时，未填写客户 Decoration 工序将阻断 P4 接收</td></tr></tbody></table></div></section>
    </template>

    <template v-else-if="props.code === 'slush'">
      <section class="payload-block"><header><div><strong>搪胶成本明细</strong><span>行金额为数量 × 单价 HKD</span></div><button type="button" :disabled="disabled" @click="addSlush"><Plus />新增明细</button></header><div class="payload-table-scroll"><table><thead><tr><th>项目</th><th>数量</th><th>单价 HKD</th><th /></tr></thead><tbody><tr v-for="(row,index) in slush.lines" :key="index"><td><input v-model="row.item" :disabled="disabled"></td><td><input v-model.number="row.quantity" :disabled="disabled" type="number" min="0"></td><td><input v-model.number="row.unit_price_hkd" :disabled="disabled" type="number" min="0"></td><td><button type="button" class="icon" :disabled="disabled" @click="remove(slush.lines,index)"><Trash2 /></button></td></tr><tr v-if="!slush.lines.length"><td colspan="4" class="empty">暂无搪胶明细</td></tr></tbody></table></div></section>
    </template>

    <template v-else-if="props.code === 'sewing'">
      <section class="payload-block"><header><div><strong>车缝产品组</strong><span>“人工”已作为材料行时，服务端不会重复加产品组人工</span></div><button type="button" :disabled="disabled" @click="addSewingGroup"><Plus />新增产品组</button></header><article v-for="(group,index) in sewing.groups" :key="index" class="nested-card"><div class="nested-head"><strong>产品组 {{ index+1 }}</strong><button type="button" class="icon" :disabled="disabled" @click="remove(sewing.groups,index)"><Trash2 /></button></div><div class="inline-fields"><label><span>组名</span><input v-model="group.name" :disabled="disabled"></label><label><span>分类</span><select v-model="group.category" :disabled="disabled"><option value="clothes">车衣</option><option value="hair">车发</option></select></label><label><span>人工 RMB</span><input v-model.number="group.labor_rmb" :disabled="disabled" type="number" min="0"></label></div><div class="subhead"><span>物料</span><button type="button" :disabled="disabled" @click="addSewingMaterial(index)"><Plus />新增物料</button></div><div class="payload-table-scroll"><table><thead><tr><th>物料</th><th>用量</th><th>单价 RMB</th><th>码点</th><th /></tr></thead><tbody><tr v-for="(row,rowIndex) in group.materials" :key="rowIndex"><td><input v-model="row.item" :disabled="disabled"></td><td><input v-model.number="row.usage" :disabled="disabled" type="number" min="0"></td><td><input v-model.number="row.unit_price_rmb" :disabled="disabled" type="number" min="0"></td><td><input v-model.number="row.markup" :disabled="disabled" type="number" min="0"></td><td><button type="button" class="icon" :disabled="disabled" @click="remove(group.materials,rowIndex)"><Trash2 /></button></td></tr></tbody></table></div></article></section>
    </template>

    <template v-else-if="props.code === 'assembly'">
      <section class="payload-block"><header><div><strong>装配与包装产品组</strong><span>人工基数 × 人数 × 小组数 ÷ 生产量</span></div><button type="button" :disabled="disabled" @click="addAssemblyGroup"><Plus />新增产品组</button></header><div class="inline-fields"><label><span>人工基数 HKD</span><input v-model.number="assembly.labor_base_hkd" :disabled="disabled" type="number" min="0"></label></div><article v-for="(group,index) in assembly.groups" :key="index" class="nested-card"><div class="nested-head"><strong>产品组 {{ index+1 }}</strong><button type="button" class="icon" :disabled="disabled" @click="remove(assembly.groups,index)"><Trash2 /></button></div><div class="inline-fields"><label><span>组名</span><input v-model="group.name" :disabled="disabled"></label><label><span>分类</span><select v-model="group.category" :disabled="disabled"><option value="assembly">组装</option><option value="packaging">包装</option></select></label></div><div class="subhead"><span>工序</span><button type="button" :disabled="disabled" @click="addAssemblyProcess(index)"><Plus />新增工序</button></div><div class="payload-table-scroll"><table><thead><tr><th>工序</th><th>人数</th><th>小组数</th><th>生产量</th><th /></tr></thead><tbody><tr v-for="(row,rowIndex) in group.processes" :key="rowIndex"><td><input v-model="row.name" :disabled="disabled"></td><td><input v-model.number="row.persons" :disabled="disabled" type="number" min="0"></td><td><input v-model.number="row.teams" :disabled="disabled" type="number" min="0"></td><td><input v-model.number="row.production_qty" :disabled="disabled" type="number" min="0"></td><td><button type="button" class="icon" :disabled="disabled" @click="remove(group.processes,rowIndex)"><Trash2 /></button></td></tr></tbody></table></div></article></section>
    </template>

    <template v-else>
      <section class="payload-block sales-packaging-materials">
        <header>
          <div><strong>包装材料</strong><span>由业务部填写；RMB 单价按本报价冻结汇率自动换算 HKD，税点仅作明细记录。</span></div>
          <button type="button" :disabled="disabled" @click="addSalesPackagingMaterial"><Plus />新增包装材料</button>
        </header>
        <div class="payload-table-scroll">
          <table class="packagingMaterials">
            <thead><tr><th>#</th><th>零件名称</th><th>规格</th><th>类别</th><th>用量</th><th>单价 RMB</th><th>单价 HKD（自动）</th><th>成品金额 HKD（自动）</th><th>税点 %</th><th>备注</th><th /></tr></thead>
            <tbody>
              <tr v-for="(row,index) in sales.packaging_materials" :key="index">
                <td>{{ index + 1 }}</td>
                <td><input v-model="row.item" :disabled="disabled" aria-label="包装材料零件名称"></td>
                <td><input v-model="row.specification" :disabled="disabled" aria-label="包装材料规格"></td>
                <td><select v-model="row.category" :disabled="disabled" aria-label="包装材料类别"><option value="blister">吸塑</option><option value="color_box_inner_card">彩盒/内卡</option><option value="leaflet_manual">利宝/说明书</option><option value="other_purchase">其他外购</option></select></td>
                <td><input v-model.number="row.quantity" :disabled="disabled" type="number" min="0" step="0.0001" aria-label="包装材料用量"></td>
                <td><input v-model.number="row.unit_price_rmb" :disabled="disabled" type="number" min="0" step="0.0001" aria-label="包装材料单价 RMB"></td>
                <td class="calculated-cell">{{ calculated(calculatePackagingMaterialUnitHkd(row, props.rmbHkdRate)) }}</td>
                <td class="calculated-cell">{{ calculated(calculatePackagingMaterialAmountHkd(row, props.rmbHkdRate)) }}</td>
                <td><input v-model.number="row.tax_rate_percent" :disabled="disabled" type="number" min="0" max="100" step="0.01" aria-label="包装材料税点"></td>
                <td><input v-model="row.remark" :disabled="disabled" aria-label="包装材料备注"></td>
                <td><button type="button" class="icon" :disabled="disabled" @click="remove(sales.packaging_materials,index)"><Trash2 /></button></td>
              </tr>
              <tr v-if="!sales.packaging_materials.length"><td colspan="11" class="empty">暂无包装材料，可按需要新增</td></tr>
            </tbody>
            <tfoot v-if="sales.packaging_materials.length"><tr><td colspan="7">包装材料合计</td><td class="calculated-cell">HKD {{ calculated(packagingMaterialTotal) }}</td><td colspan="3" /></tr></tfoot>
          </table>
        </div>
      </section>
      <section class="payload-block sales-packaging">
        <header>
          <div><strong>纸箱计算与包装尺寸</strong><span>由业务部填写；工程部不再维护纸箱和平卡。纸箱尺寸会自动计算 CU.FT、箱价和平卡单件成本。</span></div>
          <button type="button" :disabled="disabled" @click="addSalesCarton"><Plus />新增纸箱</button>
        </header>
        <div class="inline-fields four packaging-base">
          <label><span>纸价系数（箱价基数）</span><input v-model.number="sales.paper_price_factor" :disabled="disabled" type="number" min="0.01" step="0.01" aria-label="纸价系数"></label>
          <label><span>平卡纸价系数（默认同箱价）</span><input v-model.number="flatCardPriceFactor" :disabled="disabled" type="number" min="0.01" step="0.01" aria-label="平卡纸价系数"></label>
        </div>
        <div class="dimension-grid">
          <article class="dimension-card">
            <strong>产品尺寸 (cm)</strong>
            <div class="inline-fields">
              <label><span>长 L</span><input v-model.number="sales.product_size_cm.length" :disabled="disabled" type="number" min="0" step="0.01" aria-label="产品长度 CM"></label>
              <label><span>宽 W</span><input v-model.number="sales.product_size_cm.width" :disabled="disabled" type="number" min="0" step="0.01" aria-label="产品宽度 CM"></label>
              <label><span>高 H</span><input v-model.number="sales.product_size_cm.height" :disabled="disabled" type="number" min="0" step="0.01" aria-label="产品高度 CM"></label>
            </div>
          </article>
          <article class="dimension-card">
            <strong>彩盒尺寸 (cm)</strong>
            <div class="inline-fields">
              <label><span>长 L</span><input v-model.number="sales.color_box_size_cm.length" :disabled="disabled" type="number" min="0" step="0.01" aria-label="彩盒长度 CM"></label>
              <label><span>宽 W</span><input v-model.number="sales.color_box_size_cm.width" :disabled="disabled" type="number" min="0" step="0.01" aria-label="彩盒宽度 CM"></label>
              <label><span>高 H</span><input v-model.number="sales.color_box_size_cm.height" :disabled="disabled" type="number" min="0" step="0.01" aria-label="彩盒高度 CM"></label>
            </div>
          </article>
        </div>
        <article v-for="(carton,index) in sales.cartons" :key="index" class="nested-card carton-card">
          <div class="nested-head"><strong>纸箱 {{ index + 1 }}</strong><button type="button" class="icon" :disabled="disabled" @click="remove(sales.cartons,index)"><Trash2 /></button></div>
          <div class="inline-fields five">
            <label><span>纸箱名称</span><input v-model="carton.item" :disabled="disabled" aria-label="纸箱名称"></label>
            <label><span>长 L (in)</span><input v-model.number="carton.length_in" :disabled="disabled" type="number" min="0" step="0.01" aria-label="纸箱长度 IN"></label>
            <label><span>宽 W (in)</span><input v-model.number="carton.width_in" :disabled="disabled" type="number" min="0" step="0.01" aria-label="纸箱宽度 IN"></label>
            <label><span>高 H (in)</span><input v-model.number="carton.height_in" :disabled="disabled" type="number" min="0" step="0.01" aria-label="纸箱高度 IN"></label>
            <label><span>一箱装的个数</span><input v-model.number="carton.qty_per_carton" :disabled="disabled" type="number" min="1" step="1" aria-label="一箱装的个数"></label>
          </div>
          <div class="calculation-strip">
            <span><b>CU.FT</b> {{ calculated(calculateCartonCuft(carton)) }}</span>
            <span><b>箱价 HKD</b> {{ calculated(calculateCartonPriceHkd(carton, sales.paper_price_factor)) }}</span>
            <span><b>平卡合计 HKD</b> {{ calculated(flatCardTotal(index)) }}</span>
            <span><b>单件纸箱成本 HKD</b> {{ calculated(calculateCartonUnitCostHkd(carton, sales.paper_price_factor, flatCardPriceFactor)) }}</span>
            <span><b>每箱数量</b> {{ carton.qty_per_carton || 0 }}</span>
          </div>
          <div class="subhead"><span>配的平卡 (inch)</span><button type="button" :disabled="disabled" @click="addSalesFlatCard(index)"><Plus />新增平卡</button></div>
          <div class="payload-table-scroll"><table><thead><tr><th>名称</th><th>长 L (in)</th><th>宽 W (in)</th><th>平卡价 HKD（自动）</th><th /></tr></thead><tbody><tr v-for="(flat,flatIndex) in carton.flat_cards" :key="flatIndex"><td><input v-model="flat.name" :disabled="disabled" aria-label="平卡名称"></td><td><input v-model.number="flat.length_in" :disabled="disabled" type="number" min="0" step="0.01" aria-label="平卡长度 IN"></td><td><input v-model.number="flat.width_in" :disabled="disabled" type="number" min="0" step="0.01" aria-label="平卡宽度 IN"></td><td class="calculated-cell">{{ calculated(calculateFlatCardPriceHkd(flat, flatCardPriceFactor)) }}</td><td><button type="button" class="icon" :disabled="disabled" @click="remove(carton.flat_cards,flatIndex)"><Trash2 /></button></td></tr><tr v-if="!carton.flat_cards.length"><td colspan="5" class="empty">暂无平卡，可按需要新增</td></tr></tbody></table></div>
        </article>
        <div v-if="!sales.cartons.length" class="empty packaging-empty">暂无纸箱，请新增纸箱后填写尺寸和每箱数量</div>
      </section>
      <section class="payload-block sales-freight">
        <header>
          <div><strong>运费计算</strong><span>柜/车容量及运费可调整；主纸箱 CU.FT 和每箱数量直接读取上方纸箱资料，不重复填写。</span></div>
          <label class="freight-status-toggle" :class="{ inactive: !sales.freight_calc.enabled }">
            <input v-model="sales.freight_calc.enabled" :disabled="disabled" type="checkbox" aria-label="启用运费计算">
            <span>{{ sales.freight_calc.enabled ? '计算运费' : '客户自提' }}</span>
          </label>
        </header>
        <div v-if="!sales.freight_calc.enabled" class="freight-disabled-notice">
          <strong>客户自提，已暂时取消运费计算</strong>
          <span>不会生成运费权威快照，也不计入成本；容量和费用原值已保留，重新开启即可继续计算。</span>
        </div>
        <template v-else>
          <div v-if="primaryCarton" class="freight-source-strip">
            <span><b>数据来源</b> {{ primaryCarton.item || '纸箱 1' }}</span>
            <span><b>主纸箱 CU.FT</b> {{ calculated(freightSourceCuft) }}</span>
            <span><b>每箱数量</b> {{ primaryCarton.qty_per_carton || 0 }} PCS</span>
          </div>
          <div v-else class="freight-source-strip freight-source-missing">请先在“纸箱计算与包装尺寸”新增主纸箱，运费结果将自动联动。</div>
          <div class="inline-fields four freight-capacity-fields">
            <label v-for="capacity in salesFreightCapacityDefinitions" :key="capacity.key">
              <span>{{ capacity.label }}（CUFT，整数）</span>
              <input v-model.number="sales.freight_calc[capacity.key]" :disabled="disabled" type="number" min="1" step="1" :aria-label="capacity.label" @blur="normalizeFreightCapacity(capacity.key)">
            </label>
          </div>
          <div class="payload-table-scroll">
            <table class="freightTable">
              <thead><tr><th>运输方案</th><th>柜/车容量 CUFT</th><th>运费 + 吊柜费 HKD</th><th>总箱数（自动）</th><th>运费 + 吊柜 HKD/PCS（自动）</th></tr></thead>
              <tbody>
                <tr v-for="option in freightOptions" :key="option.key">
                  <td><strong>{{ option.label }}</strong><span class="freight-fee-label">{{ option.feeLabel }}</span></td>
                  <td class="calculated-cell">{{ whole(option.capacityCuft) }}</td>
                  <td><input v-model.number="sales.freight_calc[option.key]" :disabled="disabled" type="number" min="0" step="1" :aria-label="option.feeLabel"></td>
                  <td class="calculated-cell">{{ option.totalCartons || '—' }}</td>
                  <td class="calculated-cell">{{ option.totalCartons ? calculated(option.perPieceHkd) : '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="freight-formula-note">
            <strong>公式</strong>
            <span>总箱数 = ROUND(柜/车容量 ÷ 主纸箱 CU.FT)；HKD/PCS = 运费及吊柜费 ÷ 总箱数 ÷ 每箱数量。</span>
            <span>八个方案是备选参考，不重复累加到业务成本小计；最终选择的出货方案供报客价使用。</span>
          </div>
        </template>
      </section>
      <section v-if="isCaixing" class="payload-block"><header><div><strong>彩星客户报价抬头与外箱</strong><span>塑胶/毛绒类型决定专用模板；Item、日期、CU.FT/CBM、Pcs/Shipper 与纸箱价必须显式填写</span></div></header><div class="inline-fields four"><label><span>产品类型</span><select v-model="sales.customer_quote_fields.caixing.product_type" :disabled="disabled" aria-label="彩星产品类型"><option value="plastic">塑胶</option><option value="plush">毛绒</option></select></label><label><span>Item No.</span><input v-model="sales.customer_quote_fields.caixing.item_number" :disabled="disabled" aria-label="彩星 Item Number"></label><label><span>Item Description</span><input v-model="sales.customer_quote_fields.caixing.item_name" :disabled="disabled" aria-label="彩星 Item Description"></label><label><span>Quote Date</span><input v-model="sales.customer_quote_fields.caixing.quote_date" :disabled="disabled" type="date" aria-label="彩星 Quote Date"></label><label><span>Carton L (in)</span><input v-model.number="sales.customer_quote_fields.caixing.carton_length_in" :disabled="disabled" type="number" min="0" step="0.001" aria-label="彩星 Carton Length"></label><label><span>Carton W (in)</span><input v-model.number="sales.customer_quote_fields.caixing.carton_width_in" :disabled="disabled" type="number" min="0" step="0.001" aria-label="彩星 Carton Width"></label><label><span>Carton H (in)</span><input v-model.number="sales.customer_quote_fields.caixing.carton_height_in" :disabled="disabled" type="number" min="0" step="0.001" aria-label="彩星 Carton Height"></label><label><span>CU.FT</span><input v-model.number="sales.customer_quote_fields.caixing.carton_cuft" :disabled="disabled" type="number" min="0" step="0.0001" aria-label="彩星 Carton CUFT"></label><label><span>CBM</span><input v-model.number="sales.customer_quote_fields.caixing.carton_cbm" :disabled="disabled" type="number" min="0" step="0.0001" aria-label="彩星 Carton CBM"></label><label><span>Pcs / Shipper</span><input v-model.number="sales.customer_quote_fields.caixing.pcs_per_carton" :disabled="disabled" type="number" min="0" aria-label="彩星 Pcs Per Shipper"></label><label><span>Carton Price HKD</span><input v-model.number="sales.customer_quote_fields.caixing.carton_price_hkd" :disabled="disabled" type="number" min="0" step="0.0001" aria-label="彩星 Carton Price"></label></div></section>
      <section v-if="isCaixing" class="payload-block"><header><div><strong>彩星塑胶/毛绒模板分组</strong><span>每行必须选择客户模板 Group；转换器只按该字段落表，不再用中文类别猜测 Purchase、Packing、Fabric 或工序</span></div><button type="button" :disabled="disabled" @click="addCaixingCostRow"><Plus />新增分组行</button></header><div class="payload-table-scroll"><table class="extraWide"><thead><tr><th>Group</th><th>税标记</th><th>内部类别</th><th>Description</th><th>内部成本 HKD</th><th>客户成本 HKD</th><th /></tr></thead><tbody><tr v-for="(row,index) in sales.customer_quote_fields.caixing.cost_rows" :key="index"><td><select v-model="row.group" :disabled="disabled" aria-label="彩星 Cost Group"><option value="special">Special Material</option><option value="electronic">Electronic</option><option value="purchase">Purchase</option><option value="packing">Packing</option><option value="carton">Carton（外箱资料另填）</option><option value="fabric">Fabric</option><option value="spraying">Spraying</option><option value="tampo">Tampo</option><option value="assembly">Assembly Labor</option><option value="packout">Packout Labor</option><option value="rooting">Hair Rooting</option><option value="sewing">Sewing / Handfinish</option><option value="special_offer">Special Offer</option></select></td><td><input v-model="row.tax_tag" :disabled="disabled" aria-label="彩星 Tax Tag"></td><td><input v-model="row.category" :disabled="disabled" aria-label="彩星 Cost Category"></td><td><input v-model="row.description" :disabled="disabled" aria-label="彩星 Cost Description"></td><td><input v-model.number="row.base_cost_hkd" :disabled="disabled" type="number" min="0" step="0.0001" aria-label="彩星 Base Cost"></td><td><input v-model.number="row.customer_cost_hkd" :disabled="disabled" type="number" min="0" step="0.0001" aria-label="彩星 Customer Cost"></td><td><button type="button" class="icon" :disabled="disabled" @click="remove(sales.customer_quote_fields.caixing.cost_rows,index)"><Trash2 /></button></td></tr><tr v-if="!sales.customer_quote_fields.caixing.cost_rows.length"><td colspan="7" class="empty">未填写客户模板分组将阻断彩星 P4 接收</td></tr></tbody></table></div></section>
      <section v-if="isBuzzBee" class="payload-block"><header><div><strong>BuzzBee 彩盒客户分档</strong><span>真实 P4 直转必须完整填写两档整盒彩盒价、FSC 价和 MOQ；输出仍按客户规则折算并写入 FSC = 彩盒价 × 1.03</span></div><button v-if="sales.customer_quote_fields.buzzbee.color_box_tiers.length < 2" type="button" :disabled="disabled" @click="addBuzzBeeColorBoxTier"><Plus />新增分档</button></header><div class="payload-table-scroll"><table><thead><tr><th>分档</th><th>整箱报客彩盒价 HKD</th><th>整箱 FSC 价 HKD</th><th>MOQ</th><th /></tr></thead><tbody><tr v-for="(row,index) in sales.customer_quote_fields.buzzbee.color_box_tiers" :key="index"><td>第 {{ index + 1 }} 档</td><td><input v-model.number="row.quote_price_hkd" :disabled="disabled" type="number" min="0" step="0.0001" :aria-label="`BuzzBee 第 ${index + 1} 档彩盒价`"></td><td><input v-model.number="row.fsc_price_hkd" :disabled="disabled" type="number" min="0" step="0.0001" :aria-label="`BuzzBee 第 ${index + 1} 档 FSC 价`"></td><td><input v-model="row.moq" :disabled="disabled" :aria-label="`BuzzBee 第 ${index + 1} 档 MOQ`" placeholder="例如 MOQ3000"></td><td><button type="button" class="icon" :disabled="disabled" @click="remove(sales.customer_quote_fields.buzzbee.color_box_tiers,index)"><Trash2 /></button></td></tr><tr v-if="!sales.customer_quote_fields.buzzbee.color_box_tiers.length"><td colspan="5" class="empty">尚未填写；存在彩盒时，未完整填写两档将阻断 P4 接收</td></tr></tbody></table></div></section>
      <section v-if="isDisney" class="payload-block"><header><div><strong>迪士尼客户报价字段</strong><span>Item Number、报价日期/版本及 3K/5K/10K 三档必须完整；这些值只用于客户模板，不参与内部成本公式</span></div></header><div class="inline-fields four"><label><span>Item Number</span><input v-model="sales.customer_quote_fields.disney.item_number" :disabled="disabled" aria-label="迪士尼 Item Number"></label><label><span>报价日期</span><input v-model="sales.customer_quote_fields.disney.quote_date" :disabled="disabled" type="date" aria-label="迪士尼报价日期"></label><label><span>Revision</span><input v-model.number="sales.customer_quote_fields.disney.revision" :disabled="disabled" type="number" min="0" aria-label="迪士尼 Revision"></label><label><span>最低 MOQ</span><input v-model.number="sales.customer_quote_fields.disney.minimum_order_qty" :disabled="disabled" type="number" min="0" aria-label="迪士尼最低 MOQ"></label><label><span>3K 报价 USD</span><input v-model.number="sales.customer_quote_fields.disney.moq_prices_usd.qty_3000" :disabled="disabled" type="number" min="0" step="0.01" aria-label="迪士尼 3K 报价"></label><label><span>5K 报价 USD</span><input v-model.number="sales.customer_quote_fields.disney.moq_prices_usd.qty_5000" :disabled="disabled" type="number" min="0" step="0.01" aria-label="迪士尼 5K 报价"></label><label><span>10K 报价 USD</span><input v-model.number="sales.customer_quote_fields.disney.moq_prices_usd.qty_10000" :disabled="disabled" type="number" min="0" step="0.01" aria-label="迪士尼 10K 报价"></label><label><span>Transportation USD</span><input v-model.number="sales.customer_quote_fields.disney.transportation_usd" :disabled="disabled" type="number" min="0" step="0.001" aria-label="迪士尼运输费 USD"></label><label><span>Model USD</span><input v-model.number="sales.customer_quote_fields.disney.model_cost_usd" :disabled="disabled" type="number" min="0" step="0.01" aria-label="迪士尼手办费 USD"></label><label><span>Set Up Charge USD</span><input v-model.number="sales.customer_quote_fields.disney.setup_charge_usd" :disabled="disabled" type="number" min="0" step="0.01" aria-label="迪士尼设置费 USD"></label></div></section>
      <section v-if="isDickie" class="payload-block"><header><div><strong>Dickie 总表抬头与交模条款</strong><span>客户、日期、英文字款和时间条款将原样进入 Dickie 总表/Quotation，不参与内部成本公式</span></div></header><div class="inline-fields four"><label><span>Client</span><input v-model="sales.customer_quote_fields.dickie.client_name" :disabled="disabled" aria-label="Dickie Client"></label><label><span>Quote Date</span><input v-model="sales.customer_quote_fields.dickie.quote_date" :disabled="disabled" type="date" aria-label="Dickie Quote Date"></label><label><span>Attn</span><input v-model="sales.customer_quote_fields.dickie.attention" :disabled="disabled" aria-label="Dickie Attention"></label><label><span>Revision</span><input v-model="sales.customer_quote_fields.dickie.revision" :disabled="disabled" aria-label="Dickie Revision"></label><label><span>From</span><input v-model="sales.customer_quote_fields.dickie.from_name" :disabled="disabled" aria-label="Dickie From"></label><label><span>Project Name (EN)</span><input v-model="sales.customer_quote_fields.dickie.project_name_en" :disabled="disabled" aria-label="Dickie Project Name English"></label><label><span>First Shot Time</span><input v-model="sales.customer_quote_fields.dickie.first_shot_time" :disabled="disabled" aria-label="Dickie First Shot Time" placeholder="例如 45 Working Days"></label><label><span>Finish Time</span><input v-model="sales.customer_quote_fields.dickie.finish_time" :disabled="disabled" aria-label="Dickie Finish Time" placeholder="例如 75 Working Days"></label></div></section>
      <section v-if="isDickie" class="payload-block"><header><div><strong>Dickie 总表产品行</strong><span>最多 8 行；英文 ITEM、装箱资料、MOQ 与三种运输报价必须完整</span></div><button v-if="sales.customer_quote_fields.dickie.product_rows.length < 8" type="button" :disabled="disabled" @click="addDickieProductRow"><Plus />新增产品行</button></header><div class="payload-table-scroll"><table class="extraWide"><thead><tr><th>NO.</th><th>ITEM (EN)</th><th>Units/Carton</th><th>Carton CBM</th><th>Color Box (cm)</th><th>Carton Size (cm)</th><th>Production MOQ</th><th>40' HK/YT HKD</th><th>20' HK/YT HKD</th><th>LCL HKD</th><th /></tr></thead><tbody><tr v-for="(row,index) in sales.customer_quote_fields.dickie.product_rows" :key="index"><td><input v-model.number="row.line_no" :disabled="disabled" type="number" min="0" aria-label="Dickie Product Line"></td><td><textarea v-model="row.item_text_en" :disabled="disabled" rows="2" aria-label="Dickie Product English"></textarea></td><td><input v-model="row.units_per_carton" :disabled="disabled" aria-label="Dickie Units Per Carton"></td><td><input v-model.number="row.carton_cbm" :disabled="disabled" type="number" min="0" step="0.001" aria-label="Dickie Carton CBM"></td><td><input v-model="row.color_box_size_cm" :disabled="disabled" aria-label="Dickie Color Box Size"></td><td><input v-model="row.carton_size_cm" :disabled="disabled" aria-label="Dickie Carton Size"></td><td><input v-model="row.production_moq" :disabled="disabled" aria-label="Dickie Production MOQ"></td><td><input v-model.number="row.price_40h_hkd" :disabled="disabled" type="number" min="0" step="0.01" aria-label="Dickie 40 Foot Price"></td><td><input v-model.number="row.price_20h_hkd" :disabled="disabled" type="number" min="0" step="0.01" aria-label="Dickie 20 Foot Price"></td><td><input v-model.number="row.price_lcl_hkd" :disabled="disabled" type="number" min="0" step="0.01" aria-label="Dickie LCL Price"></td><td><button type="button" class="icon" :disabled="disabled" @click="remove(sales.customer_quote_fields.dickie.product_rows,index)"><Trash2 /></button></td></tr><tr v-if="!sales.customer_quote_fields.dickie.product_rows.length"><td colspan="11" class="empty">未填写总表产品行将阻断 P4 接收</td></tr></tbody></table></div></section>
      <section v-if="isDickie" class="payload-block"><header><div><strong>Dickie 英文备注与材料价</strong><span>法规、付款、知识产权等英文条款必须显式填写，P4 不从中文猜译</span></div><button type="button" :disabled="disabled" @click="addDickieRemarkLine"><Plus />新增备注</button></header><div class="payload-table-scroll"><table><thead><tr><th>编号（汇率条款可填 0）</th><th>English Remark</th><th /></tr></thead><tbody><tr v-for="(row,index) in sales.customer_quote_fields.dickie.remark_lines" :key="index"><td><input v-model.number="row.line_no" :disabled="disabled" type="number" min="0" aria-label="Dickie Remark Line"></td><td><textarea v-model="row.text_en" :disabled="disabled" rows="2" aria-label="Dickie English Remark"></textarea></td><td><button type="button" class="icon" :disabled="disabled" @click="remove(sales.customer_quote_fields.dickie.remark_lines,index)"><Trash2 /></button></td></tr><tr v-if="!sales.customer_quote_fields.dickie.remark_lines.length"><td colspan="3" class="empty">英文法规/付款条款为空将阻断 P4 接收</td></tr></tbody></table></div><div class="subhead"><span>Plastic Quotation (HK$/LB)，最多 4 项</span><button v-if="sales.customer_quote_fields.dickie.material_prices_hkd.length < 4" type="button" :disabled="disabled" @click="addDickieMaterialPrice"><Plus />新增材料价</button></div><div class="payload-table-scroll"><table><thead><tr><th>Type</th><th>Cost HKD/LB</th><th /></tr></thead><tbody><tr v-for="(row,index) in sales.customer_quote_fields.dickie.material_prices_hkd" :key="index"><td><input v-model="row.material" :disabled="disabled" aria-label="Dickie Material Type"></td><td><input v-model.number="row.price_hkd_lb" :disabled="disabled" type="number" min="0" step="0.01" aria-label="Dickie Material Cost"></td><td><button type="button" class="icon" :disabled="disabled" @click="remove(sales.customer_quote_fields.dickie.material_prices_hkd,index)"><Trash2 /></button></td></tr></tbody></table></div></section>
    </template>
  </div>
</template>

<style scoped>
.section-payload-form{display:grid;gap:12px;padding:12px;background:#f8fafc}.payload-standard-notice{display:flex;align-items:center;gap:10px;border:1px solid #99f6e4;border-radius:10px;background:#f0fdfa;padding:10px 12px}.payload-standard-notice strong{flex:0 0 auto;color:#0f766e;font-size:13px}.payload-standard-notice span{color:#475569;font-size:12px}.payload-block{overflow:hidden;border:1px solid #dbe5ea;border-radius:11px;background:#fff}.payload-block>header{display:flex;align-items:center;justify-content:space-between;gap:12px;border-bottom:1px solid #e2e8f0;padding:11px 12px;background:#f8fafc}.payload-block>header>div{display:grid}.payload-block header strong{color:#334155;font-size:13px}.payload-block header span{margin-top:2px;color:#64748b;font-size:11px}.payload-block button,.subhead button{display:inline-flex;min-height:32px;align-items:center;gap:5px;border:1px solid #99f6e4;border-radius:8px;background:#f0fdfa;padding:0 10px;color:#0f766e;font-size:12px;font-weight:800}.payload-block button svg,.subhead button svg{width:14px;height:14px}.payload-block button:disabled{cursor:not-allowed;opacity:.4}.payload-table-scroll{overflow:auto}.payload-table-scroll table{width:100%;min-width:620px;border-collapse:collapse}.payload-table-scroll table.wide{min-width:1050px}.payload-table-scroll table.extraWide{min-width:1850px}.payload-table-scroll table.caixingToolPlan{min-width:2700px}.payload-table-scroll table.painting{min-width:1500px}.payload-table-scroll th{background:#eef2f6;padding:8px;color:#64748b;font-size:11px;text-align:left;white-space:nowrap}.payload-table-scroll td{border-top:1px solid #eef2f6;padding:6px}.payload-table-scroll input,.payload-table-scroll select,.payload-table-scroll textarea,.inline-fields input,.inline-fields select{width:100%;min-width:70px;border:1px solid #dbe5ea;border-radius:7px;background:#fff;padding:0 8px;color:#334155;font-size:13px}.payload-table-scroll input,.payload-table-scroll select,.inline-fields input,.inline-fields select{height:34px}.payload-table-scroll textarea{min-height:52px;padding-block:7px;resize:vertical}.payload-table-scroll input:focus,.payload-table-scroll select:focus,.payload-table-scroll textarea:focus,.inline-fields input:focus,.inline-fields select:focus{border-color:#14b8a6;outline:2px solid rgb(20 184 166/.12)}.payload-table-scroll input:disabled,.payload-table-scroll select:disabled,.payload-table-scroll textarea:disabled,.inline-fields input:disabled,.inline-fields select:disabled{background:#f8fafc;color:#64748b}.payload-table-scroll .icon,.nested-head .icon{display:grid;width:30px;min-height:30px;place-items:center;border-color:transparent;background:transparent;padding:0;color:#94a3b8}.payload-table-scroll .icon:hover:not(:disabled),.nested-head .icon:hover:not(:disabled){background:#fef2f2;color:#dc2626}.empty{padding:22px!important;color:#94a3b8;text-align:center;font-size:12px}.inline-fields{display:grid;grid-template-columns:repeat(3,minmax(150px,1fr));gap:10px;padding:12px}.inline-fields.four{grid-template-columns:repeat(4,minmax(130px,1fr))}.inline-fields.five{grid-template-columns:repeat(5,minmax(110px,1fr));padding:0}.inline-fields label{display:grid;gap:5px}.inline-fields label span{color:#64748b;font-size:11px;font-weight:700}.nested-card{margin:10px;border:1px solid #e2e8f0;border-radius:9px;background:#fff}.nested-head,.subhead{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:8px 10px}.nested-head{border-bottom:1px solid #eef2f6;background:#f8fafc}.nested-head strong{color:#475569;font-size:12px}.subhead{border-top:1px solid #eef2f6}.subhead span{color:#475569;font-size:11px;font-weight:800}.subhead button{min-height:28px;border-color:#dbe5ea;background:#fff;color:#475569;font-size:11px}.disabled{--form-disabled:1}
.payload-table-scroll table.packagingMaterials{min-width:1450px}.payload-table-scroll tfoot td{border-top:1px solid #99f6e4;background:#f0fdfa;color:#475569;font-size:12px;font-weight:800}.packaging-base{padding-bottom:4px}.dimension-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;padding:4px 12px 10px}.dimension-card{overflow:hidden;border:1px solid #e2e8f0;border-radius:9px;background:#f8fafc}.dimension-card>strong{display:block;padding:9px 12px 0;color:#475569;font-size:12px}.dimension-card .inline-fields{padding-top:8px}.carton-card .inline-fields{padding:10px}.calculation-strip{display:flex;flex-wrap:wrap;gap:10px;margin:0 10px 10px;border:1px solid #fde68a;border-radius:8px;background:#fffbeb;padding:10px;color:#475569;font-size:12px}.calculation-strip span{display:inline-flex;gap:5px}.calculation-strip b,.calculated-cell{color:#0f766e;font-weight:800}.packaging-empty{margin:0 12px 12px;border:1px dashed #cbd5e1;border-radius:9px}
.payload-table-scroll table.engineeringHardware,.payload-table-scroll table.engineeringAuxiliary{min-width:1500px}.payload-table-scroll table.engineeringMolds{min-width:2650px}.payload-table-scroll table.productionMoldCosts{min-width:760px}.payload-table-scroll table.moldAllocationSummary{min-width:920px}.moldAllocationSummary th:nth-child(2),.moldAllocationSummary td:nth-child(2){min-width:430px}.mold-allocation-inputs{border-top:1px solid #eef2f6;background:#f8fafc}
.freight-source-strip{display:flex;flex-wrap:wrap;gap:18px;margin:12px 12px 0;border:1px solid #99f6e4;border-radius:9px;background:#f0fdfa;padding:10px 12px;color:#475569;font-size:12px}.freight-source-strip b{color:#0f766e}.freight-source-missing{border-style:dashed;border-color:#cbd5e1;background:#f8fafc;color:#94a3b8}.freight-capacity-fields{padding-bottom:10px}.payload-table-scroll table.freightTable{min-width:920px}.freightTable td:first-child strong,.freight-fee-label{display:block}.freight-fee-label{margin-top:2px;color:#94a3b8;font-size:10px}.freight-formula-note{display:grid;grid-template-columns:auto 1fr;gap:4px 10px;border-top:1px solid #e2e8f0;background:#f8fafc;padding:10px 12px;color:#64748b;font-size:11px}.freight-formula-note strong{grid-row:1/3;color:#0f766e}.freight-formula-note span{line-height:1.5}
.freight-status-toggle{display:inline-flex;min-height:32px;align-items:center;gap:7px;border:1px solid #5eead4;border-radius:999px;background:#f0fdfa;padding:0 11px;color:#0f766e;cursor:pointer}.freight-status-toggle.inactive{border-color:#cbd5e1;background:#fff;color:#64748b}.freight-status-toggle input{width:14px;height:14px;accent-color:#0f766e}.freight-status-toggle span{margin:0!important;color:inherit!important;font-size:12px!important;font-weight:800}.freight-disabled-notice{display:grid;gap:4px;margin:12px;border:1px dashed #cbd5e1;border-radius:9px;background:#f8fafc;padding:14px}.freight-disabled-notice strong{color:#475569;font-size:12px}.freight-disabled-notice span{color:#64748b;font-size:11px;line-height:1.5}
@media(max-width:900px){.inline-fields,.inline-fields.four,.inline-fields.five,.dimension-grid{grid-template-columns:1fr 1fr}}
@media(max-width:600px){.inline-fields,.inline-fields.four,.inline-fields.five,.dimension-grid{grid-template-columns:1fr}.payload-block>header{align-items:flex-start;flex-direction:column}}
</style>
