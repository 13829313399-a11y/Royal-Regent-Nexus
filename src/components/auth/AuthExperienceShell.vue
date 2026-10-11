<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { KeyRound, UserPlus, ShieldCheck, Pause, Play } from '@lucide/vue'
import AuthBrandScene from './AuthBrandScene.vue'
import './auth-experience.css'
const route = useRoute(), router = useRouter()
const paused = ref(false), hidden = ref(false), reduced = ref(false)
let media: MediaQueryList | undefined
const staticMotion = computed(() => paused.value || hidden.value || reduced.value)
const tabs = computed(() => ['login', 'register'].includes(String(route.name)))
function syncMotion() { hidden.value = document.visibilityState === 'hidden'; reduced.value = media?.matches ?? false }
function target(name: string) { return { name, query: typeof route.query.redirect === 'string' ? { redirect: route.query.redirect } : {} } }
function arrow(event: KeyboardEvent) {
  if (event.isComposing || !['ArrowLeft', 'ArrowRight'].includes(event.key)) return
  event.preventDefault(); void router.push(target(route.name === 'login' ? 'register' : 'login'))
}
watch(() => route.name, async () => { await nextTick(); document.querySelector<HTMLElement>('.ng-form-region h1')?.focus() })
onMounted(() => { media = window.matchMedia('(prefers-reduced-motion: reduce)'); syncMotion(); media.addEventListener('change', syncMotion); document.addEventListener('visibilitychange', syncMotion) })
onBeforeUnmount(() => { media?.removeEventListener('change', syncMotion); document.removeEventListener('visibilitychange', syncMotion) })
</script>
<template>
  <div class="rr-auth ng-shell" :class="{ 'ng-reduced': reduced, 'ng-paused': paused || hidden }" :data-motion="staticMotion ? 'paused' : 'enabled'">
    <a class="auth-skip" href="#auth-content">跳到表单</a>
    <AuthBrandScene />
    <section class="ng-panel" aria-label="企业账号入口">
      <div class="auth-nav-row">
        <button class="auth-motion" type="button" :aria-label="reduced ? '已遵循系统减少动态效果设置' : paused ? '开启动效' : '暂停动效'" :aria-pressed="staticMotion" :disabled="reduced" @click="paused = !paused"><component :is="staticMotion ? Play : Pause" :size="14" aria-hidden="true" />{{ reduced ? '静态' : paused ? '继续动效' : '动效' }}</button>
        <nav v-if="tabs" class="ng-panel-nav" :data-page="route.name" aria-label="认证入口" @keydown="arrow">
          <RouterLink class="ng-tab" :to="target('login')" :aria-current="route.name === 'login' ? 'page' : undefined"><KeyRound class="ng-icon" aria-hidden="true" />企业登录</RouterLink>
          <RouterLink class="ng-tab" :to="target('register')" :aria-current="route.name === 'register' ? 'page' : undefined"><UserPlus class="ng-icon" aria-hidden="true" />申请账号</RouterLink>
        </nav>
      </div>
      <main id="auth-content" class="ng-form-region"><slot /></main>
      <footer class="ng-panel-footer"><ShieldCheck class="ng-icon" aria-hidden="true" />华登集团 · 统一身份入口</footer>
    </section>
  </div>
</template>
