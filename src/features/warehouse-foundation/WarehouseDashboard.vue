<script setup lang="ts">
import { useId } from 'vue'
import { ClipboardList, RefreshCw } from '@lucide/vue'
import { Button } from '@/components/ui/button'

defineProps<{ subtitle: string; updatedAt?: string; loading: boolean; error?: string }>()
defineEmits<{ refresh: [] }>()
const todosHeading = useId()
</script>

<template>
  <div class="warehouse-dashboard" :aria-busy="loading">
    <header class="warehouse-dashboard-heading">
      <div class="warehouse-dashboard-title">
        <span class="warehouse-dashboard-icon"><ClipboardList :size="19" aria-hidden="true" /></span>
        <div><h1>工作看板</h1><p>{{ subtitle }}<span v-if="updatedAt"> · {{ updatedAt }} 更新</span></p></div>
      </div>
      <div class="warehouse-dashboard-actions">
        <Button type="button" variant="outline" :disabled="loading" @click="$emit('refresh')"><RefreshCw :size="15" aria-hidden="true" />刷新</Button>
        <slot name="primary" />
      </div>
    </header>
    <section class="warehouse-dashboard-todos" :aria-labelledby="todosHeading">
      <h2 :id="todosHeading">今日待办</h2>
      <p v-if="error" class="warehouse-dashboard-error" role="alert">{{ error }}</p>
      <div v-else class="warehouse-dashboard-panels"><slot name="todos" /></div>
    </section>
    <slot />
  </div>
</template>

<style scoped>
.warehouse-dashboard { display: grid; gap: 16px; min-width: 0; }
.warehouse-dashboard-heading, .warehouse-dashboard-todos { background: var(--card); border: 1px solid var(--border); border-radius: 12px; }
.warehouse-dashboard-heading { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px 16px; padding: 18px 16px; }
.warehouse-dashboard-title, .warehouse-dashboard-actions { display: flex; align-items: center; gap: 8px; }
.warehouse-dashboard-title { min-width: 0; }
.warehouse-dashboard-actions { flex-wrap: wrap; }
.warehouse-dashboard-icon { display: grid; flex: 0 0 36px; place-items: center; height: 36px; border-radius: 8px; color: var(--primary); background: var(--accent); }
.warehouse-dashboard-title h1 { font-size: 18px; font-weight: 600; line-height: 1.4; }
.warehouse-dashboard-title p { margin-top: 6px; color: var(--muted-foreground); font-size: 13px; line-height: 1.6; overflow-wrap: anywhere; }
.warehouse-dashboard-todos { display: grid; gap: 10px; padding: 12px; }
.warehouse-dashboard-todos h2 { padding-inline: 4px; font-size: 16px; font-weight: 650; }
.warehouse-dashboard-panels { display: grid; gap: 10px; min-width: 0; }
.warehouse-dashboard-error { padding: 8px 4px; color: var(--destructive); font-size: 13px; }
@media (min-width: 768px) {
  .warehouse-dashboard-heading { padding: 20px 24px; }
  .warehouse-dashboard-title h1 { font-size: 20px; }
  .warehouse-dashboard-panels { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
