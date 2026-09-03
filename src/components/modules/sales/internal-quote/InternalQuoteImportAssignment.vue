<script setup lang="ts">
import { computed, ref } from 'vue'
defineProps<{ rows: Array<{ key: string; label: string; source_row?: string | number; mold_no?: string }>; components: Array<{ id: string; name: string }>; disabled?: boolean }>()
const model = defineModel<Record<string, string>>({ required: true })
const selected = ref<string[]>([])
const batchTarget = ref('')
const selectedCount = computed(() => selected.value.length)
function applySelected() {
  if (!batchTarget.value) return
  model.value = { ...model.value, ...Object.fromEntries(selected.value.map(key => [key, batchTarget.value])) }
  selected.value = []
}
</script>
<template>
  <section class="quote-import-assignment" aria-label="映射明细分配">
    <p>本次一次映射当前产品的全部明细；每行必须选择分项或“不采用”，不会自动放入主体。未确认前不写入报价。</p>
    <div class="assignment-batch">
      <select v-model="batchTarget" :disabled="disabled" aria-label="批量应用分项"><option value="">选择批量目标</option><option v-for="component in components" :key="component.id" :value="component.id">{{ component.name }}</option><option value="__skip__">不采用</option></select>
      <button type="button" :disabled="disabled || !batchTarget || !selectedCount" @click="applySelected">应用到勾选的 {{ selectedCount }} 行</button>
    </div>
    <div class="assignment-scroll"><table><thead><tr><th>选择</th><th>来源行</th><th>模具 / 明细</th><th>应用分项</th></tr></thead><tbody>
      <tr v-for="row in rows" :key="row.key"><td><input v-model="selected" :value="row.key" type="checkbox" :disabled="disabled" :aria-label="`勾选 ${row.label}`"></td><td>{{ row.source_row || '—' }}</td><td>{{ row.mold_no }} {{ row.label }}</td><td><select :value="model[row.key] || ''" :disabled="disabled" :aria-label="`${row.label} 应用分项`" @change="model = { ...model, [row.key]: ($event.target as HTMLSelectElement).value }"><option value="">请选择</option><option v-for="component in components" :key="component.id" :value="component.id">{{ component.name }}</option><option value="__skip__">不采用</option></select></td></tr>
    </tbody></table></div>
  </section>
</template>
<style scoped>
.quote-import-assignment{padding:12px;background:#fff;border-top:1px solid #cbd5e1}.quote-import-assignment p{font-size:12px;color:#475569;margin:0 0 10px}.assignment-batch{display:flex;gap:8px;margin-bottom:10px}.quote-import-assignment select,.quote-import-assignment button{border:1px solid #cbd5e1;border-radius:6px;padding:7px;background:#fff;color:#0f766e}.quote-import-assignment button:disabled{opacity:.5}.assignment-scroll{max-height:360px;overflow:auto}.quote-import-assignment table{width:100%;border-collapse:collapse;font-size:12px}.quote-import-assignment th,.quote-import-assignment td{padding:8px;text-align:left;border-bottom:1px solid #e2e8f0}.quote-import-assignment th{background:#f1f5f9;position:sticky;top:0}.quote-import-assignment td select{width:100%;min-width:130px}
</style>
