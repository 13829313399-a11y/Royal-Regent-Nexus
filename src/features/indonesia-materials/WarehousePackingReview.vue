<script setup lang="ts">
import { computed } from 'vue'
import type { Data } from '@/api/indonesiaMaterials'
const props = defineProps<{ rows: Data[]; selected: Data[] }>()
const groups = computed<Data[]>(() => {
  const selected = new Set(props.selected.map(row => row.index))
  const result = new Map<string, Data>()
  for (const row of props.rows) {
    const group = row.packing_group
    if (!group) continue
    if (!result.has(group.id)) result.set(group.id, { ...group, selected: 0 })
    if (selected.has(row.index)) result.get(group.id)!.selected++
  }
  return [...result.values()].filter(group => group.selected).map(group => ({ ...group,
    problems: [...group.issues, ...(group.selected < group.row_count ? ['同箱物料未全部选中'] : [])],
  }))
})
const missing = computed(() => props.selected.filter(row => !row.packing_group).length)
</script>
<template>
  <section v-if="selected.length" class="im-stack" aria-label="装箱识别核对">
    <h3>装箱识别</h3>
    <p class="im-note">同一仓库、收料单、箱号合为一组，箱数和体积只计一次。</p>
    <div v-if="groups.length" class="im-scroll"><table><thead><tr><th>仓库／收料单</th><th>箱号</th><th>同箱明细</th><th>处理结果</th></tr></thead><tbody>
      <tr v-for="group in groups" :key="group.id"><td>{{ group.warehouse }}<small>{{ group.receipt_no }}</small></td><td>{{ group.output_label }}</td><td>已选 {{ group.selected }} / {{ group.row_count }} 行</td><td>
        <template v-if="group.problems.length"><strong class="im-danger-text">待补装箱</strong><p v-for="problem in group.problems" :key="problem" class="im-note">{{ problem }}</p></template>
        <strong v-else>{{ group.row_count > 1 ? '合为 1 个混箱包装组' : '带入 1 个包装组' }}</strong>
      </td></tr>
    </tbody></table></div>
    <p v-if="missing" class="im-note">{{ missing }} 行未填箱号，导入后补装箱。</p>
  </section>
</template>
