<script setup lang="ts">
import { computed } from 'vue'
import { Button } from '@/components/ui/button'
import { createDickieMapping, createDickieOffer, DICKIE_FIXED_MATERIALS, DICKIE_FIXED_REMARKS, type DickieOffer } from '@/lib/dickieQuote'
import type { SalesPayload, SalesFreightReferenceRoute } from '@/lib/internalQuoteSectionPayload'

const props = defineProps<{ sales: SalesPayload; routes: SalesFreightReferenceRoute[]; disabled?: boolean }>()
const mapping = computed(() => props.sales.customer_quote_fields.dickie.mapping)
const tiers = computed(() => props.sales.shipping?.markup_tiers ?? [])
const headers = [ ['client_name', '客户 Client'], ['attention', '收件人 Attn'], ['from_name', '发件人 From'], ['revision', '版本 Revision'], ['item_number', '客户产品编号 Item No.'] ] as const
const productFields = [['item_name', '产品名称'], ['item_note', '产品补充说明']] as const
const moldTerms = [['first_shot', '首次试模时间'], ['finish', '完成时间'], ['lead_time_basis', '交期起算依据']] as const
const languages = [['zh', '中文'], ['en', 'English']] as const
const routeFields = [['route_40', "40' 路线"], ['route_20', "20' 路线"], ['route_lcl', 'LCL 路线']] as const
const priceFields = [['confirmed_40', "40' 已确认价 HKD"], ['confirmed_20', "20' 已确认价 HKD"], ['confirmed_lcl', 'LCL 已确认价 HKD']] as const
const dimensions = [['length', '长'], ['width', '宽'], ['height', '高']] as const
function enable() { if (!props.disabled && !mapping.value) props.sales.customer_quote_fields.dickie.mapping = createDickieMapping() }
function addOffer() { if (!props.disabled) mapping.value?.offers.push(createDickieOffer()) }
function remove<T>(rows: T[], index: number) { if (!props.disabled) rows.splice(index, 1) }
function addRemark() { if (!props.disabled) mapping.value?.remarks.push({ zh: '', en: '' }) }
function addAdjustment(offer: DickieOffer) { if (!props.disabled) offer.adjustments.push({ label: '', percent: 0, amount_hkd: 0 }) }
function moveAdjustment(offer: DickieOffer, index: number, offset: number) {
  if (props.disabled || index + offset < 0 || index + offset >= offer.adjustments.length) return
  const row = offer.adjustments.splice(index, 1)[0]
  if (row) offer.adjustments.splice(index + offset, 0, row)
}
</script>

<template>
  <section class="dickie-sales" aria-label="Dickie 报客资料">
    <header><h3>Dickie 报客资料</h3><p>报客资料与内部成本分开保存；包装和基础价格沿用本报价已核算资料。</p></header>
    <Button v-if="!mapping" type="button" :disabled="disabled" @click="enable">启用 Dickie 报客资料</Button>
    <template v-else>
      <fieldset :disabled="disabled">
        <legend>客户抬头与产品</legend>
        <div class="fields">
          <label><span>报价公司</span><select v-model="mapping.company" aria-label="Dickie 报价公司"><option value="hk">Royal Regent (HK)</option><option value="asia">Royal Regent (Asia)</option></select></label>
          <label v-for="[key, label] in headers" :key="key"><span>{{ label }}</span><input v-model="mapping[key]" :aria-label="`Dickie ${label}`"></label>
          <label><span>报价日期</span><input v-model="mapping.quote_date" type="date" aria-label="Dickie 报价日期"></label>
          <label><span>报价类型</span><select v-model="mapping.quotation_kind" aria-label="Dickie 报价类型"><option value="quotation">正式报价 Quotation</option><option value="estimate">估价 Estimate</option></select></label>
          <template v-for="[key, label] in productFields" :key="key"><label v-for="[lang, language] in languages" :key="lang"><span>{{ label }} · {{ language }}</span><textarea v-model="mapping[key][lang]" rows="2" :aria-label="`Dickie ${label} ${language}`" /></label></template>
          <label><span>内包装数量 Inner Pack</span><input v-model.number="mapping.inner_pack" type="number" min="0" step="1" aria-label="Dickie 内包装数量"></label>
          <label><span>展示尺寸来源</span><select v-model="mapping.dimension_source" aria-label="Dickie 尺寸来源"><option value="color_box">彩盒尺寸</option><option value="product">产品尺寸</option></select></label>
          <label><span>展示尺寸单位</span><select v-model="mapping.dimension_unit" aria-label="Dickie 尺寸单位"><option value="cm">cm</option><option value="mm">mm</option></select></label>
        </div>
        <label class="check"><input v-model="mapping.customer_carton_enabled" type="checkbox" aria-label="Dickie 使用客户外箱尺寸"><span>使用客户外箱尺寸（仅用于客户文件）</span></label>
        <div v-if="mapping.customer_carton_enabled" class="fields"><label v-for="[key, label] in dimensions" :key="key"><span>客户外箱{{ label }} (cm)</span><input v-model.number="mapping.customer_carton_cm[key]" type="number" min="0" step="any" :aria-label="`Dickie 客户外箱${label}`"></label></div>
      </fieldset>

      <fieldset :disabled="disabled">
        <legend>报价方案</legend>
        <p>每项方案须明确选择 MOQ 和三条运费路线。倍率档位是否参与输出见下拉选项。</p>
        <p v-if="!tiers.length">请先在右侧报价栏保存本单 MOQ 倍率档位，再选择报客方案对应的 MOQ。</p>
        <p>价格先保留 1 位小数，再按下列顺序逐项应用调整；每项先调整百分比、再加减 HKD，并保留 1 位小数。填写正数加价、负数减价。</p>
        <article v-for="(offer, index) in mapping.offers" :key="offer.id" class="offer">
          <div class="row-head"><label class="check"><input v-model="offer.included" type="checkbox" :aria-label="`Dickie 方案 ${index + 1} 纳入输出`"><span>方案 {{ index + 1 }} · 纳入输出</span></label><Button type="button" variant="outline" size="sm" :disabled="disabled" @click="remove(mapping.offers, index)">删除方案 {{ index + 1 }}</Button></div>
          <div class="fields">
            <label><span>MOQ 倍率档位</span><select v-model.number="offer.moq" :aria-label="`Dickie 方案 ${index + 1} MOQ`"><option :value="0">请选择档位</option><option v-if="offer.moq && !tiers.some(tier => tier.moq === offer.moq)" :value="offer.moq">{{ offer.moq }}（档位已失效，请重选）</option><option v-for="tier in tiers" :key="tier.moq" :value="tier.moq">{{ tier.moq }} · {{ tier.markup_x }} 倍 · {{ tier.include_in_output === false ? '不输出' : '参与输出' }}</option></select></label>
            <label><span>客户 MOQ 文字</span><input v-model="offer.moq_text" :aria-label="`Dickie 方案 ${index + 1} MOQ 文字`"></label>
            <label v-for="[lang, language] in languages" :key="`label-${lang}`"><span>方案名称 · {{ language }}</span><input v-model="offer.label[lang]" :aria-label="`Dickie 方案 ${index + 1} 名称 ${language}`"></label>
            <label v-for="[lang, language] in languages" :key="`remark-${lang}`"><span>方案备注 · {{ language }}</span><textarea v-model="offer.remark[lang]" rows="2" :aria-label="`Dickie 方案 ${index + 1} 备注 ${language}`" /></label>
            <label v-for="[key, label] in routeFields" :key="key"><span>{{ label }}</span><select v-model="offer[key]" :aria-label="`Dickie 方案 ${index + 1} ${label}`"><option value="">请选择路线</option><option v-if="offer[key] && !routes.some(route => route.key === offer[key])" :value="offer[key]">{{ offer[key] }}（路线已失效，请重选）</option><option v-for="route in routes" :key="route.key" :value="route.key">{{ route.label }}</option></select></label>
            <label><span>基础价格来源</span><select v-model="offer.price_source" :aria-label="`Dickie 方案 ${index + 1} 价格来源`"><option value="calculated">内部核算价格</option><option value="confirmed">业务已确认价格</option></select></label>
            <template v-if="offer.price_source === 'confirmed'"><label v-for="[key, label] in priceFields" :key="key"><span>{{ label }}</span><input v-model.number="offer[key]" type="number" min="0" step="0.1" :aria-label="`Dickie 方案 ${index + 1} ${label}`"></label><label><span>已确认价格依据</span><input v-model="offer.confirmed_reference" :aria-label="`Dickie 方案 ${index + 1} 已确认价格依据`"></label></template>
          </div>
          <ol class="adjustments"><li v-for="(adjustment, adjustmentIndex) in offer.adjustments" :key="adjustmentIndex"><div class="fields"><label><span>调整 {{ adjustmentIndex + 1 }} 原因</span><input v-model="adjustment.label" :aria-label="`Dickie 方案 ${index + 1} 调整 ${adjustmentIndex + 1} 原因`"></label><label><span>百分比（可为负数）</span><input v-model.number="adjustment.percent" type="number" step="any" :aria-label="`Dickie 方案 ${index + 1} 调整 ${adjustmentIndex + 1} 百分比`"></label><label><span>HKD（可为负数）</span><input v-model.number="adjustment.amount_hkd" type="number" step="any" :aria-label="`Dickie 方案 ${index + 1} 调整 ${adjustmentIndex + 1} HKD`"></label></div><div class="actions"><Button type="button" variant="outline" size="sm" :disabled="disabled || adjustmentIndex === 0" :aria-label="`上移方案 ${index + 1} 调整 ${adjustmentIndex + 1}`" @click="moveAdjustment(offer, adjustmentIndex, -1)">上移</Button><Button type="button" variant="outline" size="sm" :disabled="disabled || adjustmentIndex === offer.adjustments.length - 1" :aria-label="`下移方案 ${index + 1} 调整 ${adjustmentIndex + 1}`" @click="moveAdjustment(offer, adjustmentIndex, 1)">下移</Button><Button type="button" variant="outline" size="sm" :disabled="disabled" :aria-label="`删除方案 ${index + 1} 调整 ${adjustmentIndex + 1}`" @click="remove(offer.adjustments, adjustmentIndex)">删除调整</Button></div></li></ol>
          <Button type="button" variant="outline" size="sm" :disabled="disabled" @click="addAdjustment(offer)">新增方案 {{ index + 1 }} 调整</Button>
        </article>
        <Button type="button" variant="outline" :disabled="disabled" @click="addOffer">新增报价方案</Button>
      </fieldset>

      <fieldset :disabled="disabled"><legend>客户补充备注</legend><div v-for="(remark, index) in mapping.remarks" :key="index" class="remark"><div class="fields"><label v-for="[lang, language] in languages" :key="lang"><span>备注 {{ index + 1 }} · {{ language }}</span><textarea v-model="remark[lang]" rows="2" :aria-label="`Dickie 备注 ${index + 1} ${language}`" /></label></div><Button type="button" variant="outline" size="sm" :disabled="disabled" @click="remove(mapping.remarks, index)">删除备注 {{ index + 1 }}</Button></div><Button type="button" variant="outline" :disabled="disabled" @click="addRemark">新增客户备注</Button></fieldset>
      <fieldset :disabled="disabled"><legend>模具报价与交期</legend><label class="check"><input v-model="mapping.include_molds" type="checkbox" aria-label="Dickie 纳入模具报价"><span>纳入模具报价（在工程部逐项选择报客模具）</span></label><div v-if="mapping.include_molds" class="fields"><template v-for="[key, label] in moldTerms" :key="key"><label v-for="[lang, language] in languages" :key="lang"><span>{{ label }} · {{ language }}</span><input v-model="mapping[key][lang]" :aria-label="`Dickie ${label} ${language}`"></label></template></div></fieldset>
    </template>
    <details class="fixed-terms"><summary>固定报客条款与材料价（只读）</summary><ol><li v-for="term in DICKIE_FIXED_REMARKS" :key="term.en"><p>{{ term.zh }}</p><p lang="en">{{ term.en }}</p></li></ol><p>Plastic Quotation (HKD/LB)</p><dl><div v-for="material in DICKIE_FIXED_MATERIALS" :key="material.material"><dt>{{ material.material }}</dt><dd>{{ material.price.toFixed(1) }}</dd></div></dl></details>
  </section>
</template>

<style scoped>
.dickie-sales{display:grid;gap:16px;min-width:0;border:1px solid var(--border);border-radius:12px;background:var(--card);padding:16px;color:var(--foreground)}
h3,legend{font-weight:700}header p,p{font-size:12px;color:var(--muted-foreground);line-height:1.6}fieldset{min-width:0;border:0;border-top:1px solid var(--border);padding:12px 0 0}legend{padding-right:8px;font-size:14px}.fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,230px),1fr));gap:12px;margin:10px 0}label{display:grid;gap:5px;min-width:0;font-size:12px}input:not([type=checkbox]),select,textarea{width:100%;min-width:0;min-height:38px;border:1px solid var(--input);border-radius:10px;padding:8px;background:var(--card);font-size:13px}input:focus-visible,select:focus-visible,textarea:focus-visible{outline:2px solid var(--ring);outline-offset:2px}.check{display:flex;align-items:center;gap:8px;padding:8px 0}.check input{width:16px;height:16px}.offer,.remark{border-bottom:1px solid var(--border);padding:12px 0;margin-bottom:12px}.row-head,.actions{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap}.actions{justify-content:flex-end}.adjustments{padding-left:24px}.adjustments li{padding-bottom:10px}.fixed-terms summary{cursor:pointer;font-size:13px;font-weight:600}.fixed-terms ol{padding-left:22px}.fixed-terms dl{display:flex;gap:24px;flex-wrap:wrap;font-size:13px}.fixed-terms dd{margin:0;font-variant-numeric:tabular-nums}fieldset:disabled input,fieldset:disabled select,fieldset:disabled textarea{opacity:.65;cursor:not-allowed;background:var(--muted)}
</style>
