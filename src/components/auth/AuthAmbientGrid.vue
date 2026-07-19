<script setup lang="ts">
import { computed } from 'vue'

type AuthAmbientGridVariant = 'login' | 'register'
type AmbientCellAnchor = 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right'
type AmbientCellAccent = 'teal' | 'blue'

interface AmbientCellConfig {
  id: string
  anchor: AmbientCellAnchor
  column: number
  row: number
  delaySeconds: number
  durationSeconds: number
  strength: number
  accent?: AmbientCellAccent
}

const props = defineProps<{
  variant: AuthAmbientGridVariant
}>()

const loginCells: readonly AmbientCellConfig[] = [
  { id: 'login-near-north-east', anchor: 'top-right', column: 1, row: 1, delaySeconds: 0, durationSeconds: 18, strength: 0.76 },
  { id: 'login-upper-east', anchor: 'top-right', column: 0, row: 4, delaySeconds: -2, durationSeconds: 18, strength: 0.88 },
  { id: 'login-middle-east', anchor: 'top-right', column: 0, row: 8, delaySeconds: -4, durationSeconds: 18, strength: 0.72 },
  { id: 'login-lower-east', anchor: 'bottom-right', column: 1, row: 1, delaySeconds: -6, durationSeconds: 18, strength: 0.84 },
  { id: 'login-lower-inner-east', anchor: 'bottom-right', column: 4, row: 3, delaySeconds: -8, durationSeconds: 18, strength: 0.68 },
  { id: 'login-lower-west', anchor: 'bottom-left', column: 1, row: 2, delaySeconds: -10, durationSeconds: 18, strength: 0.8 },
  { id: 'login-south-west', anchor: 'bottom-left', column: 4, row: 1, delaySeconds: -12, durationSeconds: 18, strength: 0.7 },
  { id: 'login-middle-west', anchor: 'top-left', column: 0, row: 7, delaySeconds: -14, durationSeconds: 18, strength: 0.9 },
  { id: 'login-south-inner', anchor: 'bottom-left', column: 9, row: 0, delaySeconds: -16, durationSeconds: 18, strength: 0.74 },
]

const registerCells: readonly AmbientCellConfig[] = [
  { id: 'register-upper-east', anchor: 'top-right', column: 0, row: 3, delaySeconds: 0, durationSeconds: 21, strength: 0.66 },
  { id: 'register-middle-east', anchor: 'top-right', column: 1, row: 10, delaySeconds: -3.5, durationSeconds: 21, strength: 0.74, accent: 'blue' },
  { id: 'register-lower-east', anchor: 'bottom-right', column: 0, row: 5, delaySeconds: -7, durationSeconds: 21, strength: 0.62 },
  { id: 'register-lower-west', anchor: 'bottom-left', column: 0, row: 4, delaySeconds: -10.5, durationSeconds: 21, strength: 0.7 },
  { id: 'register-south-inner', anchor: 'bottom-left', column: 3, row: 1, delaySeconds: -14, durationSeconds: 21, strength: 0.64, accent: 'blue' },
  { id: 'register-middle-inner', anchor: 'top-left', column: 7, row: 11, delaySeconds: -17.5, durationSeconds: 21, strength: 0.76 },
]

const cells = computed(() => props.variant === 'login' ? loginCells : registerCells)

function getGridLine(offset: number, fromEnd: boolean) {
  return String(fromEnd ? -(offset + 2) : offset + 1)
}

function getCellStyle(cell: AmbientCellConfig) {
  const fromRight = cell.anchor.endsWith('right')
  const fromBottom = cell.anchor.startsWith('bottom')

  return {
    '--ambient-grid-column': getGridLine(cell.column, fromRight),
    '--ambient-grid-row': getGridLine(cell.row, fromBottom),
    '--ambient-delay': `${cell.delaySeconds}s`,
    '--ambient-duration': `${cell.durationSeconds}s`,
    '--ambient-strength': String(cell.strength),
    '--ambient-rise-opacity': String(Number((cell.strength * 0.65).toFixed(3))),
    '--ambient-fall-opacity': String(Number((cell.strength * 0.72).toFixed(3))),
  }
}
</script>

<template>
  <div
    class="auth-ambient-grid"
    :class="`auth-ambient-grid--${variant}`"
    :data-candidate-count="cells.length"
    :data-variant="variant"
    aria-hidden="true"
  >
    <span class="auth-ambient-grid__base" aria-hidden="true"></span>

    <span class="auth-ambient-grid__cells" aria-hidden="true">
      <span
        v-for="cell in cells"
        :key="cell.id"
        class="auth-ambient-grid__cell"
        :class="[
          `auth-ambient-grid__cell--${cell.anchor}`,
          `auth-ambient-grid__cell--${cell.accent ?? 'teal'}`,
        ]"
        :data-cell-id="cell.id"
        :style="getCellStyle(cell)"
        aria-hidden="true"
      ></span>
    </span>

    <span class="auth-ambient-grid__edge-fade" aria-hidden="true"></span>
  </div>
</template>

<style scoped>
.auth-ambient-grid {
  --ambient-grid-size: 46px;
  position: absolute;
  inset: 0;
  z-index: 1;
  overflow: hidden;
  contain: layout paint style;
  pointer-events: none;
  user-select: none;
}

.auth-ambient-grid--register {
  --ambient-grid-size: 42px;
}

.auth-ambient-grid__base,
.auth-ambient-grid__cells,
.auth-ambient-grid__edge-fade {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.auth-ambient-grid__cells {
  display: grid;
  grid-template-columns: repeat(auto-fill, var(--ambient-grid-size));
  grid-template-rows: repeat(auto-fill, var(--ambient-grid-size));
  align-content: start;
  justify-content: start;
}

.auth-ambient-grid__base {
  background-image:
    linear-gradient(rgb(255 255 255 / 3.5%) 1px, transparent 1px),
    linear-gradient(90deg, rgb(255 255 255 / 3.5%) 1px, transparent 1px);
  background-size: var(--ambient-grid-size) var(--ambient-grid-size);
}

.auth-ambient-grid--register .auth-ambient-grid__base {
  background-image:
    linear-gradient(rgb(255 255 255 / 3%) 1px, transparent 1px),
    linear-gradient(90deg, rgb(255 255 255 / 3%) 1px, transparent 1px);
}

.auth-ambient-grid__cell {
  position: relative;
  grid-column: var(--ambient-grid-column);
  grid-row: var(--ambient-grid-row);
  width: calc(var(--ambient-grid-size) - 2px);
  height: calc(var(--ambient-grid-size) - 2px);
  margin: 1px;
  border: 1px solid rgb(45 212 191 / 22%);
  background: rgb(20 184 166 / 8%);
  box-shadow: inset 0 0 12px rgb(45 212 191 / 3%), 0 0 12px rgb(13 148 136 / 4%);
  opacity: 0;
  transform: translate3d(0, 1px, 0) scale(0.995);
  animation: auth-ambient-cell-pulse var(--ambient-duration) ease-in-out infinite;
  animation-delay: var(--ambient-delay);
  will-change: opacity, transform;
}

.auth-ambient-grid__cell--blue {
  border-color: rgb(96 165 250 / 18%);
  background: rgb(59 130 246 / 6%);
  box-shadow: inset 0 0 12px rgb(96 165 250 / 2.5%), 0 0 12px rgb(59 130 246 / 3%);
}

.auth-ambient-grid__edge-fade {
  background: radial-gradient(ellipse at center, transparent 44%, rgb(2 6 23 / 24%) 100%);
}

.auth-ambient-grid--register .auth-ambient-grid__edge-fade {
  background: radial-gradient(ellipse at 48% 52%, transparent 38%, rgb(2 6 23 / 30%) 100%);
}

@keyframes auth-ambient-cell-pulse {
  0%,
  100% {
    opacity: 0;
    transform: translate3d(0, 1px, 0) scale(0.995);
  }

  4% {
    opacity: var(--ambient-rise-opacity);
    transform: translate3d(0, 0, 0) scale(1.005);
  }

  7% {
    opacity: var(--ambient-strength);
    transform: translate3d(0, 0, 0) scale(1.01);
  }

  10% {
    opacity: var(--ambient-fall-opacity);
    transform: translate3d(1px, 0, 0) scale(1.005);
  }

  14% {
    opacity: 0;
    transform: translate3d(1px, 0, 0) scale(1);
  }
}

@media (max-height: 940px) {
  .auth-ambient-grid__cell:is(
    [data-cell-id='login-lower-east'],
    [data-cell-id='login-lower-inner-east'],
    [data-cell-id='login-lower-west'],
    [data-cell-id='login-south-west'],
    [data-cell-id='login-south-inner']
  ) {
    display: none;
    animation: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .auth-ambient-grid__cell {
    animation: none !important;
    opacity: 0;
    transform: none !important;
    will-change: auto;
  }
}
</style>
