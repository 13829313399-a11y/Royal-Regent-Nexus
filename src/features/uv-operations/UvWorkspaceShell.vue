<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Activity, ArrowLeft, CalendarDays, CircleHelp, ClipboardCheck, Droplets, Gauge, Menu, Settings2, RefreshCw, WifiOff, X, FileInput } from '@lucide/vue'
import { useAuthStore } from '@/stores/auth'
import { UV_BASE, displayTime } from './contracts'
import { provideUvWorkspace } from './workspace'
import UvState from './components/UvState.vue'
import TaskPassport from './components/TaskPassport.vue'
import './uv-operations.css'
const w=provideUvWorkspace(), auth=useAuthStore(), route=useRoute(), mobileMenu=ref(false)
const navigation=[{path:'live',title:'现场',icon:Activity},{path:'planning',title:'任务与排程',icon:CalendarDays},{path:'shifts',title:'班次与品质',icon:ClipboardCheck},{path:'materials',title:'材料与设备',icon:Droplets},{path:'analytics',title:'效益与核算',icon:Gauge},{path:'settings',title:'基础设置',icon:Settings2}]
const active=computed(()=>navigation.find(item=>route.path.startsWith(UV_BASE+'/'+item.path))?.path)
const brandLogoUrl='/brand/huadeng_group_dynamic_logo_topbar.svg'
</script>
<template>
  <div class="uv-workspace">
    <header class="uv-topbar"><RouterLink class="uv-brand" :to="{path:'/modules/production',query:{factory:'huakang-a'}}"><img class="uv-brand-logo" :src="brandLogoUrl" alt="华登集团"/><strong>Royal Regent Nexus</strong></RouterLink><span class="uv-topbar-divider"/><span class="uv-factory">华康 A <span>/ 生产部</span></span><h1>UV打印管理</h1><div class="uv-topbar-end"><span v-if="w.meta.value?.data_mode==='synthetic'" class="uv-badge synthetic">合成验收 · 非现场数据</span><span class="uv-avatar">{{auth.currentUser?.display_name?.slice(0,1)??'用'}}</span><span class="uv-user-name">{{auth.currentUser?.display_name}}</span></div></header>
    <aside class="uv-nav" :class="{'is-open':mobileMenu}"><button class="uv-icon-button uv-nav-close" aria-label="关闭导航" @click="mobileMenu=false"><X :size="20"/></button><nav aria-label="UV 工作区导航"><RouterLink v-for="item in navigation" :key="item.path" :aria-label="item.title" :title="item.title" :to="{path:UV_BASE+'/'+item.path,query:{factory:'huakang-a'}}" :class="{active:active===item.path}" @click="mobileMenu=false"><component :is="item.icon" :size="20"/><span>{{item.title}}</span></RouterLink></nav><div class="uv-nav-bottom"><RouterLink :to="{path:UV_BASE+'/imports',query:{factory:'huakang-a'}}"><FileInput :size="18"/>导入与导出</RouterLink><RouterLink :to="{path:'/modules/production',query:{factory:'huakang-a'}}"><ArrowLeft :size="18"/>返回生产部</RouterLink><div class="uv-nav-hint"><CircleHelp :size="16"/><span>现场采集只读<br>产量以确认核数为准</span></div></div></aside>
    <main class="uv-main" :class="{'has-passport':w.selectedTaskId.value}">
      <div v-if="w.offline.value&&w.ready.value" class="uv-connection-banner" role="status"><WifiOff :size="17"/>连接中断，保留最后一次快照 · {{displayTime(w.meta.value?.as_of)}}<button @click="w.refresh">重新连接</button></div>
      <div v-if="w.notification.value" class="uv-toast" role="status">{{w.notification.value}}<button class="uv-icon-button" aria-label="关闭提示" @click="w.notification.value=''"><X :size="16"/></button></div>
      <UvState v-if="w.loading.value&&!w.ready.value" kind="loading" title="正在建立 UV 工作区" description="正在核对厂区、授权和数据状态。"/>
      <UvState v-else-if="!w.ready.value" :kind="w.errorCode.value==='permission_denied'?'denied':'error'" :title="w.error.value||'工作区尚未就绪'" description="需完成数据库迁移、业务开关和华康 A 生产部授权后使用。"><button class="uv-button" @click="w.initialize"><RefreshCw :size="16"/>重新检查</button><RouterLink class="uv-button" :to="{path:'/modules/production',query:{factory:'huakang-a'}}">返回生产部</RouterLink></UvState>
      <template v-else><div v-if="w.error.value" class="uv-error" role="alert">{{w.error.value}}<button class="uv-link" @click="w.refresh">重试</button></div><RouterView/></template>
    </main>
    <TaskPassport/>
    <nav class="uv-mobile-nav" aria-label="移动端导航"><RouterLink v-for="item in navigation.slice(0,3)" :key="item.path" :aria-label="item.title" :title="item.title" :to="{path:UV_BASE+'/'+item.path,query:{factory:'huakang-a'}}" :class="{active:active===item.path}"><component :is="item.icon" :size="20"/><span>{{item.path==='planning'?'任务':item.path==='shifts'?'班次':'现场'}}</span></RouterLink><button :aria-expanded="mobileMenu" @click="mobileMenu=!mobileMenu"><Menu :size="20"/><span>更多</span></button></nav>
  </div>
</template>
