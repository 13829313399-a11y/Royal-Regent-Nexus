<script setup lang="ts">
import { computed, ref } from 'vue'
import { roleScopeModeLabel } from '@/components/iam/permissionCatalogLabels'
import { departmentName, permissionName } from '../positionLabels'

const props = defineProps<{ value: unknown; field?: string }>()
const labels: Record<string, string> = {
  id: '编号', role_id: '权限包', user_id: '人员', position: '岗位', official_position_title: '正式岗位',
  role_version_id: '固定版本', assignment_id: '任职', scope_mode: '范围策略', factory_id: '厂区',
  factory_ids: '厂区', factory_ceiling: '业务厂区上限', department: '部门', department_code: '部门',
  org_unit_id: '组织', valid_from: '生效时间', valid_until: '截止时间', effect: '个人例外',
  state: '状态', permission_codes: '权限', permission_id: '权限编号', permission_code: '权限',
  binding_id: '绑定', added: '新增', removed: '收回', retained: '保留', source_changed: '来源变化',
  items: '记录', status: '状态', identity_version: '身份版本', authorization_version: '授权版本',
  permissions: '权限', role_bindings: '权限包绑定', primary_assignment: '主职', employment_status: '任职状态',
  employment_epoch: '雇佣周期', before: '变更前', after: '变更后', permission_diffs: '权限差异',
}
const entries = computed(() => props.value && typeof props.value === 'object' && !Array.isArray(props.value) ? Object.entries(props.value) : null)
const open = ref(false)
const shown = ref(20)
const scalar = computed(() => {
  const v = props.value, field = props.field
  if (v == null || v === '') return '未记录'
  if (typeof v === 'boolean') return v ? '是' : '否'
  if (typeof v !== 'string') return String(v)
  if (field === 'scope_mode') return roleScopeModeLabel(v)
  if (field === 'permission_code' || field === 'permission_codes' || field === 'permissions') return permissionName(v)
  if (field === 'department' || field === 'department_code') return departmentName(v)
  if (field === 'state' || field === 'effect') return ({active: '生效中', revoked: '已撤销', allow: '个人允许', deny: '明确禁止'} as Record<string, string>)[v] || v
  return v
})
</script>
<template>
  <details v-if="Array.isArray(value) && value.length" class="audit-snapshot-list" @toggle="open = ($event.currentTarget as HTMLDetailsElement).open">
    <summary>{{ value.length }} {{ field === 'permission_codes' || field === 'permissions' ? '项权限' : '条记录' }}</summary>
    <template v-if="open">
      <ul><li v-for="(item, index) in value.slice(0, shown)" :key="index"><AuditSnapshot :value="item" :field="field" /></li></ul>
      <button v-if="value.length > shown" type="button" @click="shown += 20">再显示 {{ Math.min(20, value.length - shown) }} 项</button>
    </template>
  </details>
  <span v-else-if="Array.isArray(value)">0 项</span>
  <dl v-else-if="entries?.length" class="audit-snapshot-fields">
    <div v-for="[key, item] in entries" :key="key"><dt>{{ labels[key] || key }}</dt><dd><AuditSnapshot :value="item" :field="key" /></dd></div>
  </dl>
  <span v-else>{{ entries ? '未记录字段' : scalar }}</span>
</template>
