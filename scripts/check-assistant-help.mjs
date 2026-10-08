import { readFileSync, readdirSync, existsSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const directory = path.join(root, 'shared/assistant-help/modules')
const sources = ['src/router/index.ts', 'src/features/uv-operations/routes.ts', 'src/features/spray-production/routes.ts'].map(file => readFileSync(path.join(root,file),'utf8')).join('\n')
const ids = new Set(), issues = [], partial = []
for (const file of readdirSync(directory).filter(f => f.endsWith('.json'))) {
  for (const article of JSON.parse(readFileSync(path.join(directory,file),'utf8'))) {
    if (ids.has(article.id)) issues.push(`duplicate ID: ${article.id}`)
    ids.add(article.id)
    if (article.status !== 'verified') partial.push(article.id)
    for (const route of article.route_names) if (!sources.includes(`'${route}'`) && !sources.includes(`"${route}"`)) issues.push(`${article.id}: route missing ${route}`)
    for (const source of article.source_refs) {
      const target = path.resolve(root, source.path)
      if (!target.startsWith(root+path.sep) || !existsSync(target)) { issues.push(`${article.id}: source missing`); continue }
      const content = readFileSync(target,'utf8').replaceAll('\r\n','\n')
      if (!content.includes(source.symbol)) issues.push(`${article.id}: source symbol missing ${source.symbol}`)
      const hash = createHash('sha256').update(content).digest('hex')
      if (hash !== source.sha256) issues.push(`${article.id}: source changed; review required: ${source.path}`)
    }
    for (const field of article.field_keys) {
      if (!article.source_refs.some(s => readFileSync(path.join(root,s.path),'utf8').includes(field))) issues.push(`${article.id}: field missing ${field}`)
    }
    for (const required of ['title','summary','content','knowledge_version','verified_commit','anchor_id']) if (!article[required]) issues.push(`${article.id}: missing ${required}`)
  }
}
console.log(JSON.stringify({ articles: ids.size, partial, issues }, null, 2))
if (issues.length) process.exitCode = 1
