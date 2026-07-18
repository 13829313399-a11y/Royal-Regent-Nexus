import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const source = readFileSync(join(process.cwd(), 'src/views/LoginView.vue'), 'utf8')

for (const requiredCopy of [
  'Royal Regent Nexus',
  '华登集团 · 集团级业务中台',
  '多厂区 · 多部门统一门户',
  '一个平台，贯通集团',
  '欢迎回来',
  '企业账号',
  '登录密码',
  '继续使用上次账号',
  '记住账号',
  '切换账号',
  '主动退出后需要重新验证密码',
  '密码不会保存在本系统',
  '密码不能包含中文，请使用英文、数字或符号',
  '密码重置协助',
  '提交后系统会通知管理员核验处理',
  '联系电话或邮箱',
  '补充说明',
  '提交重置申请',
  '临时密码',
  '没有企业账号？',
  '提交账号申请',
  '审批通过后即可登录系统',
]) {
  assert.match(source, new RegExp(requiredCopy))
}

for (const requiredImplementation of [
  'useAuthStore',
  'authStore.login',
  'router.replace',
  'redirect',
  'LAST_LOGIN_ACCOUNT_STORAGE_KEY',
  'readRecentAccount',
  'saveRecentAccount',
  'localStorage',
  'passwordModel',
  'chinesePasswordPattern',
  'showPasswordHelp',
  'openPasswordHelp',
  'submitPasswordResetRequest',
  'authApi.requestPasswordReset',
  'passwordResetForm',
  'max-h-\\[calc\\(100vh-32px\\)\\]',
  'overflow-y-auto',
  'password-help-body',
  'max-height: 720px',
  'showPassword',
  'AuthAmbientGrid',
  'variant="login"',
  'brand-grid',
  'brand-glow',
  'w-\\[56%\\]',
  'lg:w-\\[44%\\]',
  'isolation: isolate',
  '@media \\(hover: hover\\) and \\(pointer: fine\\)',
  'translateY\\(-1px\\)',
  '/brand/huadeng_group_dynamic_logo.svg',
  'size-20 shrink-0',
]) {
  assert.match(source, new RegExp(requiredImplementation))
}

assert.match(source, /text-\[21px\] font-semibold leading-tight/)
assert.match(source, /text-\[13px\] text-slate-400/)
assert.match(
  source,
  /<aside class="brand-panel relative hidden w-\[56%\] flex-col overflow-hidden bg-slate-950 text-white lg:flex">/,
)
assert.match(source, /<section class="flex w-full flex-col lg:w-\[44%\]">/)
assert.match(
  source,
  /@media \(hover: hover\) and \(pointer: fine\) \{[\s\S]*?\.login-feature-card:hover \{[\s\S]*?translateY\(-1px\)/,
)
assert.match(
  source,
  /@media \(prefers-reduced-motion: reduce\) \{[\s\S]*?\.login-feature-card,[\s\S]*?\.login-feature-icon \{[\s\S]*?transform: none;[\s\S]*?transition: none;/,
)
assert.doesNotMatch(source, /login-feature-card[^"\n]*hover:/)
assert.doesNotMatch(source, /size-14 shrink-0/)
assert.doesNotMatch(source, /华兴试点账号/)
assert.doesNotMatch(source, /默认密码 123456/)
assert.doesNotMatch(source, /trialAccounts/)
assert.doesNotMatch(source, /7 天内免登录/)
