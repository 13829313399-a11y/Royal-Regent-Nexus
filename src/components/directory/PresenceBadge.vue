<script setup lang="ts">
import { computed } from 'vue'
import type { PresenceState } from '@/api/directory'

const props = defineProps<{ state: PresenceState }>()

const label = computed(() => ({
  online: '在线',
  away: '最近在线',
  offline: '离线',
})[props.state])

</script>

<template>
  <span
    class="directory-presence"
    :data-presence="state"
  >
    <span class="directory-presence-dot" aria-hidden="true" />
    {{ label }}
  </span>
</template>

<style scoped>
.directory-presence { display:inline-flex; flex-shrink:0; align-items:center; gap:7px; padding:4px 9px; border:1px solid #dce3e8; border-radius:999px; background:#f1f5f9; color:#526172; font-size:12px; font-weight:650; line-height:1.5; white-space:nowrap; }
.directory-presence-dot { width:8px; height:8px; flex:none; border-radius:50%; background:#94a3b8; }
.directory-presence[data-presence=online] { color:#166534; background:#ecfdf3; border-color:#bbebcd; }
.directory-presence[data-presence=online] .directory-presence-dot { background:#16a34a; box-shadow:0 0 0 3px #16a34a14; }
.directory-presence[data-presence=away] { color:#8a560c; background:#fff8e9; border-color:#f4dfb5; }
.directory-presence[data-presence=away] .directory-presence-dot { background:#d99218; }
</style>
