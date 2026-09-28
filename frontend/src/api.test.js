import { test } from 'node:test'
import assert from 'node:assert/strict'
import { requestJSON } from './api.js'

const jsonResponse = (status, body) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => body,
})

test('200 + JSON returns ok with data', async () => {
  const stub = async () => jsonResponse(200, { run_id: 'abc12345', pipeline_status: 'awaiting_approval' })
  const res = await requestJSON('/runs', undefined, stub)
  assert.equal(res.ok, true)
  assert.equal(res.status, 200)
  assert.deepEqual(res.data, { run_id: 'abc12345', pipeline_status: 'awaiting_approval' })
  assert.equal(res.error, null)
})

test('400 + {detail} returns ok:false with FastAPI detail string', async () => {
  const stub = async () => jsonResponse(400, { detail: 'pipeline failed cannot approve' })
  const res = await requestJSON('/runs/x/approve', { method: 'POST' }, stub)
  assert.equal(res.ok, false)
  assert.equal(res.status, 400)
  assert.equal(res.error, 'pipeline failed cannot approve')
  assert.equal(res.data.detail, 'pipeline failed cannot approve')
})

test('409 + {detail} returns ok:false with detail', async () => {
  const stub = async () => jsonResponse(409, { detail: 'run already approved' })
  const res = await requestJSON('/runs/x/approve', { method: 'POST' }, stub)
  assert.equal(res.ok, false)
  assert.equal(res.status, 409)
  assert.equal(res.error, 'run already approved')
})

test('network rejection returns ok:false with useful error, never throws', async () => {
  const stub = async () => {
    throw new TypeError('Failed to fetch')
  }
  const res = await requestJSON('/runs', undefined, stub)
  assert.equal(res.ok, false)
  assert.equal(res.status, 0)
  assert.equal(res.error, 'Failed to fetch')
  assert.equal(res.data, null)
})

test('non-JSON response returns ok:false, never throws', async () => {
  const stub = async () => ({
    ok: true,
    status: 200,
    json: async () => {
      throw new SyntaxError('Unexpected token < in JSON')
    },
  })
  const res = await requestJSON('/runs', undefined, stub)
  assert.equal(res.ok, false)
  assert.equal(res.status, 200)
  assert.equal(res.error, 'Invalid response')
  assert.equal(res.data, null)
})

test('non-2xx non-JSON body falls back to HTTP status error', async () => {
  const stub = async () => ({
    ok: false,
    status: 502,
    json: async () => {
      throw new SyntaxError('bad')
    },
  })
  const res = await requestJSON('/runs', undefined, stub)
  assert.equal(res.ok, false)
  assert.equal(res.status, 502)
  assert.equal(res.error, 'HTTP 502')
})

test('method, headers and body options are passed through', async () => {
  const calls = []
  const stub = async (url, options) => {
    calls.push({ url, options })
    return jsonResponse(200, { ok: true })
  }
  const options = {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ticker: 'RELIANCE' }),
  }
  const res = await requestJSON('/runs', options, stub)
  assert.equal(res.ok, true)
  assert.equal(calls.length, 1)
  assert.equal(calls[0].url, '/runs')
  assert.equal(calls[0].options, options)
  assert.equal(calls[0].options.method, 'POST')
  assert.equal(calls[0].options.body, JSON.stringify({ ticker: 'RELIANCE' }))
})
