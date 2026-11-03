import assert from 'node:assert/strict'
import test from 'node:test'
import { rentalActionGroups, inspectionProgress } from '../src/services/rentalActions.js'

const quote = (status, changes = {}) => ({
  status, conditions: 'Retirada combinada', items: [{ equipment: 1 }], inspections: [], transport_tasks: [],
  delivery_transport_required: false, return_transport_required: false, ...changes,
})
const actions = (record, can = () => true, busy = false) => rentalActionGroups(record, can, busy).flatMap(group => group.actions)
const enabled = (record, id) => !actions(record).find(action => action.id === id).reason

test('as mesmas 15 ações estão presentes em todas as etapas', () => {
  const expected = actions(quote('DRAFT')).map(action => action.id)
  assert.equal(expected.length, 15)
  for (const status of ['DRAFT', 'SENT', 'APPROVED', 'ACTIVE', 'RETURNED', 'COMPLETED', 'CANCELLED', 'EXPIRED']) {
    assert.deepEqual(actions(quote(status)).map(action => action.id), expected)
    assert.equal(enabled(quote(status), 'flow'), true)
  }
})

test('reserva e edição respeitam etapa, itens e condições comerciais', () => {
  assert.equal(enabled(quote('SENT'), 'reserve'), true)
  assert.equal(enabled(quote('SENT', { items: [] }), 'reserve'), false)
  assert.equal(enabled(quote('SENT', { conditions: '' }), 'reserve'), false)
  assert.equal(enabled(quote('ACTIVE'), 'edit'), false)
  assert.equal(enabled(quote('CANCELLED'), 'reserve'), false)
})

test('entrega exige inspeção aprovada dos itens atuais e viagem concluída quando contratada', () => {
  const record = quote('APPROVED', { delivery_transport_required: true })
  assert.equal(enabled(record, 'deliver'), false)
  record.inspections = [{ equipment: 1, inspection_type: 'PRE_RENTAL', result: 'APPROVED' }]
  assert.equal(enabled(record, 'deliver'), false)
  record.transport_tasks = [{ leg: 'DELIVERY', status: 'COMPLETED' }]
  assert.equal(enabled(record, 'deliver'), true)
  record.inspections[0].result = 'BLOCKED'
  assert.equal(enabled(record, 'deliver'), false)
  assert.deepEqual(inspectionProgress(record, 'PRE_RENTAL'), { done: 1, total: 1 })
})

test('devolução depende da coleta e conclusão depende da inspeção final', () => {
  const record = quote('ACTIVE', { return_transport_required: true })
  assert.equal(enabled(record, 'return'), false)
  record.transport_tasks = [{ leg: 'RETURN', status: 'COMPLETED' }]
  assert.equal(enabled(record, 'return'), true)
  record.status = 'RETURNED'
  assert.equal(enabled(record, 'return'), false)
  assert.equal(enabled(record, 'finalize'), false)
  record.inspections = [{ equipment: 1, inspection_type: 'RETURN', result: 'APPROVED' }]
  assert.equal(enabled(record, 'finalize'), true)
})

test('perfil sem permissão e operação em andamento mantêm ações visíveis e desabilitadas', () => {
  assert.ok(actions(quote('SENT'), () => false).every(action => action.reason.includes('permissão')))
  assert.ok(actions(quote('SENT'), () => true, true).every(action => action.reason.includes('andamento')))
  assert.equal(enabled(quote('COMPLETED'), 'delete'), false)
  assert.equal(enabled(quote('CANCELLED', { transport_tasks: [{ leg: 'DELIVERY' }] }), 'delete'), false)
})
