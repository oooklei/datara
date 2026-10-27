import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('production Dockerfile contract', () => {
  const dockerfile = readFileSync(resolve(process.cwd(), 'deploy/Dockerfile'), 'utf8')

  it('builds the frontend reproducibly inside a pinned Node 24 stage', () => {
    expect(dockerfile).toMatch(/^FROM node:24\.15\.0-alpine AS builder$/m)
    expect(dockerfile).toContain('COPY package.json package-lock.json ./')
    expect(dockerfile).toContain('RUN npm ci --no-audit --no-fund')
    expect(dockerfile).toContain('RUN npm run build')
  })

  it('ships only builder output in nginx and exposes a container health check', () => {
    expect(dockerfile).toContain('COPY --from=builder /app/dist /usr/share/nginx/html')
    expect(dockerfile).not.toMatch(/^COPY dist /m)
    expect(dockerfile).toContain('HEALTHCHECK')
  })
})
