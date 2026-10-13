<script setup lang="ts">
import { computed } from 'vue'
import { type MasterRecord, type MasterPaper } from '@/api/cartonMaster'
const props = defineProps<{ records: MasterRecord[]; customer: string; item: string; contract: string; product: string; lines: MasterPaper[]; disabled?: boolean }>()
const emit = defineEmits<{ select: [MasterRecord] }>()
const normalize = (value: string) => value.normalize('NFKC').toLowerCase().replace(/[\s_./-]+/g, '')
const candidates = computed(() => props.records.filter(r => r.kind === 'CONFIG' && r.status === 'ACTIVE' && ((normalize(props.item) && normalize(r.code).includes(normalize(props.item))) || (normalize(props.product) && normalize(r.data.product_name || '').includes(normalize(props.product))))))
const exact = computed(() => candidates.value.filter(r => r.code === props.item))
const signature = (lines: MasterPaper[]) => JSON.stringify(lines.map(l => [l.packaging_type.trim(), l.paper_quality.trim(), l.specification.trim(), l.dimension_unit.trim(), l.unit.trim(), Number(l.usage_quantity), l.net_weight_kg == null || l.net_weight_kg === '' ? null : Number(l.net_weight_kg), l.gross_weight_kg == null || l.gross_weight_kg === '' ? null : Number(l.gross_weight_kg)]).sort((a, b) => JSON.stringify(a).localeCompare(JSON.stringify(b))))
const differs = computed(() => exact.value.length > 0 && !exact.value.some(r => r.data.product_name === props.product && signature(r.data.lines || []) === signature(props.lines)))
const contractRecord = computed(() => props.records.find(r => r.kind === 'CONTRACT' && r.customer_code === props.customer && r.code === props.contract))
const otherCustomerContract = computed(() => !contractRecord.value && props.contract && props.records.some(r => r.kind === 'CONTRACT' && r.customer_code !== props.customer && r.code === props.contract))
</script>
<template>
  <div v-if="candidates.length || otherCustomerContract || (contractRecord && item && !contractRecord.data.item_nos?.includes(item)) || contractRecord?.status === 'INACTIVE'" class="space-y-2 rounded-xl border border-teal-100 bg-teal-50/40 p-3" aria-label="基础资料落单辅助">
    <div class="flex items-center justify-between"><b class="text-xs text-teal-800">货号基础资料</b><span class="text-[10px] text-slate-500">带出产品名称、纸品、单位、装箱数和各纸品重量</span></div>
    <p v-if="exact.length > 1 || differs" role="status" class="rounded-lg bg-amber-50 p-2 text-xs text-amber-800">{{ exact.length > 1 ? `此货号有 ${exact.length} 套历史配置。` : '' }}{{ differs ? '本次包装与已有配置不同，可能下错装箱方式。' : '' }}请核对纸品类型、纸质、规格、尺寸单位、计量单位和装箱数；核对无误可保留；正式确认后单独记录，不覆盖标准装。</p>
    <p v-if="contractRecord && item && !contractRecord.data.item_nos?.includes(item)" class="text-xs text-amber-800">本合同首次使用该货号，请核对本次要求；正式确认后自动补充历史关联。</p>
    <p v-if="otherCustomerContract" class="text-xs text-amber-800">此合同号在其他客户的资料中出现过，请核对客户归属；如确属本客户新合同，可继续落单。</p>
    <p v-if="contractRecord?.status === 'INACTIVE'" class="text-xs text-red-700">该合同已停用，不能用于新订单；请核对合同号或联系主管。</p>
    <div class="max-h-48 space-y-1 overflow-y-auto">
      <button v-for="row in candidates" :key="row.id" type="button" :disabled="disabled" class="block w-full rounded-lg border border-slate-200 bg-white p-2 text-left text-xs hover:border-teal-300 disabled:opacity-50" :aria-label="`带出基础资料 ${row.code} ${row.id}`" @click="emit('select', row)">
        <b>{{ row.code }} · {{ row.data.product_name || '产品名称未填写' }} · {{ row.data.packing_name || '其他包装' }}</b><span class="ml-2 text-teal-700">{{ row.preferred ? '推荐配置' : row.maintained ? '已维护' : '历史自动加入' }}</span>
        <div v-for="(paper, i) in row.data.lines" :key="i" class="mt-1 text-slate-600">{{ paper.packaging_type }} · {{ paper.paper_quality }} · {{ paper.specification }} {{ paper.dimension_unit }} · {{ paper.unit }} · 每箱 {{ paper.usage_quantity }} 件<span v-if="paper.net_weight_kg != null || paper.gross_weight_kg != null"> · 每箱净重 {{ paper.net_weight_kg ?? '未记录' }} kg / 毛重 {{ paper.gross_weight_kg ?? '未记录' }} kg</span></div>
        <div class="mt-1 text-[10px] text-slate-400">{{ row.sources[0]?.order_date }} {{ row.sources[0]?.contract_no }} · {{ row.sources.length }} 条来源</div>
      </button>
      <p v-if="!candidates.length" class="py-2 text-xs text-slate-500">暂无匹配的基础资料，可填写本次订单；正式确认后自动加入。</p>
    </div>
  </div>
</template>
