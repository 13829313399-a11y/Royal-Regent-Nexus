import { defineComponent } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises, enableAutoUnmount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import LoginView from '../LoginView.vue'
import RegisterView from '../RegisterView.vue'
import { usePasswordResetClaim } from '@/composables/usePasswordResetClaim'
import { useAuthStore } from '@/stores/auth'
import { useAuthDeadline } from '@/composables/useAuthDeadline'
import { readRecentAccount, saveRecentAccount, removeRecentAccount } from '@/lib/authAccountPreference'
const mocks = vi.hoisted(() => ({ login: vi.fn(), getPasswordResetClaim: vi.fn(), requestPasswordReset: vi.fn(), register: vi.fn(), organizationCatalog: vi.fn(), replace: vi.fn(), push: vi.fn() }))
vi.mock('@/api/auth', () => ({ authApi: mocks }))
vi.mock('vue-router', () => ({ useRoute: () => ({ query: { redirect: '/orders?factory=huaxing#item' } }), useRouter: () => ({ replace: mocks.replace, push: mocks.push, resolve: (path: string) => ({ fullPath: path, meta: { requiresAuth: true } }) }), RouterLink: { template: '<a><slot /></a>' } }))
enableAutoUnmount(afterEach)
const user = { id: 'qa-user', username: '001', display_name: '测试员工', force_password_change: false, roles: [], permissions: [], grants: [], factory_scopes: [], department_scopes: [] }
const none = { status: 'none', request_id: '', can_complete: false, expires_at: '', message: '无申请' }
const catalog = { organizations: [{ id: 'huaxing', name: '华兴', factory_id: 'huaxing', departments: [{ code: 'engineering', name: '工程部' }] }, { id: 'group-management', name: '总务', factory_id: '', departments: [{ code: 'system', name: '系统管理' }] }] }
function deferred<T>() { let resolve!: (value: T) => void, reject!: (error?: unknown) => void; const promise = new Promise<T>((yes,no) => { resolve = yes; reject = no }); return { promise, resolve, reject } }
function view(component: typeof LoginView | typeof RegisterView) { return mount(component, { attachTo: document.body, global: { plugins: [createPinia()] } }) }
beforeEach(() => {
  vi.restoreAllMocks(); vi.clearAllMocks(); setActivePinia(createPinia()); localStorage.clear()
  mocks.login.mockResolvedValue(user); mocks.getPasswordResetClaim.mockResolvedValue(none); mocks.organizationCatalog.mockResolvedValue(catalog)
  mocks.register.mockResolvedValue({ status: 'pending', message: '已收到', request_id: 'registration-real', submitted_at: '2026-10-10T12:00:00+08:00' })
  mocks.replace.mockResolvedValue(undefined)
})
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllEnvs() })

describe('login boundary behavior', () => {
  it.each(['','synthetic-acceptance'])('labels the login environment only for an explicit acceptance build: %s',release=>{
    vi.stubEnv('VITE_CUTTING_ACCEPTANCE_RELEASE',release)
    const wrapper=view(LoginView)
    expect(wrapper.find('[aria-label="独立验收环境标识"]').exists()).toBe(!!release)
    expect(wrapper.find('[aria-label="合成验收样本"]').exists()).toBe(false)
  })
  it.each(['getter','set','remove'])('keeps successful authentication and redirect when storage %s throws', async mode => {
    if (mode === 'getter') vi.spyOn(window, 'localStorage', 'get').mockImplementation(() => { throw new DOMException('denied', 'SecurityError') })
    else vi.spyOn(Storage.prototype, mode === 'set' ? 'setItem' : 'removeItem').mockImplementation(() => { throw new DOMException('denied') })
    const wrapper = view(LoginView)
    await wrapper.get('[name="username"]').setValue('001')
    await wrapper.get('[name="password"]').setValue(' abc123 ')
    if (mode === 'set') await wrapper.get('[type="checkbox"]').setValue(true)
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(mocks.login).toHaveBeenCalledWith({ username: '001', password: ' abc123 ' })
    expect(mocks.replace).toHaveBeenCalledWith('/orders?factory=huaxing#item')
    expect(wrapper.text()).not.toContain('登录失败')
  })
  it('survives malformed saved JSON and a failing remove operation', () => {
    localStorage.setItem('rr:last-login-account', '{broken')
    vi.spyOn(Storage.prototype,'removeItem').mockImplementation(() => { throw Error('denied') })
    expect(readRecentAccount()).toBeNull()
    expect(() => removeRecentAccount()).not.toThrow()
    saveRecentAccount(user)
    expect(JSON.parse(localStorage.getItem('rr:last-login-account')!)).not.toHaveProperty('password')
  })
  it('guards repeated submit and retries navigation without resending credentials', async () => {
    const pending = deferred<typeof user>(); mocks.login.mockReturnValue(pending.promise)
    mocks.replace.mockRejectedValueOnce(Error('navigation unavailable'))
    const wrapper = view(LoginView)
    await wrapper.get('[name="username"]').setValue('001'); await wrapper.get('[name="password"]').setValue('123456')
    await wrapper.get('form').trigger('submit'); await wrapper.get('form').trigger('submit')
    expect(mocks.login).toHaveBeenCalledTimes(1)
    pending.resolve(user); await flushPromises()
    expect(wrapper.text()).toContain('已登录，暂时无法打开工作页面')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(mocks.login).toHaveBeenCalledTimes(1); expect(mocks.replace).toHaveBeenCalledTimes(2)
  })
  it('retains Chinese input and respects IME Enter and the historical long password contract', async () => {
    const wrapper = view(LoginView)
    await wrapper.get('[name="username"]').setValue('001')
    await wrapper.get('[name="password"]').setValue(' 中文123456 ')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect((wrapper.get('[name="password"]').element as HTMLInputElement).value).toBe(' 中文123456 ')
    expect(mocks.login).not.toHaveBeenCalled()
    const input = wrapper.get('[name="username"]'); (input.element as HTMLInputElement).focus()
    await input.trigger('keydown', { key:'Enter', isComposing:true })
    expect(document.activeElement).toBe(input.element)
    await wrapper.get('[name="password"]').setValue('x'.repeat(300)); await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(mocks.login).toHaveBeenCalledWith({ username: '001', password: 'x'.repeat(300) })
  })
  it('keeps password selection and Caps Lock feedback through visibility toggle', async () => {
    const wrapper = view(LoginView), input = wrapper.get('[name="password"]')
    await input.setValue('abcdefg'); (input.element as HTMLInputElement).focus(); (input.element as HTMLInputElement).setSelectionRange(1,4)
    const keyboard = new KeyboardEvent('keydown', { key: 'A', bubbles:true }); Object.defineProperty(keyboard,'getModifierState',{ value: () => true }); input.element.dispatchEvent(keyboard)
    await flushPromises(); expect(wrapper.text()).toContain('大写锁定已开启')
    await wrapper.get('[aria-label="显示登录密码"]').trigger('click')
    expect(input.attributes('type')).toBe('text'); expect((input.element as HTMLInputElement).selectionStart).toBe(1); expect(document.activeElement).toBe(input.element)
  })
})

async function stepOne(wrapper: ReturnType<typeof view>) {
  await wrapper.get('[name="username"]').setValue('0001'); await wrapper.get('[name="display_name"]').setValue('测试员工'); await wrapper.get('[name="email"]').setValue('qa@example.test')
  await wrapper.get('form').trigger('submit'); await flushPromises()
}
async function stepTwo(wrapper: ReturnType<typeof view>, org='huaxing', dept='engineering') {
  await wrapper.get('[name="org_unit_id"]').setValue(org); await wrapper.get('[name="department"]').setValue(dept); await wrapper.get('[name="position"]').setValue('实际岗位')
  await wrapper.get('form').trigger('submit'); await flushPromises()
}
describe('three step registration', () => {
  it('submits total affairs with the authoritative empty factory mapping and shows a real receipt', async () => {
    const wrapper = view(RegisterView); await flushPromises(); await stepOne(wrapper)
    expect((wrapper.get('[name="org_unit_id"]').element as HTMLSelectElement).value).toBe('')
    await stepTwo(wrapper,'group-management','system')
    await wrapper.get('[name="password"]').setValue(' abc123 '); await wrapper.get('[name="confirm_password"]').setValue(' abc123 ')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(mocks.register).toHaveBeenCalledWith(expect.objectContaining({ org_unit_id:'group-management',factory_id:'',department:'system',password:' abc123 ' }))
    expect(wrapper.text()).toContain('registration-real'); expect(wrapper.text()).toContain('2026-10-10'); expect(wrapper.findAll('input')).toHaveLength(0); expect(mocks.login).not.toHaveBeenCalled()
    expect(document.activeElement?.textContent).toBe('申请已收到')
  })
  it('retains input on an unknown result and does not automatically resubmit', async () => {
    mocks.register.mockRejectedValue({ isAxiosError:true, code:'ECONNABORTED' })
    const wrapper = view(RegisterView); await flushPromises(); await stepOne(wrapper); await stepTwo(wrapper)
    await wrapper.get('[name="password"]').setValue('secret123'); await wrapper.get('[name="confirm_password"]').setValue('secret123'); await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(wrapper.text()).toContain('提交结果暂未确认'); expect((wrapper.get('[name="password"]').element as HTMLInputElement).value).toBe('secret123'); expect(mocks.register).toHaveBeenCalledTimes(1)
  })
  it('keeps data between steps, clears department on organization switch, and accepts an old receipt', async () => {
    mocks.register.mockResolvedValue({ status:'pending',message:'已提交' })
    const wrapper = view(RegisterView); await flushPromises(); await stepOne(wrapper); await stepTwo(wrapper)
    await wrapper.findAll('button').find(b=>b.text().includes('上一步'))!.trigger('click'); await flushPromises()
    expect((wrapper.get('[name="position"]').element as HTMLInputElement).value).toBe('实际岗位')
    await wrapper.get('[name="org_unit_id"]').setValue('group-management'); expect((wrapper.get('[name="department"]').element as HTMLSelectElement).value).toBe('')
    await wrapper.get('[name="department"]').setValue('system'); await wrapper.get('form').trigger('submit'); await flushPromises()
    await wrapper.get('[name="password"]').setValue('secret123'); await wrapper.get('[name="confirm_password"]').setValue('secret123'); await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(wrapper.text()).toContain('申请已收到'); expect(wrapper.text()).not.toContain('申请编号'); expect(wrapper.text()).not.toContain('提交时间')
  })
  it('keeps the latest catalog result and invalidates removed selections', async () => {
    const stale = deferred<typeof catalog>(); mocks.organizationCatalog.mockReturnValueOnce(stale.promise).mockResolvedValue(catalog)
    const { useRegistrationForm } = await import('@/composables/useRegistrationForm')
    let form!: ReturnType<typeof useRegistrationForm>
    mount(defineComponent({ setup(){ form = useRegistrationForm(); return () => null } }))
    await form.loadCatalog(); stale.reject(Error('late failure')); await flushPromises()
    expect(form.catalogState.value).toBe('ready')
    form.form.org_unit_id='huaxing'; await flushPromises(); form.form.department='engineering'
    mocks.organizationCatalog.mockResolvedValue({organizations:[]}); await form.loadCatalog(); await flushPromises()
    expect(form.form.org_unit_id).toBe(''); expect(form.form.department).toBe(''); expect(form.catalogState.value).toBe('empty')
  })
})

describe('claim polling lifetime and rate-limit deadline', () => {
  it('never revives polling after an unmounted request resolves', async () => {
    vi.useFakeTimers(); const pending = deferred<typeof none>(); mocks.getPasswordResetClaim.mockReturnValue(pending.promise)
    const wrapper = mount(defineComponent({ setup(){ usePasswordResetClaim(); return () => null } }))
    wrapper.unmount(); pending.resolve({...none,status:'pending'}); await flushPromises(); await vi.advanceTimersByTimeAsync(60_000)
    expect(mocks.getPasswordResetClaim).toHaveBeenCalledTimes(1)
  })
  it('retains known state on refresh failure, pauses hidden polling and ignores late hidden responses', async () => {
    vi.useFakeTimers(); let claim!: ReturnType<typeof usePasswordResetClaim>
    mocks.getPasswordResetClaim.mockResolvedValue({...none,status:'pending'})
    mount(defineComponent({setup(){claim=usePasswordResetClaim(); return () => null}})); await flushPromises()
    mocks.getPasswordResetClaim.mockRejectedValueOnce(Error('offline')); await claim.refresh()
    expect(claim.claim.value?.status).toBe('pending'); expect(claim.refreshError.value).toContain('刷新失败')
    const pending=deferred<typeof none>(); mocks.getPasswordResetClaim.mockReturnValueOnce(pending.promise); void claim.refresh()
    vi.spyOn(document,'visibilityState','get').mockReturnValue('hidden'); document.dispatchEvent(new Event('visibilitychange'))
    pending.resolve({...none,status:'approved'}); await flushPromises(); const calls=mocks.getPasswordResetClaim.mock.calls.length
    await vi.advanceTimersByTimeAsync(30_000); expect(mocks.getPasswordResetClaim).toHaveBeenCalledTimes(calls); expect(claim.claim.value?.status).toBe('pending')
    vi.spyOn(document,'visibilityState','get').mockReturnValue('visible'); document.dispatchEvent(new Event('visibilitychange')); await flushPromises(); expect(mocks.getPasswordResetClaim).toHaveBeenCalledTimes(calls+1)
  })
  it('uses the server remaining time across remounts without automatic login', async () => {
    vi.useFakeTimers(); let deadline!: ReturnType<typeof useAuthDeadline>
    const make=()=>mount(defineComponent({setup(){deadline=useAuthDeadline();return () => null}}))
    const first=make(); deadline.setRetryAfter(20); await vi.advanceTimersByTimeAsync(7000); expect(deadline.remaining.value).toBe(13); first.unmount()
    make(); expect(deadline.remaining.value).toBe(13); await vi.advanceTimersByTimeAsync(14000); expect(deadline.remaining.value).toBe(0); expect(mocks.login).not.toHaveBeenCalled()
  })
  it('does not advance the authentication boundary on a same-user refresh snapshot', async () => {
    const {getAuthenticationGeneration}=await import('@/lib/authenticationGeneration')
    const auth=useAuthStore(); auth.applySession(user); const initial=getAuthenticationGeneration(); auth.applySession(user); expect(getAuthenticationGeneration()).toBe(initial)
  })
})
