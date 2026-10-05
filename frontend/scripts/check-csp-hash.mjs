// Fails the build when vercel.json's Content-Security-Policy doesn't allow exactly the inline
// scripts in the built index.html (today: the theme pre-paint script). Runs inside the Vercel
// build command, so a mismatched hash can never reach production, and in CI.
// Usage: node scripts/check-csp-hash.mjs [--print]   (--print shows the hashes to paste)
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'

const html = readFileSync(new URL('../dist/index.html', import.meta.url), 'utf8')
const vercel = JSON.parse(readFileSync(new URL('../vercel.json', import.meta.url), 'utf8'))

// Inline scripts only: <script> tags without a src attribute. The browser hashes the exact text
// between the tags, whitespace included.
const inline = [...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g)].map((m) => m[1])
const needed = inline.map((text) => `'sha256-${createHash('sha256').update(text, 'utf8').digest('base64')}'`)

if (process.argv.includes('--print')) {
  console.log(needed.join(' '))
  process.exit(0)
}

const csp = vercel.headers
  ?.flatMap((rule) => rule.headers)
  .find((h) => h.key.toLowerCase() === 'content-security-policy')?.value
if (!csp) {
  console.error('check-csp-hash: no Content-Security-Policy header found in vercel.json')
  process.exit(1)
}
const scriptSrc = csp.split(';').map((d) => d.trim()).find((d) => d.startsWith('script-src')) ?? ''
const allowed = scriptSrc.match(/'sha256-[^']+'/g) ?? []

const missing = needed.filter((h) => !allowed.includes(h))
const stale = allowed.filter((h) => !needed.includes(h))
if (missing.length || stale.length) {
  if (missing.length) console.error(`check-csp-hash: script-src is missing ${missing.join(' ')}`)
  if (stale.length) console.error(`check-csp-hash: script-src has stale ${stale.join(' ')}`)
  console.error("Update script-src in vercel.json to: script-src 'self' " + needed.join(' '))
  process.exit(1)
}
console.log(`check-csp-hash: OK (${needed.length} inline script(s) allowed by hash)`)
