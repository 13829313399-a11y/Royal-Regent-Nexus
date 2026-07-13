<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { AlertTriangle, CheckCircle2, ClipboardCheck, LoaderCircle, XCircle } from '@lucide/vue'
import { iamApi, type AccessRequestItem } from '@/api/iam'
import IamNavigation from '@/components/iam/IamNavigation.vue'
import { permissionDisplayLabel } from '@/components/iam/permissionCatalogLabels'
import { getApiErrorMessage } from '@/lib/http'

const requests = ref<AccessRequestItem[]>([])
const statusFilter = ref('pending')
const canReviewRequests = ref(false)
const reviewReasons = ref<Record<string, string>>({})
const actionKey = ref('')
const isLoading = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
const pendingCount = computed(() => requests.value.filter((request) => request.status === 'pending').length)

function statusLabel(status: AccessRequestItem['status']) {
  return { pending: '待审批', approved: '已通过', rejected: '已拒绝', invalidated: '已失效' }[status]
}

function effectLabel(effect: string) {
  return { inherit: '继承角色模板', allow: '单独允许', deny: '单独禁止' }[effect] ?? effect
}

function permissionLabel(permissionCode: string) {
  return permissionDisplayLabel({ code: permissionCode, name: permissionCode })
}

async function loadData() {
  isLoading.value = true
  errorMessage.value = ''
  try {
    const [requestItems, scopeResponse] = await Promise.all([
      iamApi.listAccessRequests(statusFilter.value),
      iamApi.getManageableScopes(),
    ])
    requests.value = requestItems
    canReviewRequests.value = scopeResponse.can_review_access_requests
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    isLoading.value = false
  }
}

async function review(request: AccessRequestItem, decision: 'approve' | 'reject') {
  const reason = reviewReasons.value[request.id]?.trim() ?? ''
  if (!reason) {
    errorMessage.value = '审批或拒绝都必须填写复核意见。'
    return
  }
  actionKey.value = `${decision}:${request.id}`
  errorMessage.value = ''
  try {
    if (decision === 'approve') await iamApi.approveAccessRequest(request.id, reason)
    else await iamApi.rejectAccessRequest(request.id, reason)
    successMessage.value = `权限申请已${decision === 'approve' ? '批准' : '拒绝'}。`
    await loadData()
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    actionKey.value = ''
  }
}

onMounted(() => void loadData())
</script>

<template>
  <main class="min-h-screen overflow-x-hidden bg-slate-100 text-slate-950">
    <IamNavigation title="权限申请" subtitle="范围管理员发起的跨范围或高风险授权在这里由集团超级管理员复核。" />
    <div class="mx-auto grid min-w-0 max-w-[1200px] gap-5 px-4 py-6 sm:px-5 xl:px-8">
      <section class="flex min-w-0 flex-wrap items-end justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"><div class="min-w-0"><h2 class="flex items-center gap-2 font-bold"><ClipboardCheck class="size-5 shrink-0 text-emerald-700" aria-hidden="true" />申请队列</h2><p class="mt-1 text-sm text-slate-500" aria-live="polite">当前列表 {{ requests.length }} 条，待审批 {{ pendingCount }} 条。</p></div><label class="grid w-full gap-1.5 text-xs font-semibold text-slate-600 sm:w-44"><span>申请状态</span><select v-model="statusFilter" aria-label="按申请状态筛选" class="h-10 min-w-0 rounded-xl border border-slate-200 px-3 text-sm font-normal text-slate-800" @change="loadData"><option value="pending">待审批</option><option value="approved">已通过</option><option value="rejected">已拒绝</option><option value="invalidated">已失效</option></select></label></section>
      <div v-if="errorMessage" role="alert" class="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">{{ errorMessage }}</div>
      <div v-if="successMessage" role="status" class="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm font-semibold text-emerald-800">{{ successMessage }}</div>
      <div v-if="isLoading" class="grid min-h-56 place-items-center rounded-2xl bg-white" role="status" aria-label="正在加载权限申请"><LoaderCircle class="size-7 animate-spin text-emerald-700" /></div>
      <article v-for="request in requests" v-else :key="request.id" class="min-w-0 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
        <div class="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 pb-4"><div><div class="flex items-center gap-2"><h3 class="font-bold">{{ request.target_user_name }}</h3><AlertTriangle v-if="request.high_risk" class="size-4 text-amber-600" /></div><p class="mt-1 text-sm text-slate-500">申请人 {{ request.requester_name }} · {{ new Date(request.created_at).toLocaleString('zh-CN') }}</p></div><span class="rounded-full px-2.5 py-1 text-xs font-bold" :class="request.status === 'pending' ? 'bg-amber-50 text-amber-700' : request.status === 'approved' ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-600'">{{ statusLabel(request.status) }}</span></div>
        <div class="py-4"><p class="mb-3 text-sm"><b>申请原因：</b>{{ request.reason }}</p><div class="grid min-w-0 gap-2 sm:grid-cols-2"><div v-for="change in request.changes" :key="`${change.permission_code}:${change.factory_id}:${change.department}`" class="min-w-0 rounded-xl bg-slate-50 p-3 text-sm"><b class="block text-slate-800">{{ permissionLabel(change.permission_code) }}</b><code class="mt-0.5 block break-all text-xs text-slate-500">{{ change.permission_code }}</code><p class="mt-1 text-xs text-slate-500">{{ effectLabel(change.effect) }} · {{ change.factory_id }} / {{ change.department }}</p></div></div></div>
        <div v-if="request.status === 'pending' && canReviewRequests" class="grid min-w-0 gap-3 border-t border-slate-100 pt-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end"><label class="grid min-w-0 gap-1.5 text-xs font-semibold text-slate-600" :for="`review-reason-${request.id}`"><span>复核意见（必填）</span><input :id="`review-reason-${request.id}`" v-model="reviewReasons[request.id]" class="h-11 min-w-0 rounded-xl border border-slate-200 px-3 text-sm font-normal text-slate-900 outline-none focus:border-emerald-500" placeholder="说明批准或拒绝的依据"></label><div class="grid grid-cols-2 gap-2 sm:flex"><button type="button" class="inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-rose-200 px-4 text-sm font-bold text-rose-700 disabled:opacity-50" :disabled="Boolean(actionKey)" @click="review(request, 'reject')"><LoaderCircle v-if="actionKey === `reject:${request.id}`" class="size-4 animate-spin" /><XCircle v-else class="size-4" />拒绝</button><button type="button" class="inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-emerald-700 px-4 text-sm font-bold text-white disabled:opacity-50" :disabled="Boolean(actionKey)" @click="review(request, 'approve')"><LoaderCircle v-if="actionKey === `approve:${request.id}`" class="size-4 animate-spin" /><CheckCircle2 v-else class="size-4" />批准</button></div></div>
        <p v-else-if="request.status === 'pending'" class="border-t border-slate-100 pt-4 text-sm font-semibold text-blue-700">申请已进入集团超级管理员审批队列。</p>
      </article>
      <p v-if="!isLoading && !requests.length" class="rounded-2xl border border-dashed border-slate-300 bg-white p-10 text-center text-sm text-slate-500">当前筛选条件下没有权限申请。</p>
    </div>
  </main>
</template>
