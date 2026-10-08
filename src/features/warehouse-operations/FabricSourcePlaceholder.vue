<script setup lang="ts">
import { RouterLink } from 'vue-router'
defineProps<{ mode: 'scan' | 'interface' }>()
</script>
<template>
  <div class="fabric-source-placeholder">
    <span class="fabric-intake-tag">待接入</span><h2>{{ mode === 'scan' ? '送货单扫描' : '采购接口' }}</h2>
    <template v-if="mode === 'scan'"><p>扫描供应商送货单，匹配待收物料，再由仓库核实实物后登记入库。</p><ol><li>上传送货单照片或扫描条码</li><li>核对供应商、采购单、物料、数量及单位</li><li>填写实际仓位；布料补齐缸号</li><li>确认本次实收并入库</li></ol><p class="fabric-message">照片识别需要送货单样张；条码扫描需要明确编码内容和对应资料。识别结果须核对后使用。</p></template>
    <template v-else><p>接收采购已下达的订单、复期和订单变更，统一进入待收料跟进。</p><ol><li>确认采购系统和可读取的订单资料</li><li>对应唯一订单明细、供应商、物料及单位</li><li>检查新增和变更后更新待收料</li><li>仓库另行登记本次实收</li></ol><p class="fabric-message">需要采购系统接口、访问授权及字段样本。采购报到货不会直接增加库存。</p></template>
    <RouterLink class="fabric-import-link" :to="{ path: '/modules/pmc-warehouse/fabric-warehouse/receipts', query: { factory: 'huakang-c', view: 'import-review' } }">当前使用订单导入</RouterLink>
  </div>
</template>
