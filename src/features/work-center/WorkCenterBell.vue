<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { Bell, ArrowUpRight, X, RefreshCw } from '@lucide/vue'
import { PopoverRoot, PopoverTrigger, PopoverPortal, PopoverContent, PopoverClose, DialogRoot, DialogTrigger, DialogPortal, DialogOverlay, DialogContent, DialogClose, DialogTitle, DialogDescription } from 'reka-ui'
import { useWorkCenterStore } from '@/stores/workCenter'
import WorkEntryRow from './WorkEntryRow.vue'
import WorkCenterHealth from './WorkCenterHealth.vue'
import { workHealth } from './health'
import { useRouter } from 'vue-router'
const center = useWorkCenterStore(), router = useRouter()
const tab = ref<'todo' | 'info'>('todo'), mobile = ref(false)
function resize() { mobile.value = window.innerWidth < 640 }
onMounted(() => { resize(); window.addEventListener('resize', resize) })
onUnmounted(() => window.removeEventListener('resize', resize))
const label = computed(() => `待办与消息，${center.count} 项可处理，${center.summary?.info_unread_total ?? 0} 条未读知会`)
async function open(value: boolean) { center.panelOpen = value; if (value) { await center.refresh(); if (tab.value === 'info') await center.loadInformation() } }
async function changeTab(value: 'todo' | 'info') { tab.value = value; if (value === 'info') await center.loadInformation() }
function select(id: string) { center.panelOpen = false; void router.push({ name: 'notification-center', query: { entry: id, view: tab.value } }) }
</script>

<template>
  <component :is="mobile ? DialogRoot : PopoverRoot" :open="center.panelOpen" @update:open="open">
    <component :is="mobile ? DialogTrigger : PopoverTrigger" class="nc-bell" :aria-label="label"><Bell :size="21" /><span v-if="center.count" class="nc-count">{{ center.count > 99 ? '99+' : center.count }}</span><span v-else-if="center.summary?.info_unread_total" class="nc-info-dot" /></component>
    <component :is="mobile ? DialogPortal : PopoverPortal"><DialogOverlay v-if="mobile" class="nc-sheet-overlay" /><component :is="mobile ? DialogContent : PopoverContent" class="nc-popover" :class="{ 'nc-bell-sheet': mobile }" :side-offset="12" align="end">
      <DialogDescription v-if="mobile" class="sr-only">当前可处理事项与知会消息，打开事项工作台查看全部。</DialogDescription>
      <header><div><component :is="mobile ? DialogTitle : 'h2'">待办与消息</component><p>{{ center.count }} 项可处理<span v-if="center.summary?.overdue_total"> · {{ center.summary.overdue_total }} 项逾期</span></p></div><component :is="mobile ? DialogClose : PopoverClose" class="nc-icon-button" aria-label="关闭通知面板"><X :size="18" /></component></header>
      <nav aria-label="通知类别"><button :class="{ active: tab === 'todo' }" @click="changeTab('todo')">待办 {{ center.count }}</button><button :class="{ active: tab === 'info' }" @click="changeTab('info')">知会 {{ center.summary?.info_unread_total ?? 0 }}</button></nav>
      <WorkCenterHealth :snapshot="center.bell" :syncing="center.syncing" @retry="center.refresh()" /><div class="nc-bell-list"><p v-if="center.loading" class="nc-muted">正在核验当前责任…</p><p v-else-if="center.error" class="nc-error">{{ center.error }}</p><template v-else><WorkEntryRow v-for="entry in tab === 'todo' ? center.bell?.items : center.information" :key="entry.id" :entry="entry" compact @select="select" /><p v-if="!(tab === 'todo' ? center.bell?.items.length : center.information.length)" class="nc-bell-empty">{{ workHealth(center.bell)?.warning ? '暂时无法核实全部事项' : tab === 'todo' ? '已接入业务范围内暂无待办' : '暂无知会消息' }}</p></template></div>
      <footer><RouterLink :to="{ name: 'notification-center', query: { view: tab } }" @click="center.panelOpen = false">打开事项工作台<ArrowUpRight :size="16" /></RouterLink><button class="nc-icon-button" aria-label="刷新事项" @click="center.refresh()"><RefreshCw :size="16" /></button></footer>
    </component></component>
  </component>
</template>
