<script setup lang="ts">
import IamDisclosure from '@/components/iam/workspace/IamDisclosure.vue'
import type { AccessTuple, ChangePreview } from '@/api/identity'
import { formatBusinessDateTime } from '@/lib/dateTime'
import { registrationDepartmentLabel } from '@/data/registrationDepartments'
defineProps<{ preview: ChangePreview }>()
function grouped(tuples: AccessTuple[]) {
  const groups = new Map<string, { name: string; scopes: Map<string, Set<string>> }>()
  for (const tuple of tuples) {
    const entry = groups.get(tuple.permission_code) ?? {
      name: tuple.permission_name || tuple.permission_code,
      scopes: new Map(),
    }
    const factory = tuple.factory_name || tuple.factory_id
    const scopes = entry.scopes.get(factory) ?? new Set<string>()
    scopes.add(tuple.department_name || tuple.department)
    entry.scopes.set(factory, scopes)
    groups.set(tuple.permission_code, entry)
  }
  return [...groups].map(([code, entry]) => ({
    code,
    name: entry.name,
    scopes: [...entry.scopes].map(
      ([factory, departments]) =>
        `${factory} · ${departments.has('全部部门') ? '全部部门' : [...departments].join('、')}`,
    ),
  }))
}
</script>
<template>
  <section class="iam-impact" aria-label="变更影响">
    <h3>变更影响</h3>
    <div class="iamx-comparison">
      <div>
        <small>变更前</small
        >{{
          preview.before_identity.primary_assignment?.org_name ||
          preview.before_identity.primary_factory_id ||
          '未确认组织'
        }}
        ·
        {{
          registrationDepartmentLabel(preview.before_identity.primary_department) +
          ' · ' +
          (preview.before_identity.position || '无主职')
        }}
      </div>
      <span aria-hidden="true">→</span>
      <div>
        <small>变更后</small
        >{{ preview.after_identity.primary_assignment?.org_name || '无有效主职' }} ·
        {{
          registrationDepartmentLabel(preview.after_identity.primary_department) +
          ' · ' +
          (preview.after_identity.position || '—')
        }}
      </div>
    </div>
    <p>生效时间：{{ formatBusinessDateTime(preview.effective_at) }}（北京时间）</p>
    <p v-if="preview.high_risk" class="iamx-error">涉及高风险授权，请逐项核对以下影响。</p>
    <IamDisclosure
      v-for="(label, key) in {
        removed: '停止权限',
        added: '新增权限',
        retained: '保留权限',
        source_changed: '来源变化，能力保留',
      }"
      :key="key"
      :default-open="key === 'removed' || key === 'added'"
      :title="`${label} · ${grouped(preview.permission_diffs[key]).length} 项操作 / ${preview.permission_diffs[key].length} 条范围记录`"
      ><ul class="iamx-diff-list">
        <li v-for="item in grouped(preview.permission_diffs[key])" :key="item.code">
          <strong>{{ item.name }}</strong>
          <p v-for="scope in item.scopes" :key="scope">{{ scope }}</p>
        </li>
      </ul>
      <p v-if="!preview.permission_diffs[key].length" class="iamx-muted">
        无此类变化
      </p></IamDisclosure
    >
    <p class="iam-notice">
      已识别 {{ preview.handover_summary.count }} 项工作责任。{{
        preview.handover_summary.coverage.filter((c) => c.status === 'uncovered').length
      }}
      个模块需人工核实，变更生效后仍可继续办理交接。
    </p>
    <p v-if="preview.requires_approval" class="iam-notice">
      此变更需提交覆盖完整范围的管理员审核。
    </p>
  </section>
</template>
