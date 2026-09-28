<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import IamDisclosure from '@/components/iam/workspace/IamDisclosure.vue'
import { iamApi, type PermissionCatalogItem } from '@/api/iam'
import type { OrganizationCatalog } from '@/api/identity'
import { http, getApiErrorMessage } from '@/lib/http'
import { Button } from '@/components/ui/button'
const props = defineProps<{
  userId: string
  catalog: OrganizationCatalog
  defaultFactory?: string
  defaultDepartment?: string
}>()
const permissions = ref<PermissionCatalogItem[]>([])
const code = ref('')
const factory = ref(props.defaultFactory || '')
const department = ref(props.defaultDepartment || '')
const at = ref('')
const busy = ref(false)
const error = ref('')
const result = ref<{ allowed: boolean; reason: string; source_ids: string[]; limitation: string }>()
const departments = computed(
  () => props.catalog.organizations.find((o) => o.id === factory.value)?.departments ?? [],
)
let generation = 0
let alive = true
const opened = ref(false)
async function expand(value: boolean) {
  if (!value || opened.value) return
  opened.value = true
  try {
    const data = await iamApi.listPermissions('all')
    if (alive) permissions.value = data
  } catch (e) {
    if (alive) {
      error.value = getApiErrorMessage(e)
      opened.value = false
    }
  }
}
watch(
  [code, factory, department, at],
  () => {
    ++generation
    result.value = undefined
    error.value = ''
    busy.value = false
  },
  { flush: 'sync' },
)
onBeforeUnmount(() => {
  alive = false
  ++generation
})
async function explain() {
  const request = ++generation
  busy.value = true
  error.value = ''
  result.value = undefined
  try {
    const data = (
      await http.post(`/iam/users/${props.userId}/access/explain`, {
        permission_code: code.value,
        factory_id: factory.value,
        department: department.value,
        ...(at.value
          ? { at: `${at.value.length === 16 ? at.value + ':00' : at.value}+08:00` }
          : {}),
      })
    ).data
    if (request === generation) result.value = data
  } catch (e) {
    if (request === generation) error.value = getApiErrorMessage(e)
  } finally {
    if (request === generation) busy.value = false
  }
}
</script>
<template>
  <IamDisclosure title="查看授权依据" @update:open="expand"
    ><form class="iam-wizard" @submit.prevent="explain">
      <label
        >操作权限<select v-model="code" required>
          <option value="">选择要核对的操作</option>
          <option v-for="p in permissions" :key="p.code" :value="p.code">
            {{ p.module_name }} · {{ p.name }}
          </option>
        </select></label
      >
      <div class="iam-fields">
        <label
          >业务厂区<select v-model="factory" required>
            <option value="">请选择业务厂区</option>
            <option value="*">集团管理范围</option>
            <option
              v-for="o in catalog.organizations.filter((o) => o.kind === 'factory')"
              :key="o.id"
              :value="o.id"
            >
              {{ o.name }}
            </option>
          </select></label
        ><label
          >作用部门<select v-model="department" required>
            <option value="">请选择作用部门</option>
            <option value="*">全部部门</option>
            <option v-for="d in departments" :key="d.code" :value="d.code">{{ d.name }}</option>
          </select></label
        >
      </div>
      <label>查询时间（北京时间，留空表示现在）<input v-model="at" type="datetime-local" /></label
      ><Button type="submit" variant="outline" :disabled="busy || !code">核对授权</Button>
      <p v-if="error" role="alert" class="iam-error">{{ error }}</p>
      <div v-if="result" role="status">
        <strong
          >{{ result.allowed ? '此授权检查允许' : '此授权检查拒绝' }} · {{ result.reason }}</strong
        >
        <p>具体业务仍需满足单据状态、人员资格和模块规则。</p>
        <small>{{ result.limitation }}</small>
      </div>
    </form></IamDisclosure
  >
</template>
