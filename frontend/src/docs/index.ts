// Docs registry. Add a new entry here + a sibling .md file to extend the
// /docs hub. Markdown sources are bundled at build time via Vite ?raw imports
// so there's no runtime fetch.
import metricsSource from './metrics.md?raw'
import howToUseSource from './how-to-use.md?raw'

export interface DocEntry {
  slug: string
  title: string
  source: string
}

export const DOCS: DocEntry[] = [
  { slug: 'metrics', title: 'Metrics & Definitions', source: metricsSource },
  { slug: 'how-to-use', title: 'How to use this platform', source: howToUseSource },
]

export function getDoc(slug: string | undefined): DocEntry {
  return DOCS.find((d) => d.slug === slug) ?? DOCS[0]
}
