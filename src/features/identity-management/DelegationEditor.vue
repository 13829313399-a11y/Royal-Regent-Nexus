<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import IamDisclosure from '@/components/iam/workspace/IamDisclosure.vue'
import type { OrganizationCatalog } from '@/api/identity'
import { iamApi, type RoleSummary } from '@/api/iam'
import { http, getApiErrorMessage } from '@/lib/http'
import { createRandomUuid } from '@/lib/randomUuid'
import { Button } from '@/components/ui/button'
const props = defineProps<{
  userId: string
  catalog: OrganizationCatalog
  defaultOrg?: string
  defaultDepartment?: string
}>()
interface Delegation {
  id: string
  revision: number
  org_unit_id: string
  department: string
  role_ids: string[]
  factory_ids: string[]
  status: string
}
const rows = ref<Delegation[]>([])
const roles = ref<RoleSummary[]>([])
const current = ref<Delegation>()
const org = ref(props.defaultOrg || '')
const department = ref(props.defaultDepartment || '')
const selectedRoles = ref<string[]>([])
const factories = ref<string[]>([])
const status = ref('active')
const reason = ref('')
const busy = ref(false)
const error = ref('')
const saved = ref('')
const newId = ref(createRandomUuid())
const departments = computed(
  () => props.catalog.organizations.find((o) => o.id === org.value)?.departments ?? [],
)
let alive = true
const opened = ref(false)
async function expand(value: boolean) {
  if (value && !opened.value) {
    opened.value = true
    await load()
  }
}
async function load() {
  try {
    const [data, packages] = await Promise.all([
      http.get<{ items: Delegation[] }>(`/iam/users/${props.userId}/delegations`),
      iamApi.listRoles(),
    ])
    if (alive) {
      rows.value = data.data.items
      roles.value = packages.filter((r) => r.code !== 'admin')
    }
  } catch (e) {
    error.value = getApiErrorMessage(e)
  }
}
function edit(row?: Delegation) {
  current.value = row
  newId.value = createRandomUuid()
  org.value = row?.org_unit_id || props.defaultOrg || ''
  department.value = row?.department || props.defaultDepartment || ''
  selectedRoles.value = [...(row?.role_ids ?? [])]
  factories.value = [...(row?.factory_ids ?? [])]
  status.value = row?.status || 'active'
  reason.value = ''
  saved.value = ''
}
async function save() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  saved.value = ''
  try {
    current.value = (
      await http.put<Delegation>(
        `/iam/users/${props.userId}/delegations/${current.value?.id || newId.value}`,
        {
          expected_revision: current.value?.revision ?? 0,
          org_unit_id: org.value,
          department: department.value,
          role_ids: selectedRoles.value,
          factory_ids: factories.value,
          status: status.value,
          reason: reason.value,
        },
      )
    ).data
    saved.value = '转授上限已保存，后续办理仍会检查其实际管理权限。'
    await load()
  } catch (e) {
    error.value = getApiErrorMessage(e)
  } finally {
    busy.value = false
  }
}
onBeforeUnmount(() => {
  alive = false
})
</script>
<template>
  <IamDisclosure title="高级设置 · 地方管理员转授上限" @update:open="expand"
    ><p>此设置限定可以授出的权限包和厂区；人员还需具备对应的用户管理与授权管理权限。</p>
    <div class="iam-actions">
      <Button v-for="row in rows" :key="row.id" variant="outline" @click="edit(row)"
        >{{ catalog.organizations.find((o) => o.id === row.org_unit_id)?.name }} ·
        {{ row.status === 'active' ? '在用' : '已撤销' }}</Button
      ><Button variant="outline" @click="edit()">新增范围</Button>
    </div>
    <form class="iam-wizard" @submit.prevent="save">
      <div class="iam-fields">
        <label
          >可管理组织<select v-model="org" required>
            <option value="">请选择组织</option>
            <option
              v-for="o in catalog.organizations.filter(
                (o) => o.kind !== 'group' && o.status === 'active',
              )"
              :key="o.id"
              :value="o.id"
            >
              {{ o.name }}
            </option>
          </select></label
        ><label
          >可管理部门<select v-model="department" required>
            <option value="">请选择部门</option>
            <option value="*">全部部门</option>
            <option v-for="d in departments" :key="d.code" :value="d.code">{{ d.name }}</option>
          </select></label
        >
      </div>
      <label
        >可授出的权限包<select v-model="selectedRoles" multiple size="5">
          <option v-for="r in roles" :key="r.id" :value="r.id">{{ r.name }}</option>
        </select></label
      >
      <fieldset>
        <legend>最大业务厂区范围</legend>
        <div class="iam-checks">
          <label v-for="o in catalog.organizations.filter((o) => o.kind === 'factory')" :key="o.id"
            ><input v-model="factories" type="checkbox" :value="o.id" />{{ o.name }}</label
          >
        </div>
      </fieldset>
      <label
        >状态<select v-model="status">
          <option value="active">在用</option>
          <option value="revoked">撤销</option>
        </select></label
      ><label>设置原因<textarea v-model="reason" required rows="2" /></label>
      <p v-if="error" role="alert" class="iam-error">{{ error }}</p>
      <p v-if="saved" role="status" class="iam-success">{{ saved }}</p>
      <Button type="submit" :disabled="busy || !catalog.writes_enabled">保存转授上限</Button>
    </form></IamDisclosure
  >
</template>
