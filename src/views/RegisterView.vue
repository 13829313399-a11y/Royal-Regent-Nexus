<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowLeft, Building2, CircleAlert, LoaderCircle, Lock, Send, UserRound } from '@lucide/vue'
import { useRouter } from 'vue-router'
import { authApi } from '@/api/auth'
import { departments, factoryContexts } from '@/data/enterpriseMock'
import { getApiErrorMessage } from '@/lib/http'

const router = useRouter()

const username = ref('')
const displayName = ref('')
const password = ref('')
const confirmPassword = ref('')
const phone = ref('')
const email = ref('')
const factoryId = ref('huaxing')
const department = ref('engineering')
const position = ref('')
const isSubmitting = ref(false)
const errorMessage = ref('')
const successMessage = ref('')

const factoryOptions = computed(() => factoryContexts.filter((factory) => factory.id !== 'group'))
const departmentOptions = computed(() => departments.filter((item) => item.id !== 'overview'))

function validateForm() {
  if (!username.value.trim()) return '请输入账号或工号'
  if (!displayName.value.trim()) return '请输入姓名'
  if (password.value.length < 6) return '密码至少需要 6 位'
  if (password.value !== confirmPassword.value) return '两次输入的密码不一致'
  if (!phone.value.trim() && !email.value.trim()) return '手机或邮箱至少填写一项'
  if (!factoryId.value) return '请选择厂区'
  if (!department.value) return '请选择部门'
  if (!position.value.trim()) return '请输入职位'
  return ''
}

async function submitRegistration() {
  errorMessage.value = ''
  successMessage.value = ''

  const validationMessage = validateForm()
  if (validationMessage) {
    errorMessage.value = validationMessage
    return
  }

  isSubmitting.value = true
  try {
    const response = await authApi.register({
      username: username.value.trim(),
      display_name: displayName.value.trim(),
      password: password.value,
      confirm_password: confirmPassword.value,
      phone: phone.value.trim(),
      email: email.value.trim(),
      factory_id: factoryId.value,
      department: department.value,
      position: position.value.trim(),
    })
    successMessage.value = response.message || '账号申请已提交，请等待管理员审批'
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    isSubmitting.value = false
  }
}
</script>

<template>
  <main class="min-h-screen bg-slate-100 text-slate-950">
    <div class="mx-auto flex min-h-screen w-full max-w-6xl items-center px-5 py-8">
      <section class="grid w-full overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm lg:grid-cols-[0.82fr_1fr]">
        <aside class="hidden bg-slate-950 px-10 py-10 text-white lg:block">
          <button
            type="button"
            class="mb-12 inline-flex items-center gap-2 text-sm font-semibold text-slate-300 transition hover:text-white"
            @click="router.replace('/login')"
          >
            <ArrowLeft class="size-4" aria-hidden="true" />
            返回登录
          </button>

          <div class="flex items-center gap-4">
            <span class="flex size-16 items-center justify-center rounded-lg bg-white p-2">
              <img src="/brand/huadeng_group_dynamic_logo.svg" alt="华登集团" class="h-full w-full object-contain">
            </span>
            <div>
              <p class="text-lg font-bold">Royal Regent Nexus</p>
              <p class="mt-1 text-xs text-slate-400">账号申请 · 管理员审批后启用</p>
            </div>
          </div>

          <div class="mt-16 space-y-6">
            <div class="flex gap-3">
              <span class="flex size-9 shrink-0 items-center justify-center rounded-lg bg-teal-500/15 text-teal-300">
                <UserRound class="size-4" aria-hidden="true" />
              </span>
              <div>
                <h2 class="text-sm font-bold">提交员工基础信息</h2>
                <p class="mt-1 text-sm leading-6 text-slate-400">账号进入待审批状态，审批通过前不能登录系统。</p>
              </div>
            </div>
            <div class="flex gap-3">
              <span class="flex size-9 shrink-0 items-center justify-center rounded-lg bg-blue-500/15 text-blue-300">
                <Building2 class="size-4" aria-hidden="true" />
              </span>
              <div>
                <h2 class="text-sm font-bold">按厂区和部门审批</h2>
                <p class="mt-1 text-sm leading-6 text-slate-400">管理员会根据职位推荐角色，并在通过前确认最终权限。</p>
              </div>
            </div>
          </div>
        </aside>

        <section class="px-6 py-8 sm:px-10 lg:px-12">
          <button
            type="button"
            class="mb-6 inline-flex items-center gap-2 text-sm font-semibold text-slate-500 transition hover:text-slate-900 lg:hidden"
            @click="router.replace('/login')"
          >
            <ArrowLeft class="size-4" aria-hidden="true" />
            返回登录
          </button>

          <div class="mb-7">
            <p class="text-xs font-bold uppercase tracking-wide text-teal-700">Account Request</p>
            <h1 class="mt-2 text-2xl font-black">申请开通账号</h1>
            <p class="mt-2 text-sm text-slate-500">请填写真实岗位信息，提交后由系统管理员审批。</p>
          </div>

          <form class="grid gap-4 sm:grid-cols-2" novalidate @submit.prevent="submitRegistration">
            <label class="block">
              <span class="mb-1.5 block text-xs font-semibold text-slate-600">账号 / 工号</span>
              <input v-model="username" class="field" autocomplete="username" placeholder="例如 zhangsan" type="text">
            </label>
            <label class="block">
              <span class="mb-1.5 block text-xs font-semibold text-slate-600">姓名</span>
              <input v-model="displayName" class="field" autocomplete="name" placeholder="真实姓名" type="text">
            </label>
            <label class="block">
              <span class="mb-1.5 block text-xs font-semibold text-slate-600">登录密码</span>
              <input v-model="password" class="field" autocomplete="new-password" placeholder="至少 6 位" type="password">
            </label>
            <label class="block">
              <span class="mb-1.5 block text-xs font-semibold text-slate-600">确认密码</span>
              <input v-model="confirmPassword" class="field" autocomplete="new-password" placeholder="再次输入密码" type="password">
            </label>
            <label class="block">
              <span class="mb-1.5 block text-xs font-semibold text-slate-600">手机</span>
              <input v-model="phone" class="field" autocomplete="tel" placeholder="手机或邮箱至少填一项" type="tel">
            </label>
            <label class="block">
              <span class="mb-1.5 block text-xs font-semibold text-slate-600">邮箱</span>
              <input v-model="email" class="field" autocomplete="email" placeholder="name@example.com" type="email">
            </label>
            <label class="block">
              <span class="mb-1.5 block text-xs font-semibold text-slate-600">厂区</span>
              <select v-model="factoryId" class="field">
                <option v-for="factory in factoryOptions" :key="factory.id" :value="factory.id">
                  {{ factory.shortName }}
                </option>
              </select>
            </label>
            <label class="block">
              <span class="mb-1.5 block text-xs font-semibold text-slate-600">部门</span>
              <select v-model="department" class="field">
                <option v-for="item in departmentOptions" :key="item.id" :value="item.id">
                  {{ item.name }}
                </option>
              </select>
            </label>
            <label class="block sm:col-span-2">
              <span class="mb-1.5 block text-xs font-semibold text-slate-600">职位</span>
              <input v-model="position" class="field" placeholder="例如 工程师、QA 检验员、啤机文员" type="text">
            </label>

            <div
              v-if="errorMessage"
              class="flex items-center gap-2 rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-sm font-semibold text-red-700 sm:col-span-2"
            >
              <CircleAlert class="size-4 shrink-0" aria-hidden="true" />
              <span>{{ errorMessage }}</span>
            </div>
            <div
              v-if="successMessage"
              class="rounded-lg border border-emerald-100 bg-emerald-50 px-3 py-3 text-sm font-semibold text-emerald-700 sm:col-span-2"
            >
              {{ successMessage }}
            </div>

            <div class="flex flex-col gap-3 pt-2 sm:col-span-2 sm:flex-row">
              <button
                class="inline-flex h-11 flex-1 items-center justify-center gap-2 rounded-lg bg-teal-700 px-4 text-sm font-bold text-white transition hover:bg-teal-800 disabled:cursor-wait disabled:bg-slate-300"
                type="submit"
                :disabled="isSubmitting || Boolean(successMessage)"
              >
                <LoaderCircle v-if="isSubmitting" class="size-4 animate-spin" aria-hidden="true" />
                <Send v-else class="size-4" aria-hidden="true" />
                {{ isSubmitting ? '提交中...' : '提交申请' }}
              </button>
              <button
                class="inline-flex h-11 items-center justify-center gap-2 rounded-lg border border-slate-200 px-4 text-sm font-bold text-slate-600 transition hover:bg-slate-50"
                type="button"
                @click="router.replace('/login')"
              >
                <Lock class="size-4" aria-hidden="true" />
                返回登录
              </button>
            </div>
          </form>
        </section>
      </section>
    </div>
  </main>
</template>

<style scoped>
.field {
  height: 44px;
  width: 100%;
  border-radius: 8px;
  border: 1px solid rgb(226 232 240);
  background: rgb(248 250 252);
  padding: 0 12px;
  font-size: 14px;
  outline: none;
  transition: border-color 0.15s ease, background-color 0.15s ease, box-shadow 0.15s ease;
}

.field:focus {
  border-color: rgb(15 118 110);
  background: white;
  box-shadow: 0 0 0 3px rgb(15 118 110 / 12%);
}
</style>
