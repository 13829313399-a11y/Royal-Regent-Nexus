/** Material names from the supplied board specification; contains no prices. */
export const quotePaperMaterialGroups = [
  { label: '单坑（B楞）', names: ['B3B', 'A3B', 'A3A', 'K3A', 'K3K', 'K+K', 'L3H', 'L4H', 'L+L', 'H5H', 'H5A'] },
  { label: '双坑（BC楞）', names: ['B=B', 'A=B', 'A=A', 'B33+B', 'A33+B', 'A33+A', 'K=K', 'K535A', 'H757A', 'L+H+H', 'R+3+R'] },
] as const

export function standardQuotePaperName(name: string) {
  const normalized = name.trim().toUpperCase()
  return quotePaperMaterialGroups.flatMap(group => [...group.names]).find(value => value === normalized)
}
