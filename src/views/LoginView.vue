<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  ArrowRight,
  Building2,
  CircleAlert,
  Eye,
  EyeOff,
  Gauge,
  GitBranch,
  LayoutGrid,
  LoaderCircle,
  Lock,
  MessageCircle,
  ScanFace,
  ShieldCheck,
  UserRound,
} from '@lucide/vue'
import { useRoute, useRouter } from 'vue-router'
import { getApiErrorMessage } from '@/lib/http'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const username = ref('engineer')
const password = ref('123456')
const rememberSession = ref(true)
const showPassword = ref(false)
const isSubmitting = ref(false)
const errorMessage = ref('')

const redirect = computed(() => {
  const value = route.query.redirect
  return typeof value === 'string' && value.startsWith('/') ? value : '/'
})

const brandFeatures = [
  {
    title: '多厂区协同',
    detail: '华康A/B · 华登 · 华兴统一调度',
    icon: Building2,
  },
  {
    title: '部门模块中心',
    detail: '工程 / PMC / 生产 / QA / 业务',
    icon: LayoutGrid,
  },
  {
    title: '全流程审批',
    detail: '单据流转留痕、权责清晰',
    icon: GitBranch,
  },
  {
    title: '运营驾驶舱',
    detail: '在线服务 23/24 · 实时监控',
    icon: Gauge,
  },
]

const trialAccounts = [
  { role: '工程师', username: 'engineer' },
  { role: '工程主管', username: 'supervisor' },
  { role: '经理', username: 'manager' },
  { role: '啤机部文员', username: 'molding_clerk' },
  { role: '管理员', username: 'admin' },
]

async function submitLogin() {
  errorMessage.value = ''

  if (!username.value.trim() || !password.value) {
    errorMessage.value = !username.value.trim() && !password.value
      ? '请输入账号和密码'
      : !username.value.trim() ? '请输入企业账号' : '请输入登录密码'
    return
  }

  isSubmitting.value = true

  try {
    await authStore.login({
      username: username.value.trim(),
      password: password.value,
    })
    await router.replace(redirect.value)
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    isSubmitting.value = false
  }
}
</script>

<template>
  <main class="flex min-h-screen bg-white font-sans text-slate-950">
    <aside class="brand-panel relative hidden w-[56%] flex-col overflow-hidden bg-slate-950 text-white lg:flex">
      <div class="brand-grid absolute inset-0" aria-hidden="true"></div>
      <div class="brand-glow absolute inset-0" aria-hidden="true"></div>

      <div class="relative z-10 flex items-center gap-3 px-14 pt-12">
        <span class="flex size-14 shrink-0 items-center justify-center rounded-lg bg-white/95 p-1.5 shadow-lg shadow-black/20">
          <img
            src="/brand/huadeng_group_dynamic_logo.svg"
            alt="华登集团"
            class="h-full w-full object-contain"
          >
        </span>
        <div>
          <div class="text-[17px] font-semibold leading-tight">Royal Regent Nexus</div>
          <div class="text-[12px] text-slate-400">华登集团 · 集团级业务中台</div>
        </div>
      </div>

      <section class="relative z-10 flex flex-1 flex-col justify-center px-14">
        <div class="mb-3 inline-flex w-fit items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1 text-[12px] font-medium text-teal-300">
          <span class="size-1.5 rounded-full bg-teal-400"></span>
          多厂区 · 多部门统一门户
        </div>
        <h1 class="max-w-lg text-[34px] font-bold leading-[1.25]">
          一个平台，贯通集团<br>制造全业务链
        </h1>
        <p class="mt-4 max-w-md text-[14px] leading-relaxed text-slate-300">
          从工程开单、PMC 排产到生产执行与质量放行，跨华康、华登、华兴多厂区协同，让订单、模具、审批与看板在同一中台实时流转。
        </p>

        <div class="mt-10 grid max-w-lg grid-cols-2 gap-x-8 gap-y-5">
          <div v-for="feature in brandFeatures" :key="feature.title" class="flex items-start gap-3">
            <span class="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-white/10 text-teal-300">
              <component :is="feature.icon" class="size-4" aria-hidden="true" />
            </span>
            <div>
              <div class="text-[13.5px] font-semibold">{{ feature.title }}</div>
              <div class="text-[12px] leading-5 text-slate-400">{{ feature.detail }}</div>
            </div>
          </div>
        </div>
      </section>

      <div class="relative z-10 flex items-center justify-between px-14 pb-9 text-[11px] text-slate-500">
        <span>© 2026 华登集团 · 数字化中心</span>
        <span class="flex items-center gap-1.5">
          <ShieldCheck class="size-3.5" aria-hidden="true" />
          内部系统，仅限授权访问
        </span>
      </div>
    </aside>

    <section class="flex w-full flex-col lg:w-[44%]">
      <div class="flex items-center gap-3 border-b border-slate-800 bg-slate-950 px-6 py-3 text-white lg:hidden">
        <span class="flex size-10 shrink-0 items-center justify-center rounded-lg bg-white/95 p-1">
          <img src="/brand/huadeng_group_dynamic_logo.svg" alt="华登集团" class="h-full w-full object-contain">
        </span>
        <div>
          <div class="text-[15px] font-semibold leading-tight">Royal Regent Nexus</div>
          <div class="text-[10px] text-slate-400">华登集团 · 集团级业务中台</div>
        </div>
      </div>

      <div class="flex flex-1 items-center justify-center bg-white px-6 py-10 sm:px-14">
        <div class="fade-in w-full max-w-[400px]">
          <div class="mb-8">
            <h2 class="text-[24px] font-semibold text-slate-950">欢迎回来</h2>
            <p class="mt-1.5 text-[13.5px] text-slate-500">登录华登集团业务中台，请使用企业统一账号</p>
          </div>

          <form class="space-y-4" novalidate @submit.prevent="submitLogin">
            <label class="block">
              <span class="mb-1.5 block text-[12.5px] font-medium text-slate-700">企业账号</span>
              <span class="field flex h-11 items-center rounded-lg border border-slate-200 bg-slate-50 px-3 transition-colors focus-within:border-teal-700 focus-within:bg-white focus-within:ring-2 focus-within:ring-teal-700/15">
                <UserRound class="field-icon size-4 text-slate-400 transition-colors" aria-hidden="true" />
                <input
                  v-model="username"
                  class="ml-2.5 h-full w-full bg-transparent text-[14px] outline-none placeholder:text-slate-400"
                  autocomplete="username"
                  placeholder="工号 / 企业邮箱"
                  type="text"
                >
              </span>
            </label>

            <label class="block">
              <span class="mb-1.5 block text-[12.5px] font-medium text-slate-700">登录密码</span>
              <span class="field flex h-11 items-center rounded-lg border border-slate-200 bg-slate-50 px-3 transition-colors focus-within:border-teal-700 focus-within:bg-white focus-within:ring-2 focus-within:ring-teal-700/15">
                <Lock class="field-icon size-4 text-slate-400 transition-colors" aria-hidden="true" />
                <input
                  v-model="password"
                  class="ml-2.5 h-full w-full bg-transparent text-[14px] outline-none placeholder:text-slate-400"
                  autocomplete="current-password"
                  placeholder="请输入密码"
                  :type="showPassword ? 'text' : 'password'"
                >
                <button
                  class="ml-2 flex size-7 items-center justify-center rounded-md text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
                  type="button"
                  :aria-label="showPassword ? '隐藏密码' : '显示密码'"
                  @click="showPassword = !showPassword"
                >
                  <EyeOff v-if="showPassword" class="size-4" aria-hidden="true" />
                  <Eye v-else class="size-4" aria-hidden="true" />
                </button>
              </span>
            </label>

            <div class="flex items-center justify-between pt-0.5">
              <label class="flex cursor-pointer select-none items-center gap-2 text-[12.5px] text-slate-600">
                <input
                  v-model="rememberSession"
                  class="size-4 rounded border-slate-300 text-teal-700 focus:ring-teal-600/40"
                  type="checkbox"
                >
                7 天内免登录
              </label>
              <button class="text-[12.5px] font-medium text-teal-700 transition-colors hover:text-teal-800" type="button">
                忘记密码？
              </button>
            </div>

            <div
              v-if="errorMessage"
              class="flex items-center gap-1.5 rounded-lg bg-red-50 px-3 py-2 text-[12.5px] font-medium text-red-600"
            >
              <CircleAlert class="size-4 shrink-0" aria-hidden="true" />
              <span>{{ errorMessage }}</span>
            </div>

            <button
              class="flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-teal-700 text-[14.5px] font-semibold text-white transition hover:bg-teal-800 active:scale-[0.99] disabled:cursor-not-allowed disabled:bg-slate-300 disabled:active:scale-100"
              type="submit"
              :disabled="isSubmitting"
            >
              <LoaderCircle v-if="isSubmitting" class="size-4 animate-spin" aria-hidden="true" />
              <span>{{ isSubmitting ? '登录中...' : '登录' }}</span>
              <ArrowRight v-if="!isSubmitting" class="size-4" aria-hidden="true" />
            </button>
          </form>

          <section class="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-3">
            <div class="mb-2 flex items-center justify-between gap-2">
              <span class="text-[12px] font-semibold text-slate-700">华兴试点账号</span>
              <span class="text-[11px] font-medium text-slate-400">默认密码 123456</span>
            </div>
            <div class="grid grid-cols-2 gap-2">
              <button
                v-for="account in trialAccounts"
                :key="account.username"
                type="button"
                class="min-w-0 rounded-md border border-slate-200 bg-white px-2 py-1.5 text-left transition hover:border-teal-200 hover:bg-teal-50"
                @click="username = account.username"
              >
                <span class="block truncate text-[11px] font-semibold text-slate-800">{{ account.role }}</span>
                <span class="block truncate font-mono text-[11px] text-slate-500">{{ account.username }}</span>
              </button>
            </div>
          </section>

          <div class="my-6 flex items-center gap-3 text-[11px] text-slate-400">
            <span class="h-px flex-1 bg-slate-200"></span>
            企业身份登录
            <span class="h-px flex-1 bg-slate-200"></span>
          </div>

          <div class="grid grid-cols-2 gap-3">
            <button
              class="flex h-10 items-center justify-center gap-2 rounded-lg border border-slate-200 text-[12.5px] font-medium text-slate-400"
              type="button"
              disabled
            >
              <MessageCircle class="size-4 text-emerald-500" aria-hidden="true" />
              企业微信
            </button>
            <button
              class="flex h-10 items-center justify-center gap-2 rounded-lg border border-slate-200 text-[12.5px] font-medium text-slate-400"
              type="button"
              disabled
            >
              <ScanFace class="size-4 text-blue-500" aria-hidden="true" />
              扫码登录
            </button>
          </div>

          <p class="mt-8 text-center text-[12px] text-slate-400">
            账号由集团数字化中心统一开通 ·
            <button class="font-medium text-slate-600 transition-colors hover:text-slate-900" type="button">联系管理员</button>
          </p>
        </div>
      </div>
    </section>
  </main>
</template>

<style scoped>
.brand-grid {
  background-image:
    linear-gradient(rgb(255 255 255 / 3.5%) 1px, transparent 1px),
    linear-gradient(90deg, rgb(255 255 255 / 3.5%) 1px, transparent 1px);
  background-size: 46px 46px;
}

.brand-glow {
  background:
    radial-gradient(680px circle at 18% 12%, rgb(13 148 136 / 28%), transparent 55%),
    radial-gradient(560px circle at 88% 92%, rgb(5 207 99 / 16%), transparent 52%);
}

.fade-in {
  animation: fade 0.45s ease both;
}

.field:focus-within .field-icon {
  color: #0f766e;
}

@keyframes fade {
  from {
    opacity: 0;
    transform: translateY(8px);
  }

  to {
    opacity: 1;
    transform: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .fade-in {
    animation: none;
  }
}
</style>
