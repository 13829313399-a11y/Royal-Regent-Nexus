import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { authApi, type RegisterResponse } from '@/api/auth'
import { authProblem } from '@/lib/authProblem'
import { focusFirstError, newPasswordErrors, type FieldErrors } from '@/lib/authFormValidation'

export function useRegistrationForm() {
  const step = ref(1)
  const form = reactive({ username: '', display_name: '', phone: '', email: '', org_unit_id: '', department: '', position: '', password: '', confirm_password: '' })
  const organizations = ref<Awaited<ReturnType<typeof authApi.organizationCatalog>>['organizations']>([])
  const catalogState = ref<'loading' | 'ready' | 'empty' | 'error'>('loading')
  const catalogNotice = ref('')
  const errors = ref<FieldErrors>({})
  const message = ref('')
  const submitting = ref(false)
  const receipt = ref<RegisterResponse | null>(null)
  const submittedSummary = ref({ username: '', name: '', organization: '', department: '', position: '' })
  const organization = computed(() => organizations.value.find(o => o.id === form.org_unit_id))
  const departments = computed(() => organization.value?.departments ?? [])
  let disposed = false, catalogGeneration = 0
  async function loadCatalog() {
    const generation = ++catalogGeneration
    catalogState.value = 'loading'
    try {
      const result = await authApi.organizationCatalog()
      if (disposed || generation !== catalogGeneration) return
      organizations.value = result.organizations
      catalogState.value = result.organizations.length ? 'ready' : 'empty'
    } catch { if (!disposed && generation === catalogGeneration) catalogState.value = 'error' }
  }
  watch(() => form.org_unit_id, () => { form.department = '' })
  watch(organizations, () => {
    if (form.org_unit_id && !organization.value) { form.org_unit_id = ''; catalogNotice.value = '组织目录已更新，请重新选择组织与部门' }
    if (form.department && !departments.value.some(d => d.code === form.department)) { form.department = ''; catalogNotice.value = '部门目录已更新，请重新选择部门' }
  })
  function validate(upTo = step.value) {
    const result: FieldErrors = {}
    const required: [keyof typeof form, number, string][] = [['username',64,'账号或工号'],['display_name',128,'姓名']]
    if (upTo >= 2) required.push(['org_unit_id',64,'所属组织'],['department',64,'部门'],['position',128,'实际职位'])
    for (const [key, max, label] of required) {
      if (!form[key].trim()) result[key] = `请填写${label}`
      else if (form[key].trim().length > max) result[key] = `${label}不能超过 ${max} 个字符`
    }
    if (!form.phone.trim() && !form.email.trim()) result.phone = '手机或邮箱至少填写一项'
    if (form.phone.trim().length > 64) result.phone = '手机不能超过 64 个字符'
    if (form.email.trim().length > 128) result.email = '邮箱不能超过 128 个字符'
    else if (form.email.trim() && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())) result.email = '请输入有效邮箱'
    if (upTo >= 2) {
      if (catalogState.value !== 'ready') result.org_unit_id = '请先加载可申请的组织目录'
      else if (!organization.value) result.org_unit_id = '请选择有效组织'
      else if (!departments.value.some(d => d.code === form.department)) result.department = '请选择所属组织的有效部门'
    }
    if (upTo >= 3) {
      const passwordErrors = newPasswordErrors(form.password, form.confirm_password)
      if (passwordErrors.new_password) result.password = passwordErrors.new_password
      if (passwordErrors.confirm_password) result.confirm_password = passwordErrors.confirm_password
    }
    errors.value = result
    return !Object.keys(result).length
  }
  async function showErrors() {
    const first = Object.keys(errors.value)[0]
    step.value = ['username','display_name','phone','email'].includes(first ?? '') ? 1 : ['org_unit_id','department','position'].includes(first ?? '') ? 2 : 3
    await nextTick(); focusFirstError(errors.value)
  }
  async function next() {
    if (submitting.value) return
    if (!validate()) { message.value = '请检查标出的信息'; await showErrors(); return }
    message.value = ''; step.value = Math.min(3, step.value + 1)
    await nextTick(); document.querySelector<HTMLElement>('[data-auth-step-title]')?.focus()
  }
  async function submit() {
    if (submitting.value || receipt.value) return
    if (!validate(3)) { message.value = '请检查标出的信息'; await showErrors(); return }
    submitting.value = true; message.value = ''
    const summary = { username: form.username.trim(), name: form.display_name.trim(), organization: organization.value!.name, department: departments.value.find(d => d.code === form.department)!.name, position: form.position.trim() }
    try {
      const result = await authApi.register({ ...form, username: form.username.trim(), display_name: form.display_name.trim(), phone: form.phone.trim(), email: form.email.trim(), position: form.position.trim(), factory_id: organization.value!.factory_id })
      if (disposed) return
      form.password = ''; form.confirm_password = ''; submittedSummary.value = summary; receipt.value = result
      await nextTick(); document.querySelector<HTMLElement>('[data-auth-receipt-title]')?.focus()
    } catch (error) {
      if (disposed) return
      const problem = authProblem(error)
      message.value = problem.uncertain ? '提交结果暂未确认，请核对现有申请后再手动重试。已填信息仍保留。' : problem.message
      errors.value = problem.fieldErrors
      if (['AUTH_ORGANIZATION_CHANGED','ORG_UNAVAILABLE','DEPARTMENT_UNAVAILABLE','INVALID_ORG'].includes(problem.code)) await loadCatalog()
      if (Object.keys(errors.value).length) await showErrors()
    } finally { if (!disposed) submitting.value = false }
  }
  function restart() { for (const key of Object.keys(form) as (keyof typeof form)[]) form[key] = ''; errors.value = {}; message.value = ''; receipt.value = null; step.value = 1 }
  onMounted(loadCatalog)
  onBeforeUnmount(() => { disposed = true; catalogGeneration++; form.password = ''; form.confirm_password = '' })
  return { form, step, organizations, organization, departments, catalogState, catalogNotice, loadCatalog, errors, message, submitting, receipt, submittedSummary, next, submit, restart }
}
