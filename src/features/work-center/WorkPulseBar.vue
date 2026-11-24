<script setup lang="ts">
import { computed } from 'vue'
import { CheckCircle2, LocateFixed } from '@lucide/vue'
import { Button } from '@/components/ui'
import { factoryContexts } from '@/data/enterpriseMock'
import { useAppStore } from '@/stores/app'
import { moduleMeta, normalizeFactory } from './metadata'
import type { WorkFacet, WorkQuery, WorkSnapshot } from './types'

const props = defineProps<{ snapshot: WorkSnapshot | null; query: WorkQuery; mode: 'pulse' | 'facets' }>()
const emit = defineEmits<{ change: [values: Record<string, string | undefined>]; snoozed: [] }>()
const app = useAppStore()
const segments = computed(() => {
  const s = props.snapshot?.summary
  if (
    !s ||
    s.assigned_focus_total === undefined ||
    s.team_focus_total === undefined ||
    s.overdue_active_total === undefined
  )
    return []
  return [
    { id: 'overdue', label: '逾期', count: s.overdue_active_total },
    { id: 'assigned', label: '指派给我', count: s.assigned_focus_total },
    { id: 'team', label: '团队队列', count: s.team_focus_total },
    { id: 'snoozed', label: '已稍后', count: s.snoozed_total },
  ].filter((x) => x.count > 0)
})
function segment(id: string) {
  if (id === 'snoozed') {
    emit('snoozed')
    return
  }
  emit('change', {
    view: id === props.query.view || id === 'overdue' ? 'todo' : id,
    due: id === 'overdue' && props.query.due !== 'overdue' ? 'overdue' : undefined,
  })
}
function facets(items: WorkFacet[] | undefined, selected: string, label: string) {
  const list = items ?? []
  return selected && !list.some((it) => it.id === selected)
    ? [...list, { id: selected, label, count: 0 }]
    : list
}
const factories = computed(() =>
  facets(
    props.snapshot?.facets?.factories,
    props.query.factory_scope === 'authorized' ? '' : props.query.factory_scope,
    factoryContexts.find((f) => f.id === props.query.factory_scope)?.shortName || '所选厂区',
  ),
)
const modules = computed(() =>
  facets(props.snapshot?.facets?.modules, props.query.module, moduleMeta(props.query.module).label),
)
</script>
<template>
  <div
    v-if="mode === 'pulse' && snapshot && ['todo', 'assigned', 'team'].includes(query.view)"
    class="nc-pulse"
  >
    <template v-if="segments.length"
      ><div class="nc-strip" aria-label="待办责任分布">
        <Button
          v-for="s in segments"
          type="button"
          variant="ghost"
          size="xs"
          :key="s.id"
          :class="'pulse-' + s.id"
          :style="{ flexGrow: s.count }"
          :aria-label="s.label + ' ' + s.count + ' 项'"
          @click="segment(s.id)"
        />
      </div>
      <div class="nc-legend">
        <Button
          v-for="s in segments"
          :key="s.id"
          variant="ghost"
          size="xs"
          :aria-pressed="query.view === s.id || (s.id === 'overdue' && query.due === 'overdue')"
          @click="segment(s.id)"
        >
          <i :class="'pulse-' + s.id" />{{ s.label }} <b>{{ s.count }}</b>
        </Button>
      </div></template
    >
    <span v-else-if="snapshot.health.status === 'fresh' && !snapshot.summary.actionable_total" class="nc-sub"
      ><CheckCircle2 :size="14" />待办已清</span
    >
  </div>
  <div v-else-if="mode === 'facets'" class="nc-facets">
    <div class="nc-chip-set" role="group" aria-label="按厂区筛选">
      <Button
        class="nc-chip"
        size="xs"
        :variant="query.factory_scope === 'authorized' ? 'soft' : 'ghost'"
        :aria-pressed="query.factory_scope === 'authorized'"
        @click="emit('change', { factory: undefined })"
        >全部授权</Button
      ><Button
        v-for="f in factories"
        :key="f.id"
        class="nc-chip"
        size="xs"
        :variant="query.factory_scope === f.id ? 'default' : 'ghost'"
        :aria-pressed="query.factory_scope === f.id"
        @click="emit('change', { factory: query.factory_scope === f.id ? undefined : f.id })"
        >{{ f.label }} <span>{{ f.count }}</span></Button
      >
    </div>
    <div class="nc-chip-set" role="group" aria-label="按模块筛选">
      <Button
        class="nc-chip"
        size="xs"
        :variant="!query.module ? 'soft' : 'ghost'"
        :aria-pressed="!query.module"
        @click="emit('change', { module: undefined })"
        >全部模块</Button
      ><Button
        v-for="m in modules"
        :key="m.id"
        class="nc-chip"
        size="xs"
        :variant="query.module === m.id ? 'default' : 'ghost'"
        :aria-pressed="query.module === m.id"
        @click="emit('change', { module: query.module === m.id ? undefined : m.id })"
        >{{ m.label }} <span>{{ m.count }}</span></Button
      >
    </div>
    <Button
      v-if="normalizeFactory(app.activeFactoryId) !== 'authorized'"
      size="xs"
      variant="ghost"
      class="nc-sync-factory"
      @click="
        emit('change', {
          factory: query.factory_scope === app.activeFactoryId ? undefined : app.activeFactoryId,
        })
      "
      ><LocateFixed :size="13" />{{
        query.factory_scope === app.activeFactoryId
          ? '当前仅看：' + app.activeFactory?.shortName + ' ×'
          : '定位到当前厂区：' + app.activeFactory?.shortName
      }}</Button
    >
  </div>
</template>
