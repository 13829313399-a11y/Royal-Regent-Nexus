<script setup lang="ts">
import { nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, ArrowRight, UserRound, AtSign, Phone, Mail, BriefcaseBusiness, Building2, CircleAlert } from '@lucide/vue'
import AuthField from '@/components/auth/AuthField.vue'
import AuthPasswordField from '@/components/auth/AuthPasswordField.vue'
import AuthRegistrationReceipt from '@/components/auth/AuthRegistrationReceipt.vue'
import { useRegistrationForm } from '@/composables/useRegistrationForm'
import { handoffRegistrationUsername } from '@/lib/authAccountPreference'
const router = useRouter(), route = useRoute()
const { form, step, organizations, organization, departments, catalogState, catalogNotice, loadCatalog, errors, message, submitting, receipt, submittedSummary, next, submit, restart } = useRegistrationForm()
const basics = [{ name: 'username', label: '企业账号 / 工号', icon: AtSign, auto: 'username' }, { name: 'display_name', label: '姓名', icon: UserRound, auto: 'name' }, { name: 'phone', label: '手机', icon: Phone, auto: 'tel' }, { name: 'email', label: '邮箱', icon: Mail, auto: 'email' }] as const
async function back(value: number) { if (submitting.value || value > step.value) return; step.value = value; message.value = ''; await nextTick(); document.querySelector<HTMLElement>('[data-auth-step-title]')?.focus() }
async function login() { handoffRegistrationUsername(submittedSummary.value.username); await router.push({ name: 'login', query: route.query.redirect ? { redirect: route.query.redirect } : {} }) }
</script>
<template>
  <AuthRegistrationReceipt v-if="receipt" :receipt="receipt" :summary="submittedSummary" @login="login" @restart="restart" />
  <div v-else class="ng-page-enter">
    <header class="ng-form-header ng-register-header"><h1 tabindex="-1">申请开通账号</h1><p>填写真实信息，由管理员核验组织与岗位。</p></header>
    <ol class="ng-stepper" aria-label="账号申请进度"><li v-for="(label,index) in ['基础信息','组织岗位','设置密码']" :key="label" :aria-current="step === index + 1 ? 'step' : undefined" :class="{ 'ng-step-done': step > index + 1 }"><button type="button" :disabled="step < index + 1 || submitting" @click="back(index + 1)"><span class="ng-step-index">{{ index + 1 }}</span>{{ label }}</button></li></ol>
    <form novalidate :aria-busy="submitting" @submit.prevent="step < 3 ? next() : submit()" @keydown.enter="event => { if (event.isComposing) event.preventDefault() }">
      <div v-if="message" class="ng-alert" data-tone="error" role="alert"><CircleAlert class="ng-icon" aria-hidden="true" />{{ message }}</div>
      <section v-if="step === 1" key="basic" class="ng-page-enter">
        <h2 class="ng-step-title" tabindex="-1" data-auth-step-title><span>01</span>先认识一下你</h2>
        <AuthField v-for="item in basics" :key="item.name" :id="`register-${item.name}`" :label="item.label" :error="errors[item.name]" :hint="item.name === 'phone' ? '手机或邮箱至少填写一项，供管理员核验。' : undefined" :required="['username','display_name'].includes(item.name)" v-slot="field">
          <div class="ng-control"><component :is="item.icon" class="ng-icon" aria-hidden="true" /><input :id="`register-${item.name}`" v-model="form[item.name]" :name="item.name" :autocomplete="item.auto" :type="item.name === 'email' ? 'email' : item.name === 'phone' ? 'tel' : 'text'" :placeholder="item.label" :aria-invalid="field.invalid" :aria-describedby="field.describedby" @input="delete errors[item.name]" /></div>
        </AuthField>
      </section>
      <section v-else-if="step === 2" key="organization" class="ng-page-enter">
        <h2 class="ng-step-title" tabindex="-1" data-auth-step-title><span>02</span>你属于哪个团队？</h2>
        <div v-if="catalogState !== 'ready'" class="ng-alert" role="status"><div>{{ catalogState === 'loading' ? '正在加载组织目录' : catalogState === 'empty' ? '暂时没有可申请的组织，请联系管理员' : '组织目录暂时无法加载' }}<button v-if="catalogState !== 'loading'" type="button" class="ng-text-link" @click="loadCatalog">重试加载组织目录</button></div></div>
        <p v-if="catalogNotice" class="auth-hint" role="status">{{ catalogNotice }}</p>
        <AuthField id="register-organization" label="所属组织" :error="errors.org_unit_id || errors.factory_id" required v-slot="field"><div class="ng-control"><Building2 class="ng-icon" aria-hidden="true" /><select id="register-organization" v-model="form.org_unit_id" name="org_unit_id" :disabled="catalogState !== 'ready'" :aria-invalid="field.invalid" :aria-describedby="field.describedby" @change="delete errors.org_unit_id"><option value="" disabled>请选择所属组织</option><option v-for="org in organizations" :key="org.id" :value="org.id">{{ org.name }}</option></select></div></AuthField>
        <AuthField id="register-department" label="部门" :error="errors.department" required v-slot="field"><div class="ng-control"><select id="register-department" v-model="form.department" name="department" :disabled="catalogState !== 'ready' || !organization" :aria-invalid="field.invalid" :aria-describedby="field.describedby" @change="delete errors.department"><option value="" disabled>请选择部门</option><option v-for="dept in departments" :key="dept.code" :value="dept.code">{{ dept.name }}</option></select></div></AuthField>
        <AuthField id="register-position" label="实际职位" :error="errors.position" hint="填写实际工作职位，管理员将核验并配置对应访问范围。" required v-slot="field"><div class="ng-control"><BriefcaseBusiness class="ng-icon" aria-hidden="true" /><input id="register-position" v-model="form.position" name="position" placeholder="例如：工程师、生产文员" autocomplete="organization-title" :aria-invalid="field.invalid" :aria-describedby="field.describedby" @input="delete errors.position" /></div></AuthField>
        <div class="auth-preview"><small>申请预览 / 待核验</small><strong>{{ form.display_name || '申请人' }}</strong><p>{{ organization?.name || '待选择组织' }} · {{ departments.find(d => d.code === form.department)?.name || '待选择部门' }}<br>{{ form.position || '待填写实际职位' }}</p></div>
        <button type="button" class="ng-text-link" :disabled="catalogState === 'loading'" @click="loadCatalog">刷新组织目录</button>
      </section>
      <section v-else key="password" class="ng-page-enter">
        <h2 class="ng-step-title" tabindex="-1" data-auth-step-title><span>03</span>设置密码，核对申请</h2>
        <AuthPasswordField id="register-password" v-model="form.password" name="password" label="设置密码" hint="6–256 个字符，当前不支持中文；输入内容会完整保留。" :error="errors.password" :disabled="submitting" @update:model-value="delete errors.password" />
        <AuthPasswordField id="register-confirm-password" v-model="form.confirm_password" name="confirm_password" label="确认密码" :error="errors.confirm_password" :disabled="submitting" @update:model-value="delete errors.confirm_password" />
        <section class="ng-summary" aria-label="申请信息摘要"><div class="ng-summary-top"><h3>申请信息</h3><button class="ng-text-link" type="button" :disabled="submitting" @click="back(1)">修改信息</button></div><dl><dt>申请人</dt><dd>{{ form.display_name }} · {{ form.username }}</dd><dt>组织</dt><dd>{{ organization?.name }} / {{ departments.find(d => d.code === form.department)?.name }}</dd><dt>职位</dt><dd>{{ form.position }}</dd><dt>联系</dt><dd>{{ form.phone || form.email }}</dd></dl></section>
      </section>
      <div class="ng-form-actions"><button v-if="step > 1" class="ng-secondary" type="button" :disabled="submitting" @click="back(step - 1)"><ArrowLeft class="ng-icon" aria-hidden="true" />上一步</button><button class="ng-primary" type="submit" :disabled="submitting"><span v-if="submitting" class="ng-spinner" aria-hidden="true" />{{ submitting ? '正在提交' : step === 3 ? '提交账号申请' : '下一步' }}<ArrowRight v-if="!submitting" class="ng-icon ng-arrow" aria-hidden="true" /></button></div>
      <p class="ng-form-note">申请提交后须由管理员核验。实际职位用于说明工作职责，不代表已经获得系统权限。</p>
    </form>
  </div>
</template>
