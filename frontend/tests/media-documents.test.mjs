import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { setImmediate } from 'node:timers/promises'
import test from 'node:test'
import { compileScript, parse } from '@vue/compiler-sfc'
import * as vue from 'vue'

// Executa o setup real dos componentes e seus hooks, sem dependência de DOM.
function mount(name, props, services) {
  const source = readFileSync(new URL(`../src/components/${name}.vue`, import.meta.url), 'utf8')
  let code = compileScript(parse(source).descriptor, { id: name }).content
  code = code.replace(/import\s+\{([^}]+)\}\s+from\s+'([^']+)'/g, (_, names, path) => {
    const dependency = path === 'vue' ? 'vue' : path.includes('services/api') ? 'services' : '{}'
    return `const {${names}} = ${dependency}`
  }).replace(/import (\w+) from '[^']+'/g, 'const $1 = {}')
  const component = new Function('vue', 'services', code.replace('export default', 'return'))(vue, services)
  component.render = () => null
  const renderer = vue.createRenderer({
    createComment: () => ({}), insert() {}, remove() {}, parentNode() {}, nextSibling() {},
  })
  const app = renderer.createApp(component, props)
  app.mount({})
  return { state: app._instance.setupState, unmount: () => app.unmount() }
}
const flush = async () => { await setImmediate(); await vue.nextTick() }
const services = api => ({ api, rows: data => data?.results || data || [], can: () => true, shortDate: value => value, apiError: error => error.response?.data?.detail || 'Falha de conexão' })
const media = (id, extension) => ({ id, name: `Arquivo ${id}`, file: `equipment/file-${id}.${extension}` })

test('mídias da OS: consulta e upload usam o vínculo com o atendimento', async t => {
  const calls = [], bodies = []
  const mounted = mount('EquipmentMediaModal', { equipment: { id: 7 }, order: { id: 8, number: 'OS-8' } }, services({
    get: async (url, options) => { calls.push(options.params); return { data: [] } },
    post: async (url, body) => { bodies.push(body); return { data: { id: 1 } } },
  }))
  t.after(mounted.unmount); await flush()
  assert.deepEqual(calls[0], { service_order: 8, page: 1 })
  mounted.state.openUpload()
  assert.equal(mounted.state.form.category, 'INSPECTION')
  mounted.state.file = new File(['foto de teste'], 'foto.png', { type: 'image/png' })
  await mounted.state.save()
  assert.equal(bodies[0].get('service_order'), '8')
  assert.equal(bodies[0].has('equipment'), false)
})

test('inspeção integrada: salva andamento antes do checklist e aguarda a atualização da OS', async t => {
  const sequence = []
  const item = { id: 7, equipment: 1, result: 'PENDING', condition: 'GOOD', observations: '', critical_impediment: false, checklist: [{ id: '1', label: 'Testar', status: 'PENDING', notes: '' }] }
  const mounted = mount('RentalInspectionModal', {
    quote: { id: 3, status: 'APPROVED' }, type: 'PRE_RENTAL', initialId: 7, embedded: true,
    beforeSave: async () => { sequence.push('andamento'); return true },
    afterSave: async () => { await flush(); sequence.push('OS atualizada') },
  }, services({
    get: async url => ({ data: url === '/rental-inspections/' ? [structuredClone(item)] : [] }),
    patch: async (url, data) => { sequence.push(url); Object.assign(item, JSON.parse(JSON.stringify(data))) },
  }))
  t.after(mounted.unmount); await flush()
  assert.equal(mounted.state.hasChanges, false)
  mounted.state.selected.checklist[0].status = 'OK'; mounted.state.selected.result = 'APPROVED'
  assert.equal(mounted.state.hasChanges, true)
  assert.equal(await mounted.state.save(), true)
  assert.deepEqual(sequence, ['andamento', '/rental-inspections/7/', 'OS atualizada'])
  assert.equal(mounted.state.hasChanges, false)
})

test('inspeção integrada: falha ao salvar o andamento impede o envio do checklist', async t => {
  let patches = 0
  const mounted = mount('RentalInspectionModal', { quote: { id: 3, status: 'APPROVED' }, type: 'PRE_RENTAL', initialId: 7, embedded: true, beforeSave: async () => false }, services({
    get: async url => ({ data: url === '/rental-inspections/' ? [{ id: 7, checklist: [], result: 'PENDING' }] : [] }),
    patch: async () => { patches++ },
  }))
  t.after(mounted.unmount); await flush()
  assert.equal(await mounted.state.save(), false)
  assert.equal(patches, 0)
})

function blobMocks(t) {
  const created = [], revoked = [], links = []
  t.mock.method(URL, 'createObjectURL', () => { const url = `blob:test-${created.length}`; created.push(url); return url })
  t.mock.method(URL, 'revokeObjectURL', url => revoked.push(url))
  const previousDocument = globalThis.document, previousWindow = globalThis.window
  globalThis.document = { body: { appendChild() {} }, createElement() { const link = { click() { links.push(this) }, remove() {} }; return link } }
  globalThis.window = { setTimeout(callback) { callback() } }
  t.after(() => { globalThis.document = previousDocument; globalThis.window = previousWindow })
  return { created, revoked, links }
}

test('mídias: todas as páginas, API de conteúdo, seleção e liberação dos blobs', async t => {
  const blobs = blobMocks(t), calls = []
  const first = media(1, 'png'), second = media(2, 'pdf')
  const mounted = mount('EquipmentMediaModal', { equipment: { id: 7 } }, services({
    async get(url, options) {
      calls.push({ url, options })
      if (url === '/media/') return { data: { results: options.params.page === 1 ? [first] : [second], next: options.params.page === 1 ? 'page=2' : null } }
      return { data: new Blob(['conteúdo']) }
    },
  }))
  await flush()
  assert.equal(mounted.state.items.length, 2)
  assert.deepEqual(calls.slice(0, 2).map(call => call.options.params), [{ equipment: 7, page: 1 }, { equipment: 7, page: 2 }])
  assert.equal(calls[2].url, '/media/1/content/')
  assert.equal(calls[2].options.responseType, 'blob')
  await mounted.state.selectItem(second)
  assert.deepEqual(blobs.revoked, ['blob:test-0'])
  assert.equal(mounted.state.previewType(second), 'pdf')
  mounted.unmount()
  assert.deepEqual(blobs.revoked, blobs.created)
})

test('mídias: respostas atrasadas não substituem a seleção e não criam blobs após fechar', async t => {
  const blobs = blobMocks(t)
  let resolveFirst, resolveSecond
  const mounted = mount('EquipmentMediaModal', { equipment: { id: 7 } }, services({
    async get(url) {
      if (url === '/media/') return { data: [] }
      return new Promise(resolve => { if (url.includes('/1/')) resolveFirst = resolve; else resolveSecond = resolve })
    },
  }))
  await flush()
  const firstRequest = mounted.state.selectItem(media(1, 'jpg'))
  const secondRequest = mounted.state.selectItem(media(2, 'pdf'))
  resolveFirst({ data: new Blob(['antigo']) }); await firstRequest
  assert.equal(blobs.created.length, 0)
  mounted.unmount()
  resolveSecond({ data: new Blob(['fechado']) }); await secondRequest
  assert.equal(blobs.created.length, 0)
})

test('mídias: DOCX permite download autenticado sem solicitar prévia', async t => {
  const blobs = blobMocks(t), calls = [], item = media(5, 'docx')
  const mounted = mount('EquipmentMediaModal', { equipment: { id: 7 } }, services({
    async get(url, options) { calls.push({ url, options }); return { data: url === '/media/' ? [item] : new Blob(['documento']) } },
  }))
  await flush()
  assert.equal(calls.length, 1)
  assert.equal(mounted.state.previewType(item), 'unsupported')
  await mounted.state.download()
  assert.equal(calls[1].url, '/media/5/content/')
  assert.equal(calls[1].options.params.download, '1')
  assert.equal(blobs.links[0].download, 'file-5.docx')
  assert.deepEqual(blobs.created, blobs.revoked)
  mounted.unmount()
})

test('mídias: falha de prévia e falha de listagem têm estado de erro', async t => {
  blobMocks(t)
  const mounted = mount('EquipmentMediaModal', { equipment: { id: 7 } }, services({
    async get(url) { if (url === '/media/') return { data: [media(1, 'png')] }; throw new Error('ausente') },
  }))
  await flush()
  assert.match(mounted.state.previewError, /Não foi possível carregar/)
  assert.equal(mounted.state.previewLoading, false)
  mounted.unmount()
  const failed = mount('EquipmentMediaModal', { equipment: { id: 7 } }, services({ async get() { throw new Error('offline') } }))
  await flush()
  assert.equal(failed.state.error, 'Falha de conexão')
  assert.equal(failed.state.loading, false)
  failed.unmount()
})

test('documentos: geração atualiza o histórico e baixa a versão retornada', async t => {
  const blobs = blobMocks(t), calls = []
  const item = { id: 9, kind: 'QUOTE', version: 2 }
  const mounted = mount('RentalDocumentsPanel', { quote: { id: 4, number: 'ORC-TESTE' } }, services({
    async get(url) { calls.push(url); return { data: url.endsWith('/pdf/') ? new Blob(['pdf']) : [item] } },
    async post(url, payload) { calls.push({ url, payload }); return { data: item } },
  }))
  await flush()
  await mounted.state.generate('QUOTE')
  assert.deepEqual(calls[1], { url: '/rental-quotes/4/documents/', payload: { kind: 'QUOTE' } })
  assert.equal(calls[3], '/rental-quotes/4/documents/9/pdf/')
  assert.equal(mounted.state.documents[0].version, 2)
  assert.equal(blobs.links[0].download, 'pandora-orc-teste-quote-v2.pdf')
  assert.deepEqual(blobs.created, blobs.revoked)
  mounted.unmount()
})

test('documentos: erro JSON de integridade recebido como blob aparece na interface', async t => {
  blobMocks(t)
  const mounted = mount('RentalDocumentsPanel', { quote: { id: 4 } }, services({
    async get(url) {
      if (!url.endsWith('/pdf/')) return { data: [] }
      throw { response: { data: new Blob([JSON.stringify({ detail: 'Integridade comprometida' })], { type: 'application/json' }) } }
    },
  }))
  await flush()
  await mounted.state.download({ id: 9 })
  assert.equal(mounted.state.error, 'Integridade comprometida')
  assert.equal(mounted.state.busy, false)
  mounted.unmount()
})
