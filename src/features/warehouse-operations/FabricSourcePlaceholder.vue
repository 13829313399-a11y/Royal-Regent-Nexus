<script setup lang="ts">
import { RouterLink } from 'vue-router'
defineProps<{ mode: 'interface' }>()
</script>
<template>
  <div class="fabric-source-placeholder">
    <span class="fabric-intake-tag">待接入</span><h2>采购接口</h2>
    <p>接收采购已下达的订单、复期和订单变更，统一进入待收料跟进。</p><ol><li>确认采购系统和可读取的订单资料</li><li>对应唯一订单明细、供应商、物料及单位</li><li>检查新增和变更后更新待收料</li><li>仓库另行登记本次实收</li></ol><p class="fabric-message">需要采购系统接口、访问授权及字段样本。采购报到货不会直接增加库存。</p>
    <RouterLink class="fabric-import-link" :to="{ path: '/modules/pmc-warehouse/fabric-warehouse/receipts', query: { factory: 'huakang-c', view: 'import-review' } }">当前使用订单导入</RouterLink>
  </div>
</template>
