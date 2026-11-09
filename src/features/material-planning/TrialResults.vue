<script setup lang="ts">
import { computed, ref } from 'vue'
import { quantityText, type TrialResult } from './api'
const props = defineProps<{ result: TrialResult }>()
const process = ref('')
const processes = computed(() => [...new Set(props.result.lines.map(line => line.process))])
const lines = computed(() => props.result.lines.filter(line => !process.value || line.process === process.value))
</script>

<template>
  <div class="space-y-4">
    <p v-if="result.order_basis">订单依据：{{ result.order_basis.customer_name }} ／ {{ result.order_basis.reference_no }} ／ {{ result.order_basis.product_no }} · 版本 {{ result.order_basis.revision }} · 当时订单数量 {{ result.order_basis.quantity }}</p>
    <p v-if="result.release_gate" class="text-sm text-amber-800">尚不能正式放单：库存核实、有效在途分配及放单流程仍待接通。自制与委外需求分别保留。</p>
    <p>成品数量基准：{{ quantityText(result.finished_quantity) }} {{ result.finished_unit }}。采购数量：待资料核实，尚未计算。</p>
    <p class="text-sm text-amber-800">待核实：{{ result.pending.join('、') }}。下表为含损耗毛需求；“≈”表示展示约数。</p>
    <label class="flex max-w-xs flex-col gap-1 text-sm">工序明细筛选<select v-model="process" class="rounded-md border bg-white p-2"><option value="">全部工序</option><option v-for="p in processes" :key="p">{{ p }}</option></select></label>
    <div class="overflow-x-auto"><table class="usage-table"><caption>逐工序用料明细</caption><thead><tr><th>工序</th><th>物料／版本</th><th>属性</th><th>基础用量</th><th>损耗</th><th>含损耗用量</th><th>单位</th><th>免损</th></tr></thead><tbody><tr v-for="line in lines" :key="line.key"><td>{{ line.process }}</td><td>{{ line.code }} {{ line.name }} · v{{ line.material_version }}</td><td>{{ line.attribute }}</td><td>{{ quantityText(line.base) }}</td><td>{{ quantityText(line.loss) }}</td><td>{{ quantityText(line.gross) }}</td><td>{{ line.unit }}</td><td>{{ line.exempt_loss ? '是' : '否' }}</td></tr></tbody></table></div>
    <div class="overflow-x-auto"><table class="usage-table"><caption>同物料同属性汇总（包含全部工序）</caption><thead><tr><th>物料／版本</th><th>本次属性</th><th>工序</th><th>基础用量</th><th>损耗</th><th>含损耗用量</th><th>单位</th></tr></thead><tbody><tr v-for="line in result.totals" :key="`${line.material_id}:${line.material_version}:${line.unit}:${line.attribute}`"><td>{{ line.code }} {{ line.name }} · v{{ line.material_version }}</td><td>{{ line.attribute }}</td><td>{{ line.processes.join('、') }}</td><td>{{ quantityText(line.base) }}</td><td>{{ quantityText(line.loss) }}</td><td>{{ quantityText(line.gross) }}</td><td>{{ line.unit }}</td></tr></tbody></table></div>
    <p v-if="!result.lines.length" class="text-sm text-slate-600">此 BOM 只有成品根项，暂无子项用料。</p>
  </div>
</template>

<style scoped>
.usage-table { width: 100%; min-width: 700px; border-collapse: collapse; font-size: .875rem; }
.usage-table caption { text-align: left; font-weight: 600; padding: .6rem 0; }
.usage-table th, .usage-table td { text-align: center; padding: .65rem; border-bottom: 1px solid var(--color-slate-200); }
.usage-table th { background: var(--color-slate-50); white-space: nowrap; }
</style>
