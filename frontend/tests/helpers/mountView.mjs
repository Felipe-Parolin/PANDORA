import { readFileSync } from 'node:fs'
import { setImmediate } from 'node:timers/promises'
import { compileScript, parse } from '@vue/compiler-sfc'
import * as vue from 'vue'
import * as pagination from '../../src/services/pagination.js'
import * as destinations from '../../src/services/rentalDestinations.js'
import * as dates from '../../src/services/formDates.js'
import * as actions from '../../src/services/rentalActions.js'
import * as documents from '../../src/services/documents.js'
import * as listFilters from '../../src/services/listFilters.js'
import * as formatters from '../../src/services/formatters.js'
import * as periods from '../../src/services/rentalPeriods.js'

export const flush = async () => { await setImmediate(); await vue.nextTick() }

// Monta o setup real das telas. Apenas rede, roteador e renderização são substituídos.
export function mountView(t, name, overrides = {}, directory = 'views') {
  const calls = []
  const services = {
    api: { get: async (url, config) => { calls.push({ url, config }); return { data: url.endsWith('/catalog/') ? [] : {} } }, post: async () => ({ data: {} }) },
    fetchAll: async url => { calls.push({ url }); return { data: { results: [], next: null } } },
    can: () => true, canAny: () => true, auth: { user: { id: 1, full_name: 'Teste', permissions: ['*'] } },
    rows: data => data?.results || data || [], money: String, shortDate: value => value, apiError: () => 'Falha de consulta',
    ...overrides,
  }
  const dependencies = { destinations, vue, services, pagination, dates, actions, periods, listFilters, formatters, documents, icons: {}, ai: { canUseAI: () => false, ...overrides.ai }, router: { useRoute: () => vue.reactive({ query: {} }), useRouter: () => ({ replace() {} }) } }
  let code = compileScript(parse(readFileSync(new URL(`../../src/${directory}/${name}.vue`, import.meta.url), 'utf8')).descriptor, { id: name }).content
  code = code.replace(/import\s+\{([^}]+)\}\s+from\s+'([^']+)'/g, (_, names, path) => {
    const name = ({ vue: 'vue', 'vue-router': 'router', 'lucide-vue-next': 'icons' })[path]
      || ({ api: 'services', pagination: 'pagination', formDates: 'dates', rentalActions: 'actions', rentalPeriods: 'periods', rentalDestinations: 'destinations', listFilters: 'listFilters', formatters: 'formatters', documents: 'documents', ai: 'ai' })[path.split('/').at(-1)]
    if (!name) throw new Error(`Dependência não prevista no teste: ${path}`)
    return `const {${names}} = dependencies.${name}`
  }).replace(/import (\w+) from '[^']+'/g, 'const $1 = {}')
  const component = new Function('dependencies', code.replace('export default', 'return'))(dependencies)
  component.render = () => null
  const renderer = vue.createRenderer({ createComment: () => ({}), insert() {}, remove() {}, parentNode() {}, nextSibling() {} })
  const app = renderer.createApp(component)
  app.mount({})
  t.after(() => app.unmount())
  return { state: app._instance.setupState, calls }
}
