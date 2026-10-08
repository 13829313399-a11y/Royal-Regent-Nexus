<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { cartonCustomerResponsibilitiesApi as api, emptyResponsibilities } from '@/api/cartonCustomerResponsibilities'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage } from '@/lib/http'

const props = defineProps<{ factoryId: string }>()
const emit = defineEmits<{ changed: [] }>()
const auth = useAuthStore()
const data = ref(emptyResponsibilities()), error = ref(''), search = ref(''), saving = ref(false), loading = ref(false)
const editing = ref(''), selected = ref<string[]>([]), reason = ref('')
const rows = computed(() => data.value.customers.filter(row => [row.name, row.code, ...row.users.map(user => user.name)].some(value => value.toLowerCase().includes(search.value.trim().toLowerCase()))))
let epoch = 0, controller = new AbortController()
async function refresh() {
  const current = ++epoch
  controller.abort(); controller = new AbortController()
  data.value = emptyResponsibilities(); editing.value = ''; saving.value = false; loading.value = true; error.value = ''
  try {
    const result = await api.get(props.factoryId, controller.signal)
    if (current === epoch) data.value = result
  } catch (cause) { if (current === epoch) error.value = getApiErrorMessage(cause) }
  finally { if (current === epoch) loading.value = false }
}
async function save() {
  const row = data.value.customers.find(row => row.id === editing.value)
  if (!row || saving.value || !data.value.can_manage) return
  if (reason.value.trim().length < 4) { error.value = '请填写至少四个字的责任分配原因。'; return }
  const current = epoch, factory = props.factoryId
  saving.value = true; error.value = ''
  try {
    const result = await api.save(factory, row.id, [...selected.value], row.revision, reason.value.trim(), controller.signal)
    if (current !== epoch) return
    data.value = result; editing.value = ''; reason.value = ''; emit('changed')
  } catch (cause) { if (current === epoch) error.value = `${getApiErrorMessage(cause)}；若请求中断，请刷新核实分配结果。` }
  finally { if (current === epoch) saving.value = false }
}
watch(() => [props.factoryId, auth.currentUser?.id, auth.authorizationVersion], () => { void refresh() }, { immediate: true })
onBeforeUnmount(() => { epoch++; controller.abort() })
</script>

<template>
  <article class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm" aria-label="客户责任范围">
    <div class="flex flex-wrap items-center justify-between gap-3"><div><h3 class="font-bold">客户责任范围</h3><p class="mt-1 text-xs leading-5 text-slate-500">普通经办人仅操作已分配客户的订单；同一客户可多人负责。主管、经理及管理员仍须具备对应厂区权限。收发库存与 QC 检查沿用岗位权限。</p></div><button type="button" :disabled="saving" class="rounded-lg border px-3 py-2 text-xs" @click="refresh">刷新责任范围</button></div>
    <p v-if="error" role="alert" class="mt-3 text-sm text-red-700">{{ error }}</p>
    <p v-if="loading" class="mt-3 text-sm text-slate-500">正在读取责任范围…</p>
    <template v-else-if="data.can_manage">
      <input v-model="search" aria-label="搜索责任客户" placeholder="客户 / 责任人员" class="mt-3 h-9 w-full rounded-lg border px-3 text-sm">
      <div v-for="row in rows" :key="row.id" class="mt-3 rounded-lg border p-3 text-sm"><div class="flex items-center gap-3"><b>{{ row.name }}</b><span class="flex-1 text-xs text-slate-500">{{ row.users.map(user => user.name).join('、') || '尚未分配（普通经办人无法操作）' }}</span><button type="button" :disabled="saving" :aria-label="`分配客户 ${row.name}`" class="rounded border px-3 py-1.5 text-teal-700" @click="editing = row.id; selected = row.users.map(user => user.id); reason = ''; error = ''">分配人员</button></div>
        <form v-if="editing === row.id" class="mt-3 space-y-3" @submit.prevent="save"><div class="grid max-h-64 gap-2 overflow-y-auto sm:grid-cols-3"><label v-for="user in [...data.users, ...row.users.filter(assigned => !data.users.some(user => user.id === assigned.id))]" :key="user.id" class="flex items-center gap-2 text-xs"><input v-model="selected" type="checkbox" :value="user.id" :disabled="saving">{{ user.name }}<span v-if="!data.users.some(candidate => candidate.id === user.id)" class="text-amber-700">（已不具备操作资格，请移除）</span></label></div><p v-if="!data.users.length" class="text-xs text-amber-700">没有具备本厂订单操作权限的有效人员；请先维护岗位权限。</p><textarea v-model="reason" required minlength="4" maxlength="500" aria-label="客户责任分配原因" placeholder="填写责任分配或交接原因" class="w-full rounded-lg border p-2 text-sm" :disabled="saving" /><div class="flex gap-2"><button type="submit" :disabled="saving" class="rounded-lg bg-teal-700 px-4 py-2 text-white">保存分配</button><button type="button" :disabled="saving" class="rounded-lg border px-4 py-2" @click="editing = ''">取消</button></div></form>
      </div>
    </template>
    <p v-else-if="!loading && !error" class="mt-3 text-sm text-slate-600">{{ data.own_customer_codes.length ? `已分配 ${data.own_customer_codes.length} 个客户，可操作对应订单。` : '尚未分配客户，请联系主管；仍可按岗位进行收发库存或 QC 检查。' }}</p>
  </article>
</template>
