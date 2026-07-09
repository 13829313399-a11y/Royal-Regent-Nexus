<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  ArrowLeft,
  AtSign,
  BriefcaseBusiness,
  Building2,
  CheckCircle2,
  ChevronDown,
  CircleAlert,
  Factory,
  LoaderCircle,
  Lock,
  Mail,
  Phone,
  Send,
  ShieldCheck,
  SquarePen,
  UserRound,
} from '@lucide/vue'
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
const passwordInputMessage = ref('')

const chinesePasswordPattern = /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]/
const chinesePasswordGlobalPattern = /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]/g
const passwordChineseMessage = '密码不能包含中文，请使用英文、数字或符号'

const factoryOptions = computed(() => factoryContexts.filter((factory) => factory.id !== 'group'))
const departmentOptions = computed(() => departments.filter((item) => item.id !== 'overview'))

function normalizePasswordInput(value: string) {
  const normalizedValue = value.replace(chinesePasswordGlobalPattern, '')
  passwordInputMessage.value = normalizedValue === value ? '' : passwordChineseMessage
  return normalizedValue
}

const passwordModel = computed({
  get: () => password.value,
  set: (value: string) => {
    password.value = normalizePasswordInput(value)
  },
})

const confirmPasswordModel = computed({
  get: () => confirmPassword.value,
  set: (value: string) => {
    confirmPassword.value = normalizePasswordInput(value)
  },
})

function validateForm() {
  if (!username.value.trim()) return '请输入账号或工号'
  if (!displayName.value.trim()) return '请输入姓名'
  if (password.value.length < 6) return '密码至少需要 6 位'
  if (chinesePasswordPattern.test(password.value) || chinesePasswordPattern.test(confirmPassword.value)) {
    return passwordChineseMessage
  }
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
  <main class="register-page">
    <div class="mx-auto flex min-h-screen w-full max-w-6xl items-center px-5 py-8">
      <section class="register-card">
        <aside class="register-aside">
          <div class="aside-grid" aria-hidden="true"></div>
          <div class="aside-glow aside-glow-top" aria-hidden="true"></div>
          <div class="aside-glow aside-glow-bottom" aria-hidden="true"></div>

          <button
            type="button"
            class="relative z-10 mb-10 inline-flex w-fit items-center gap-2 text-[12.5px] font-semibold text-slate-400 transition hover:text-white"
            @click="router.replace('/login')"
          >
            <ArrowLeft class="size-4" aria-hidden="true" />
            返回登录
          </button>

          <div class="relative z-10 flex items-center gap-3">
            <span class="flex size-14 items-center justify-center rounded-xl bg-white/95 p-2 text-teal-700 shadow-lg shadow-black/20">
              <img src="/brand/huadeng_group_dynamic_logo.svg" alt="华登集团" class="h-full w-full object-contain">
            </span>
            <div>
              <p class="text-[17px] font-bold">Royal Regent Nexus</p>
              <p class="mt-1 text-xs text-slate-400">账号申请 · 管理员审批后启用</p>
            </div>
          </div>

          <div class="relative z-10 mt-12 space-y-5">
            <div class="approval-step">
              <span class="approval-step-icon text-teal-300">
                <SquarePen class="size-5" aria-hidden="true" />
              </span>
              <div>
                <h2>提交员工基础信息</h2>
                <p>账号进入待审批状态，审批通过前不能登录系统。</p>
              </div>
            </div>
            <div class="approval-step">
              <span class="approval-step-icon text-blue-300">
                <ShieldCheck class="size-5" aria-hidden="true" />
              </span>
              <div>
                <h2>按厂区和部门审批</h2>
                <p>管理员会根据职位推荐角色，并在通过前确认最终权限。</p>
              </div>
            </div>
          </div>

          <div class="relative z-10 mt-auto flex items-center gap-2 pt-10 text-[11.5px] text-slate-500">
            <Lock class="size-3.5 text-teal-300" aria-hidden="true" />
            信息仅用于集团内部账号开通与授权
          </div>
        </aside>

        <section class="register-form-panel">
          <button
            type="button"
            class="mb-6 inline-flex items-center gap-2 text-sm font-semibold text-slate-500 transition hover:text-slate-900 lg:hidden"
            @click="router.replace('/login')"
          >
            <ArrowLeft class="size-4" aria-hidden="true" />
            返回登录
          </button>

          <div class="mb-7">
            <p class="text-[11px] font-bold uppercase tracking-[0.22em] text-teal-700">Account Request</p>
            <h1 class="mt-3 text-[25px] font-bold tracking-[-0.02em] text-slate-950">申请开通账号</h1>
            <p class="mt-2 text-[13px] text-slate-500">请填写真实岗位信息，提交后由系统管理员审批。</p>
          </div>

          <div v-if="errorMessage" class="status-banner status-banner-error">
            <CircleAlert class="size-4 shrink-0" aria-hidden="true" />
            <span>{{ errorMessage }}</span>
          </div>
          <div v-if="successMessage" class="status-banner status-banner-success">
            <CheckCircle2 class="size-4 shrink-0" aria-hidden="true" />
            <span>{{ successMessage }}</span>
          </div>

          <form class="form-grid" novalidate @submit.prevent="submitRegistration">
            <label class="field-block">
              <span>账号 / 工号 <b>*</b></span>
              <span class="control">
                <AtSign class="control-icon" aria-hidden="true" />
                <input v-model="username" autocomplete="username" placeholder="例如 zhangsan" type="text">
              </span>
            </label>
            <label class="field-block">
              <span>姓名 <b>*</b></span>
              <span class="control">
                <UserRound class="control-icon" aria-hidden="true" />
                <input v-model="displayName" autocomplete="name" placeholder="真实姓名" type="text">
              </span>
            </label>
            <label class="field-block">
              <span>登录密码 <b>*</b></span>
              <span class="control">
                <Lock class="control-icon" aria-hidden="true" />
                <input
                  v-model="passwordModel"
                  autocapitalize="off"
                  autocomplete="new-password"
                  placeholder="至少 6 位，不能包含中文"
                  spellcheck="false"
                  type="password"
                >
              </span>
              <small v-if="passwordInputMessage" class="password-hint-error">{{ passwordInputMessage }}</small>
            </label>
            <label class="field-block">
              <span>确认密码 <b>*</b></span>
              <span class="control">
                <ShieldCheck class="control-icon" aria-hidden="true" />
                <input
                  v-model="confirmPasswordModel"
                  autocapitalize="off"
                  autocomplete="new-password"
                  placeholder="再次输入密码"
                  spellcheck="false"
                  type="password"
                >
              </span>
            </label>
            <label class="field-block">
              <span>手机</span>
              <span class="control">
                <Phone class="control-icon" aria-hidden="true" />
                <input v-model="phone" autocomplete="tel" placeholder="手机或邮箱至少填一项" type="tel">
              </span>
            </label>
            <label class="field-block">
              <span>邮箱</span>
              <span class="control">
                <Mail class="control-icon" aria-hidden="true" />
                <input v-model="email" autocomplete="email" placeholder="name@example.com" type="email">
              </span>
            </label>
            <label class="field-block">
              <span>厂区 <b>*</b></span>
              <span class="control">
                <Factory class="control-icon" aria-hidden="true" />
                <select v-model="factoryId">
                <option v-for="factory in factoryOptions" :key="factory.id" :value="factory.id">
                  {{ factory.shortName }}
                </option>
              </select>
                <ChevronDown class="select-icon" aria-hidden="true" />
              </span>
            </label>
            <label class="field-block">
              <span>部门 <b>*</b></span>
              <span class="control">
                <Building2 class="control-icon" aria-hidden="true" />
                <select v-model="department">
                <option v-for="item in departmentOptions" :key="item.id" :value="item.id">
                  {{ item.name }}
                </option>
              </select>
                <ChevronDown class="select-icon" aria-hidden="true" />
              </span>
            </label>
            <label class="field-block field-full">
              <span>职位 <b>*</b></span>
              <span class="control">
                <BriefcaseBusiness class="control-icon" aria-hidden="true" />
                <input v-model="position" placeholder="例如 工程师、QA 检验员、啤机文员" type="text">
              </span>
              <small>管理员将根据职位推荐系统角色，通过审批前可调整。</small>
            </label>

            <div class="submit-row">
              <button
                class="submit-button"
                type="submit"
                :disabled="isSubmitting || Boolean(successMessage)"
              >
                <LoaderCircle v-if="isSubmitting" class="size-4 animate-spin" aria-hidden="true" />
                <Send v-else class="size-4" aria-hidden="true" />
                {{ isSubmitting ? '提交中...' : '提交申请' }}
              </button>
              <span class="login-link">已有账号？<button type="button" @click="router.replace('/login')">返回登录</button></span>
            </div>
          </form>
        </section>
      </section>
    </div>
  </main>
</template>

<style scoped>
.register-page {
  min-height: 100vh;
  background:
    radial-gradient(circle at top left, rgb(14 165 233 / 10%), transparent 34%),
    linear-gradient(180deg, #f8fafc 0%, #eef4f8 100%);
  color: #020617;
}

.register-card {
  display: grid;
  width: 100%;
  overflow: hidden;
  border: 1px solid rgb(226 232 240);
  border-radius: 1rem;
  background: white;
  box-shadow: 0 24px 60px rgb(15 23 42 / 18%);
}

.register-aside {
  position: relative;
  display: none;
  min-height: 640px;
  flex-direction: column;
  overflow: hidden;
  background: #020617;
  padding: 38px 36px;
  color: white;
}

.aside-grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgb(255 255 255 / 3%) 1px, transparent 1px),
    linear-gradient(90deg, rgb(255 255 255 / 3%) 1px, transparent 1px);
  background-size: 42px 42px;
}

.aside-glow {
  position: absolute;
  border-radius: 999px;
  filter: blur(80px);
  pointer-events: none;
}

.aside-glow-top {
  left: -110px;
  top: -120px;
  width: 340px;
  height: 340px;
  background: rgb(13 148 136 / 26%);
}

.aside-glow-bottom {
  right: -100px;
  bottom: -120px;
  width: 300px;
  height: 300px;
  background: rgb(59 130 246 / 16%);
}

.approval-step {
  display: flex;
  gap: 13px;
}

.approval-step-icon {
  display: grid;
  width: 40px;
  height: 40px;
  flex: none;
  place-items: center;
  border: 1px solid rgb(20 184 166 / 22%);
  border-radius: 11px;
  background: rgb(20 184 166 / 14%);
}

.approval-step:nth-child(2) .approval-step-icon {
  border-color: rgb(59 130 246 / 22%);
  background: rgb(59 130 246 / 14%);
}

.approval-step h2 {
  margin: 2px 0 0;
  color: #e2e8f0;
  font-size: 13.5px;
  font-weight: 700;
}

.approval-step p {
  margin: 5px 0 0;
  color: #94a3b8;
  font-size: 12px;
  line-height: 1.6;
}

.register-form-panel {
  padding: 36px 38px 32px;
}

.status-banner {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-bottom: 18px;
  border-radius: 0.625rem;
  padding: 11px 14px;
  font-size: 13px;
  font-weight: 600;
}

.status-banner-error {
  border: 1px solid #fecaca;
  background: #fef2f2;
  color: #b91c1c;
}

.status-banner-success {
  border: 1px solid #a7f3d0;
  background: #ecfdf5;
  color: #047857;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 15px 16px;
}

.field-block {
  display: block;
  min-width: 0;
}

.field-block > span:first-child {
  display: block;
  margin-bottom: 7px;
  color: #334155;
  font-size: 12.5px;
  font-weight: 600;
}

.field-block b {
  color: #b91c1c;
}

.field-full {
  grid-column: 1 / -1;
}

.field-block small {
  display: block;
  margin-top: 7px;
  color: #64748b;
  font-size: 11.5px;
}

.field-block small.password-hint-error {
  color: #dc2626;
  font-weight: 600;
}

.control {
  position: relative;
  display: flex;
  height: 44px;
  align-items: center;
  border: 1px solid rgb(226 232 240);
  border-radius: 8px;
  background: rgb(248 250 252);
  padding: 0 12px;
  transition: border-color 0.16s ease, background-color 0.16s ease, box-shadow 0.16s ease;
}

.control:focus-within {
  border-color: rgb(15 118 110);
  background: white;
  box-shadow: 0 0 0 3px rgb(15 118 110 / 14%);
}

.control-icon {
  width: 17px;
  height: 17px;
  flex: none;
  color: #94a3b8;
  transition: color 0.16s ease;
}

.control:focus-within .control-icon {
  color: #0f766e;
}

.control input,
.control select {
  height: 100%;
  min-width: 0;
  flex: 1;
  border: 0;
  background: transparent;
  color: #020617;
  font: inherit;
  font-size: 14px;
  outline: none;
  padding: 0 10px;
}

.control input::placeholder {
  color: #94a3b8;
}

.control select {
  cursor: pointer;
  appearance: none;
}

.select-icon {
  width: 16px;
  height: 16px;
  flex: none;
  color: #94a3b8;
  pointer-events: none;
}

.submit-row {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 8px;
}

.submit-button {
  display: inline-flex;
  height: 46px;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border: 0;
  border-radius: 8px;
  background: #0f766e;
  color: white;
  font-size: 14.5px;
  font-weight: 700;
  padding: 0 26px;
  transition: background 0.16s ease, transform 0.1s ease;
}

.submit-button:hover {
  background: #115e59;
}

.submit-button:active {
  transform: scale(0.99);
}

.submit-button:disabled {
  cursor: wait;
  background: #cbd5e1;
  transform: none;
}

.login-link {
  color: #64748b;
  font-size: 12.5px;
}

.login-link button {
  color: #0f766e;
  font-weight: 700;
}

@media (min-width: 992px) {
  .register-card {
    grid-template-columns: 0.82fr 1fr;
  }

  .register-aside {
    display: flex;
  }
}

@media (max-width: 640px) {
  .register-form-panel {
    padding: 28px 22px;
  }
}

@media (max-width: 560px) {
  .form-grid {
    grid-template-columns: 1fr;
  }

  .submit-row {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
