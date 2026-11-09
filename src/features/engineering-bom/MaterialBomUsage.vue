<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import { Button } from '@/components/ui/button'
import { engineeringApi as api, type Material, type MaterialBomUsage } from './api'

const props = defineProps<{ material: Material; disabled?: boolean }>()
const emit = defineEmits<{ denied: [error: unknown] }>()
const report = ref<MaterialBomUsage | null>(null), busy = ref(false), error = ref('')
let generation = 0
function invalidate() { generation++; report.value = null; busy.value = false; error.value = '' }
async function query() {
  if (props.disabled || busy.value) return
  const token = ++generation
  report.value = null; error.value = ''; busy.value = true
  try {
    const value = await api.materialUsage(props.material.id, props.material.version)
    if (token === generation && !props.disabled) report.value = value
  } catch (e) {
    if (token !== generation) return
    const response = (e as { response?: { status?: number; data?: { detail?: unknown } } }).response
    if ([401, 403].includes(response?.status || 0)) { invalidate(); emit('denied', e); return }
    error.value = typeof response?.data?.detail === 'string' ? response.data.detail : '引用查询失败，请重新查询。'
  } finally { if (token === generation) busy.value = false }
}
watch(() => [props.material.id, props.material.version, props.disabled], () => { invalidate(); if (!props.disabled) void query() }, { immediate: true, flush: 'sync' })
onBeforeUnmount(invalidate)
</script>

<template>
  <SectionPanel title="物料的 BOM 引用" subtitle="查询各 BOM 的最新保存版和当前有效版，逐行保留物料属性与工序。">
    <div class="space-y-3">
      <div class="flex flex-wrap items-center gap-3"><p>{{ material.code }} · {{ material.name }} · 档案 v{{ material.version }}</p><Button variant="outline" :disabled="disabled || busy" @click="query">{{ busy ? '正在查询…' : '重新查询引用' }}</Button></div>
      <p v-if="disabled" class="text-sm text-amber-800">请先保存修改或完成当前操作，再查询已保存资料。</p>
      <p v-if="error" role="alert" class="text-red-800">{{ error }}</p>
      <template v-if="report">
        <p class="text-sm text-slate-600">查询时间：{{ report.checked_at }} · 涉及 {{ report.bom_count }} 份 BOM，{{ report.items.length }} 条版本用料记录。</p>
        <p v-if="!report.items.length" role="status">最新保存版和当前有效版中未查到此物料引用；不代表历史单据或其他模块没有使用。</p>
        <div v-else class="overflow-x-auto"><table class="material-usage-table min-w-[760px] w-full text-sm"><thead><tr><th>货号／BOM</th><th>版本与用途</th><th>用料行／工序</th><th>当时物料依据</th><th>本层分子／分母</th></tr></thead><tbody>
          <tr v-for="item in report.items" :key="`${item.bom_id}:${item.bom_version}:${item.key}`">
            <td>{{ item.item_no }}<br>{{ item.bom_name }}</td>
            <td>v{{ item.bom_version }} · {{ item.status === 'APPROVED' ? '已审核' : '待审核' }}<p>{{ item.roles.map(role => role === 'LATEST' ? '最新保存版' : '当前有效版').join('／') }}</p></td>
            <td>第 {{ item.row }} 行<br>{{ item.process || '工序待补齐' }}</td>
            <td>{{ item.code }} {{ item.name }}<br>物料 v{{ item.material_version }} ／ {{ item.attribute || '属性待核对' }}</td>
            <td>{{ item.numerator }} ／ {{ item.denominator }} {{ item.unit }}</td>
          </tr>
        </tbody></table></div>
      </template>
      <p class="text-sm text-slate-500">同一版本兼任最新和有效版时只列一次；不同版本分别展示，不累加为需求量。同编码不同属性不合并。未匹配物料的导入行不算已建立引用。查询不替换物料、不检查订单或库存，正式下发仍未开放。</p>
    </div>
  </SectionPanel>
</template>

<style scoped>
.material-usage-table th, .material-usage-table td { padding: .65rem; border-bottom: 1px solid var(--color-slate-200); text-align: left; vertical-align: top; overflow-wrap: anywhere; }
.material-usage-table th { background: var(--color-slate-50); }
</style>
