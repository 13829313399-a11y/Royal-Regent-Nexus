<script setup lang="ts">
import { computed } from 'vue'
import { numberWarning, type NumberRule } from '@/api/cartonMaster'
import { describeNumberTemplate } from '@/lib/cartonNumberPatterns'

const props = defineProps<{ rule: NumberRule; value: string; label: string }>()
const mismatch = computed(() => numberWarning(props.rule, props.value))
const hasTemplate = computed(() => props.rule.frozen && !!props.rule.templates?.length)
const description = computed(() => hasTemplate.value
  ? props.rule.templates!.map(describeNumberTemplate).join('；')
  : props.rule.mode === 'AUTO' ? ''
    : `前缀 ${props.rule.prefix || '不限'}，${props.rule.min_length}–${props.rule.max_length} 字${props.rule.characters === 'DIGITS' ? '，纯数字' : props.rule.characters === 'ALNUM_DASH' ? '，字母数字及 -_' : ''}`)
</script>

<template>
  <p v-if="rule.mode === 'OFF'" class="mt-1.5 text-[11px] text-slate-500">此客户不检查{{ label }}格式</p>
  <p v-else-if="!description" class="mt-1.5 text-[11px] text-amber-700" role="status">此客户尚未设置{{ label }}格式，暂不核对；可在基础资料的客户规则中识别并保存。</p>
  <p v-else-if="mismatch" role="alert" class="mt-1.5 rounded border border-amber-200 bg-amber-50 px-2 py-1 text-xs font-medium text-amber-800">
    {{ label }}格式不符，应为：{{ description }}。{{ rule.mode === 'BLOCK' ? '请修改后再保存。' : '请核对；当前为软提醒。' }}
  </p>
  <p v-else class="mt-1.5 text-[11px] text-slate-500">{{ label }}格式：{{ description }}</p>
</template>
