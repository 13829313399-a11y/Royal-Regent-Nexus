<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { cartonCustomerResponsibilitiesApi as api, emptyResponsibilities } from '@/api/cartonCustomerResponsibilities'
import { useAuthStore } from '@/stores/auth'
import { getApiErrorMessage } from '@/lib/http'

const props = defineProps<{ factoryId: string }>()
const emit = defineEmits<{ changed: [] }>()
const auth = useAuthStore()
const data = ref(emptyResponsibilities()), error = ref(''), search = ref(''), saving = ref(false), loading = ref(false)
const editing = ref(''), selected = ref<string[]>([]), reason = ref(''), ownerId = ref<string | undefined>()
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
  if (!row || saving.value || !(row.can_manage ?? data.value.unrestricted)) return
  if (reason.value.trim().length < 4) { error.value = '请填写至少四个字的责任分配原因。'; return }
  const current = epoch, factory = props.factoryId
  saving.value = true; error.value = ''
  try {
    const result = await api.save(factory, row.id, [...selected.value], row.revision, reason.value.trim(), controller.signal,
      data.value.unrestricted && ownerId.value !== undefined ? ownerId.value || null : undefined)
    if (current !== epoch) return
    data.value = result; editing.value = ''; reason.value = ''; emit('changed')
  } catch (cause) { if (current === epoch) error.value = `${getApiErrorMessage(cause)}；若请求中断，请刷新核实分配结果。` }
  finally { if (current === epoch) saving.value = false }
}
async function claim(row: typeof data.value.customers[number]) {
  if (saving.value || !row.can_claim) return
  const current = epoch, factory = props.factoryId
  saving.value = true; error.value = ''
  try {
    const result = await api.claim(factory, row.id, row.revision, controller.signal)
    if (current !== epoch) return
    data.value = result; emit('changed')
  } catch (cause) { if (current === epoch) error.value = `${getApiErrorMessage(cause)}；请刷新核实认领结果。` }
  finally { if (current === epoch) saving.value = false }
}
// Session heartbeats replace currentUser even when authorization is unchanged.
// Compare each stable boundary separately so they do not discard the list or a draft.
watch([
  () => props.factoryId,
  () => auth.currentUser?.id,
  () => auth.authorizationVersion,
  () => auth.authzMode,
  () => auth.currentUser?.identity?.effective_context_key,
  () => auth.currentUser?.identity?.employment_epoch,
], () => { void refresh() }, { immediate: true })
onBeforeUnmount(() => { epoch++; controller.abort() })
</script>

<template>
  <article class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm" aria-label="客户责任范围">
    <div class="flex flex-wrap items-center justify-between gap-3"><div><h3 class="font-bold">客户认领与协作</h3><p class="mt-1 text-xs leading-5 text-slate-500">未认领客户对本厂有岗位权限的人员开放；认领后，负责人和获授权同事可操作订单及入库登记；默认显示自己客户，需要时可切换查看其他客户。负责人可授权同事；主管、经理、管理员在原有厂区权限内统筹，库存和 QC 仍按岗位共享。</p></div><button type="button" :disabled="saving" class="rounded-lg border px-3 py-2 text-xs" @click="refresh">刷新责任范围</button></div>
    <p v-if="error" role="alert" class="mt-3 text-sm text-red-700">{{ error }}</p>
    <p v-if="loading" class="mt-3 text-sm text-slate-500">正在读取责任范围…</p>
    <template v-else-if="!error">
      <input v-model="search" aria-label="搜索责任客户" placeholder="客户 / 责任人员" class="mt-3 h-9 w-full rounded-lg border px-3 text-sm">
      <div v-for="row in rows" :key="row.id" class="mt-3 rounded-lg border p-3 text-sm">
        <div class="flex flex-wrap items-center gap-3"><b>{{ row.name }}</b><span class="flex-1 text-xs text-slate-500">{{ row.users.length ? `负责人：${row.owner?.name || '待主管指定'}；协作人员：${row.users.map(user => user.name).join('、')}` : '未认领 · 本厂有岗位权限的人员均可操作' }}</span>
          <button v-if="row.can_claim" type="button" :disabled="saving" :aria-label="`认领客户 ${row.name}`" class="rounded border bg-teal-700 px-3 py-1.5 text-white" @click="claim(row)">我来负责</button>
          <button v-if="row.can_manage ?? data.unrestricted" type="button" :disabled="saving" :aria-label="`分配客户 ${row.name}`" class="rounded border px-3 py-1.5 text-teal-700" @click="editing = row.id; selected = row.users.map(user => user.id); ownerId = row.owner?.id; reason = ''; error = ''">授权同事</button>
        </div>
        <form v-if="editing === row.id" class="mt-3 space-y-3" @submit.prevent="save">
          <div class="grid max-h-64 gap-2 overflow-y-auto sm:grid-cols-3"><label v-for="user in [...data.users, ...row.users.filter(assigned => !data.users.some(user => user.id === assigned.id))]" :key="user.id" class="flex items-center gap-2 text-xs"><input v-model="selected" type="checkbox" :value="user.id" :disabled="saving || (!data.unrestricted && user.id === row.owner?.id)">{{ user.name }}<span v-if="!data.users.some(candidate => candidate.id === user.id)" class="text-amber-700">（已不具备操作资格，请移除）</span></label></div>
          <label v-if="data.unrestricted" class="block text-xs">客户负责人<select v-model="ownerId" aria-label="客户负责人" class="ml-2 rounded border p-2" :disabled="saving"><option :value="undefined">保持当前负责人</option><option value="">暂无负责人（保留所选人员）</option><option v-for="user in data.users.filter(user => selected.includes(user.id))" :key="user.id" :value="user.id">{{ user.name }}</option></select></label>
          <p v-if="data.unrestricted" class="text-xs text-slate-500">取消所有人员并保存，可解除认领，重新向本厂人员开放。已有多人分配且无负责人时，可在此指定。</p>
          <p v-if="!data.users.length" class="text-xs text-amber-700">没有具备本厂订单或入库权限的有效人员；请先维护岗位权限。</p>
          <textarea v-model="reason" required minlength="4" maxlength="500" aria-label="客户责任分配原因" class="w-full rounded-lg border p-2 text-sm" :disabled="saving" />
          <div class="flex gap-2"><button type="submit" :disabled="saving" class="rounded-lg bg-teal-700 px-4 py-2 text-white">保存分配</button><button type="button" :disabled="saving" class="rounded-lg border px-4 py-2" @click="editing = ''">取消</button></div>
        </form>
      </div><p v-if="!rows.length" class="mt-3 text-sm text-slate-500">暂无匹配客户；未设置责任范围的客户按岗位权限开放。</p>
    </template>
  </article>
</template>
