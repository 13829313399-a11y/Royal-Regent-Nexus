<script setup lang="ts">
import { CheckCircle2, Layers3, PackageOpen } from '@lucide/vue'
import type { SalesPricingComponent } from '@/lib/internalQuoteSectionPayload'

defineProps<{
  productName: string
  components: SalesPricingComponent[]
}>()
const model = defineModel<string>({ required: true })
</script>

<template>
  <section class="quote-component-scope" aria-label="JustPlay 当前配件">
    <div class="quote-component-scope-copy">
      <span class="quote-component-scope-icon"><Layers3 /></span>
      <span>
        <strong>JustPlay 当前配件</strong>
        <small>当前款：{{ productName }} · 切换后，各部门只显示该配件明细；新增明细自动归入该配件。</small>
      </span>
    </div>
    <div class="quote-component-options" role="radiogroup" aria-label="选择当前报价配件">
      <button
        v-for="(component,index) in components"
        :key="component.id"
        type="button"
        :class="{ active: model === component.id }"
        role="radio"
        :aria-checked="model === component.id"
        :aria-label="`选择配件 ${component.name}`"
        @click="model = component.id"
      >
        <span><PackageOpen /></span>
        <span><small>配件 {{ index + 1 }}</small><strong>{{ component.name }}</strong></span>
        <CheckCircle2 />
      </button>
    </div>
    <p>包装材料、纸箱及包装/混装工序属于当前单款共用项，不随配件切换隐藏。</p>
  </section>
</template>

<style scoped>
.quote-component-scope{display:grid;gap:12px;border:1px solid #5eead4;border-radius:13px;background:linear-gradient(110deg,#f0fdfa,#fff);padding:14px 15px;box-shadow:0 10px 24px rgb(15 118 110/.08)}.quote-component-scope-copy{display:flex;align-items:center;gap:11px}.quote-component-scope-icon{display:grid;width:38px;height:38px;flex:0 0 38px;place-items:center;border-radius:10px;background:#0f766e;color:#fff}.quote-component-scope-icon svg{width:19px}.quote-component-scope-copy>span:last-child{display:grid;gap:3px}.quote-component-scope-copy strong{color:#134e4a;font-size:14px}.quote-component-scope-copy small{color:#47716d;font-size:11px;line-height:1.5}.quote-component-options{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px}.quote-component-options button{display:grid;min-width:0;grid-template-columns:32px minmax(0,1fr) 18px;align-items:center;gap:8px;border:1px solid #cbd5e1;border-radius:10px;background:#fff;padding:9px 10px;color:#475569;text-align:left;cursor:pointer;transition:border-color .16s ease,background .16s ease,box-shadow .16s ease}.quote-component-options button:hover{border-color:#5eead4;background:#f0fdfa}.quote-component-options button.active{border-color:#0d9488;background:#ecfdf5;box-shadow:0 0 0 2px rgb(13 148 136/.1);color:#0f766e}.quote-component-options button>span:first-child{display:grid;width:32px;height:32px;place-items:center;border-radius:8px;background:#f1f5f9}.quote-component-options button.active>span:first-child{background:#ccfbf1}.quote-component-options svg{width:16px}.quote-component-options button>span:nth-child(2){display:grid;min-width:0;gap:2px}.quote-component-options small{color:#94a3b8;font-size:9px;font-weight:800}.quote-component-options strong{overflow:hidden;color:inherit;font-size:12px;text-overflow:ellipsis;white-space:nowrap}.quote-component-options button>svg{color:#cbd5e1}.quote-component-options button.active>svg{color:#0d9488}.quote-component-scope>p{margin:0;border-top:1px dashed #99f6e4;padding-top:9px;color:#64748b;font-size:10px;line-height:1.5}
@media(max-width:600px){.quote-component-options{grid-template-columns:1fr}.quote-component-scope-copy{align-items:flex-start}}
</style>
