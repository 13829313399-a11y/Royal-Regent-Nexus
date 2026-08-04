<script setup lang="ts">
import { computed } from 'vue'
import { Bell, Bot, CalendarDays, CircleHelp, Database, MessageSquareText, RefreshCw, RotateCcw, Save, Search, Sparkles } from '@lucide/vue'
import type { FactoryId } from '../types'

const props = defineProps<{ factoryId: FactoryId; factoryName: string; sourceMode: 'live' | 'fallback'; sourceMessage: string; refreshing: boolean; search: string; lastSyncedAt: string; planStatus: string; pendingCount: number; saving: boolean; canSave: boolean; saveMessage: string }>()
const emit = defineEmits<{ 'update:factoryId': [value: string]; 'update:search': [value: string]; refresh: []; openAutoSchedule: []; save: []; discard: [] }>()
const today = computed(() => new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date()).replaceAll('/', '-'))
</script>

<template>
  <header class="scheduling-topbar">
    <div class="brand-mark"><Bot :size="22" /></div>
    <div class="brand-copy"><strong>Royal Regent Nexus</strong><span>INJECTION SCHEDULING · V2</span></div>
    <div class="topbar-live"><span class="live-dot"></span><span>计划中枢在线</span><b>{{ sourceMode === 'live' ? '正式数据' : '演示模式' }}</b></div>
    <div class="topbar-actions"><button aria-label="帮助"><CircleHelp :size="18" /></button><button aria-label="消息"><MessageSquareText :size="18" /></button><button aria-label="通知"><Bell :size="18" /></button><div class="avatar">KS</div></div>
  </header>
  <section class="scheduling-commandbar" aria-label="排产命令栏">
    <div class="page-identity"><span class="eyebrow">生产部 / 注塑排产</span><strong>注塑排产中枢</strong><span class="readonly-badge editable">Phase 5 · 运营与校准</span></div>
    <label class="command-field factory-field"><span>厂区</span><select :value="factoryId" @change="emit('update:factoryId', ($event.target as HTMLSelectElement).value)"><option value="huaxing">华兴</option><option value="huakang-a">华康 A</option><option value="huakang-b">华康 B</option><option value="huakang-c">华康 C</option><option value="huakang-d">华康 D</option><option value="huadeng">华登</option></select></label>
    <div class="command-field date-field"><CalendarDays :size="15" /><span>{{ today }}</span></div>
    <label class="command-search"><Search :size="16" /><input :value="search" placeholder="搜索机台、工模、订单、货号…" @input="emit('update:search', ($event.target as HTMLInputElement).value)" /></label>
    <div class="source-pill" :class="sourceMode"><Database :size="15" /><span :title="sourceMessage">{{ sourceMode === 'live' ? '正式数据库' : '只读演示数据' }}</span></div>
    <button class="command-button" :disabled="refreshing" @click="emit('refresh')"><RefreshCw :size="15" :class="{ spinning: refreshing }" />{{ refreshing ? '同步中' : '刷新同步' }}</button>
    <button v-if="pendingCount" class="command-button" @click="emit('discard')"><RotateCcw :size="15" />撤销 {{ pendingCount }}</button>
    <button class="command-button save" :disabled="!canSave || !pendingCount || saving" @click="emit('save')"><Save :size="15" />{{ saving ? '保存中' : `保存 ${pendingCount}` }}</button>
    <button class="command-button auto" @click="emit('openAutoSchedule')"><Sparkles :size="15" />自动排期</button>
    <span class="sync-time" :title="saveMessage">{{ saveMessage || (lastSyncedAt ? `${lastSyncedAt} 已同步` : `${factoryName} · ${planStatus || '无计划'}`) }}</span>
  </section>
</template>
