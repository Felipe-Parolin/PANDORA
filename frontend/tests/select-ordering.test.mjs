import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { compileScript, parse } from '@vue/compiler-sfc'
import * as Vue from 'vue'
import * as filters from '../src/services/listFilters.js'

// Executa o controlador real. Os hooks que medem/observam o DOM pertencem ao roteiro de navegador.
function selectController(t) {
  const scope = Vue.effectScope(), events = [], props = Vue.reactive({ modelValue: 10, disabled: false, searchable: true, modelModifiers: {} })
  const vue = { ...Vue, onMounted() {}, onUpdated() {}, onBeforeUnmount() {}, useId: () => 'test', useAttrs: () => ({}) }
  let code = compileScript(parse(readFileSync(new URL('../src/components/AppSelect.vue', import.meta.url), 'utf8')).descriptor, { id: 'AppSelect' }).content
  code = code.replace(/import\s+\{([^}]+)\}\s+from\s+'([^']+)'/g, (_, names, path) => `const {${names}} = ${path === 'vue' ? 'vue' : path.includes('listFilters') ? 'filters' : '{}'}`)
  const component = new Function('vue', 'filters', code.replace('export default', 'return'))(vue, filters)
  const state = Vue.proxyRefs(scope.run(() => component.setup(props, { expose() {}, emit: (...args) => events.push(args) })))
  state.native = { selectedIndex: -1, options: [] }
  state.trigger = { focus() {} }
  state.options = [{ index: 0, label: 'Zulu', value: 99 }, { index: 1, label: 'Água 10', value: 10 }, { index: 2, label: 'água 2', value: 2 }, { index: 3, label: 'Bloqueado', value: 3, disabled: true }]
  t.after(() => scope.stop())
  return { state, props, events }
}

test('seletor: pesquisar preserva ordem, valor e índice original', t => {
  const { state, events } = selectController(t)
  state.search = 'agua'
  assert.deepEqual(state.filtered.map(item => item.value), [10, 2])
  assert.equal(state.selected.value, 10)
  state.choose(state.filtered[1])
  assert.equal(state.native.selectedIndex, 2)
  assert.deepEqual(events[0], ['update:modelValue', 2])
  state.choose(state.options[3])
  assert.equal(events.filter(item => item[0] === 'update:modelValue').length, 1)
})

test('seletor: mil cadastros limitam o painel e a busca alcança os últimos registros', t => {
  const { state, props } = selectController(t)
  state.options = Array.from({ length: 1000 }, (_, i) => ({ index: i, label: `Cliente ${i+1}`, value: i+1 }))
  props.modelValue = 999
  assert.equal(state.filtered.length, 50)
  assert.equal(state.filtered.at(-1).value, 999)
  state.search = 'cliente 1000'
  assert.deepEqual(state.filtered.map(item => item.value), [1000])
  state.choose(state.filtered[0])
  assert.equal(state.native.selectedIndex, 999)
})
