import type { AIBusinessResult, AIKnowledgeHit } from '../types'
import {
  boundedInteger,
  hasExactKeys,
  localId,
  record,
  safeLinks,
  text,
} from './contracts'

const RESULT_KEYS = [
  'source_type',
  'result_type',
  'schema_version',
  'authority',
  'conflict_policy',
  'query',
  'evidence_missing',
  'message',
  'hits',
  'truncated',
] as const
const HIT_KEYS = ['score', 'text_markdown', 'citation', 'deep_links'] as const
const CITATION_KEYS = [
  'knowledge_id',
  'version',
  'section_id',
  'source_path',
  'heading',
  'reviewed_at',
  'content_hash',
] as const
const CLOSED_ID = /^[a-z0-9][a-z0-9-]{0,95}$/
const VERSION = /^\d+\.\d+\.\d+$/
const DATE = /^\d{4}-\d{2}-\d{2}$/
const HASH = /^sha256:[a-f0-9]{64}$/

export function isKnowledgeSearchCandidate(value: Record<string, unknown>) {
  return value.schema_version === 'knowledge-search-v1'
    || value.result_type === 'knowledge.search_results'
}

export function extractKnowledgeSearchResult(
  value: Record<string, unknown>,
): AIBusinessResult | null {
  if (
    !hasExactKeys(value, RESULT_KEYS)
    || value.source_type !== 'VERSIONED_MODULE_KNOWLEDGE'
    || value.result_type !== 'knowledge.search_results'
    || value.schema_version !== 'knowledge-search-v1'
    || value.authority !== 'PROCESS_GUIDANCE'
    || value.conflict_policy !== 'FORMAL_TOOL_WINS'
    || typeof value.evidence_missing !== 'boolean'
    || typeof value.truncated !== 'boolean'
    || !Array.isArray(value.hits)
    || value.hits.length > 5
  ) return null

  const query = text(value.query, 200)
  const message = text(value.message, 240)
  if (!message) return null
  const hits: AIKnowledgeHit[] = []
  for (const item of value.hits) {
    const hit = record(item)
    if (!hit || !hasExactKeys(hit, HIT_KEYS)) return null
    const score = boundedInteger(hit.score, 1, 1_000)
    const body = text(hit.text_markdown, 8_000)
    const citation = record(hit.citation)
    if (score === null || !body || !citation || !hasExactKeys(citation, CITATION_KEYS)) {
      return null
    }
    const knowledgeId = text(citation.knowledge_id, 96)
    const version = text(citation.version, 32)
    const sectionId = text(citation.section_id, 80)
    const sourcePath = text(citation.source_path, 255)
    const heading = text(citation.heading, 160)
    const reviewedAt = text(citation.reviewed_at, 10)
    const contentHash = text(citation.content_hash, 71)
    if (
      !CLOSED_ID.test(knowledgeId)
      || !CLOSED_ID.test(sectionId)
      || !VERSION.test(version)
      || !DATE.test(reviewedAt)
      || !HASH.test(contentHash)
      || !sourcePath.startsWith('docs/ai/modules/')
      || !sourcePath.endsWith('.md')
      || !heading
    ) return null
    const rawLinks = Array.isArray(hit.deep_links)
      ? hit.deep_links.map((entry) => {
          const link = record(entry)
          return link ? { label: link.label, route: link.path } : null
        }).filter((entry) => entry !== null)
      : []
    hits.push({
      score,
      textMarkdown: body,
      citation: {
        knowledgeId,
        version,
        sectionId,
        sourcePath,
        heading,
        reviewedAt,
        contentHash,
      },
      links: safeLinks(rawLinks),
    })
  }
  if (value.evidence_missing !== (hits.length === 0)) return null

  return {
    id: localId('knowledge'),
    kind: 'knowledge_search',
    title: query ? `模块知识：${query}` : '当前模块知识',
    summary: message,
    sourceType: 'VERSIONED_MODULE_KNOWLEDGE',
    truncated: value.truncated,
    links: [],
    knowledgeSearch: {
      evidenceMissing: value.evidence_missing,
      conflictPolicy: 'FORMAL_TOOL_WINS',
      hits,
    },
  }
}
