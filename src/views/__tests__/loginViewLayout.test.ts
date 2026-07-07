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
  '7 天内免登录',
  '企业身份登录',
  '企业微信',
  '扫码登录',
  '华兴试点账号',
  'carton_warehouse',
  'qa_inspector',
  'molding_clerk',
  'admin',
]) {
  assert.match(source, new RegExp(requiredCopy))
}

for (const requiredImplementation of [
  'useAuthStore',
  'authStore.login',
  'router.replace',
  'redirect',
  'showPassword',
  'brand-grid',
  'brand-glow',
  '/brand/huadeng_group_dynamic_logo.svg',
  'size-20 shrink-0',
]) {
  assert.match(source, new RegExp(requiredImplementation))
}

assert.match(source, /text-\[21px\] font-semibold leading-tight/)
assert.match(source, /text-\[13px\] text-slate-400/)
assert.doesNotMatch(source, /size-14 shrink-0/)
