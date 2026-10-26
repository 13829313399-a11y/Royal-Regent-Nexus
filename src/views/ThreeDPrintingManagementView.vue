<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/auth';
import { threeDCanRead, threeDScopeKey } from '@/features/three-d-printing/navigationGuard';
import WorkspaceView from "@/features/three-d-printing/WorkspaceView.vue";
const auth = useAuthStore(), router = useRouter();
const boundary = ref(0), resetting = ref(false);
const scopeKey = computed(() => `${threeDScopeKey(auth)}:${boundary.value}`);
const canRead = computed(() => threeDCanRead(auth));
let sequence = 0;
const sessionBoundary = () => { boundary.value++; };
window.addEventListener('auth-session-boundary-changed', sessionBoundary);
onBeforeUnmount(() => { sequence++; window.removeEventListener('auth-session-boundary-changed', sessionBoundary); });
watch([scopeKey, canRead], async () => {
  const token = ++sequence;
  resetting.value = true;
  try {
    if (router.currentRoute.value.query.printer)
      await router.replace({ query: { ...router.currentRoute.value.query, printer: undefined } });
  } finally { if (token === sequence) resetting.value = false; }
}, { flush: 'sync' });
</script>
<template>
  <WorkspaceView v-if="canRead && !resetting" :key="scopeKey" />
  <p v-else role="status" class="p-6">{{ resetting ? '正在更新当前账号的工作区…' : '当前账号无华康 A 的 3D 读取权限。' }}</p>
</template>
