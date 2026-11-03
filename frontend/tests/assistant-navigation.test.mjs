import assert from 'node:assert/strict'
import test from 'node:test'
import { mountView, flush } from './helpers/mountView.mjs'

test('assistente: resposta atrasada não substitui uma consulta de outro equipamento', async t => {
  let resolve
  const { state } = mountView(t, 'AssistantView', { ai: { aiApi: { status: async () => ({ configured: true, available: true }), ask: () => new Promise(done => { resolve = done }) } } })
  await flush()
  state.equipmentId = 1; state.question = 'Verificar lubrificação'
  const pending = state.ask()
  state.equipmentId = 2
  resolve({ analysis: { answer: 'Resposta do equipamento anterior' } }); await pending
  assert.equal(state.answer, null)
  assert.equal(state.busy, false)
})

test('assistente: histórico filtra e ordena todos os registros antes de paginar', async t => {
  const { state } = mountView(t, 'AssistantView', { ai: { aiApi: { status: async () => ({ configured: true, available: true }) } } }); await flush()
  state.history = Array.from({ length: 13 }, (_, i) => ({ id: i+1, kind: i%2 ? 'ASK' : 'DIAGNOSE', kind_label: i%2 ? 'Pergunta' : 'Diagnóstico', equipment_name: `Equipamento ${i+1}`, created_at: `2026-11-${String(i+1).padStart(2,'0')}T12:00:00Z`, decisions: [] }))
  await flush()
  assert.equal(state.historyRows.length, 10)
  assert.equal(state.historyRows[0].id, 13)
  state.historyPage = 2; state.historySearch = 'Equipamento 13'; await flush()
  assert.equal(state.historyPage, 1)
  assert.deepEqual(state.historyRows.map(item => item.id), [13])
  state.historySearch = ''; state.historyKind = 'ASK'; await flush()
  assert.equal(state.filteredHistory.length, 6)
})

test('logística: link de uma viagem filtra o registro exato sem alterar os dados', async t => {
  const { state } = mountView(t, 'LogisticsView'); await flush()
  state.trips = [{ id: 1, status: 'PLANNED', quote_number: 'ORC-1' }, { id: 2, status: 'PLANNED', quote_number: 'ORC-1' }]
  state.route.query.trip = '2'
  assert.deepEqual(state.visibleTrips.map(item => item.id), [2])
  state.route.query.trip = undefined
  assert.equal(state.visibleTrips.length, 2)
})
