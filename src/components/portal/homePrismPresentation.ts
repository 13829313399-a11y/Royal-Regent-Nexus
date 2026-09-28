import { BookOpen, Boxes, Cog, DraftingCompass, ScanLine, ShieldCheck, FileText, LayoutDashboard } from '@lucide/vue'
import type { Component } from 'vue'
import type { ModuleDepartmentId } from '@/data/enterpriseMock'

export type HomeIdentity = ModuleDepartmentId | 'dashboard'
interface HomePalette { accent: string; soft: string; light: string; icon: Component }
export const homePrismPresentation: Record<HomeIdentity, HomePalette> = {
  dashboard: { accent: '#075D50', soft: '#E7F2ED', light: '#67C7B1', icon: LayoutDashboard },
  engineering: { accent: '#2366A8', soft: '#EAF2FC', light: '#65BFE4', icon: DraftingCompass },
  'pmc-warehouse': { accent: '#236C60', soft: '#E8F4EC', light: '#83C6A4', icon: Boxes },
  production: { accent: '#0F766E', soft: '#E5F5F2', light: '#60D4C5', icon: Cog },
  qa: { accent: '#6D5299', soft: '#F0ECF8', light: '#B7A2DF', icon: ShieldCheck },
  qc: { accent: '#176D83', soft: '#E7F3F8', light: '#65C5D9', icon: ScanLine },
  'sales-business': { accent: '#6559B1', soft: '#EEEFFA', light: '#AFAAE8', icon: FileText },
  accounting: { accent: '#796129', soft: '#F7F1E4', light: '#D9C594', icon: BookOpen },
}
export function homePaletteStyle(identity: HomeIdentity) {
  const palette = homePrismPresentation[identity]
  return { '--home-accent': palette.accent, '--home-soft': palette.soft, '--home-light': palette.light }
}
