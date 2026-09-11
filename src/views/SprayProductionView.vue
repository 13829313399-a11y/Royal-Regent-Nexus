<script setup lang="ts">
import { computed, onBeforeUnmount, watch } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { ArrowLeft, RefreshCw } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { useAppStore } from '@/stores/app'
import { useSprayWorkspace, factories } from '@/features/spray-production/workspace'
import BatchInspector from '@/features/spray-production/components/BatchInspector.vue'
import ExportRecords from '@/features/spray-production/components/ExportRecords.vue'
import '@/features/spray-production/workspace.css'
const route = useRoute(), router = useRouter(), app = useAppStore(), store = useSprayWorkspace()
const scope = computed(() => String(route.query.factory ?? app.activeFactoryId))
const root = '/modules/production/spray-production'
const tabs = [{ path: 'overview', label: '生产总览' }, { path: 'orders', label: '工单交付' }, { path: 'schedule', label: '排产画布' }, { path: 'reports', label: '现场报工' }, { path: 'wip', label: '在制与质量' }, { path: 'logistics', label: '收发交接' }, { path: 'finance', label: '经营核算' }, { path: 'master', label: '资料中心' }, { path: 'imports', label: '历史导入' }]
watch(scope, value => store.load(value), { immediate: true })
const timer = window.setInterval(() => { if (!document.hidden && !store.busy) void store.load() }, 60000)
onBeforeUnmount(() => { window.clearInterval(timer); store.clear() })
function changeFactory(event: Event) { void router.replace({ query: { factory: (event.target as HTMLSelectElement).value } }) }
</script>
<template>
  <div class="spray-workspace">
    <header class="spray-topbar"><RouterLink :to="{ path: '/modules/production', query: { factory: scope } }" class="spray-back"><ArrowLeft :size="18" />生产部</RouterLink><h1>喷油部生产管理</h1><label>执行厂区 <select :value="scope" :disabled="store.busy" @change="changeFactory"><option value="group">选择厂区</option><option v-for="f in factories" :key="f.id" :value="f.id">{{ f.name }}</option></select></label><span class="spray-updated">{{ store.summary ? '更新于 ' + new Date(store.summary.as_of).toLocaleTimeString('zh-CN') : '等待数据' }}</span><Button variant="ghost" size="sm" :disabled="store.loading" aria-label="刷新喷油数据" @click="store.load()"><RefreshCw :size="16" /></Button></header>
    <div class="spray-body"><nav class="spray-nav" aria-label="喷油工作区"><RouterLink v-for="tab in tabs" :key="tab.path" :to="{ path: root + '/' + tab.path, query: { factory: scope } }">{{ tab.label }}</RouterLink><p>四厂共用业务组件<br>按执行厂区独立记账</p></nav>
      <main id="spray-main" class="spray-main">
        <ExportRecords class="mb-4" />
        <div v-if="store.error" role="alert" class="spray-message spray-error">{{ store.error }}<Button variant="outline" size="sm" @click="store.load()">重试读取</Button></div>
        <div v-if="store.notice" role="status" class="spray-message">{{ store.notice }}</div>
        <div v-if="store.truncated" role="alert" class="spray-message">当前加载各类最近 1,000 条记录。大数据检索请使用分页接口，当前汇总明细并非完整账册。</div>
        <div v-if="!factories.some(f => f.id === scope)" class="spray-empty"><h2>选择执行厂区</h2><p>华兴、华康 A、华康 B、华登各自维护喷油资料。集团视图不记库存。</p></div>
        <div v-else-if="store.loading && !store.summary" class="spray-empty" role="status">正在读取工单、批次与资源…</div>
        <RouterView v-else-if="store.summary" :key="scope" />
      </main><BatchInspector />
    </div>
  </div>
</template>
