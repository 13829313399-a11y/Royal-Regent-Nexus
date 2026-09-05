<script setup lang="ts">
defineProps<{ flags: string[] }>();
const labels: Record<string, string> = {
  material_shortage: "缺料待处理",
  product_match_required: "待匹配产品",
  pending_device_reconciliation: "设备待对账",
  cost_snapshot_requires_review: "历史成本待核对",
  device_job_changed_without_end: "任务结束待核对",
  completion_evidence_missing: "缺少完成证据",
};
</script>
<template>
  <span
    v-for="flag in flags"
    :key="flag"
    class="mr-1 inline-block rounded bg-amber-50 px-2 py-1 text-xs text-amber-800"
    >⚠ {{ labels[flag] || flag }}</span
  >
</template>
