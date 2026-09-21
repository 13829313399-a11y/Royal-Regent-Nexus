<script setup lang="ts">
import { normalizeDickieMold } from '@/lib/dickieQuote'
import type { EngineeringMoldRow } from '@/lib/internalQuoteSectionPayload'

const props = defineProps<{ molds: EngineeringMoldRow[]; disabled?: boolean }>()
const languages = [['zh', '中文'], ['en', 'English']] as const
const bilingualFields = [['group', '项目分组'], ['shared_products', '共用产品'], ['remark', '客户备注']] as const
function toggle(row: EngineeringMoldRow, event: Event) {
  if (props.disabled) return
  const included = (event.target as HTMLInputElement).checked
  if (!row.dickie_export && included) row.dickie_export = normalizeDickieMold({ included: true })
  else if (row.dickie_export) row.dickie_export.included = included
}
</script>

<template>
  <section class="dickie-molds" aria-label="Dickie 模具报客资料">
    <header><h3>Dickie 模具报客资料</h3><p>选择需要报客的工程模具，并补充英文名称、客户价格与备注。尺寸、穴数、套数和材料读取上方工程资料。</p></header>
    <p v-if="!molds.length">请先在模具部分新增工程模具。</p>
    <article v-for="(row, index) in molds" :key="index">
      <label class="check"><input type="checkbox" :checked="row.dickie_export?.included === true" :disabled="disabled" :aria-label="`Dickie 模具 ${index + 1} 纳入报客`" @change="toggle(row, $event)"><span>模具 {{ index + 1 }} · {{ row.chinese_name || row.item || row.mold_no || '未命名' }} · 纳入报客</span></label>
      <dl class="facts"><div><dt>工程模号</dt><dd>{{ row.mold_no || '未填写' }}</dd></div><div><dt>模具尺寸</dt><dd>{{ row.mold_size || row.mold_specification || '未填写' }}</dd></div><div><dt>穴数</dt><dd>{{ row.cavity || '未填写' }}</dd></div><div><dt>套数</dt><dd>{{ row.quantity }}</dd></div><div><dt>胶料</dt><dd>{{ row.material_type || '未填写' }}</dd></div><div><dt>模胚材料</dt><dd>{{ row.mold_base_material || '未填写' }}</dd></div></dl>
      <fieldset v-if="row.dickie_export" :disabled="disabled">
        <legend>模具 {{ index + 1 }} 客户补充资料{{ row.dickie_export.included ? '' : '（已保留，暂不报客）' }}</legend>
        <div class="fields">
          <label><span>客户模号（留空沿用工程模号）</span><input v-model="row.dickie_export.customer_mold_no" :placeholder="row.mold_no" :aria-label="`Dickie 模具 ${index + 1} 客户模号`"></label>
          <label><span>英文部件名称</span><input v-model="row.dickie_export.parts_en" :aria-label="`Dickie 模具 ${index + 1} 英文部件名称`"></label>
          <label><span>工程模具尺寸单位</span><select v-model="row.dickie_export.size_unit" :aria-label="`Dickie 模具 ${index + 1} 尺寸单位`"><option value="cm">cm</option><option value="mm">mm</option></select></label>
          <label><span>客户模价 HKD</span><input v-model.number="row.dickie_export.customer_price_hkd" type="number" min="0" step="0.1" :aria-label="`Dickie 模具 ${index + 1} 客户模价 HKD`"></label>
          <template v-for="[key, label] in bilingualFields" :key="key"><label v-for="[lang, language] in languages" :key="lang"><span>{{ label }} · {{ language }}</span><textarea v-model="row.dickie_export[key][lang]" rows="2" :aria-label="`Dickie 模具 ${index + 1} ${label} ${language}`" /></label></template>
        </div>
      </fieldset>
    </article>
  </section>
</template>

<style scoped>
.dickie-molds{display:grid;gap:12px;min-width:0;border:1px solid var(--border);border-radius:12px;background:var(--card);padding:16px;color:var(--foreground)}h3,legend{font-weight:700}p{font-size:12px;line-height:1.6;color:var(--muted-foreground)}article{border-top:1px solid var(--border);padding-top:12px}.check{display:flex;align-items:center;gap:8px;font-size:13px;font-weight:600}.check input{width:16px;height:16px}.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:12px;margin:12px 0;font-size:12px}.facts dt{color:var(--muted-foreground)}.facts dd{margin:4px 0;overflow-wrap:anywhere}fieldset{border:0;padding:0;min-width:0}legend{font-size:12px}.fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,230px),1fr));gap:12px;margin-top:10px}label{display:grid;gap:5px;min-width:0;font-size:12px}input:not([type=checkbox]),select,textarea{width:100%;min-width:0;min-height:38px;border:1px solid var(--input);border-radius:10px;padding:8px;background:var(--card);font-size:13px}input:focus-visible,select:focus-visible,textarea:focus-visible{outline:2px solid var(--ring);outline-offset:2px}fieldset:disabled input,fieldset:disabled select,fieldset:disabled textarea{opacity:.65;cursor:not-allowed;background:var(--muted)}
</style>
