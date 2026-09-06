<script setup lang="ts">
import type { FieldSpec, FilterNode } from './types';
import { parseValue } from './types';
const props = defineProps<{
  modelValue: FilterNode;
  fields: FieldSpec[];
  depth?: number;
}>();
const emit = defineEmits<{ 'update:modelValue': [FilterNode] }>();
const names: Record<string, string> = {
  eq: '等于',
  ne: '不等于',
  contains: '包含',
  prefix: '开头',
  in: '属于列表',
  not_in: '排除列表',
  is_empty: '为空',
  not_empty: '非空',
  gt: '大于',
  gte: '大于等于',
  lt: '小于',
  lte: '小于等于',
  between: '区间',
  today: '今天',
  next_days: '未来 N 天',
  overdue: '逾期',
  on_day: '某天',
};
function update(index: number, node: FilterNode) {
  const children = [...(props.modelValue.children || [])];
  children[index] = node;
  emit('update:modelValue', { ...props.modelValue, children });
}
function add(group = false) {
  emit('update:modelValue', {
    ...props.modelValue,
    children: [
      ...(props.modelValue.children || []),
      group
        ? {
            op: 'or',
            children: [{ field: 'delivery_slack_hours', op: 'lt', value: 0 }],
          }
        : { field: 'remaining_shots', op: 'gt', value: 0 },
    ],
  });
}
function remove(index: number) {
  emit('update:modelValue', {
    ...props.modelValue,
    children: props.modelValue.children?.filter((_, i) => i !== index),
  });
}
function setValue(index: number, node: FilterNode, raw: string) {
  const field = props.fields.find((f) => f.key === node.field);
  if (!field) return;
  let value: unknown = raw;
  try {
    value = ['in', 'not_in', 'between'].includes(node.op!)
      ? raw.split(/[,，\n]/).map((v) => parseValue(v.trim(), field))
      : node.op === 'next_days'
        ? Number(raw)
        : parseValue(raw, field);
  } catch {
    /* Invalid text remains reviewable; server validation is authoritative. */
  }
  update(index, { ...node, value });
}
</script>
<template>
  <div class="inj-filter-group">
    <div class="inj-inline">
      <select
        aria-label="条件组关系"
        :value="modelValue.op"
        @change="
          emit('update:modelValue', {
            ...modelValue,
            op: ($event.target as HTMLSelectElement).value,
          })
        "
      >
        <option value="and">同时满足 AND</option>
        <option value="or">任一满足 OR</option></select
      ><button @click="add()">＋ 条件</button
      ><button v-if="(depth || 0) < 4" @click="add(true)">＋ 分组</button>
    </div>
    <div
      v-for="(node, index) in modelValue.children"
      :key="index"
      class="inj-filter-row"
    >
      <FilterGroup
        v-if="node.children"
        :model-value="node"
        :fields="fields"
        :depth="(depth || 0) + 1"
        @update:model-value="update(index, $event)"
      />
      <template v-else
        ><select
          aria-label="筛选字段"
          :value="node.field"
          @change="
            update(index, {
              field: ($event.target as HTMLSelectElement).value,
              op: 'eq',
              value: '',
            })
          "
        >
          <option v-for="field in fields" :key="field.key" :value="field.key">
            {{ field.label }}
          </option></select
        ><select
          aria-label="筛选运算"
          :value="node.op"
          @change="
            update(index, {
              ...node,
              op: ($event.target as HTMLSelectElement).value,
            })
          "
        >
          <option
            v-for="op in fields.find((f) => f.key === node.field)?.filter_ops"
            :key="op"
            :value="op"
          >
            {{ names[op] || op }}
          </option></select
        ><input
          v-if="
            !['is_empty', 'not_empty', 'today', 'overdue'].includes(node.op!)
          "
          aria-label="条件值"
          :value="Array.isArray(node.value) ? node.value.join(',') : node.value"
          placeholder="列表 / 区间用逗号分隔"
          @input="
            setValue(index, node, ($event.target as HTMLInputElement).value)
          "
      /></template>
      <button aria-label="移除条件" @click="remove(index)">×</button>
    </div>
  </div>
</template>
