<script setup lang="ts">
import { computed, ref } from 'vue'
import type { ApiInternalQuote, ApiInternalQuoteVersionComparison } from '@/api/internalQuote'
import { buildQuoteComparison, comparisonConditions, type CompareRow } from '@/lib/internalQuoteDetailComparison'

const props = defineProps<{ comparison: ApiInternalQuoteVersionComparison; base: ApiInternalQuote; target: ApiInternalQuote; baseLabel: string; targetLabel: string; previewOnly?: boolean }>()
const showAll = ref(false)
const expandedSame = ref<string[]>([])
const sections = computed(() => buildQuoteComparison(props.base, props.target, props.comparison))
const conditions = computed(() => comparisonConditions(props.comparison))
const visibleSections = computed(() => sections.value.map(section => ({ ...section,
  sameRows: section.groups.reduce((sum, group) => sum + group.rows.filter(row => !row.changed).length, 0),
  groups: section.groups.map(group => ({ ...group, rows: group.rows.filter(row => showAll.value || expandedSame.value.includes(section.section_code) || !section.changedRows || row.changed) })).filter(group => group.rows.length),
})))
function toggleSame(code: string) {
  expandedSame.value = expandedSame.value.includes(code) ? expandedSame.value.filter(value => value !== code) : [...expandedSame.value, code]
}
const money = (value: string) => Number(value).toFixed(4)
const mainFields = ['规格', '用量', '单价 RMB', '单价 HKD']
function fields(row: CompareRow, extra = false) {
  const keys = [...new Set([...Object.keys(row.before?.fields ?? {}), ...Object.keys(row.after?.fields ?? {})])]
  return extra ? keys.filter(key => !mainFields.includes(key)) : mainFields.filter(key => keys.includes(key) || key === '规格')
}
function changed(row: CompareRow, key: string) { return (row.before?.fields[key] ?? '—') !== (row.after?.fields[key] ?? '—') }
function extraChanged(row: CompareRow) { return fields(row, true).some(key => changed(row, key)) }
</script>

<template>
  <section class="comparison" aria-label="报价明细对比">
    <div v-if="!previewOnly" class="costs">
      <div><span>{{ baseLabel }}</span><strong>HK$ {{ money(comparison.total_before_hkd) }}</strong></div>
      <div><span>{{ targetLabel }}</span><strong>HK$ {{ money(comparison.total_after_hkd) }}</strong></div>
      <div><span>单件成本差额</span><strong :class="{ difference: Number(comparison.total_delta_hkd) !== 0 }">{{ Number(comparison.total_delta_hkd) > 0 ? '+' : '' }}{{ money(comparison.total_delta_hkd) }}</strong></div>
    </div>
    <div class="toolbar"><span>默认展开差异，黄色为改动；相同明细可按部门点开。</span><label><input v-model="showAll" type="checkbox">展开全部明细</label></div>
    <table v-if="conditions.length" class="conditions"><thead><tr><th>报价条件</th><th>{{ baseLabel }}</th><th>{{ targetLabel }}</th></tr></thead><tbody><tr v-for="condition in conditions" :key="condition.label"><th>{{ condition.label }}</th><td>{{ condition.before }}</td><td>{{ condition.after }}</td></tr></tbody></table>
    <details v-for="section in visibleSections" :key="section.section_code" :open="showAll || section.changedRows > 0 || section.payload_changes.length > 0" class="department">
      <summary><strong>{{ section.section_name }}</strong><span v-if="!previewOnly">小计 HK$ {{ money(section.before_total_hkd) }} → {{ money(section.after_total_hkd) }}</span><em>{{ section.changedRows ? `${section.changedRows} 项明细变化` : section.payload_changes.length ? '附加资料有变化' : `明细相同 · 点击查看 ${section.sameRows} 项` }}</em></summary>
      <button v-if="section.changedRows && section.sameRows && !showAll" type="button" class="same-toggle" @click="toggleSame(section.section_code)">{{ expandedSame.includes(section.section_code) ? '收起相同明细' : `查看相同明细（${section.sameRows} 项）` }}</button>
      <div v-for="group in section.groups" :key="group.name" class="group">
        <h4>{{ group.name }}</h4>
        <div class="table-scroll"><table><thead><tr><th class="status-col">变化</th><th>{{ baseLabel }}</th><th>{{ targetLabel }}</th></tr></thead>
          <tbody><tr v-for="(row, index) in group.rows" :key="index" :class="{ modified: row.changed }">
            <td class="status-col"><span class="badge" :class="{ changed: row.changed }">{{ row.status }}</span></td>
            <td v-for="side in (['before', 'after'] as const)" :key="side">
              <template v-if="row[side]">
                <strong class="item-name">{{ row[side]!.name }}</strong>
                <dl><div v-for="field in fields(row)" :key="field" :class="{ highlight: changed(row, field) }"><dt>{{ field }}</dt><dd>{{ row[side]!.fields[field] ?? '—' }}</dd></div></dl>
                <details v-if="fields(row, true).length" class="extra" :open="extraChanged(row)"><summary>{{ extraChanged(row) ? '其他资料有变化' : '更多资料' }}</summary><dl><div v-for="field in fields(row, true)" :key="field" :class="{ highlight: changed(row, field) }"><dt>{{ field }}</dt><dd>{{ row[side]!.fields[field] ?? '—' }}</dd></div></dl></details>
              </template><span v-else class="absent">此版无此项</span>
            </td>
          </tr></tbody>
        </table></div>
      </div>
      <p v-if="section.payload_changes.length && !section.changedRows" class="note">另有附加资料或排列变化，可打开两版查看。</p>
    </details>
    <p v-if="!sections.some(section => section.changedRows || section.payload_changes.length) && !conditions.length" class="note">当前展示的明细没有差异，可点开部门查看。</p>
    <p class="note">{{ previewOnly ? '这里预览资料替换，确认同步后按目标方案自己的汇率、料价和倍率核算。未选中的类别保留。' : '这里对照已保存的核价明细；报客补充资料及完整参考料价可打开对应版本查看。单价保留原币种，部门小计使用系统核算的港币金额。' }}</p>
  </section>
</template>

<style scoped>
.comparison{display:grid;gap:14px;margin-top:16px;color:#334155;font-size:13px}.costs{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}.costs>div{padding:14px;border-radius:9px;background:#f0fdfa;display:grid;gap:6px}.costs span{font-size:12px;color:#64748b}.costs strong{font-size:18px;color:#115e59}.costs .difference{color:#b45309}.toolbar{display:flex;align-items:center;gap:20px;flex-wrap:wrap}.toolbar label{display:flex;align-items:center;gap:7px;font-weight:600}.toolbar span,.note{color:#64748b;font-size:12px}.department{border:1px solid #dbe5eb;border-radius:10px;overflow:hidden}.department>summary{cursor:pointer;background:#f8fafc;padding:13px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}.department>summary strong{font-size:15px;color:#134e4a}.department>summary span{font-size:12px}.department em{font-size:12px;font-style:normal;color:#64748b;margin-left:auto}.group{padding:12px 14px}.group h4{font-size:14px;margin:0 0 9px}.table-scroll{overflow:auto}table{width:100%;border-collapse:collapse;table-layout:fixed}th,td{border:1px solid #e2e8f0;padding:10px 14px;vertical-align:top;text-align:left;overflow-wrap:anywhere}th{background:#f1f5f9;color:#475569;font-size:12px}th.status-col,td.status-col{width:76px;text-align:center;padding:12px 6px}.item-name{display:block;font-size:14px;margin-bottom:8px}.badge{font-size:11px;color:#64748b;white-space:nowrap}.badge.changed{color:#92400e;background:#fef3c7;padding:4px 7px;border-radius:5px}dl{margin:0;display:grid;gap:3px}dl>div{display:grid;grid-template-columns:110px 1fr;gap:7px;padding:3px 5px;border-radius:4px}dt{color:#64748b;font-size:12px}dd{margin:0;white-space:pre-wrap}.highlight{background:#fef3c7}.extra{margin-top:8px}.extra>summary{cursor:pointer;font-size:12px;color:#64748b;margin-bottom:6px}.absent{color:#94a3b8}.note{margin:0;line-height:1.6}.department>.note{padding:10px 14px}.conditions th:first-child{width:140px}@media(max-width:700px){.costs{grid-template-columns:1fr}.table-scroll table{min-width:610px}dl>div{grid-template-columns:90px 1fr}.department em{margin-left:0}}
.same-toggle{margin:12px 14px 0;padding:7px 12px;border:1px solid #cbd5e1;border-radius:6px;background:white;color:#0f766e;cursor:pointer;font-size:12px}
</style>
