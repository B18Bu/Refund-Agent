import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

const compose = fs.readFileSync(new URL('../../deploy/compose/docker-compose.yml', import.meta.url), 'utf8')
const dockerfile = fs.readFileSync(new URL('../../backend/Dockerfile', import.meta.url), 'utf8')
const coreMigration = fs.readFileSync(
  new URL('../../backend/migrations/20260829_create_core_users_tickets.sql', import.meta.url),
  'utf8'
)
const apiService = compose.match(/^  api:\n([\s\S]*?)(?=^  [\w-]+:\n|^volumes:)/m)?.[1]

test('Compose must create core users and tickets before dependent migrations', () => {
  assert.match(compose, /core-migrate:\s*\n/)
  assert.match(compose, /backend\/migrations\/20260829_create_core_users_tickets\.sql/)
  const coreMigrate = compose.match(/^  core-migrate:\n([\s\S]*?)^  migrate:/m)?.[1]

  assert.ok(coreMigrate, 'Compose must define a core-migrate service')
  assert.match(coreMigrate, /20260829_create_core_users_tickets\.sql/)
  assert.match(coreMigrate, /postgres:[\s\S]*condition: service_healthy/)

  const migrate = compose.match(/^  migrate:\n([\s\S]*?)^  rag-migrate:/m)?.[1]
  assert.ok(migrate, 'Compose must define the evaluation migration service')
  assert.match(migrate, /core-migrate:[\s\S]*condition: service_completed_successfully/)
})

test('Core migration must not duplicate unique constraint indexes', () => {
  assert.doesNotMatch(coreMigration, /CREATE INDEX IF NOT EXISTS ix_users_username ON users \(username\);/)
  assert.doesNotMatch(coreMigration, /CREATE INDEX IF NOT EXISTS ix_tickets_ticket_no ON tickets \(ticket_no\);/)
})

test('Compose must run evaluation migration before API starts', () => {
  assert.match(compose, /migrate:\s*\n/)
  assert.match(compose, /backend\/migrations\/20260830_add_agent_evaluation_runs\.sql/)
  assert.ok(apiService, 'Compose must define an api service')
  assert.match(apiService, /migrate:[\s\S]*condition: service_completed_successfully/)
})

test('Compose must provide independent RAG migration and healthy embedding service', () => {
  assert.match(compose, /pgvector\/pgvector/)
  assert.match(compose, /rag-migrate:\s*\n/)
  assert.match(compose, /20260906_add_rag_knowledge\.sql/)
  const ragMigrate = compose.match(/^  rag-migrate:\n([\s\S]*?)^  rag-embedding:/m)?.[1]

  assert.ok(ragMigrate, 'Compose must define a rag-migrate service')
  assert.match(
    ragMigrate,
    /depends_on:[\s\S]*postgres:[\s\S]*condition: service_healthy/
  )
  assert.match(
    ragMigrate,
    /depends_on:[\s\S]*migrate:[\s\S]*condition: service_completed_successfully/
  )
  assert.match(compose, /rag-embedding:\s*\n/)
  assert.match(compose, /rag-embedding:[\s\S]*healthcheck:/)
  assert.ok(apiService, 'Compose must define an api service')
  assert.match(apiService, /rag-migrate:[\s\S]*condition: service_completed_successfully/)
  assert.doesNotMatch(apiService, /rag-embedding:[\s\S]*service_healthy/)
})

test('RAG embedding must use a dedicated CPU-only image without OCR dependencies', () => {
  assert.match(
    compose,
    /rag-embedding:\s*\n\s+build:\s*\n\s+context: \.\.\/\.\.\/backend\s*\n\s+target: rag-embedding/
  )
  const embeddingStage = dockerfile.match(/FROM python:3\.11-slim AS rag-embedding([\s\S]*?)(?=\nFROM |$)/)?.[1]

  assert.ok(embeddingStage, 'Dockerfile must define a rag-embedding build target')
  assert.match(embeddingStage, /requirements-rag-embedding\.txt/)
  assert.match(embeddingStage, /--index-url https:\/\/download\.pytorch\.org\/whl\/cpu/)
  assert.doesNotMatch(embeddingStage, /requirements-ocr\.txt/)
})
