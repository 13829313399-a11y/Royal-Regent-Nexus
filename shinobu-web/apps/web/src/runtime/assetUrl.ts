/** Keep the standalone app and the rr subdirectory build on their own assets. */
export function assetUrl(path: string): string {
  return `${import.meta.env.BASE_URL ?? '/'}${path.replace(/^\/+/, '')}`;
}
