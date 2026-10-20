<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { authApi } from '@/api/auth'
const organizations = ref<{id:string;name:string}[]>([])
const points = [[125,196],[568,134],[657,274],[604,407],[152,401],[80,311],[391,459]]
const tracks = [
  'M134 216 232 273 150 320 294 403 395 345',
  'M566 184 637 225 539 282 663 354',
  'M241 136 369 210 544 109',
  'M115 369 187 410 314 337',
  'M457 372 532 415 627 360',
]
let disposed = false
onMounted(async () => { try { const result = await authApi.organizationCatalog(); if (!disposed) organizations.value = result.organizations } catch { /* No invented organization nodes. */ } })
onBeforeUnmount(() => { disposed = true })
</script>
<template>
<aside class="ng-brand" aria-label="华登集团数字化协作平台">
<header class="ng-brand-header"><div class="ng-logo"><img src="/brand/huadeng_group_dynamic_logo_topbar.svg" alt="华登集团" /></div><div class="ng-brand-name"><div class="ng-brand-word">Royal Regent Nexus</div><div class="ng-brand-sub">华登集团 · 数字化协作平台</div></div></header>
<section class="ng-heading"><h2>让每一次协作，<span>从容启程。</span></h2><p>连接集团各厂区与部门，<br>让日常工作在同一平台顺畅开展。</p><span class="ng-rule" aria-hidden="true" /></section>
<div class="ng-art" aria-hidden="true">
   <svg viewBox="0 0 780 500" xmlns="http://www.w3.org/2000/svg">
    <defs>
     <linearGradient id="ng-glass-top" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#82d2b2" stop-opacity=".75"/><stop offset=".42" stop-color="#528c82" stop-opacity=".38"/><stop offset="1" stop-color="#458283" stop-opacity=".09"/></linearGradient>
     <linearGradient id="ng-glass-front" x1="0" y1="0" x2=".8" y2="1"><stop stop-color="#68c998" stop-opacity=".35"/><stop offset=".45" stop-color="#4b8178" stop-opacity=".22"/><stop offset="1" stop-color="#1c564e" stop-opacity=".75"/></linearGradient>
     <linearGradient id="ng-glass-right" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#bde7cb" stop-opacity=".5"/><stop offset=".55" stop-color="#4b807c" stop-opacity=".15"/><stop offset="1" stop-color="#c4a6ee" stop-opacity=".38"/></linearGradient>
     <linearGradient id="ng-edge" x1=".2" y1="0" x2=".8" y2="1"><stop stop-color="#f8f1d3" stop-opacity=".85"/><stop offset=".36" stop-color="#97e2bc" stop-opacity=".7"/><stop offset=".75" stop-color="#72b7a7" stop-opacity=".15"/><stop offset="1" stop-color="#c9bbea" stop-opacity=".75"/></linearGradient>
     <linearGradient id="ng-base" x1="0" y1="0" x2="1" y2=".7"><stop stop-color="#8acaab" stop-opacity=".23"/><stop offset=".5" stop-color="#409d85" stop-opacity=".17"/><stop offset="1" stop-color="#6b93a6" stop-opacity=".07"/></linearGradient>
     <linearGradient id="ng-facet" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#e0f7cf" stop-opacity=".65"/><stop offset=".48" stop-color="#ace4b0" stop-opacity=".06"/><stop offset=".5" stop-color="#b0a4e4" stop-opacity=".3"/><stop offset="1" stop-color="#639c8d" stop-opacity=".04"/></linearGradient>
     <radialGradient id="ng-floor-glow"><stop stop-color="#70d9ac" stop-opacity=".22"/><stop offset=".5" stop-color="#53b587" stop-opacity=".08"/><stop offset="1" stop-color="#53b587" stop-opacity="0"/></radialGradient>
     <linearGradient id="ng-sheen"><stop stop-color="#eeffd8" stop-opacity="0"/><stop offset=".25" stop-color="#eeffd8" stop-opacity=".06"/><stop offset=".48" stop-color="#edffe0" stop-opacity=".34"/><stop offset=".62" stop-color="#e5fbe8" stop-opacity=".22"/><stop offset=".8" stop-color="#beb4f4" stop-opacity=".09"/><stop offset="1" stop-color="#b9f2de" stop-opacity="0"/></linearGradient>
     <linearGradient id="ng-core-light" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#dbffda" stop-opacity="0"/><stop offset=".55" stop-color="#bcffdd" stop-opacity=".18"/><stop offset="1" stop-color="#c7c2f0" stop-opacity="0"/></linearGradient>
     <clipPath id="ng-lower-clip"><path d="M227 255 379 167 558 270 558 297 406 385 227 282Z"/></clipPath>
     <clipPath id="ng-upper-clip"><path d="M264 203 380 136 520 217 520 236 404 303 264 222Z"/></clipPath>
     <clipPath id="ng-portal-clip"><path d="M320 130 392 88 463 130 463 206 391 249 320 208Z"/></clipPath>
     <filter id="ng-soft"><feGaussianBlur stdDeviation="22"/></filter><filter id="ng-shadow"><feGaussianBlur stdDeviation="11"/></filter>
    </defs>
    <ellipse class="ng-floor-light" cx="395" cy="345" rx="283" ry="127" fill="url(#ng-floor-glow)"/>
    <g class="ng-orbit" fill="none" stroke="#83b7a2" stroke-width=".6" opacity=".16"><path d="M12 305 346 112 759 348M26 342 360 149 745 371M41 378 374 185 729 392M64 413 387 227 691 403M107 443 402 273 653 418M144 96 697 415M106 122 658 442M65 149 617 467M27 177 574 493"/><ellipse cx="389" cy="282" rx="325" ry="149" transform="rotate(-10 389 282)"/><ellipse cx="389" cy="282" rx="347" ry="164" transform="rotate(-10 389 282)" stroke-dasharray="2 9"/></g>
    <!-- Rotation is inside the fixed projection; labels never inherit it. -->
    <g class="ng-orbit-travel" transform="translate(389 282) rotate(-10) scale(1 .458)">
     <g class="ng-orbit-spin" fill="none">
      <circle r="325" stroke="#a8e8ca" stroke-width="1.1" stroke-dasharray="55 455" opacity=".35"/>
      <g v-for="angle in [0,90,180,270]" :key="angle" :transform="`rotate(${angle}) translate(325 0)`">
       <ellipse rx="7" ry="11" fill="#9debc1" opacity=".13"/>
       <ellipse rx="2.4" ry="4.5" :fill="angle % 180 ? '#cfbbea' : '#e3efbd'"/>
      </g>
     </g>
    </g>
    <ellipse class="ng-floor-shadow" cx="395" cy="370" rx="161" ry="41" fill="#020f15" opacity=".3" filter="url(#ng-shadow)"/>
    <g class="ng-track-group" fill="none" stroke-width="1">
     <g v-for="(track,index) in tracks" :key="track">
      <path :d="track" stroke="#97beab" opacity=".27"/>
      <path class="ng-ray" :d="track" pathLength="100" stroke="#d8eec3" stroke-width="1.6" :style="{ animationDelay: `${index * -1.6}s`, animationDuration: `${7 + index * .6}s` }"/>
     </g>
    </g>
    <g class="ng-crystal" stroke-linejoin="round">
     <g class="ng-base-layer">
     <path d="M175 318 373 204 602 336 403 451Z" fill="#438f7910" stroke="#b1ddad" stroke-opacity=".22"/>
     <path d="M202 311 375 211 576 327 402 428 202 312V320L402 436 576 335V327" fill="url(#ng-base)" stroke="#8fc2a9" stroke-opacity=".24"/>
     <path d="M214 310 376 217 561 324 401 417Z" fill="none" stroke="#94b790" stroke-opacity=".25"/>
     <path d="M253 307 376 236 521 320 399 390Z" fill="#a3ffd026" filter="url(#ng-soft)"/>
     <path class="ng-base-rim" d="M214 310 376 217 561 324 401 417Z" fill="none" stroke="#b7ead0" stroke-width="1.1" pathLength="100"/>
     </g>
     <!-- Layered industrial light plates; this artwork is not the group trademark. -->
     <g class="ng-float-layer ng-lower-layer">
     <path d="M227 255 379 167 558 270 406 358Z" fill="url(#ng-glass-top)" stroke="url(#ng-edge)" stroke-width="1"/>
     <path d="M227 255 406 358 406 385 227 282Z" fill="url(#ng-glass-front)" stroke="#76bfa4" stroke-opacity=".32"/>
     <path d="M406 358 558 270 558 297 406 385Z" fill="url(#ng-glass-right)" stroke="#adb3d4" stroke-opacity=".4"/>
     <path d="M239 255 379 174 546 270 406 351Z" fill="none" stroke="#d9edbf" stroke-opacity=".25"/>
     <path d="m238 280 168 97 141-82" fill="none" stroke="#91d2b0" stroke-opacity=".45"/>
     <path d="m227 255 179 103 152-88" fill="none" stroke="#d7ecd2" stroke-opacity=".6" stroke-width="1.3"/>
     <path d="m247 268 132-77 148 85-121 70" fill="none" stroke="#83e6bd" stroke-opacity=".3" stroke-width=".8"/>
     <g clip-path="url(#ng-lower-clip)"><rect class="ng-glass-sheen" x="-70" y="130" width="250" height="280" fill="url(#ng-sheen)"/></g>
     <g stroke="#97d1b4" stroke-width=".6" opacity=".35"><path d="M439 326l7-4m-1 7 7-4m-1 7 7-4m-1 7 7-4m-1 7 7-4"/></g>
     <g fill="#d8f1c9"><circle cx="227" cy="255" r="1.5"/><circle cx="406" cy="358" r="1.7"/></g>
     </g>
     <g class="ng-float-layer ng-upper-layer">
     <path d="M264 203 380 136 520 217 404 284Z" fill="url(#ng-glass-top)" stroke="url(#ng-edge)" stroke-width="1"/>
     <path d="M264 203 404 284 404 303 264 222Z" fill="url(#ng-glass-front)" stroke="#acddae" stroke-opacity=".28"/>
     <path d="M404 284 520 217 520 236 404 303Z" fill="url(#ng-glass-right)" stroke="#c2cae0" stroke-opacity=".45"/>
     <path d="M274 203 381 141 510 217 404 278Z" fill="none" stroke="#e6e3c3" stroke-opacity=".5"/>
     <path d="M264 203 404 284 520 217" fill="none" stroke="#d6f7cf" stroke-width="1.4" stroke-opacity=".75"/>
     <g clip-path="url(#ng-upper-clip)"><rect class="ng-glass-sheen" x="-70" y="110" width="250" height="220" fill="url(#ng-sheen)"/></g>
     <g stroke="#97d1b4" stroke-width=".6" opacity=".35"><path d="M278 242 287 247m-2-9 9 5m-2-9 9 5m-2-9 9 5m-2-9 9 5m-2-9 9 5"/></g>
     <circle cx="404" cy="284" r="1.8" fill="#d8f1c9"/>
     </g>
     <!-- A faceted open portal, light passing through its core. -->
     <g class="ng-float-layer ng-portal-layer">
     <path d="M320 130 392 88 463 130 391 173Z" fill="url(#ng-facet)" stroke="#d9ead0" stroke-opacity=".7"/>
     <path d="M320 130 391 173 391 249 320 208Z" fill="url(#ng-glass-front)" stroke="#a7dcb9" stroke-opacity=".6"/>
     <path d="M391 173 463 130 463 206 391 249Z" fill="url(#ng-glass-right)" stroke="#c9cff0" stroke-opacity=".65"/>
     <path d="M343 136 392 107 440 136 391 165Z" fill="#082f30" stroke="#b4d9b2" stroke-opacity=".6"/>
     <path d="M343 136 343 183 391 211 391 165Z" fill="#477b6045" stroke="#94d2ad" stroke-opacity=".36"/>
     <path d="M391 165 440 136 440 183 391 211Z" fill="#b4c5bc17" stroke="#cedccb" stroke-opacity=".3"/>
     <path d="M343 183 392 155 440 183 391 211Z" fill="url(#ng-glass-top)" stroke="#a8d7b8" stroke-opacity=".4"/>
     <path class="ng-core-glow" d="M359 125 392 105 425 125 425 204 392 224 359 204Z" fill="url(#ng-core-light)"/>
     <path d="m320 130 71 43 72-43M391 173v76" fill="none" stroke="#e5f7d2" stroke-width="1.5" stroke-opacity=".8"/>
     <path d="m320 130 72-42 71 42" fill="none" stroke="#ecf3ce" stroke-width="1.5" stroke-opacity=".85"/>
     <path d="m463 132 0 74-72 43" fill="none" stroke="#b8aadf" stroke-width="1.7" stroke-opacity=".7"/>
     <path d="m320 131 0 77 71 41" fill="none" stroke="#a9e7b0" stroke-width="1.2" stroke-opacity=".6"/>
     <g clip-path="url(#ng-portal-clip)"><rect class="ng-glass-sheen" x="-70" y="70" width="250" height="200" fill="url(#ng-sheen)"/></g>
     <g fill="#d8f1c9"><circle cx="320" cy="130" r="2"/><circle cx="391" cy="249" r="1.6"/></g>
     </g>
    </g>
    <g class="ng-node-group">
     <!-- Keep SVG placement separate: a CSS transform on this outer group replaces translate(). -->
     <g v-for="(org,index) in organizations.slice(0,7)" :key="org.id" class="ng-org-position" :transform="`translate(${points[index]?.[0]},${points[index]?.[1]})`">
      <g class="ng-dot" :style="{ animationDelay: `${index * 20}ms`, '--ng-node-phase': `${index * -.8}s` }">
       <path d="m0 -11 20 11-20 12-20-12Z" fill="#86bc9912" stroke="#abd7b5" stroke-opacity=".25"/>
       <g class="ng-node-pulse"><ellipse class="ng-node-halo" rx="9" ry="5.2"/><circle class="ng-node-signal" r="4.8"/></g>
       <circle class="ng-org-node" r="2.2"/>
       <text class="ng-org-label" y="-24" text-anchor="middle">{{ org.name }}</text>
      </g>
     </g>
    </g></svg></div>
<footer class="ng-brand-footer"><span class="ng-caption">组织协同示意</span><span>华登集团</span></footer>
</aside>
</template>
