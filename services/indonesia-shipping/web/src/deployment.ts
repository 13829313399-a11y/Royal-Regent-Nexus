export function nexusBase(): string | null {
  if (typeof document === 'undefined') return null
  return document.querySelector<HTMLMetaElement>('meta[name="nexus-shipping-base"]')?.content.replace(/\/$/, '') || null
}

export function publicBase(baseUrl: string): string {
  return nexusBase() ?? baseUrl.replace(/\/$/, '')
}

export function apiBase(baseUrl: string): string {
  return `${publicBase(baseUrl)}/api`
}

export function publicAsset(baseUrl: string, fileName: string): string {
  return `${publicBase(baseUrl)}/${fileName.replace(/^\/+/, '')}`
}

export function nexusFactory(): string {
  return nexusBase()?.match(/^\/api\/indonesia-shipping\/([^/]+)\/app$/)?.[1] || ''
}

export function nexusBusinessUrl(): string {
  const factory = nexusFactory()
  return '/modules/sales-business' + (factory ? `?factory=${encodeURIComponent(factory)}` : '')
}

export function nexusFactoryName(): string {
  return ({ 'huakang-a': '华康A', 'huakang-b': '华康B', 'huakang-c': '华康C', 'huakang-d': '华康D', huadeng: '华登', huaxing: '华兴' } as Record<string, string>)[nexusFactory()] || '未选择厂区'
}
