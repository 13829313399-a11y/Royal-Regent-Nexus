<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
import type { HomeIdentity } from './homePrismPresentation'
import { useHomeAppearance } from '@/composables/useHomeAppearance'
defineProps<{ identity: HomeIdentity }>()
const id = useId().replace(/:/g, '')
const surface = ref<HTMLElement | null>(null)
const { effectiveMotion } = useHomeAppearance()
let host: HTMLElement | null = null
let frame = 0
let pointer: MediaQueryList | undefined
function reset() {
  cancelAnimationFrame(frame); frame = 0
  surface.value?.style.setProperty('--art-x', '0px')
  surface.value?.style.setProperty('--art-y', '0px')
}
function move(event: PointerEvent) {
  if (effectiveMotion.value !== 'expressive' || !pointer?.matches || frame) return
  frame = requestAnimationFrame(() => {
    frame = 0
    if (!host) return
    const rect = host.getBoundingClientRect()
    surface.value?.style.setProperty('--art-x', `${Math.max(-6, Math.min(6, (event.clientX - rect.left) / rect.width * 12 - 6))}px`)
    surface.value?.style.setProperty('--art-y', `${Math.max(-6, Math.min(6, (event.clientY - rect.top) / rect.height * 12 - 6))}px`)
  })
}
onMounted(() => {
  host = surface.value?.closest('.portal-hero, .dashboard-hero') ?? null
  pointer = window.matchMedia?.('(hover: hover) and (pointer: fine) and (min-width: 1024px)')
  pointer?.addEventListener('change', reset)
  host?.addEventListener('pointermove', move)
  host?.addEventListener('pointerleave', reset)
})
watch(effectiveMotion, reset)
onBeforeUnmount(() => { reset(); pointer?.removeEventListener('change', reset); host?.removeEventListener('pointermove', move); host?.removeEventListener('pointerleave', reset) })
</script>
<template>
  <div ref="surface" class="home-artwork" aria-hidden="true">
    <svg :key="identity" :data-artwork="identity" viewBox="0 0 640 240" fill="none" focusable="false">
      <defs>
        <linearGradient :id="`${id}-glass`" x1="270" y1="20" x2="530" y2="240" gradientUnits="userSpaceOnUse"><stop stop-color="var(--home-light)" stop-opacity=".65" /><stop offset="1" stop-color="var(--home-light)" stop-opacity=".06" /></linearGradient>
        <linearGradient :id="`${id}-edge`" x1="250" y1="10" x2="600" y2="220" gradientUnits="userSpaceOnUse"><stop stop-color="#ECFFFA" stop-opacity=".9" /><stop offset=".55" stop-color="var(--home-light)" stop-opacity=".65" /><stop offset="1" stop-color="var(--home-light)" stop-opacity=".1" /></linearGradient>
        <pattern :id="`${id}-grid`" width="22" height="22" patternUnits="userSpaceOnUse"><path d="M22 0H0V22" stroke="var(--home-light)" stroke-opacity=".2" stroke-width=".6" /></pattern>
      </defs>
      <g class="home-artwork__back" stroke="var(--home-light)" opacity=".3"><path d="M250 210H610M290 225H590M310 15H610" /><path d="M604 22V44M593 33H615M262 177V193M254 185H270" /></g>
      <g v-if="identity === 'engineering'" :stroke="`url(#${id}-edge)`" stroke-width="1.3">
        <g class="home-artwork__back"><path d="M350 18 592 58 550 183 308 143Z" :fill="`url(#${id}-glass)`" /><path d="M368 33 570 68 539 165 337 131Z" /><path d="M402 37 371 137M446 46 414 145M490 53 458 153M536 63 502 160M351 90 555 125" opacity=".4" /></g>
        <g class="home-artwork__front"><path d="M308 73 554 113 510 224 264 184Z" fill="#103F49" fill-opacity=".85" /><path d="M308 63 554 103 510 214 264 174Z" :fill="`url(#${id}-glass)`" /><path d="M343 89 473 110 446 179 316 158Z" /><path d="M359 103 441 117 424 163 342 150Z" /><path d="M325 116 458 138M389 96 361 169M495 114 528 120M489 130 522 136M483 146 516 152" /><path d="M280 158 289 135 299 137M319 74 309 72 303 87M490 198 500 200 506 185" stroke="#F1D6A1" stroke-width="2" /></g>
        <g class="home-artwork__trace" stroke="#D9C594"><path d="M278 191 502 228M279 186 276 196M503 223 500 233M570 106 532 210M565 105 575 107M527 209 537 211" /></g>
      </g>
      <g v-else-if="identity === 'pmc-warehouse'" :stroke="`url(#${id}-edge)`" stroke-linejoin="round">
        <g v-for="(y, index) in [28, 87, 146]" :key="y" :class="index === 2 ? 'home-artwork__front' : 'home-artwork__back'" :transform="`translate(0 ${y})`">
          <path d="M280 20 450 0 595 39 425 60Z" :fill="`url(#${id}-glass)`" /><path d="M280 20V49L425 89V60M425 89 595 68V39" fill="#75B99C" fill-opacity=".18" /><path d="M304 21 449 5 568 38 423 55Z" stroke-opacity=".3" /><path d="M447 66 479 62" stroke="#E3CEA4" stroke-width="5" /><path d="M491 59V72M497 58V71M505 57V70M510 56V69M517 55V68M525 54V67" stroke-opacity=".7" /><path d="M301 38 326 45M337 48 365 55M376 58 403 65" />
        </g>
      </g>
      <g v-else-if="identity === 'production'" :stroke="`url(#${id}-edge)`" stroke-linejoin="round">
        <g class="home-artwork__back"><path v-for="y in [40, 92, 144]" :key="y" :d="`M265 ${y+45} 535 ${y-15} 610 ${y+12} 340 ${y+72}Z`" :fill="`url(#${id}-glass)`" /><path d="M278 91 547 32M302 103 571 44M278 143 547 84M302 155 571 96M278 195 547 136M302 207 571 148" /></g>
        <g class="home-artwork__front"><path d="M382 45 475 24 475 161 382 182Z" :fill="`url(#${id}-glass)`" /><path d="M399 62 458 49V139L399 152Z" /><ellipse cx="429" cy="98" rx="19" ry="29" transform="rotate(16 429 98)" /><path d="M382 45 400 52V192L382 182M475 24 493 32V172L400 192" /><path d="M511 126 560 115V150L511 161Z" fill="#E3CEA4" fill-opacity=".3" /></g>
        <path class="home-artwork__trace" d="M267 195 373 172" stroke="#B8FFF0" stroke-width="3" />
      </g>
      <g v-else-if="identity === 'qa'" :stroke="`url(#${id}-edge)`">
        <g class="home-artwork__back" transform="translate(19 -15)"><path d="M521 56C475 12 376 20 339 82S342 192 407 205 553 180 562 123" stroke-width="25" stroke-opacity=".25" /><path d="M521 56C475 12 376 20 339 82S342 192 407 205 553 180 562 123" stroke-width="1.5" /></g>
        <g class="home-artwork__front"><path d="M529 72C482 23 389 34 357 88S353 180 414 193 544 171 551 123" stroke="var(--home-light)" stroke-opacity=".4" stroke-width="24" /><path d="M529 72C482 23 389 34 357 88S353 180 414 193 544 171 551 123" stroke-width="2" /><path d="M409 113 437 141 491 86" stroke="#F1D6A1" stroke-width="5" stroke-linecap="round" stroke-linejoin="round" /><circle cx="446" cy="117" r="61" stroke-dasharray="2 12" /></g>
        <g class="home-artwork__trace" stroke="#D9C594"><path d="M311 75H342M314 151H337M560 84H596M559 164H587" /><circle cx="589" cy="164" r="3" /></g>
      </g>
      <g v-else-if="identity === 'qc'" :stroke="`url(#${id}-edge)`">
        <g class="home-artwork__back"><path d="M334 25H570V191H334Z" :fill="`url(#${id}-grid)`" /><path d="M346 14V5M368 14V8M390 14V5M412 14V8M434 14V5M456 14V8M478 14V5M500 14V8M522 14V5M544 14V8M566 14V5" /></g>
        <g class="home-artwork__front"><rect x="294" y="58" width="240" height="163" rx="12" :fill="`url(#${id}-glass)`" /><path d="M310 86V74H331M497 74H518V86M310 192V204H331M497 204H518V192" stroke-width="2" /><path d="M333 101H497M333 135H497M333 169H497M363 92V184M397 92V184M431 92V184M465 92V184" opacity=".5" /><circle cx="430" cy="135" r="33" stroke="#D9C594" /><path d="M453 159 482 188M418 134 428 144 445 124" stroke="#D9C594" stroke-width="3" /></g>
        <path class="home-artwork__scan" d="M306 108H520" stroke="#C4F5FF" stroke-width="2" />
      </g>
      <g v-else-if="identity === 'sales-business'" :stroke="`url(#${id}-edge)`" stroke-linejoin="round">
        <g class="home-artwork__back"><path d="M389 18 587 53 558 210 360 175Z" :fill="`url(#${id}-glass)`" /><path d="M352 25 550 60 521 218 323 183Z" fill="#6559B1" fill-opacity=".35" /></g>
        <g class="home-artwork__front"><path d="M308 24 453 50 489 103 466 226 273 192Z" fill="#304F69" /><path d="M308 24 453 50 489 103 466 226 273 192Z" :fill="`url(#${id}-glass)`" /><path d="M453 50 445 94 489 103" fill="#C1BFEC" fill-opacity=".4" /><path d="M324 64 406 79M318 95 391 108M312 126 450 150M307 151 444 175M302 176 372 188" /><path d="M324 64 406 79" stroke="#D9C594" stroke-width="4" /><path d="M389 198 425 204 446 187" stroke="#D9C594" stroke-width="2" /></g>
      </g>
      <g v-else-if="identity === 'accounting'" :stroke="`url(#${id}-edge)`" stroke-linejoin="round">
        <g class="home-artwork__back"><path d="M290 49 425 22 579 53V211L425 182 290 213Z" fill="#D9C594" fill-opacity=".15" /><path d="M290 49V213L425 182 579 211M302 217 425 190 579 217" /></g>
        <g class="home-artwork__front"><path d="M285 34 420 10 573 40V197L420 169 285 199Z" :fill="`url(#${id}-glass)`" /><path d="M420 10V169" stroke="#EBDDAB" stroke-width="3" /><path v-for="y in [66, 92, 118, 144, 170]" :key="y" :d="`M302 ${y} 400 ${y-18}M441 ${y-14} 551 ${y+6}`" stroke-opacity=".6" /><path d="M335 51V178M471 39V173M523 48V184" stroke-opacity=".35" /><path d="M314 39 381 27M443 28 540 47" stroke="#F0DBAB" stroke-width="3" /></g>
      </g>
      <g v-else :stroke="`url(#${id}-edge)`" stroke-linejoin="round">
        <g class="home-artwork__back"><path d="M339 28 500 10 601 84 440 105Z" :fill="`url(#${id}-glass)`" /><path d="M306 66 467 48 568 122 407 143Z" fill="#2366A8" fill-opacity=".3" /></g>
        <g class="home-artwork__front"><path d="M270 106 431 87 534 162 373 184Z" :fill="`url(#${id}-glass)`" /><path d="M270 106V126L373 204 534 182V162M373 184V204" fill="#67C7B1" fill-opacity=".18" /><path d="M309 112 420 100 496 154 384 169Z" /><path d="M362 106 438 162M336 133 455 119" /><path d="M495 191 555 182V145M286 166V185L336 222" stroke="#D9C594" stroke-width="2" /></g>
        <path class="home-artwork__trace" d="M354 39 490 25 580 87M328 78 459 65 546 125" stroke="#D9C594" />
      </g>
    </svg>
  </div>
</template>
