<script setup lang="ts">
import { Building2, CheckCircle2, Copy, FilePlus2, Snowflake, X } from '@lucide/vue'
import { computed, reactive, ref, watch } from 'vue'
import { internalQuoteSectionDefinitions } from '@/data/internalQuoteDeskConfig'
import type { InternalQuote, InternalQuoteBusinessOwner, InternalQuoteCreatePayload } from '@/types/internalQuoteDesk'

const props = withDefaults(defineProps<{
  open: boolean
  mode: 'create' | 'clone'
  sourceQuote?: InternalQuote
  businessOwners: InternalQuoteBusinessOwner[]
  busy?: boolean
  externalError?: string
  factoryId?: string
  factoryName?: string
  allowedInitiatorDepartments?: Array<'sales-business' | 'engineering'>
}>(), {
  factoryId: 'huaxing',
  factoryName: '华兴',
  allowedInitiatorDepartments: () => ['sales-business', 'engineering'],
})

const emit = defineEmits<{
  close: []
  confirm: [payload: InternalQuoteCreatePayload]
}>()

const errorMessage = ref('')
const form = reactive<InternalQuoteCreatePayload>({
  quoteNo: '',
  productName: '',
  customer: '',
  versionLabel: 'V1.0',
  initiatorDepartment: 'sales-business',
  businessOwnerId: '',
  businessOwner: '',
  quantity: 10000,
  targetDate: '2026-08-30',
  remark: '',
})

const title = computed(() => props.mode === 'clone' ? '复制内部报价' : '新建内部报价')

watch(() => [props.open, props.mode, props.sourceQuote?.id, props.businessOwners[0]?.id] as const, ([open]) => {
  if (!open) return
  errorMessage.value = ''
  if (props.mode === 'clone' && props.sourceQuote) {
    Object.assign(form, {
      quoteNo: `${props.sourceQuote.quoteNo}-COPY`,
      productName: props.sourceQuote.productName,
      customer: props.sourceQuote.customer,
      versionLabel: 'V1.0',
      initiatorDepartment: props.sourceQuote.initiatorDepartment,
      businessOwnerId: props.sourceQuote.businessOwnerId,
      businessOwner: props.sourceQuote.businessOwner,
      quantity: props.sourceQuote.quantity,
      targetDate: props.sourceQuote.targetDate,
      remark: `复制自 ${props.sourceQuote.quoteNo} ${props.sourceQuote.versionLabel}`,
    })
    return
  }
  Object.assign(form, {
    quoteNo: '',
    productName: '',
    customer: '',
    versionLabel: 'V1.0',
    initiatorDepartment: props.allowedInitiatorDepartments[0] ?? 'sales-business',
    businessOwnerId: props.businessOwners[0]?.id ?? '',
    businessOwner: props.businessOwners[0]?.displayName ?? '',
    quantity: 10000,
    targetDate: '2026-08-30',
    remark: '',
  })
}, { immediate: true })

function submit() {
  errorMessage.value = ''
  if (props.mode === 'create' && !props.allowedInitiatorDepartments.includes(form.initiatorDepartment)) {
    errorMessage.value = '当前账号不能以所选部门发起内部报价。'
    return
  }
  if (!form.quoteNo.trim() || !form.productName.trim() || !form.customer.trim()) {
    errorMessage.value = '请填写报价号、产品名称和客户。'
    return
  }
  if (!form.businessOwnerId || !form.businessOwner.trim()) {
    errorMessage.value = '业务部和工程部建单时都必须指定业务负责人。'
    return
  }
  if (!Number.isFinite(Number(form.quantity)) || Number(form.quantity) <= 0) {
    errorMessage.value = '出货数量必须大于 0。'
    return
  }
  emit('confirm', { ...form, quantity: Number(form.quantity) })
}

function selectBusinessOwner() {
  const selected = props.businessOwners.find((item) => item.id === form.businessOwnerId)
  form.businessOwner = selected?.displayName ?? ''
}
</script>

<template>
  <Teleport to="body">
    <Transition name="quote-dialog">
      <div v-if="open" class="quote-dialog-backdrop" role="presentation" @mousedown.self="emit('close')">
        <section class="quote-dialog" role="dialog" aria-modal="true" :aria-label="title">
          <header class="quote-dialog-head">
            <div class="quote-dialog-heading">
              <span class="quote-dialog-icon">
                <Copy v-if="mode === 'clone'" aria-hidden="true" />
                <FilePlus2 v-else aria-hidden="true" />
              </span>
              <div>
                <h2>{{ title }}</h2>
                <p>业务部与工程部均可发起；创建时冻结参考快照并生成八个责任分段。</p>
              </div>
            </div>
            <button type="button" class="quote-icon-button" aria-label="关闭" @click="emit('close')">
              <X aria-hidden="true" />
            </button>
          </header>

          <div class="quote-dialog-body">
            <div v-if="mode === 'clone' && sourceQuote" class="quote-copy-note">
              <Copy aria-hidden="true" />
              <span>复制 {{ sourceQuote.quoteNo }} {{ sourceQuote.versionLabel }} 的单头、分段明细和参考快照；全部审批、最终放行和导出状态会清零。</span>
            </div>

            <fieldset class="quote-department-choice">
              <legend>发起部门</legend>
              <label :class="{ active: form.initiatorDepartment === 'sales-business', disabled: !allowedInitiatorDepartments.includes('sales-business') }">
                <input v-model="form.initiatorDepartment" type="radio" value="sales-business" :disabled="!allowedInitiatorDepartments.includes('sales-business')">
                <span class="quote-choice-check"><CheckCircle2 aria-hidden="true" /></span>
                <strong>业务部建单</strong>
                <small>维护单头、业务分段及最终放行</small>
              </label>
              <label :class="{ active: form.initiatorDepartment === 'engineering', disabled: !allowedInitiatorDepartments.includes('engineering') }">
                <input v-model="form.initiatorDepartment" type="radio" value="engineering" :disabled="!allowedInitiatorDepartments.includes('engineering')">
                <span class="quote-choice-check"><CheckCircle2 aria-hidden="true" /></span>
                <strong>工程部建单</strong>
                <small>发起工程核价，同时指定业务负责人</small>
              </label>
            </fieldset>

            <div class="quote-form-grid">
              <label>
                <span>报价号 / 货号 <b>*</b></span>
                <input v-model="form.quoteNo" type="text" placeholder="例如 IQ-HX-2026-0716-06">
              </label>
              <label>
                <span>版本标签 <b>*</b></span>
                <input v-model="form.versionLabel" type="text" placeholder="V1.0">
              </label>
              <label class="wide">
                <span>产品名称 <b>*</b></span>
                <input v-model="form.productName" type="text" placeholder="填写产品名称">
              </label>
              <label>
                <span>客户 <b>*</b></span>
                <select v-model="form.customer">
                  <option value="" disabled>选择客户</option>
                  <option>BuzzBee</option>
                  <option>Disney</option>
                  <option>Dickie</option>
                  <option>彩星</option>
                  <option>Huaxing Demo</option>
                </select>
              </label>
              <label>
                <span>业务负责人 <b>*</b></span>
                <select v-model="form.businessOwnerId" :disabled="!businessOwners.length" @change="selectBusinessOwner">
                  <option value="" disabled>{{ businessOwners.length ? '选择业务负责人' : '当前厂区暂无可选业务负责人' }}</option>
                  <option v-for="owner in businessOwners" :key="owner.id" :value="owner.id">{{ owner.displayName }}（{{ owner.username }}）</option>
                </select>
              </label>
              <label>
                <span>出货数量 <b>*</b></span>
                <input v-model.number="form.quantity" type="number" min="1" step="1">
              </label>
              <label>
                <span>预计完成日期</span>
                <input v-model="form.targetDate" type="date">
              </label>
              <label class="wide">
                <span>备注</span>
                <textarea v-model="form.remark" rows="2" placeholder="记录客户要求、报价范围或版本说明" />
              </label>
            </div>

            <section class="quote-create-baseline">
              <div class="quote-baseline-title">
                <Building2 aria-hidden="true" />
                <div><strong>当前厂区：{{ factoryName }}</strong><span>统一车间 {{ factoryId }}-workshop，不在页面内重复切换厂区</span></div>
              </div>
              <div class="quote-segment-pills">
                <span v-for="segment in internalQuoteSectionDefinitions" :key="segment.code">
                  <CheckCircle2 aria-hidden="true" />{{ segment.label }}
                </span>
              </div>
              <p><Snowflake aria-hidden="true" />创建后冻结汇率、材料价与机型价参考快照；同步新参考表会产生新 revision。</p>
            </section>

            <p v-if="errorMessage || externalError" class="quote-form-error" role="alert">{{ errorMessage || externalError }}</p>
          </div>

          <footer class="quote-dialog-actions">
            <button type="button" class="quote-secondary-button" :disabled="busy" @click="emit('close')">取消</button>
            <button type="button" class="quote-primary-button" :disabled="busy || !businessOwners.length" @click="submit">
              <Copy v-if="mode === 'clone'" aria-hidden="true" />
              <FilePlus2 v-else aria-hidden="true" />
              {{ busy ? '正在提交…' : mode === 'clone' ? '确认复制并进入协作' : '创建并进入协作' }}
            </button>
          </footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.quote-dialog-backdrop{position:fixed;inset:0;z-index:100;display:grid;place-items:center;padding:24px;background:rgb(15 23 42/.5);backdrop-filter:blur(5px)}
.quote-dialog{width:min(820px,100%);max-height:min(920px,calc(100vh - 48px));overflow:auto;border:1px solid #d8e2e7;border-radius:18px;background:#fff;box-shadow:0 30px 80px rgb(15 23 42/.24)}
.quote-dialog-head,.quote-dialog-actions{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:18px 22px;border-color:#e2e8f0;background:#f8fafc}
.quote-dialog-head{border-bottom:1px solid #e2e8f0}.quote-dialog-actions{justify-content:flex-end;border-top:1px solid #e2e8f0}
.quote-dialog-heading{display:flex;min-width:0;align-items:center;gap:13px}.quote-dialog-heading h2{margin:0;color:#0f172a;font-size:20px;font-weight:900}.quote-dialog-heading p{margin:5px 0 0;color:#64748b;font-size:12px;line-height:1.5}
.quote-dialog-icon{display:grid;width:42px;height:42px;flex:0 0 auto;place-items:center;border-radius:12px;background:#ccfbf1;color:#0f766e}.quote-dialog-icon svg,.quote-icon-button svg{width:20px;height:20px}
.quote-icon-button{display:grid;width:36px;height:36px;flex:0 0 auto;place-items:center;border:0;border-radius:9px;background:transparent;color:#64748b}.quote-icon-button:hover{background:#e2e8f0;color:#0f172a}
.quote-dialog-body{display:grid;gap:18px;padding:22px}.quote-copy-note{display:flex;gap:9px;border:1px solid #bfdbfe;border-radius:10px;background:#eff6ff;padding:11px 13px;color:#1e40af;font-size:12px;line-height:1.55}.quote-copy-note svg{width:17px;height:17px;flex:0 0 auto;margin-top:1px}
.quote-department-choice{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:0;padding:0;border:0}.quote-department-choice legend{grid-column:1/-1;margin-bottom:1px;color:#475569;font-size:12px;font-weight:800}.quote-department-choice label{position:relative;display:grid;grid-template-columns:auto 1fr;gap:2px 9px;border:1px solid #dbe5ea;border-radius:11px;padding:13px 14px;cursor:pointer}.quote-department-choice label.active{border-color:#14b8a6;background:#f0fdfa;box-shadow:0 0 0 3px rgb(20 184 166/.09)}.quote-department-choice input{position:absolute;opacity:0}.quote-choice-check{grid-row:1/3;color:#94a3b8}.active .quote-choice-check{color:#0f766e}.quote-choice-check svg{width:18px;height:18px}.quote-department-choice strong{color:#0f172a;font-size:13px}.quote-department-choice small{color:#64748b;font-size:11px;line-height:1.45}
.quote-department-choice label.disabled{cursor:not-allowed;opacity:.48}.quote-department-choice label.disabled:hover{border-color:#dbe5ea;box-shadow:none}
.quote-form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.quote-form-grid label{display:grid;gap:6px}.quote-form-grid label.wide{grid-column:1/-1}.quote-form-grid label>span{color:#475569;font-size:11px;font-weight:800}.quote-form-grid b{color:#dc2626}.quote-form-grid input,.quote-form-grid select,.quote-form-grid textarea{width:100%;border:1px solid #dbe5ea;border-radius:9px;background:#fff;padding:9px 11px;color:#0f172a;font-size:13px;outline:none}.quote-form-grid textarea{resize:vertical}
.quote-create-baseline{display:grid;gap:12px;border:1px solid #dbe5ea;border-radius:12px;background:#f8fafc;padding:15px}.quote-baseline-title{display:flex;align-items:center;gap:9px}.quote-baseline-title>svg{width:20px;color:#0f766e}.quote-baseline-title div{display:grid}.quote-baseline-title strong{color:#0f172a;font-size:13px}.quote-baseline-title span{margin-top:2px;color:#64748b;font-size:11px}.quote-segment-pills{display:flex;flex-wrap:wrap;gap:7px}.quote-segment-pills span{display:inline-flex;align-items:center;gap:4px;border:1px solid #ccfbf1;border-radius:999px;background:#fff;padding:5px 8px;color:#0f766e;font-size:10px;font-weight:800}.quote-segment-pills svg{width:12px;height:12px}.quote-create-baseline p{display:flex;align-items:flex-start;gap:6px;margin:0;color:#64748b;font-size:11px;line-height:1.5}.quote-create-baseline p svg{width:15px;height:15px;flex:0 0 auto;color:#0d9488}.quote-form-error{margin:0;border-radius:8px;background:#fef2f2;padding:9px 11px;color:#b91c1c;font-size:12px}
.quote-primary-button,.quote-secondary-button{display:inline-flex;min-height:38px;align-items:center;justify-content:center;gap:7px;border-radius:9px;padding:0 16px;font-size:12px;font-weight:900}.quote-primary-button{border:1px solid #0f766e;background:#0f766e;color:#fff}.quote-primary-button:hover{background:#115e59}.quote-secondary-button{border:1px solid #cbd5e1;background:#fff;color:#475569}.quote-primary-button svg{width:16px;height:16px}.quote-dialog-enter-active,.quote-dialog-leave-active{transition:opacity .16s ease}.quote-dialog-enter-active .quote-dialog,.quote-dialog-leave-active .quote-dialog{transition:transform .18s ease}.quote-dialog-enter-from,.quote-dialog-leave-to{opacity:0}.quote-dialog-enter-from .quote-dialog,.quote-dialog-leave-to .quote-dialog{transform:translateY(8px) scale(.985)}
.quote-department-choice small,.quote-form-grid label>span,.quote-baseline-title span,.quote-create-baseline p{font-size:12px}.quote-segment-pills span{font-size:11px}.quote-primary-button,.quote-secondary-button{font-size:13px}.quote-icon-button,.quote-primary-button,.quote-secondary-button,.quote-department-choice label{transition:color .18s ease,background-color .18s ease,border-color .18s ease,box-shadow .18s ease,transform .18s ease}.quote-icon-button:hover,.quote-primary-button:hover,.quote-secondary-button:hover{transform:translateY(-1px)}.quote-icon-button:active,.quote-primary-button:active,.quote-secondary-button:active{transform:translateY(0) scale(.98)}.quote-secondary-button:hover{border-color:#99f6e4;background:#f0fdfa;color:#0f766e}.quote-department-choice label:hover{border-color:#99f6e4;box-shadow:0 8px 18px rgb(15 118 110/.08)}.quote-form-grid input,.quote-form-grid select,.quote-form-grid textarea{transition:border-color .18s ease,box-shadow .18s ease,background-color .18s ease}.quote-form-grid input:hover,.quote-form-grid select:hover,.quote-form-grid textarea:hover{border-color:#94a3b8}.quote-form-grid input:focus,.quote-form-grid select:focus,.quote-form-grid textarea:focus{border-color:#14b8a6;box-shadow:0 0 0 3px rgb(20 184 166/.1)}
@media(max-width:650px){.quote-dialog-backdrop{padding:0}.quote-dialog{max-height:100vh;border-radius:0}.quote-department-choice,.quote-form-grid{grid-template-columns:1fr}.quote-form-grid label.wide{grid-column:auto}.quote-dialog-actions{position:sticky;bottom:0}}
@media(prefers-reduced-motion:reduce){.quote-icon-button,.quote-primary-button,.quote-secondary-button,.quote-department-choice label,.quote-form-grid input,.quote-form-grid select,.quote-form-grid textarea{transition:none}}
</style>
