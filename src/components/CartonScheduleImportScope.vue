<script setup lang="ts">
import { computed, ref } from 'vue'
import type { CartonScheduleImportScope } from '@/api/cartonScheduleCoverage'
import { scheduleScopeErrors } from '@/api/cartonScheduleCoverage'
import { formatBusinessDate } from '@/lib/dateTime'

const props = defineProps<{ modelValue: CartonScheduleImportScope; disabled?: boolean; showErrors?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: CartonScheduleImportScope] }>()
const touched = ref(false)
const errors = computed(() => scheduleScopeErrors(props.modelValue))
const today = () => formatBusinessDate(new Date().toISOString())
function update(fields: Partial<CartonScheduleImportScope>, confirmation = false) {
  if (props.disabled) return
  touched.value = true
  emit('update:modelValue', {
    ...props.modelValue,
    ...fields,
    ...(fields.scope_mode === 'INCREMENTAL' ? { coverage_start: '', coverage_end: '' } : {}),
    ...(!confirmation ? { full_scope_confirmed: false } : {}),
  })
}
const valueOf = (event: Event) => (event.target as HTMLInputElement).value
</script>

<template>
  <section class="mt-4 space-y-3 border-t border-border pt-4 text-xs" aria-label="排期导入范围">
    <div class="grid gap-3 sm:grid-cols-2" :class="{ 'xl:grid-cols-4': modelValue.scope_mode === 'FULL' }">
      <div class="block space-y-1 font-semibold text-muted-foreground"><span>本次导入方式</span><div data-testid="carton-schedule-import-mode" class="flex h-10 w-full items-center rounded-lg border border-input bg-muted/50 px-3 font-normal text-foreground">{{ modelValue.scope_mode === 'FULL' ? '全量 · 核对覆盖段内缺行' : '增量 · 只更新出现的记录' }}</div></div>
      <label class="block space-y-1 font-semibold text-muted-foreground"><span>业务排期日期 <span class="text-destructive">*</span></span><input :value="modelValue.as_of_date" :disabled="disabled" type="date" :max="today()" aria-label="业务排期日期" class="h-10 w-full rounded-lg border border-input bg-card px-3 font-normal text-foreground" @input="update({ as_of_date: valueOf($event) })"><span class="block text-[11px] font-normal">默认当天，可按业务排期修改。</span></label>
      <label v-if="modelValue.scope_mode === 'FULL'" class="block space-y-1 font-semibold text-muted-foreground"><span>客户交期覆盖开始 <span class="text-destructive">*</span></span><input :value="modelValue.coverage_start" :disabled="disabled" type="date" aria-label="客户交期覆盖开始" class="h-10 w-full rounded-lg border border-input bg-card px-3 font-normal text-foreground" @input="update({ coverage_start: valueOf($event) })"></label>
      <label v-if="modelValue.scope_mode === 'FULL'" class="block space-y-1 font-semibold text-muted-foreground"><span>客户交期覆盖结束 <span class="text-destructive">*</span></span><input :value="modelValue.coverage_end" :disabled="disabled" type="date" aria-label="客户交期覆盖结束" class="h-10 w-full rounded-lg border border-input bg-card px-3 font-normal text-foreground" @input="update({ coverage_end: valueOf($event) })"></label>
    </div>
    <div v-if="modelValue.scope_mode === 'FULL'" class="space-y-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-amber-900"><label class="flex items-start gap-2"><input :checked="modelValue.full_scope_confirmed" :disabled="disabled" type="checkbox" aria-label="确认全量排期完整性" class="mt-0.5 size-4 shrink-0" @change="update({ full_scope_confirmed: ($event.target as HTMLInputElement).checked }, true)"><span>我确认本文件包含所选客户在上述客户交期段内的完整在排记录（含起止日）。缺行仅生成待核实记录，不自动取消采购单。</span></label><p class="text-[11px]">修改版本日期或覆盖范围后须重新确认。日期不完整的行单独排除核实，重复身份保留全组。范围内无有效业务行不能声明全量，请补齐来源文件或明确改为增量。</p></div>
    <p v-else class="rounded-lg bg-muted/50 p-3 text-muted-foreground">增量仅新增或更新文件中出现的记录，不因未出现而推断缺行。</p>
    <ul v-if="(showErrors || touched) && errors.length" role="alert" class="space-y-1 text-red-700"><li v-for="error in errors" :key="error">{{ error }}</li></ul>
  </section>
</template>
