<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import { Button } from '@/components/ui/button'
import { engineeringApi as api, type Bom, type BomComparison, type BomEvidence } from './api'

const props = defineProps<{ versions: Bom[]; disabled?: boolean }>()
const emit = defineEmits<{ denied: [error: unknown] }>()
const from = ref(0), to = ref(0), result = ref<BomComparison | null>(null), busy = ref(false), error = ref('')
let sequence = 0
const versions = computed(() => [...props.versions].sort((a, b) => b.version - a.version))
const valid = computed(() => versions.value.length >= 2 && versions.value.every(v => v.id === versions.value[0]?.id)
  && versions.value.some(v => v.version === from.value) && versions.value.some(v => v.version === to.value) && from.value < to.value)
function invalidate() { sequence++; result.value = null; busy.value = false; error.value = '' }
watch(() => props.versions, () => { invalidate(); to.value = versions.value[0]?.version || 0; from.value = versions.value[1]?.version || 0 }, { immediate: true })
watch([from, to, () => props.disabled], invalidate, { flush: 'sync' })
onBeforeUnmount(invalidate)
const status = (value: string) => value === 'APPROVED' ? '已审核' : value === 'DRAFT' ? '待审核' : value
const value = (entry: BomEvidence | null, field: string) => typeof entry?.[field] === 'boolean' ? (entry[field] ? '是' : '否') : String(entry?.[field] ?? '') || '—'
const extraFields = [{ field: 'specification', label: '物料规格' }, { field: 'color', label: '颜色' }, { field: 'department', label: '负责部门' }, { field: 'exempt_loss', label: '免损' }, { field: 'note', label: '备注' }, { field: 'review_note', label: '核对说明' }]
async function compare() {
  if (!valid.value || props.disabled || busy.value) return
  const token = ++sequence, identity = versions.value[0]!.id
  result.value = null; error.value = ''; busy.value = true
  try { const report = await api.compare(identity, from.value, to.value); if (token === sequence && !props.disabled) result.value = report }
  catch (e) {
    if (token !== sequence) return
    const response = (e as { response?: { status?: number; data?: { detail?: unknown } } }).response
    if ([401, 403].includes(response?.status || 0)) { invalidate(); emit('denied', e); return }
    error.value = typeof response?.data?.detail === 'string' ? response.data.detail : '版本比较失败，请重新核对。'
  } finally { if (token === sequence) busy.value = false }
}
</script>

<template>
  <SectionPanel title="BOM 历史版本比较" subtitle="只比较同一 BOM 已保存的版本；草稿与已审核版本会分别标明。">
    <div class="bom-comparison space-y-3">
      <p class="text-sm text-slate-600">逐用料行比较，不按编码汇总。路径用量是工程理论单套用量，不含订单损耗、库存抵扣或采购取整。表内行序不代表生产工艺先后。</p>
      <div class="flex flex-wrap items-end gap-3">
        <label class="flex flex-col gap-1 text-sm">原版本<select v-model.number="from" aria-label="比较原版本" :disabled="disabled" class="rounded-md border bg-white p-2"><option v-for="v in versions" :key="v.version" :value="v.version">v{{ v.version }} · {{ status(v.status) }}</option></select></label>
        <label class="flex flex-col gap-1 text-sm">对比版本<select v-model.number="to" aria-label="比较新版本" :disabled="disabled" class="rounded-md border bg-white p-2"><option v-for="v in versions" :key="v.version" :value="v.version">v{{ v.version }} · {{ status(v.status) }}</option></select></label>
        <Button variant="outline" :disabled="disabled || !valid || busy" @click="compare">{{ busy ? '正在比较…' : '比较已保存版本' }}</Button>
      </div>
      <p v-if="disabled" class="text-sm text-amber-800">请先处理未保存内容或当前操作，再比较历史版本。</p>
      <p v-else-if="!valid" class="text-sm text-amber-800">原版本须早于对比版本。</p>
      <p v-if="error" role="alert" class="text-red-800">{{ error }}</p>
      <template v-if="result">
        <p>v{{ result.from_version }}（{{ status(result.from_status) }}）→ v{{ result.to_version }}（{{ status(result.to_status) }}）；{{ result.unchanged_count }} 条用料无变化。</p>
        <ul v-if="result.header.length"><li v-for="h in result.header" :key="h.field">{{ h.label }}：{{ h.before || '—' }} → {{ h.after || '—' }}</li></ul>
        <p v-if="!result.rows.length && !result.header.length">所选版本的工程内容无变化；审核状态见版本标识。</p>
        <div v-if="result.rows.length" class="overflow-x-auto"><table class="min-w-[800px] w-full text-sm"><thead><tr><th>用料行／变化</th><th>原版本依据</th><th>对比版本依据</th></tr></thead><tbody>
          <tr v-for="row in result.rows" :key="row.key">
            <td>{{ row.key }} · {{ row.kind === 'ADDED' ? '新增' : row.kind === 'REMOVED' ? '移除' : '修改' }}<ul><li v-for="change in row.changes" :key="change.field">{{ change.label }}</li></ul></td>
            <td v-for="side in ['before', 'after'] as const" :key="side" class="break-words">
              <template v-if="row[side]">
                <p>{{ value(row[side], 'code') }} {{ value(row[side], 'name') }} · 物料 v{{ value(row[side], 'material_version') }} ／ {{ value(row[side], 'attribute') }}</p>
                <p>路径：{{ value(row[side], 'path') }}</p><p>工序：{{ value(row[side], 'process') }} ／ {{ value(row[side], 'unit') }}</p>
                <p>分子／分母：{{ value(row[side], 'numerator') }} ／ {{ value(row[side], 'denominator') }}</p>
                <p>沿路径单套用量：{{ value(row[side], 'cumulative') }} {{ value(row[side], 'unit') }}</p>
                <ul><li v-for="change in row.changes.filter(c => !['path', 'process', 'unit', 'numerator', 'denominator', 'cumulative'].includes(c.field))" :key="change.field">{{ change.label }}：{{ value(row[side], change.field) }}</li></ul>
                <details v-if="row.kind !== 'CHANGED'"><summary>其他工程字段</summary><ul><li v-for="field in extraFields" :key="field.field">{{ field.label }}：{{ value(row[side], field.field) }}</li></ul></details>
              </template><template v-else>此版本无该用料行</template>
            </td>
          </tr>
        </tbody></table></div>
        <p class="text-sm text-slate-600">用料行标识改变时分别列为移除／新增，不猜测替代关系。比较不改写历史或下游单据，正式下发仍未开放。</p>
      </template>
    </div>
  </SectionPanel>
</template>

<style scoped>
.bom-comparison th, .bom-comparison td { padding: .65rem; border-bottom: 1px solid var(--color-slate-200); text-align: left; vertical-align: top; }
.bom-comparison th { background: var(--color-slate-50); }
</style>
