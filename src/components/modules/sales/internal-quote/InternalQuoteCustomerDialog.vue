<script setup lang="ts">
import { Check, Pencil, Plus, Trash2, Users, X } from '@lucide/vue'
import { ref, watch } from 'vue'
import type { ApiInternalQuoteCustomer } from '@/api/internalQuote'

const props = defineProps<{
  open: boolean
  customers: ApiInternalQuoteCustomer[]
  busy: boolean
  factoryName: string
  externalError?: string
}>()

const emit = defineEmits<{
  close: []
  create: [name: string]
  update: [customer: ApiInternalQuoteCustomer, name: string]
  delete: [customer: ApiInternalQuoteCustomer]
}>()

const newName = ref('')
const editingId = ref('')
const editingName = ref('')
const pendingDeleteId = ref('')
const localError = ref('')

watch(() => props.open, (open) => {
  if (!open) return
  newName.value = ''
  editingId.value = ''
  editingName.value = ''
  pendingDeleteId.value = ''
  localError.value = ''
})

function normalized(value: string) {
  return value.trim().replace(/\s+/g, ' ').toLocaleLowerCase()
}

function validateName(value: string, currentId = '') {
  const name = value.trim().replace(/\s+/g, ' ')
  if (!name) return '客户名称不能为空'
  if (props.customers.some((item) => item.id !== currentId && normalized(item.name) === normalized(name))) {
    return '当前厂区已存在同名客户'
  }
  return ''
}

function createCustomer() {
  localError.value = validateName(newName.value)
  if (localError.value || props.busy) return
  emit('create', newName.value.trim().replace(/\s+/g, ' '))
  newName.value = ''
}

function startEdit(customer: ApiInternalQuoteCustomer) {
  editingId.value = customer.id
  editingName.value = customer.name
  pendingDeleteId.value = ''
  localError.value = ''
}

function saveEdit(customer: ApiInternalQuoteCustomer) {
  localError.value = validateName(editingName.value, customer.id)
  if (localError.value || props.busy) return
  emit('update', customer, editingName.value.trim().replace(/\s+/g, ' '))
  editingId.value = ''
  editingName.value = ''
}

function requestDelete(customer: ApiInternalQuoteCustomer) {
  if (pendingDeleteId.value !== customer.id) {
    pendingDeleteId.value = customer.id
    editingId.value = ''
    localError.value = ''
    return
  }
  emit('delete', customer)
  pendingDeleteId.value = ''
}
</script>

<template>
  <Teleport to="body">
    <Transition name="customer-dialog">
      <div v-if="open" class="customer-dialog-backdrop" @mousedown.self="emit('close')">
        <section class="customer-dialog" role="dialog" aria-modal="true" aria-labelledby="customer-dialog-title">
          <header>
            <div class="customer-dialog-heading">
              <span><Users aria-hidden="true" /></span>
              <div>
                <h2 id="customer-dialog-title">客户资料</h2>
                <p>{{ factoryName }} · 仅本厂业务主管可新增、修改和删除</p>
              </div>
            </div>
            <button type="button" class="customer-close" :disabled="busy" aria-label="关闭客户资料" @click="emit('close')"><X aria-hidden="true" /></button>
          </header>

          <div class="customer-dialog-body">
            <form class="customer-create-row" @submit.prevent="createCustomer">
              <label>
                <span>新增客户</span>
                <input v-model="newName" maxlength="128" :disabled="busy" placeholder="输入客户名称" aria-label="新增客户名称">
              </label>
              <button type="submit" :disabled="busy || !newName.trim()"><Plus aria-hidden="true" />新增</button>
            </form>

            <p class="customer-rule-note">删除只会从后续建单选项中移除，不会改动历史报价中的客户名称。</p>
            <p v-if="localError || externalError" class="customer-error" role="alert">{{ localError || externalError }}</p>

            <div class="customer-list" :aria-busy="busy">
              <article v-for="customer in customers" :key="customer.id">
                <div v-if="editingId === customer.id" class="customer-edit-row">
                  <input v-model="editingName" maxlength="128" :disabled="busy" :aria-label="`修改客户 ${customer.name}`" @keyup.enter="saveEdit(customer)">
                  <button type="button" class="save" :disabled="busy" title="保存修改" @click="saveEdit(customer)"><Check aria-hidden="true" /></button>
                  <button type="button" :disabled="busy" title="取消修改" @click="editingId = ''"><X aria-hidden="true" /></button>
                </div>
                <template v-else>
                  <div class="customer-name">
                    <strong>{{ customer.name }}</strong>
                    <small>revision {{ customer.revision }} · {{ customer.updated_by_name || customer.created_by_name || '系统迁移' }}</small>
                  </div>
                  <div class="customer-actions">
                    <button type="button" :disabled="busy" title="修改客户名称" @click="startEdit(customer)"><Pencil aria-hidden="true" /></button>
                    <button
                      type="button"
                      class="delete"
                      :class="{ confirm: pendingDeleteId === customer.id }"
                      :disabled="busy"
                      :title="pendingDeleteId === customer.id ? '再次点击确认删除' : '删除客户'"
                      @click="requestDelete(customer)"
                    ><Trash2 aria-hidden="true" /><span v-if="pendingDeleteId === customer.id">确认删除</span></button>
                  </div>
                </template>
              </article>
              <div v-if="!customers.length" class="customer-empty">当前厂区还没有客户，请先新增客户后再建报价。</div>
            </div>
          </div>

          <footer>
            <span>共 {{ customers.length }} 个客户</span>
            <button type="button" :disabled="busy" @click="emit('close')">完成</button>
          </footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.customer-dialog-backdrop{position:fixed;z-index:95;inset:0;display:grid;place-items:center;background:rgb(15 23 42/.48);padding:24px;backdrop-filter:blur(5px)}.customer-dialog{display:flex;width:min(640px,100%);max-height:calc(100vh - 48px);flex-direction:column;overflow:hidden;border:1px solid #dbe5ea;border-radius:18px;background:#f8fafc;box-shadow:0 30px 80px rgb(15 23 42/.28)}.customer-dialog>header,.customer-dialog>footer{display:flex;align-items:center;justify-content:space-between;gap:16px;background:#fff;padding:18px 20px}.customer-dialog>header{border-bottom:1px solid #e2e8f0}.customer-dialog>footer{border-top:1px solid #e2e8f0}.customer-dialog-heading{display:flex;align-items:center;gap:12px}.customer-dialog-heading>span{display:grid;width:44px;height:44px;place-items:center;border-radius:13px;background:#ccfbf1;color:#0f766e}.customer-dialog-heading svg{width:22px}.customer-dialog-heading h2{margin:0;color:#0f172a;font-size:20px;font-weight:950}.customer-dialog-heading p{margin:4px 0 0;color:#64748b;font-size:12px}.customer-close{display:grid;width:34px;height:34px;place-items:center;border:0;border-radius:9px;background:transparent;color:#64748b}.customer-close:hover{background:#f1f5f9;color:#0f172a}.customer-close svg{width:19px}.customer-dialog-body{display:grid;gap:12px;overflow:auto;padding:18px 20px}.customer-create-row{display:grid;grid-template-columns:1fr auto;align-items:end;gap:10px}.customer-create-row label{display:grid;gap:6px}.customer-create-row label span{color:#475569;font-size:11px;font-weight:900}.customer-create-row input,.customer-edit-row input{height:38px;border:1px solid #dbe5ea;border-radius:9px;background:#fff;padding:0 11px;color:#0f172a;font-size:13px;outline:none}.customer-create-row input:focus,.customer-edit-row input:focus{border-color:#14b8a6;box-shadow:0 0 0 3px rgb(20 184 166/.1)}.customer-create-row button,.customer-dialog>footer button{display:inline-flex;height:38px;align-items:center;justify-content:center;gap:6px;border:1px solid #0f766e;border-radius:9px;background:#0f766e;padding:0 14px;color:#fff;font-size:12px;font-weight:900}.customer-create-row button svg{width:15px}.customer-create-row button:disabled,.customer-dialog button:disabled{cursor:not-allowed;opacity:.5}.customer-rule-note{margin:0;border:1px solid #bae6fd;border-radius:9px;background:#f0f9ff;padding:9px 11px;color:#0369a1;font-size:11px;line-height:1.55}.customer-error{margin:0;border:1px solid #fecaca;border-radius:9px;background:#fef2f2;padding:9px 11px;color:#b91c1c;font-size:12px}.customer-list{display:grid;gap:7px}.customer-list article{display:flex;min-height:58px;align-items:center;justify-content:space-between;gap:12px;border:1px solid #e2e8f0;border-radius:11px;background:#fff;padding:9px 10px}.customer-name{display:grid;min-width:0;gap:3px}.customer-name strong{overflow:hidden;color:#0f172a;font-size:13px;text-overflow:ellipsis;white-space:nowrap}.customer-name small{color:#94a3b8;font-size:10px}.customer-actions,.customer-edit-row{display:flex;align-items:center;gap:6px}.customer-actions button,.customer-edit-row button{display:inline-flex;min-width:34px;height:34px;align-items:center;justify-content:center;gap:5px;border:1px solid #dbe5ea;border-radius:8px;background:#fff;padding:0 8px;color:#64748b;font-size:10px;font-weight:900}.customer-actions button:hover,.customer-edit-row button:hover{border-color:#99f6e4;background:#f0fdfa;color:#0f766e}.customer-actions button.delete{border-color:#fee2e2;color:#dc2626}.customer-actions button.delete.confirm{background:#dc2626;color:#fff}.customer-actions svg,.customer-edit-row svg{width:14px}.customer-edit-row{width:100%}.customer-edit-row input{min-width:0;flex:1}.customer-edit-row button.save{border-color:#99f6e4;background:#f0fdfa;color:#0f766e}.customer-empty{display:grid;min-height:110px;place-items:center;border:1px dashed #cbd5e1;border-radius:11px;background:#fff;color:#94a3b8;font-size:12px}.customer-dialog>footer>span{color:#64748b;font-size:11px}.customer-dialog>footer button{border-color:#cbd5e1;background:#fff;color:#475569}.customer-dialog-enter-active,.customer-dialog-leave-active{transition:opacity .18s ease}.customer-dialog-enter-active .customer-dialog,.customer-dialog-leave-active .customer-dialog{transition:transform .2s ease}.customer-dialog-enter-from,.customer-dialog-leave-to{opacity:0}.customer-dialog-enter-from .customer-dialog,.customer-dialog-leave-to .customer-dialog{transform:translateY(8px) scale(.985)}
@media(max-width:620px){.customer-dialog-backdrop{align-items:end;padding:0}.customer-dialog{max-height:94vh;border-radius:18px 18px 0 0}.customer-dialog>header,.customer-dialog-body,.customer-dialog>footer{padding-left:14px;padding-right:14px}.customer-create-row{grid-template-columns:1fr}.customer-list article{align-items:stretch;flex-direction:column}.customer-actions{justify-content:flex-end}.customer-edit-row{align-items:stretch;flex-wrap:wrap}.customer-edit-row input{flex-basis:100%}}
@media(prefers-reduced-motion:reduce){.customer-dialog-enter-active,.customer-dialog-leave-active,.customer-dialog-enter-active .customer-dialog,.customer-dialog-leave-active .customer-dialog{transition:none}}
</style>
