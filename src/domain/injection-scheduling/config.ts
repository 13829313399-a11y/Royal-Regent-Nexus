import type { ColorFamily, MachineClass } from '@/types/injectionScheduling'

export const moldChangeHoursByMachineClass: Partial<Record<MachineClass, number>> = {
  '5A': 0.72,
  '7A': 0.84,
  '12A': 1.08,
  '14A': 1.44,
  '18A': 1.44,
  '24A': 1.68,
  '32A': 2.04,
  '60A': 2.4,
  '80A': 3.24,
  '104A': 3.96,
  '120A': 4.8,
}

export const colorChangeHoursByMachineClass: Partial<Record<MachineClass, number>> = {
  '5A': 0.408,
  '7A': 0.408,
  '12A': 0.6,
  '14A': 0.6,
  '18A': 0.6,
  '24A': 0.804,
  '32A': 0.804,
  '60A': 1.008,
  '80A': 1.2,
  '104A': 1.2,
  '120A': 1.308,
}

export const colorFamilyRank: Record<Exclude<ColorFamily, 'special'>, number> = {
  natural: 0,
  light: 1,
  medium: 2,
  dark: 3,
  black: 4,
}

export const schedulingScoreWeights = {
  urgency: 26,
  overdueRisk: 26,
  sameMold: 18,
  colorPath: 10,
  sameMaterial: 8,
  rightSizedMachine: 7,
  loadBalance: 5,
} as const

export const defaultDownstreamBufferHours = 72
