import assert from 'node:assert/strict'
import test from 'node:test'
import { documentCaret, formatDocument, normalizeDocument } from '../src/services/documents.js'
import { mountView, flush } from './helpers/mountView.mjs'

test('documentos: formata CPF/CNPJ completos e parciais sem calcular ou completar números', () => {
  assert.equal(formatDocument('12345678909', 'PF'), '123.456.789-09')
  assert.equal(formatDocument('04252011000110', 'PJ'), '04.252.011/0001-10')
  assert.equal(formatDocument('042', 'PJ'), '04.2')
  assert.equal(formatDocument('042520110001', 'PJ'), '04.252.011/0001')
  assert.equal(formatDocument('', 'PJ'), '')
  const oversized = '09.376.908/00001-79'
  assert.equal(normalizeDocument(formatDocument(oversized, 'PJ')), normalizeDocument(oversized))
})

test('documentos: preserva CNPJ alfanumérico e valores inválidos para a validação existente', () => {
  assert.equal(formatDocument('12abc34501de35', 'PJ'), '12.ABC.345/01DE-35')
  assert.equal(normalizeDocument('12.ABC.345/01DE-35'), '12ABC34501DE35')
  assert.equal(normalizeDocument('04.252.011@/0001-10'), '04252011@000110')
  assert.equal(documentCaret('04.252.011/0001-10', 5), 6)
})

test('cliente: edição no meio do documento preserva o cursor e troca de tipo não apaga o valor', async t => {
  const { state } = mountView(t, 'PeopleView'); await flush()
  state.openCustomer()
  let selection
  const input = { value: '04252011000110', selectionStart: 5, setSelectionRange: (...args) => { selection = args } }
  state.onCustomerDocumentInput({ target: input })
  assert.equal(input.value, '04.252.011/0001-10')
  assert.equal(state.customerForm.document, '04252011000110')
  assert.deepEqual(selection, [6, 6])
  state.customerForm.person_type = 'PF'
  assert.equal(state.customerForm.document, '04252011000110')
  state.customerForm.document = '12345678909'
  assert.equal(state.customerDocument, '123.456.789-09')
})

test('cliente: cadastro envia o documento canônico e mantém endereço e notas', async t => {
  const writes = []
  const { state } = mountView(t, 'PeopleView', { api: { get: async () => ({ data: [] }), post: async (url, payload) => { writes.push({ url, payload }); return { data: {} } } } }); await flush()
  state.openCustomer()
  Object.assign(state.customerForm, { name: 'Empresa de teste', document: '12.ABC.345/01DE-35', notes: 'Nota interna', address: 'Rua de teste, 120' })
  await state.saveCustomer()
  assert.equal(writes[0].url, '/customers/')
  assert.equal(writes[0].payload.document, '12ABC34501DE35')
  assert.equal(writes[0].payload.notes, 'Nota interna')
  assert.equal(writes[0].payload.address, 'Rua de teste, 120')
})
