<script setup lang="ts">
import { displayValue, type FieldSpec } from '../types';
defineProps<{ value: unknown; field?: FieldSpec }>();
</script>
<template>
  <span
    :class="{
      'inj-mono':
        ['number', 'integer', 'datetime'].includes(field?.value_type || '') ||
        ['mold_code', 'order_no', 'item_no', 'machine_code'].includes(
          field?.key || '',
        ),
      'inj-a-chip': field?.key === 'required_machine_a' && value != null,
      'inj-cell-reason': field?.key === 'unplaced_reason',
    }"
    :title="
      value == null
        ? '未填写'
        : String(typeof value === 'object' ? JSON.stringify(value) : value)
    "
    >{{ displayValue(value, field)
    }}<small v-if="value != null && field?.key === 'required_machine_a'">
      A</small
    ><small v-else-if="value != null && field?.key === 'delivery_slack_hours'">
      h</small
    ></span
  >
</template>
