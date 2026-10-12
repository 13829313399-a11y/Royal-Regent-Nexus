<script setup lang="ts">
import { RouterLink } from 'vue-router'
defineProps<{ mode: 'scan' | 'interface' }>()
</script>
<template>
  <div class="fabric-source-placeholder">
    <span class="fabric-intake-tag">{{ mode === 'scan' ? '独立模块已启用' : '待接入' }}</span><h2>{{ mode === 'scan' ? '送货单扫描' : '采购接口' }}</h2>
    <template v-if="mode === 'scan'"><p>供应商拖入自己的送货文档，核对统一明细后生成交接二维码；仓库扫码办理本次实际收发。</p><ol><li>在制单模块发放供应商或车间的专用链接</li><li>上传原单，核对物料编码、数量、单位和缸号</li><li>确认生成二维码，仓库扫码勾选本次实物数量</li><li>选择实际仓位或出库批次，确认后更新本仓库存</li></ol><p class="fabric-message">支持不同版式的 Excel、DOCX、PDF 和照片。扫码实收不更新采购来源追货进度，请勿在采购收料页重复登记同一批实物。</p><RouterLink class="fabric-import-link" to="/modules/pmc-warehouse/material-handover?factory=huakang-c&tab=scan">打开制单与扫码交接</RouterLink></template>
    <template v-else><p>接收采购已下达的订单、复期和订单变更，统一进入待收料跟进。</p><ol><li>确认采购系统和可读取的订单资料</li><li>对应唯一订单明细、供应商、物料及单位</li><li>检查新增和变更后更新待收料</li><li>仓库另行登记本次实收</li></ol><p class="fabric-message">需要采购系统接口、访问授权及字段样本。采购报到货不会直接增加库存。</p></template>
    <RouterLink v-if="mode === 'interface'" class="fabric-import-link" :to="{ path: '/modules/pmc-warehouse/fabric-warehouse/receipts', query: { factory: 'huakang-c', view: 'import-review' } }">当前使用订单导入</RouterLink>
  </div>
</template>
