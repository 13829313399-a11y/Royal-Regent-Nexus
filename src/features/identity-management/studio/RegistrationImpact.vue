<script setup lang="ts">
import { ArrowRightLeft, CircleMinus, CirclePlus, Files, ShieldCheck } from '@lucide/vue'
import type { AccessTuple } from '@/api/identity'
import type { ReviewPreview } from '@/api/positionReviews'
import { Button } from '@/components/ui/button'
import { formatBusinessDateTime } from '@/lib/dateTime'
import { departmentName, permissionName } from '../positionLabels'

defineProps<{
  preview?: ReviewPreview
  loading: boolean
  canRetry: boolean
  denials: AccessTuple[]
  closed: boolean
  readOnly: boolean
}>()
defineEmits<{ retry: [] }>()

const groups = [
  { key: 'added', label: '新增权限', icon: CirclePlus },
  { key: 'removed', label: '将收回权限', icon: CircleMinus },
  { key: 'retained', label: '保持不变', icon: Files },
  { key: 'source_changed', label: '来源变化', icon: ArrowRightLeft },
] as const
const tupleScope = (row: AccessTuple) => [row.factory_name || row.factory_id, row.department_name || departmentName(row.department)].filter(Boolean).join(' · ')
</script>

<template>
  <aside class="iam2-registration-impact" aria-label="本次实际权限变化" :aria-busy="loading">
    <header><h3><ShieldCheck :size="17" aria-hidden="true" />本次实际权限变化</h3><small v-if="preview">有效至 {{ formatBusinessDateTime(preview.expires_at) }}</small></header>
    <div v-if="!closed && !readOnly || preview" class="iam2-impact-totals">
      <div v-for="group in groups" :key="group.key" :data-change="group.key">
        <strong>{{ preview ? preview.permission_diffs[group.key].length : '—' }}</strong><span>{{ group.label }}</span>
      </div>
    </div>
    <p v-if="loading" class="iam2-impact-message" role="status">正在核对所选权限包及作用范围…</p>
    <template v-else-if="preview">
      <p v-if="preview.high_risk" class="pw-risk" role="status">本次变更涉及高风险权限，请核对新增项及其作用范围。</p>
      <details v-for="group in groups" :key="group.key" :data-change="group.key" :open="group.key === 'added' && !!preview.permission_diffs.added.length">
        <summary><component :is="group.icon" :size="15" aria-hidden="true" />{{ group.label }}<small>{{ preview.permission_diffs[group.key].length }} 项</small></summary>
        <ul v-if="preview.permission_diffs[group.key].length"><li v-for="row in preview.permission_diffs[group.key]" :key="[row.permission_code, row.factory_id, row.department].join(':')"><span>{{ permissionName(row.permission_code, row.permission_name) }}</span><small>{{ tupleScope(row) }}</small></li></ul>
        <p v-else>本次无此类变化。</p>
      </details>
      <p v-if="preview.handover_summary">{{ preview.handover_summary }}</p>
      <p v-for="message in preview.blocked_reasons" :key="message" class="pw-error">{{ message }}</p>
    </template>
    <div v-else-if="closed || readOnly" class="iam2-impact-message" role="status"><strong>{{ closed ? '申请已结束' : '仅可查看资料' }}</strong><p>{{ closed ? '可查看已保存的办理意见与确认资料。' : '此申请当前无法预览权限变更。' }}</p></div>
    <div v-else class="iam2-impact-message" role="status"><strong>等待权限预览</strong><p>将权限包和厂区加入本单后，即可查看实际变化。</p>
      <Button v-if="canRetry" variant="outline" @click="$emit('retry')">重新核对影响</Button>
    </div>
    <div v-if="denials.length" class="pw-notice"><strong>继续生效的明确禁止</strong><p v-for="row in denials" :key="[row.permission_code, row.factory_id, row.department].join(':')">{{ permissionName(row.permission_code, row.permission_name) }} · {{ tupleScope(row) }}</p></div>
  </aside>
</template>
