<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useAppStore } from '@/stores/app'
import { getAuthenticationGeneration } from '@/lib/authenticationGeneration'
import Workspace from './CartonProcurementView.vue'
const auth = useAuthStore(), app = useAppStore(), route = useRoute(), router = useRouter()
const boundary = ref(0), resetting = ref(false)
const actorKey = computed(() => JSON.stringify([auth.currentUser?.id, auth.currentUser?.identity?.employment_epoch,
  auth.authorizationVersion, auth.authzMode, getAuthenticationGeneration(), boundary.value]))
const factory = computed(() => typeof route.query.factory === 'string' ? route.query.factory : app.activeProductionFactory.id)
const allowed = computed(() => ['carton', 'pmc-warehouse'].some(dept =>
  auth.can('carton_procurement:read', factory.value, dept) || auth.can('carton_procurement:special_request_submit', factory.value, dept)))
let sequence = 0
const sessionBoundary = () => { boundary.value++ }
window.addEventListener('auth-session-boundary-changed', sessionBoundary)
onBeforeUnmount(() => { sequence++; window.removeEventListener('auth-session-boundary-changed', sessionBoundary) })
watch(actorKey, async () => {
  const token = ++sequence
  resetting.value = true
  try {
    if (route.query.carton_record || route.query.special_request) await router.replace({ query: { ...route.query,
      carton_record: undefined, carton_from: undefined, carton_to: undefined, special_request: undefined, order_kind: undefined } })
  } finally { if (token === sequence) resetting.value = false }
}, { flush: 'sync' })
</script>
<template>
  <Workspace v-if="allowed && !resetting" :key="`${actorKey}:${factory}`" />
  <p v-else role="status" class="p-6">{{ resetting ? '正在更新当前账号的纸箱工作区…' : '当前账号无此厂区的纸箱读取权限。' }}</p>
</template>
