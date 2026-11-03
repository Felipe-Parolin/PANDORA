import assert from 'node:assert/strict'
import test from 'node:test'
import { computed, effectScope, ref } from 'vue'
import { toDateTimeInput, toDateTimePayload } from '../src/services/formDates.js'
import { TABLE_PAGE_SIZE, usePagination } from '../src/services/pagination.js'

test('datas opcionais vazias são enviadas como null, e horários mantêm o mesmo instante na edição', () => {
  assert.equal(toDateTimePayload(''), null)
  assert.equal(toDateTimePayload(null), null)
  assert.equal(toDateTimeInput(null), '')
  const timestamp = '2026-11-02T14:30:00.000Z'
  assert.equal(toDateTimePayload(toDateTimeInput(timestamp)), timestamp)
  assert.throws(() => toDateTimePayload('inválido'))
})

test('paginação mantém no máximo dez itens e ajusta a última página após exclusão', () => {
  const scope = effectScope()
  scope.run(() => {
    const records = ref(Array.from({ length: 23 }, (_, id) => ({ id })))
    const paging = usePagination(computed(() => records.value))
    assert.equal(TABLE_PAGE_SIZE, 10)
    assert.equal(paging.items.value.length, 10)
    paging.page.value = 2
    assert.equal(paging.items.value[0].id, 10)
    paging.page.value = 3
    assert.equal(paging.items.value.length, 3)
    records.value = records.value.slice(0, 11)
    assert.equal(paging.page.value, 2)
    assert.equal(paging.items.value.length, 1)
  })
  scope.stop()
})
