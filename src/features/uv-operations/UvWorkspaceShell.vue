<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowLeft, CircleHelp, Menu, RefreshCw, WifiOff, X } from '@lucide/vue'
import { useAuthStore } from '@/stores/auth'
import { UV_BASE, displayTime } from './contracts'
import { provideUvWorkspace } from './workspace'
import { uvNavigation as navigation } from './presentation'
import { provideUvMotionPreference } from './composables/useUvMotionPreference'
import { useUvIndicator } from './composables/useUvIndicator'
import { useUvPresence } from './composables/useUvPresence'
import { useUvScrollLock } from './composables/useUvScrollLock'
import UvState from './components/UvState.vue'
import UvBrandLogo from './components/UvBrandLogo.vue'
import TaskPassport from './components/TaskPassport.vue'
import './uv-operations.css'
import './styles/motion.css'
const w=provideUvWorkspace(), auth=useAuthStore(), route=useRoute()
const motion=provideUvMotionPreference(()=>auth.currentUser?.id)
const active=computed(()=>navigation.find(item=>route.path===UV_BASE+'/'+item.path)?.path??'')
const nav=ref<HTMLElement|null>(null), indicator=useUvIndicator(nav,()=>active.value)
const menu=ref<HTMLDialogElement|null>(null), menuOpen=ref(false), menuPresentation=useUvPresence(menu,undefined,motion)
useUvScrollLock(()=>menuPresentation.present.value)
let menuVersion=0
watch(menuOpen,async open=>{
  const version=++menuVersion
  if(open){menuPresentation.open();await nextTick();if(version===menuVersion&&!menu.value?.open)menu.value?.showModal()}
  else menuPresentation.close(()=>menu.value?.close())
})
watch(()=>route.path,()=>{menuOpen.value=false})
watch(w.contextVersion,()=>{menuVersion++;menuOpen.value=false;menuPresentation.close(()=>menu.value?.close(),true)})
onBeforeUnmount(()=>{menuVersion++;menu.value?.close()})
</script>
<template>
  <div class="uv-workspace" :data-uv-motion="motion.attribute.value" data-yl-help="uv-operations.overview">
    <header class="uv-topbar"><RouterLink class="uv-brand" :to="{path:'/modules/production',query:{factory:'huakang-a'}}"><UvBrandLogo/><strong>Royal Regent Nexus</strong></RouterLink><span class="uv-topbar-divider"/><span class="uv-factory">华康 A <span>/ 生产部</span></span><h1>UV打印管理</h1><div class="uv-topbar-end"><span v-if="w.meta.value?.data_mode==='synthetic'" class="uv-badge synthetic">合成验收 · 非现场数据</span><span class="uv-avatar">{{auth.currentUser?.display_name?.slice(0,1)??'用'}}</span><span class="uv-user-name">{{auth.currentUser?.display_name}}</span></div></header>
    <aside class="uv-nav"><nav ref="nav" class="uv-indicator-host" aria-label="UV 工作区导航"><span class="uv-active-plate" :style="indicator.style" aria-hidden="true"/><RouterLink v-for="item in navigation" :key="item.path" :aria-label="item.title" :title="item.title" :to="{path:UV_BASE+'/'+item.path,query:{factory:'huakang-a'}}" :class="{active:active===item.path}"><component :is="item.icon" :size="20" aria-hidden="true"/><span>{{item.title}}</span></RouterLink></nav><div class="uv-nav-bottom"><RouterLink :to="{path:'/modules/production',query:{factory:'huakang-a'}}"><ArrowLeft :size="18" aria-hidden="true"/>返回生产部</RouterLink><div class="uv-nav-hint"><CircleHelp :size="16" aria-hidden="true"/><span>现场采集只读<br>产量以确认核数为准</span></div></div></aside>
    <main class="uv-main" :class="{'has-passport':w.selectedTaskId.value}" tabindex="-1" data-uv-focus-fallback>
      <div v-if="w.offline.value&&w.ready.value" class="uv-connection-banner" role="status"><WifiOff :size="17" aria-hidden="true"/>连接中断，保留最后一次快照 · {{displayTime(w.meta.value?.as_of)}}<button :disabled="w.refreshing.value" :aria-busy="w.refreshing.value" @click="w.refresh">{{w.refreshing.value?'正在重连…':'重新连接'}}</button></div>
      <div v-if="w.notification.value" class="uv-toast" role="status">{{w.notification.value}}<button class="uv-icon-button" aria-label="关闭提示" @click="w.notification.value=''"><X :size="16" aria-hidden="true"/></button></div>
      <UvState v-if="w.loading.value&&!w.ready.value" kind="loading" title="正在建立 UV 工作区" description="正在核对厂区、授权和数据状态。"/>
      <UvState v-else-if="!w.ready.value" :kind="w.errorCode.value==='permission_denied'?'denied':'error'" :title="w.error.value||'工作区尚未就绪'" description="需完成数据库迁移、业务开关和华康 A 生产部授权后使用。"><button class="uv-button" :disabled="w.loading.value" :aria-busy="w.loading.value" @click="w.initialize"><RefreshCw :size="16" aria-hidden="true"/>重新检查</button><RouterLink class="uv-button" :to="{path:'/modules/production',query:{factory:'huakang-a'}}">返回生产部</RouterLink></UvState>
      <template v-else><div v-if="w.error.value" class="uv-error" role="alert">{{w.error.value}}<button class="uv-link" :disabled="w.refreshing.value" @click="w.refresh">重试</button></div><RouterView v-slot="{Component}"><Transition name="uv-route" :css="motion.allowed.value"><component :is="Component" :key="route.name??route.path"/></Transition></RouterView></template>
    </main>
    <TaskPassport/>
    <nav class="uv-mobile-nav" aria-label="移动端导航"><RouterLink v-for="item in navigation.slice(0,3)" :key="item.path" :aria-label="item.title" :title="item.title" :to="{path:UV_BASE+'/'+item.path,query:{factory:'huakang-a'}}" :class="{active:active===item.path}"><component :is="item.icon" :size="20" aria-hidden="true"/><span>{{item.path==='planning'?'任务':item.path==='shifts'?'班次':'现场'}}</span></RouterLink><button :aria-expanded="menuOpen" aria-haspopup="dialog" aria-controls="uv-mobile-menu" @click="menuOpen=true"><Menu :size="20" aria-hidden="true"/><span>更多</span></button></nav>
    <dialog id="uv-mobile-menu" ref="menu" class="uv-dialog uv-mobile-menu" aria-labelledby="uv-menu-title" :data-phase="menuPresentation.phase.value" @cancel.prevent="menuOpen=false"><header><h2 id="uv-menu-title">UV 工作区导航</h2><button class="uv-icon-button" aria-label="关闭导航" @click="menuOpen=false"><X :size="20" aria-hidden="true"/></button></header><nav aria-label="全部 UV 页面"><RouterLink v-for="item in navigation" :key="item.path" :to="{path:UV_BASE+'/'+item.path,query:{factory:'huakang-a'}}" @click="active===item.path&&(menuOpen=false)"><component :is="item.icon" :size="20" aria-hidden="true"/>{{item.title}}</RouterLink><RouterLink :to="{path:'/modules/production',query:{factory:'huakang-a'}}"><ArrowLeft :size="20" aria-hidden="true"/>返回生产部</RouterLink></nav></dialog>
  </div>
</template>
