<script setup lang="ts">
import type { PortalMotifKind } from '@/components/portal/portalPresentation'

/**
 * 七部门低对比刻线纹样。
 *
 * 只做身份装饰，不表达任何业务数据：不含数值刻度、日期、任务点或品牌 Logo。
 * 由使用方置于 `aria-hidden` 且 `pointer-events: none` 的装饰层里。
 */
defineProps<{
  motif: PortalMotifKind
}>()
</script>

<template>
  <svg
    class="portal-motif"
    :data-motif="motif"
    viewBox="0 0 640 240"
    fill="none"
    stroke="currentColor"
    stroke-width="1"
    vector-effect="non-scaling-stroke"
    aria-hidden="true"
    focusable="false"
  >
    <!-- 工程部：错位矩形框 + 转角定位线 + 两条尺寸短线 -->
    <g v-if="motif === 'blueprint'">
      <rect x="150" y="52" width="270" height="112" rx="7" />
      <rect x="286" y="104" width="256" height="104" rx="7" />
      <path d="M150 52h26M150 52v22M406 164h-28M406 164v-20" />
      <path d="M176 186h148M176 179v14M324 179v14" />
      <path d="M452 64h72" opacity="0.6" />
    </g>

    <!-- PMC / 仓管：三组不同长度的叠层框 -->
    <g v-else-if="motif === 'storage'">
      <rect x="178" y="48" width="252" height="58" rx="6" />
      <rect x="216" y="118" width="288" height="58" rx="6" />
      <rect x="256" y="188" width="212" height="46" rx="6" />
      <path d="M178 77h252M216 147h288M256 211h212" opacity="0.55" />
      <path d="M470 48v58M544 118v58" opacity="0.45" />
    </g>

    <!-- 生产部：三条平行导轨，局部短线错位，无数据刻度 -->
    <g v-else-if="motif === 'rail'">
      <path d="M164 76h312M164 130h248M164 184h336" />
      <path d="M496 76h164M432 130h228M520 184h140" opacity="0.6" />
      <path d="M248 62v28M356 116v28M300 170v28" opacity="0.5" />
      <path d="M452 62v28M540 170v28" opacity="0.35" />
    </g>

    <!-- QA 部：两层不完整的圆角轮廓，形成内外检查关系 -->
    <g v-else-if="motif === 'ring'">
      <path d="M300 44h84a40 40 0 0 1 40 40v56a40 40 0 0 1-40 40h-84" />
      <path d="M300 196h-34a40 40 0 0 1-40-40v-56a40 40 0 0 1 40-40h34" />
      <path d="M352 84h54a26 26 0 0 1 26 26v36a26 26 0 0 1-26 26h-54" opacity="0.62" />
      <path d="M248 84h-18a26 26 0 0 0-26 26v36a26 26 0 0 0 26 26h18" opacity="0.62" />
    </g>

    <!-- QC 部：规则方格的一角 + 两组短刻线 -->
    <g v-else-if="motif === 'grid'">
      <path d="M196 46h300v148" />
      <path d="M196 46v148h300" opacity="0.45" />
      <path d="M271 46v148M346 46v148M421 46v148" opacity="0.7" />
      <path d="M196 95h300M196 145h300" opacity="0.7" />
      <path d="M524 60h68M524 76h44" opacity="0.6" />
      <path d="M548 176h44M572 192h20" opacity="0.6" />
    </g>

    <!-- 业务部：两张交错的抽象单据框，短线形成前后关系 -->
    <g v-else-if="motif === 'document'">
      <rect x="216" y="44" width="216" height="150" rx="8" />
      <rect x="336" y="72" width="216" height="150" rx="8" opacity="0.72" />
      <path d="M252 86h120M252 112h144M252 138h96" opacity="0.6" />
      <path d="M372 122h120M372 148h96M372 174h132" opacity="0.45" />
      <path d="M180 60h-24M180 60v24" opacity="0.5" />
    </g>

    <!-- 会计部：竖向账册分栏 + 水平基线，小面积香槟点缀 -->
    <g v-else-if="motif === 'ledger'">
      <rect x="188" y="48" width="304" height="152" rx="7" />
      <path d="M264 48v152M340 48v152M416 48v152" opacity="0.72" />
      <path d="M188 100h304M188 150h304" opacity="0.55" />
      <path class="portal-motif__accent" d="M516 70h84" />
      <path d="M516 190h56" opacity="0.5" />
    </g>

    <!-- 跨厂区工作台：单据流转的前后关系，不带审批结果暗示 -->
    <g v-else>
      <rect x="196" y="72" width="132" height="96" rx="7" />
      <path d="M196 100h132M196 128h96" opacity="0.55" />
      <path d="M336 120h96" opacity="0.5" />
      <path d="M424 114l14 6-14 6" opacity="0.5" />
      <rect x="446" y="72" width="132" height="96" rx="7" />
      <path d="M446 100h132M446 128h96" opacity="0.55" />
      <path d="M352 46h96" opacity="0.4" />
      <path class="portal-motif__accent" d="M520 196h68" />
    </g>
  </svg>
</template>

<style scoped>
.portal-motif {
  display: block;
  width: 100%;
  height: 100%;
}

.portal-motif__accent {
  stroke: var(--portal-champagne);
  opacity: 0.55;
}
</style>
