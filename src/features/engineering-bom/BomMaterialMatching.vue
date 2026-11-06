<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import SectionPanel from '@/components/common/SectionPanel.vue'
import { Button } from '@/components/ui/button'
import type { Material, Node } from './api'
import { materialMatches, type MaterialMatch, type MatchSelection } from './materialMatching'

const props = defineProps<{ nodes: Node[]; materials: Material[]; disabled?: boolean }>()
const emit = defineEmits<{ apply: [selections: MatchSelection[]] }>()
const rows = ref<MaterialMatch[] | null>(null), selected = ref<number[]>([])
const count = computed(() => props.nodes.filter(n => !n.material_id).length)
watch(() => [props.nodes, props.materials, props.disabled], () => { rows.value = null; selected.value = [] }, { deep: true, flush: 'sync' })
function preview() { if (props.disabled) return; selected.value = []; rows.value = materialMatches(props.nodes, props.materials) }
function apply() {
  if (props.disabled || !selected.value.length || !rows.value) return
  const selections = rows.value.filter(row => row.material && selected.value.includes(row.row)).map(row => ({
    row: row.row, key: row.key, material_id: row.material!.id, material_version: row.material!.version,
  }))
  if (selections.length) emit('apply', selections)
}
</script>

<template>
  <SectionPanel v-if="count" title="未匹配用料核对" subtitle="只处理尚未选择物料的行；已有物料版本保持原样。">
    <div class="space-y-3">
      <p class="text-sm text-slate-600">还有 {{ count }} 条未匹配用料。根据当前已加载的物料档案查找候选；新建或修改物料后，请先保存 BOM 并刷新资料。</p>
      <Button variant="outline" :disabled="disabled" @click="preview">查看未匹配用料候选</Button>
      <template v-if="rows">
        <ul class="space-y-2"><li v-for="row in rows" :key="row.row" class="rounded-md border border-slate-200 p-3 text-sm">
          <div class="flex items-start gap-3">
            <input v-model="selected" type="checkbox" :value="row.row" :aria-label="`选择匹配第${row.row}行`" :disabled="disabled || !row.material" class="mt-1" />
            <div class="min-w-0 break-words">
              <p>第 {{ row.row }} 行 · {{ row.code }} {{ row.name }} ／ {{ row.unit }} ／ 来源属性：{{ row.sourceAttribute || '未提供' }}</p>
              <p v-if="row.material" class="mt-1 text-teal-800">候选：{{ row.material.code }} {{ row.material.name }} · v{{ row.material.version }} ／ {{ row.material.data.engineering?.attribute }} ／ {{ row.material.data.engineering?.department }}</p>
              <p v-else class="mt-1 text-amber-800">{{ row.issue }}</p>
            </div>
          </div>
        </li></ul>
        <Button :disabled="disabled || !selected.length" @click="apply">将勾选物料填入当前编辑内容</Button>
      </template>
      <p class="text-sm text-slate-500">请逐行核对后勾选。同编码不同来源属性不互相匹配，不合并用料行。只填物料身份与版本，不改变用量、工序或来源核对说明；之后仍需保存和审核，正式下发仍未开放。</p>
    </div>
  </SectionPanel>
</template>
