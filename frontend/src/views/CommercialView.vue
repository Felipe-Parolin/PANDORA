<script setup>
import { formatPhone, formatDate, formatNumber, formatPercent, rentalStatusLabel } from '../services/formatters'
import RevenueChart from '../components/RevenueChart.vue'
import ReceivablesPanel from '../components/ReceivablesPanel.vue'
import ModalDialog from '../components/ModalDialog.vue'
import { matchesSearch, sortRecords, dateValue } from '../services/listFilters'
import { usePagination } from '../services/pagination'
import { computed, onMounted, ref } from 'vue'
import { RefreshCw, TrendingUp, ShoppingCart, Mail, Search, Image, CheckCircle2, Eye, BarChart3, Users, FileText, ArrowUpRight, Send, AlertTriangle, Sparkles, Boxes, Check, Ban, PackageCheck } from 'lucide-vue-next'
import { api, apiError, can, money, rows, fetchAll } from '../services/api'

const receivablesPanel = ref(null)
const tab = ref(can('rentals.view') ? 'billing' : can('commercial.receivables.view') ? 'receivables' : can('assets.view') ? 'purchases' : 'campaigns')
const loading = ref(false)
const purchaseSearch = ref(''), purchaseStatus = ref(''), purchasePriority = ref(''), purchaseOrdering = ref('-created')
const selectedRecommendation = ref(null), decision = ref(null), decisionNote = ref(''), decisionError = ref(''), decisionBusy = ref(false)
const purchaseSortOptions = [['-created','Mais recentes'],['created','Mais antigos'],['category','Categoria A–Z'],['-quantity','Mais unidades']]
const purchaseStatusLabels = {PENDING:'Pendente',APPROVED:'Aprovada',REJECTED:'Rejeitada',ACQUIRED:'Adquirida'}
const filteredRecommendations = computed(()=>sortRecords(recommendations.value.filter(item=>matchesSearch(purchaseSearch.value,item.category_name,item.rationale,...suggestedModels(item).map(model=>model.name))&&(!purchaseStatus.value||item.status===purchaseStatus.value)&&(!purchasePriority.value||item.priority===purchasePriority.value)),purchaseOrdering.value,{created:item=>dateValue(item.created_at),category:item=>item.category_name,quantity:item=>item.suggested_quantity}))
function clearPurchaseFilters(){purchaseSearch.value='';purchaseStatus.value='';purchasePriority.value='';purchaseOrdering.value='-created'}
const error = ref(''), campaignError = ref('')
const startDate = ref('')
const endDate = ref('')
const billingGroup = ref('month')
const billingCategory = ref('')
const billingEquipment = ref('')
const billingCustomer = ref('')
const billing = ref(null)
const revenueChartVersion = ref(0)
const categories = ref([])
const recommendations = ref([])
const lostWithoutCategory = ref(0)
const brl = value => Number(value || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
const suggestedModels = item => item.evidence?.suggested_equipment || []
const modelLabel = m => [m.brand, m.model].filter(Boolean).join(' · ')
const days1 = value => Number(value || 0).toLocaleString('pt-BR', { maximumFractionDigits: 1 })
// A "Ruptura" já aparece no alerta vermelho; não repete a mesma frase no texto.
const rationaleText = item => (item.rationale || '').split(/(?<=\.)\s+(?=[A-ZÀ-Ú0-9])/).filter(part => !(item.evidence?.lost_requests && part.startsWith('Ruptura:'))).join(' ').trim()
const campaigns = ref([])
const customers = ref([])
const selectedCustomers = ref([])
const campaignSearch = ref('')
const campaignImageUrl = ref('')
const recipientSearch = ref('')
const recipientType = ref(''), recipientOrdering = ref('name')
const campaignStatus = ref(''), campaignSchedule = ref(''), campaignOrdering = ref('-created')
const billingOrdering = ref('-created')
const recipientSortOptions = [['name', 'Nome A–Z'], ['-name', 'Nome Z–A'], ['email', 'E-mail A–Z']]
const campaignSortOptions = [['-created', 'Mais recentes'], ['created', 'Mais antigos'], ['title', 'Título A–Z'], ['scheduled', 'Agenda próxima'], ['-recipients', 'Mais destinatários']]
const billingSortOptions = [['-created', 'Mais recentes'], ['start', 'Próximo início'], ['customer', 'Cliente A–Z'], ['number', 'Nº do contrato'], ['-total', 'Maior valor'], ['total', 'Menor valor']]
const showPreview = ref(false)
const campaignForm = ref({ title: '', subject: '', body_html: '', scheduled_at: null })
const campaignBusy = ref(false)

const activeCustomers = computed(() => customers.value.filter(c => c.is_active && c.marketing_opt_in && c.email))
const filteredRecipients = computed(() => sortRecords(activeCustomers.value.filter(item => matchesSearch(recipientSearch.value, item.name, item.email, item.phone) && (!recipientType.value || item.person_type === recipientType.value)), recipientOrdering.value, { name: item => item.name, email: item => item.email }))
const filteredCampaigns = computed(() => sortRecords(campaigns.value.filter(item => matchesSearch(campaignSearch.value, item.title, item.subject) && (!campaignStatus.value || item.status === campaignStatus.value) && (!campaignSchedule.value || Boolean(item.scheduled_at) === (campaignSchedule.value === 'scheduled'))), campaignOrdering.value, { created: item => dateValue(item.created_at), title: item => item.title, scheduled: item => dateValue(item.scheduled_at), recipients: item => Number(item.recipient_count || 0) }))
const sortedContracts = computed(() => sortRecords(billing.value?.contracts || [], billingOrdering.value, { created: item => dateValue(item.created_at), start: item => dateValue(item.start_date), customer: item => item.customer__name, number: item => item.number, total: item => Number(item.total) }))
function clearCampaignFilters() { campaignSearch.value = ''; campaignStatus.value = ''; campaignSchedule.value = ''; campaignOrdering.value = '-created' }
function clearRecipientFilters() { recipientSearch.value = ''; recipientType.value = ''; recipientOrdering.value = 'name' }
const categoryChartMax = computed(() => Math.max(1, ...(billing.value?.by_category || []).map(item => Number(item.total || 0))))
const campaignPreviewHtml = computed(() => `<!doctype html><html><body style="margin:0;padding:24px;background:#f4f4f2;font-family:Arial,sans-serif"><div style="max-width:640px;margin:auto;background:#fff"><header style="padding:20px;background:#252a32;color:#fff;font-weight:bold">MAZZI</header><main style="padding:24px">${campaignForm.value.body_html || '<p>O conteúdo da campanha aparecerá aqui.</p>'}</main><footer style="padding:16px;color:#888;font-size:12px">Prévia do rodapé de descadastro</footer></div></body></html>`)

async function loadBilling() {
  const params = { group_by: billingGroup.value }
  if (startDate.value) params.start_date = startDate.value
  if (endDate.value) params.end_date = endDate.value
  if (billingCategory.value) params.category = billingCategory.value
  if (billingEquipment.value) params.equipment = billingEquipment.value
  if (billingCustomer.value) params.customer = billingCustomer.value
  billing.value = (await api.get('/billing/analytics/', { params })).data
  revenueChartVersion.value += 1
}
async function applyBillingFilters(){loading.value=true;error.value='';try{await loadBilling()}catch(event){error.value=apiError(event)}finally{loading.value=false}}
async function loadCategories() { categories.value = rows((await fetchAll('/categories/')).data) }
async function loadRecommendations() { recommendations.value = rows((await fetchAll('/purchase-recommendations/')).data); if(selectedRecommendation.value) selectedRecommendation.value=recommendations.value.find(item=>item.id===selectedRecommendation.value.id)||null }
async function loadCampaigns() { campaigns.value = rows((await fetchAll('/marketing-campaigns/')).data) }
async function loadCustomers() { customers.value = rows((await fetchAll('/customers/')).data) }
async function loadAll() {
  loading.value = true; error.value = ''
  try {
    await Promise.all([
      can('commercial.receivables.view') ? receivablesPanel.value?.refresh() : Promise.resolve(),
      can('rentals.view') ? loadBilling() : Promise.resolve(),
      can('assets.view') ? loadCategories() : Promise.resolve(),
      can('assets.view') ? loadRecommendations() : Promise.resolve(),
      can('customers.view') ? Promise.all([loadCampaigns(), loadCustomers()]) : Promise.resolve(),
    ])
  } catch (e) { error.value = apiError(e) }
  finally { loading.value = false }
}
async function analyzePurchases() {
  loading.value = true; error.value = ''
  try {
    const { data } = await api.post('/purchase-recommendations/analyze/')
    lostWithoutCategory.value = data.lost_without_category || 0
    await loadRecommendations()
  }
  catch (e) { error.value = apiError(e) }
  finally { loading.value = false }
}
function decide(item,status) { decision.value={item,status};decisionNote.value='';decisionError.value='' }
async function confirmDecision() {
  if(decisionBusy.value)return
  decisionBusy.value=true;decisionError.value=''
  try { await api.post(`/purchase-recommendations/${decision.value.item.id}/decision/`,{status:decision.value.status,note:decisionNote.value});decision.value=null;await loadRecommendations() }
  catch(event) { decisionError.value=apiError(event) }
  finally { decisionBusy.value=false }
}
function insertCampaignImage() {
  const url = campaignImageUrl.value.trim()
  let safeUrl
  try { safeUrl = new URL(url) } catch { error.value = 'Informe uma URL de imagem válida.'; return }
  if (!['http:', 'https:'].includes(safeUrl.protocol)) { error.value = 'Use uma URL de imagem HTTP ou HTTPS.'; return }
  campaignForm.value.body_html += `\n<p><img src=\"${safeUrl.href}\" alt=\"Imagem da campanha\" style=\"display:block;max-width:100%;height:auto;margin:18px auto\"></p>`
  campaignImageUrl.value = ''
  error.value = ''
}
async function createCampaign() {
  campaignBusy.value = true; campaignError.value = ''
  try {
    await api.post('/marketing-campaigns/', { ...campaignForm.value, scheduled_at: campaignForm.value.scheduled_at || null })
    campaignForm.value = { title: '', subject: '', body_html: '', scheduled_at: null }; showPreview.value = false
    await loadCampaigns()
  } catch (e) { campaignError.value = apiError(e) }
  finally { campaignBusy.value = false }
}
async function campaignAction(item, action) {
  if (action === 'prepare') {
    if (!selectedCustomers.value.length) { error.value = 'Selecione os clientes autorizados que receberão esta campanha.'; return }
    if (!window.confirm(`Preparar campanha para ${selectedCustomers.value.length} cliente(s) selecionado(s)?`)) return
  }
  if (action === 'send' && !window.confirm(`Enviar agora para ${item.recipient_count} destinatário(s) previamente preparados?`)) return
  campaignBusy.value = true; error.value = ''
  try {
    const payload = action === 'prepare' ? { customer_ids: selectedCustomers.value } : {}
    await api.post(`/marketing-campaigns/${item.id}/${action}/`, payload)
    selectedCustomers.value = []
    await loadCampaigns()
  } catch (e) { error.value = apiError(e) }
  finally { campaignBusy.value = false }
}
function percent(value, total) { return total ? Math.min(100, Math.max(0, Number(value || 0) / total * 100)) : 0 }
onMounted(loadAll)
const {page:purchasePage,items:purchaseRows}=usePagination(filteredRecommendations,[purchaseSearch,purchaseStatus,purchasePriority,purchaseOrdering])

const { page: topPage, items: topRows } = usePagination(computed(() => billing.value?.top_equipment || []), [])
const { page: clientPage, items: clientRows } = usePagination(computed(() => billing.value?.by_customer || []), [])
const { page: contractPage, items: contractRows } = usePagination(sortedContracts, [billingOrdering])
const { page: campaignPage, items: campaignRows } = usePagination(filteredCampaigns, [campaignSearch, campaignStatus, campaignSchedule, campaignOrdering])
const { page: recipientPage, items: recipientRows } = usePagination(filteredRecipients, [recipientSearch, recipientType, recipientOrdering])
</script>

<template>
  <section class="page commercial-page">
    <header class="page-heading">
      <div><h1>Comercial</h1><p>Contas, faturamento e relacionamento com clientes.</p></div>
      <button class="btn secondary" :disabled="loading" @click="loadAll"><RefreshCw :size="16" :class="{ spinning: loading }"/> Atualizar dados</button>
    </header>
    <GeneralError v-if="error" :message="error" @close="error = ''" />

    <nav class="commercial-tabs" aria-label="Áreas do Comercial">
      <button v-if="can('rentals.view')" :class="{ active: tab === 'billing' }" @click="tab = 'billing'"><TrendingUp :size="17"/> Faturamento</button>
      <button v-if="can('commercial.receivables.view')" :class="{active:tab==='receivables'}" @click="tab='receivables'"><FileText :size="17"/> Contas a receber</button>
      <button v-if="can('assets.view')" :class="{ active: tab === 'purchases' }" @click="tab = 'purchases'"><ShoppingCart :size="17"/> Sugestões de compra</button>
      <button v-if="can('customers.view')" :class="{ active: tab === 'campaigns' }" @click="tab = 'campaigns'"><Mail :size="17"/> E-mail de marketing</button>
    </nav>

    <ReceivablesPanel v-if="tab==='receivables'&&can('commercial.receivables.view')" ref="receivablesPanel"/>
    <div v-else-if="tab === 'billing' && can('rentals.view')" class="commercial-content">
      <section class="commercial-filter panel">
        <div class="section-heading"><div><h2>Faturamento de locações</h2><p>Valores contratuais. Os pagamentos registrados ficam em Contas a receber.</p></div><BarChart3 :size="22"/></div>
        <div class="commercial-filters">
          <label>Data inicial<AppDateTime v-model="startDate" type="date"/></label><label>Data final<AppDateTime v-model="endDate" type="date"/></label>
          <label>Visualização<AppSelect v-model="billingGroup"><option value="day">Diária</option><option value="week">Semanal</option><option value="month">Mensal</option><option value="year">Anual</option></AppSelect></label>
          <label>Categoria<AppSelect searchable v-model="billingCategory"><option value="">Todas</option><option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name }}</option></AppSelect></label>
          <label>Cliente<input v-model="billingCustomer" type="search" placeholder="Todos os clientes"></label><label>Equipamento<input v-model="billingEquipment" type="search" placeholder="Nome ou código"></label>
          <ListOrdering v-model="billingOrdering" :options="billingSortOptions" label="Ordenar contratos" /><button class="btn primary"  :disabled="loading" @click="applyBillingFilters">Aplicar filtros</button>
        </div>
      </section>
      <div v-if="billing" class="commercial-metrics">
        <article class="commercial-metric metric-dark"><span>Receita contratual líquida</span><strong>{{ money(billing.net) }}</strong><small>{{ billing.count }} locações contabilizadas</small></article>
        <article v-if="Math.abs(Number(billing.gross) - Number(billing.net)) > 0.004" class="commercial-metric"><span>Valor bruto</span><strong>{{ money(billing.gross) }}</strong><small>Diárias + fretes, antes dos descontos</small></article>
        <article class="commercial-metric"><span>Fretes</span><strong>{{ money(billing.freight) }}</strong><small>Componente de transporte</small></article>
        <article class="commercial-metric"><span>Descontos</span><strong>{{ money(billing.discounts) }}</strong><small>Concessões registradas</small></article><article class="commercial-metric"><span>Contratos ativos</span><strong>{{ billing.active_contracts }}</strong><small>Locações em andamento</small></article><article class="commercial-metric"><span>Ticket médio</span><strong>{{ money(billing.average_ticket) }}</strong><small>Valor líquido por contrato no filtro</small></article>
      </div>
      <div v-if="billing?.comparison" class="commercial-compare"><div><span>Comparativo com período anterior</span><strong>{{ money(billing.comparison.previous_net) }}</strong><small>{{ formatDate(billing.comparison.start_date) }} a {{ formatDate(billing.comparison.end_date) }}</small></div><div :class="billing.comparison.difference >= 0 ? 'positive' : 'negative'"><ArrowUpRight :size="19"/><strong>{{ money(Math.abs(billing.comparison.difference)) }}</strong><small>{{ billing.comparison.percent_change === null ? 'Sem base anterior' : formatPercent(billing.comparison.percent_change) }} {{ billing.comparison.difference >= 0 ? 'acima' : 'abaixo' }}</small></div></div>
      <div class="commercial-insights">
        <section class="panel commercial-chart-panel"><header class="section-heading"><div><h2>Receita por período</h2></div></header>
          <RevenueChart v-if="billing?.by_period?.length" :key="revenueChartVersion" :points="billing.by_period" :group-by="billing.period?.group_by || 'month'" />
          <div v-else class="commercial-empty">Nenhum faturamento no período selecionado.</div>
        </section>
        <section class="panel"><header class="section-heading"><div><h2>Por categoria</h2></div></header><div class="category-revenue-list"><div v-for="item in billing?.by_category || []" :key="item.equipment__category__name" class="category-revenue-row"><strong class="category-revenue-name">{{ item.equipment__category__name || 'Sem categoria' }}</strong><small class="category-revenue-count">{{ item.rentals }} locação(ões) · {{ item.items }} item(ns)</small><div class="category-revenue-track"><i :style="{ width: `${percent(item.total, categoryChartMax)}%` }"></i></div><strong class="category-revenue-value">{{ money(item.total) }}</strong></div><p v-if="!billing?.by_category?.length" class="commercial-empty">Sem dados por categoria.</p></div></section>
      </div>
      <div class="commercial-insights">
        <section class="panel"><header class="section-heading"><div><h2>Equipamentos de maior receita</h2></div></header><div class="table-wrap"><table><thead><tr><th>Equipamento</th><th>Categoria</th><th>Locações</th><th class="right">Receita</th></tr></thead><tbody><tr v-for="item in topRows" :key="item.equipment__internal_code"><td><div class="commercial-cell-detail"><strong>{{ item.equipment__name }}</strong><small>{{ item.equipment__internal_code }}</small></div></td><td>{{ item.equipment__category__name }}</td><td>{{ item.rentals }}</td><td class="right">{{ money(item.total) }}</td></tr><tr v-if="!billing?.top_equipment?.length"><td colspan="4" class="empty">Sem dados.</td></tr></tbody></table><PaginationBar v-model="topPage" :total="(billing?.top_equipment || []).length" /></div></section>
        <section class="panel"><header class="section-heading"><div><h2>Principais clientes</h2></div></header><div class="table-wrap"><table><thead><tr><th>Cliente</th><th>Locações</th><th class="right">Receita</th></tr></thead><tbody><tr v-for="item in clientRows" :key="item.customer__name"><td>{{ item.customer__name }}</td><td>{{ item.contracts }}</td><td class="right">{{ money(item.total) }}</td></tr><tr v-if="!billing?.by_customer?.length"><td colspan="3" class="empty">Sem dados.</td></tr></tbody></table><PaginationBar v-model="clientPage" :total="(billing?.by_customer || []).length" /></div></section>
      </div>
      <section class="panel"><header class="section-heading"><div><h2>Contratos considerados no faturamento</h2><p>Consulte os registros que compõem os indicadores acima.</p></div><FileText :size="21"/></header><div class="table-wrap"><table><thead><tr><th>Contrato</th><th>Cliente</th><th>Período</th><th>Status</th><th>Diárias</th><th>Frete</th><th>Desconto</th><th>Total líquido</th></tr></thead><tbody><tr v-for="item in contractRows" :key="item.id"><td><strong>{{ item.number }}</strong></td><td>{{ item.customer__name }}</td><td>{{ formatDate(item.start_date) }} – {{ formatDate(item.end_date) }}</td><td>{{ rentalStatusLabel(item.status) }}</td><td>{{ money(item.subtotal) }}</td><td>{{ money(item.transport_fee) }}</td><td>{{ money(item.discount) }}</td><td><strong>{{ money(item.total) }}</strong></td></tr><tr v-if="!billing?.contracts?.length"><td colspan="8" class="empty">Nenhum contrato contabilizado.</td></tr></tbody></table><PaginationBar v-model="contractPage" :total="(billing?.contracts || []).length" /></div></section>

    </div>

    <div v-else-if="tab === 'purchases'" class="commercial-content">
      <section class="purchase-intro"><div><h2>Sugestões de compra</h2><p>Análise baseada no histórico real de locações, disponibilidade, ordens de serviço e pedidos não atendidos (ruptura) dos últimos 90 dias.</p></div><button v-if="can('assets.manage')" class="btn primary" :disabled="loading" @click="analyzePurchases"><Sparkles :size="17"/> Analisar histórico</button></section>
      <div class="purchase-summary"><div><strong>{{ recommendations.filter(r => r.status === 'PENDING').length }}</strong><span>Pendentes de análise</span></div><div><strong>{{ recommendations.filter(r => r.priority === 'HIGH' && r.status === 'PENDING').length }}</strong><span>Prioridade alta</span></div><div><strong>{{ recommendations.filter(r => r.status === 'ACQUIRED').length }}</strong><span>Já adquiridas</span></div></div>
      <section class="panel purchase-table-panel">
        <ListToolbar><template #search><label class="list-control list-search"><span>Pesquisar</span><span class="search-box"><Search :size="17"/><input v-model="purchaseSearch" type="search" placeholder="Categoria, equipamento ou justificativa" aria-label="Pesquisar sugestões de compra"/></span></label></template><template #filters><label class="list-control"><span>Situação</span><AppSelect v-model="purchaseStatus"><option value="">Todas</option><option v-for="(label,key) in purchaseStatusLabels" :key="key" :value="key">{{label}}</option></AppSelect></label><label class="list-control"><span>Prioridade</span><AppSelect v-model="purchasePriority"><option value="">Todas</option><option value="HIGH">Alta</option><option value="MEDIUM">Média</option><option value="LOW">Baixa</option></AppSelect></label><ListOrdering v-model="purchaseOrdering" :options="purchaseSortOptions"/></template><template #meta><div class="filter-meta"><span>{{filteredRecommendations.length}} sugestão(ões)</span><button class="btn secondary" @click="clearPurchaseFilters">Limpar filtros</button></div></template></ListToolbar>
        <div class="table-wrap"><table><thead><tr><th>Categoria / equipamento</th><th>Prioridade</th><th>Frota disponível</th><th class="right">Qtd. sugerida</th><th>Situação</th><th class="right">Ações</th></tr></thead><tbody><tr v-for="item in purchaseRows" :key="item.id"><td><div class="commercial-cell-detail"><strong>{{item.category_name}}</strong><small>{{suggestedModels(item).map(model=>model.name).join(', ')||'Reforço da categoria'}}</small></div></td><td><span class="priority-tag" :class="item.priority.toLowerCase()">{{item.priority==='HIGH'?'Alta':item.priority==='LOW'?'Baixa':'Média'}}</span></td><td>{{item.current_available}} / {{item.current_total}}</td><td class="right">{{item.suggested_quantity}}</td><td>{{purchaseStatusLabels[item.status]||item.status_label}}</td><td class="right"><button class="btn secondary" @click="selectedRecommendation=item"><Eye :size="16"/> Visualizar</button></td></tr><tr v-if="!filteredRecommendations.length"><td colspan="6" class="empty">{{recommendations.length?'Nenhuma sugestão corresponde aos filtros.':'Nenhuma sugestão encontrada. Analise o histórico para começar.'}}</td></tr></tbody></table></div>
        <PaginationBar v-model="purchasePage" :total="filteredRecommendations.length"/>
      </section>
      <p v-if="lostWithoutCategory" class="commercial-footnote">{{lostWithoutCategory}} pedido(s) sem categoria não entram nas sugestões. Informe a categoria ao registrar o pedido.</p>
    </div>

    <div v-else-if="tab === 'campaigns'" class="commercial-content">
      <p v-if="!can('customers.manage')" class="commercial-footnote">Acesso de consulta: para criar, preparar ou enviar campanhas, é necessária a permissão de gerenciamento de clientes.</p>
      <section v-if="can('customers.manage')" class="panel campaign-editor"><header class="section-heading"><div><h2>Nova campanha de e-mail</h2><p>Somente contatos ativos com autorização explícita de marketing podem receber campanhas.</p></div><Mail :size="23"/></header>
        <form @submit.prevent="createCampaign" class="campaign-form"><div class="campaign-fields"><label class="wide-field"><span>Título interno<span class="required-mark" aria-hidden="true"> *</span></span><input v-model="campaignForm.title" required maxlength="160" placeholder="Ex.: Oferta de novembro"></label><label class="wide-field"><span>Assunto do e-mail<span class="required-mark" aria-hidden="true"> *</span></span><input v-model="campaignForm.subject" required maxlength="180" placeholder="Uma oferta especial para sua obra"></label><label>Data planejada (opcional)<AppDateTime v-model="campaignForm.scheduled_at" type="datetime-local"/></label><label>Imagem da campanha (URL)<div class="campaign-image-insert"><input v-model="campaignImageUrl" type="url" placeholder="https://.../banner.jpg"><button type="button" class="btn secondary" @click="insertCampaignImage"><Image :size="15"/> Inserir</button></div></label><label class="wide-field"><span>Conteúdo da mensagem<span class="required-mark" aria-hidden="true"> *</span></span><textarea v-model="campaignForm.body_html" rows="7" required placeholder="Escreva o conteúdo em HTML. Ex.: <h1>Oferta especial</h1><p>Confira nossos equipamentos...</p>"></textarea></label></div><div v-if="campaignError" class="error-message" role="alert">{{ campaignError }}</div><div class="campaign-actions"><button type="button" class="btn secondary" @click="showPreview = !showPreview"><Eye :size="16"/> {{ showPreview ? 'Ocultar prévia' : 'Visualizar prévia' }}</button><button class="btn primary" :disabled="campaignBusy"><CheckCircle2 :size="16"/> Salvar rascunho</button></div></form>
        <div v-if="showPreview" class="campaign-preview"><div class="preview-toolbar"><strong>Prévia do e-mail</strong><span>Assunto: {{ campaignForm.subject || 'Sem assunto' }}</span></div><iframe class="preview-frame" sandbox="" :srcdoc="campaignPreviewHtml" title="Prévia segura da campanha"></iframe></div>
      </section>
      <section v-if="can('customers.manage')" class="panel recipient-panel"><header class="section-heading"><div><h2>Destinatários autorizados</h2><p>Selecione os clientes que poderão receber a campanha que será preparada.</p></div><Users :size="22"/></header><ListToolbar><template #search><label class="list-control list-search"><span>Pesquisar</span><span class="search-box"><Search :size="16" /><input v-model="recipientSearch" type="search" placeholder="Cliente, e-mail ou telefone" aria-label="Buscar destinatários" /></span></label></template><template #filters><label class="list-control"><span>Tipo de pessoa</span><AppSelect v-model="recipientType"><option value="">Todos</option><option value="PF">Pessoa física</option><option value="PJ">Pessoa jurídica</option></AppSelect></label><ListOrdering v-model="recipientOrdering" :options="recipientSortOptions" /></template><template #meta><div class="filter-meta"><span>{{ selectedCustomers.length }} selecionado(s) · {{ filteredRecipients.length }} no filtro</span><button type="button" class="btn secondary" @click="clearRecipientFilters">Limpar filtros</button></div></template></ListToolbar><div class="table-wrap"><table class="recipient-table"><thead><tr><th>Selecionar</th><th>Cliente</th><th>E-mail</th><th>Telefone</th></tr></thead><tbody><tr v-for="customer in recipientRows" :key="customer.id"><td><input v-model="selectedCustomers" type="checkbox" :value="customer.id" :aria-label="`Selecionar ${customer.name}`"/></td><td><strong>{{customer.name}}</strong></td><td>{{customer.email}}</td><td>{{formatPhone(customer.phone)}}</td></tr><tr v-if="!filteredRecipients.length"><td colspan="4" class="empty">{{activeCustomers.length?'Nenhum cliente corresponde à busca.':'Nenhum contato ativo com autorização de marketing e e-mail cadastrado.'}}</td></tr></tbody></table></div><PaginationBar v-model="recipientPage" :total="filteredRecipients.length" /><div class="recipient-note">A seleção é validada novamente pelo servidor no momento da preparação. O envio continua sendo uma ação manual e explícita.</div></section>
      <section class="panel"><header class="section-heading"><div><h2>Campanhas cadastradas</h2></div></header><ListToolbar><template #search><label class="list-control list-search"><span>Pesquisar</span><span class="search-box"><Search :size="16" /><input v-model="campaignSearch" type="search" placeholder="Título ou assunto" aria-label="Buscar campanhas" /></span></label></template><template #filters><label class="list-control"><span>Situação</span><AppSelect v-model="campaignStatus"><option value="">Todas</option><option value="DRAFT">Rascunho</option><option value="READY">Pronta para envio</option><option value="SENT">Enviada</option><option value="FAILED">Falha</option><option value="PARTIAL">Parcialmente enviada</option></AppSelect></label><label class="list-control"><span>Agendamento</span><AppSelect v-model="campaignSchedule"><option value="">Todos</option><option value="scheduled">Com agendamento</option><option value="immediate">Sem agendamento</option></AppSelect></label><ListOrdering v-model="campaignOrdering" :options="campaignSortOptions" /></template><template #meta><div class="filter-meta"><span>{{ filteredCampaigns.length }} campanha(s)</span><button type="button" class="btn secondary" @click="clearCampaignFilters">Limpar filtros</button></div></template></ListToolbar><div class="table-wrap"><table><thead><tr><th>Campanha</th><th>Status</th><th>Destinatários</th><th>Agendada / enviada</th><th>Ações</th></tr></thead><tbody><tr v-for="item in campaignRows" :key="item.id"><td><div class="commercial-cell-detail"><strong>{{ item.title }}</strong><small>{{ item.subject }}</small><details v-if="item.result_log?.length" class="campaign-log"><summary>Ver registro</summary><p v-if="item.result_log[0]?.prepared_customer_ids">Lista preparada com {{ item.result_log[0].prepared_customer_ids.length }} destinatário(s).</p><p v-for="(log, index) in item.result_log.filter(row => row.email)" :key="index">{{ log.email }} · {{ log.sent ? 'Enviado' : `Falha: ${log.error || 'não enviado'}` }}</p></details></div></td><td><span class="campaign-status" :class="item.status.toLowerCase()">{{ ({DRAFT:'Rascunho',READY:'Pronta',SENT:'Enviada',FAILED:'Falha',PARTIAL:'Envio parcial'})[item.status]||item.status }}</span></td><td>{{ item.recipient_count }}</td><td>{{ item.sent_at ? formatDate(item.sent_at) : item.scheduled_at ? `Agendada: ${new Date(item.scheduled_at).toLocaleString('pt-BR')}` : '—' }}</td><td><div class="decision-buttons"><button v-if="can('customers.manage') && (item.status === 'DRAFT' || item.status === 'FAILED')" class="btn secondary" :disabled="campaignBusy" @click="campaignAction(item, 'prepare')">Preparar</button><button v-if="can('customers.manage') && item.status === 'READY' && (!item.scheduled_at || new Date(item.scheduled_at) <= new Date())" class="btn primary" :disabled="campaignBusy" @click="campaignAction(item, 'send')"><Send :size="14"/> Enviar</button><span v-if="can('customers.manage') && item.status === 'READY' && item.scheduled_at && new Date(item.scheduled_at) > new Date()" class="scheduled-waiting">Aguardando horário</span></div></td></tr><tr v-if="!filteredCampaigns.length"><td colspan="5" class="empty">Nenhuma campanha cadastrada.</td></tr></tbody></table><PaginationBar v-model="campaignPage" :total="(filteredCampaigns).length" /></div></section>
      <p class="commercial-footnote">Salve o rascunho, selecione os destinatários e prepare a campanha antes do envio. Campanhas com data planejada dependem da rotina de envio configurada no sistema.</p>
    </div>
    <ModalDialog v-if="selectedRecommendation" :title="`Sugestão · ${selectedRecommendation.category_name}`" wide @close="selectedRecommendation=null">
        <article v-for="item in [selectedRecommendation]" :key="item.id" class="purchase-card" :class="[item.priority.toLowerCase(), item.status.toLowerCase()]">
          <header class="purchase-card-head">
            <div><span class="card-kicker">{{ item.category_name }}</span><h3>Recomendação de aquisição</h3></div>
            <span class="priority-tag" :class="item.priority.toLowerCase()">{{ item.priority === 'HIGH' ? 'Alta prioridade' : item.priority === 'LOW' ? 'Prioridade baixa' : 'Prioridade média' }}</span>
          </header>

          <section class="purchase-pick" aria-label="Equipamento sugerido para compra">
            <span class="purchase-pick-label"><Boxes :size="14"/> O que comprar</span>
            <ul v-if="suggestedModels(item).length">
              <li v-for="(model, index) in suggestedModels(item)" :key="model.name + model.model + index" :class="{ main: index === 0 }">
                <div class="pick-main">
                  <strong>{{ model.name }}</strong>
                  <small v-if="modelLabel(model)">{{ modelLabel(model) }}</small>
                  <small v-else-if="model.source === 'requested'">Item pedido por clientes (ainda fora do catálogo)</small>
                </div>
                <div class="pick-chips">
                  <span v-if="index === 0" class="pick-qty">+{{ item.suggested_quantity }} {{ item.suggested_quantity === 1 ? 'unidade' : 'unidades' }}</span>
                  <span v-if="model.source === 'catalog'">{{ model.units }} na frota · {{ model.available }} disp.</span>
                  <span v-if="model.rentals_90d">{{ model.rentals_90d }} {{ model.rentals_90d === 1 ? 'locação' : 'locações' }} em 90d</span>
                  <span v-if="model.avg_daily_rate">{{ brl(model.avg_daily_rate) }}/dia</span>
                </div>
              </li>
            </ul>
            <p v-else class="pick-empty">Sem modelo definido: reforce a categoria <strong>{{ item.category_name }}</strong>. Rode “Analisar histórico” novamente para listar os modelos mais demandados.</p>
          </section>

          <dl class="purchase-stats">
            <div><dt>Disponíveis / total</dt><dd>{{ item.current_available }}<small>/ {{ item.current_total }}</small></dd></div>
            <div><dt>Locações em 90 dias</dt><dd>{{ item.demand_events }}</dd></div>
            <div><dt>Unidades sugeridas</dt><dd>{{ item.suggested_quantity }}</dd></div>
            <div><dt>Indisponibilidade</dt><dd>{{ days1(item.unavailable_days) }}<small>dias</small></dd></div>
          </dl>

          <p v-if="item.evidence?.lost_requests" class="purchase-lost"><AlertTriangle :size="16"/><span><strong>Ruptura:</strong> {{ item.evidence.lost_requests }} pedido(s) não atendido(s) · {{ item.evidence.lost_units }} unidade(s) · {{ item.evidence.lost_customers }} cliente(s)<template v-if="item.evidence.lost_revenue"> · <b>{{ brl(item.evidence.lost_revenue) }}</b> em receita perdida</template><template v-if="item.evidence.lost_requested_items?.length"> · Pedido: {{ item.evidence.lost_requested_items.join(', ') }}</template></span></p>

          <p v-if="rationaleText(item)" class="purchase-reason">{{ rationaleText(item) }}</p>

          <details class="purchase-evidence">
            <summary>Ver evidências e limitações</summary>
            <dl>
              <div><dt>Ordens de serviço</dt><dd>{{ item.evidence?.service_orders_total ?? item.maintenance_orders }}</dd></div>
              <div><dt>OS em aberto</dt><dd>{{ item.evidence?.open_service_orders ?? 'Não informado' }}</dd></div>
              <div><dt>Tempo médio por OS</dt><dd>{{ formatNumber(item.evidence?.average_downtime_hours) }} h</dd></div>
              <div><dt>Ocupação atual</dt><dd>{{ formatPercent(item.evidence?.utilization_percent) }}</dd></div>
              <div><dt>Solicitações/itens</dt><dd>{{ item.evidence?.requested_equipment_items ?? '—' }}</dd></div>
            </dl>
            <p>{{ item.evidence?.limitations || 'A análise utiliza os registros disponíveis e não estima solicitações recusadas que não tenham sido registradas.' }}</p>
          </details>

          <footer class="purchase-card-foot">
            <div class="purchase-status"><span class="decision-status" :class="item.status.toLowerCase()">{{ item.status_label }}</span><small v-if="item.decided_by_name">Por {{ item.decided_by_name }} · {{ formatDate(item.decided_at) }}</small></div>
            <div v-if="item.status === 'PENDING' && can('assets.manage')" class="purchase-actions">
              <button class="btn primary" @click="decide(item, 'APPROVED')"><Check :size="15"/>Aprovar</button>
              <button class="btn secondary" @click="decide(item, 'ACQUIRED')"><PackageCheck :size="15"/>Já adquirida</button>
              <button class="btn danger-outline" @click="decide(item, 'REJECTED')"><Ban :size="15"/>Rejeitar</button>
            </div>
          </footer>
        </article>
    </ModalDialog>
    <ModalDialog v-if="decision" title="Registrar decisão de compra" @close="!decisionBusy&&(decision=null)">
      <form @submit.prevent="confirmDecision"><p>{{decision.item.category_name}} · {{purchaseStatusLabels[decision.status]}}</p><div class="form-field"><label>Observação da decisão</label><textarea v-model="decisionNote" rows="3" placeholder="Motivo da decisão ou referência da compra"/></div><div v-if="decisionError" class="error-message" role="alert">{{decisionError}}</div><div class="modal-actions"><span class="spacer"/><button class="btn primary" :disabled="decisionBusy">{{decisionBusy?'Salvando…':'Confirmar decisão'}}</button></div></form>
    </ModalDialog>
  </section>
</template>

<style scoped>
.commercial-cell-detail{min-width:0;flex:1}.commercial-cell-detail strong{display:block}.commercial-cell-detail small{display:block;margin-top:5px;color:var(--muted);font-size:12px;line-height:1.5}

.commercial-page .panel{overflow:hidden;border-radius:14px}
.commercial-page .commercial-tabs{margin-bottom:20px;box-shadow:none}
.commercial-page .commercial-tabs button.active{box-shadow:none;background:#f6b623}
.commercial-content{align-content:start;gap:18px}
.commercial-filters{grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;padding:18px 22px}
.commercial-filters>.btn{width:100%}
.commercial-content>.commercial-filter .section-heading{padding-bottom:15px}
.commercial-page .list-toolbar{padding:16px 20px}
.commercial-insights{display:grid;grid-template-columns:minmax(0,1fr);gap:16px}
.commercial-insights>.panel{min-height:0}
.commercial-insights>.panel>.section-heading{padding:14px 20px}
.commercial-insights>.panel>.section-heading h2{margin:0;font-size:16px}
.commercial-insights .category-revenue-list{gap:0;padding:4px 20px}
.category-revenue-row{display:grid;grid-template-columns:minmax(180px,1.2fr) minmax(140px,.8fr) minmax(120px,2fr) minmax(110px,auto);align-items:center;gap:18px;padding:9px 0;border-bottom:1px solid var(--line)}
.category-revenue-row:last-child{border-bottom:0}
.category-revenue-name{min-width:0;font-size:13px;overflow-wrap:anywhere}
.commercial-insights .category-revenue-count{margin:0;font-size:11px;line-height:1.4}
.category-revenue-value{white-space:nowrap;text-align:right;font-size:13px;font-variant-numeric:tabular-nums}
.commercial-page .commercial-insights table th{padding:10px 16px}
.commercial-page .commercial-insights table td{padding:9px 16px}
.commercial-insights .commercial-cell-detail{display:flex;flex-wrap:wrap;align-items:baseline;gap:2px 12px}
.commercial-insights .commercial-cell-detail small{margin-top:0}
.commercial-insights .pagination-bar{padding:10px 16px}
.commercial-page .commercial-insights .commercial-empty{min-height:64px;padding:14px}
.commercial-page .commercial-empty{min-height:95px;line-height:1.6}
.commercial-page .table-wrap{border-radius:0;min-width:0}
.commercial-page .table-wrap table td{vertical-align:middle}
.purchase-card::before{display:none}
.purchase-intro{color:var(--ink);background:white;border:1px solid var(--line);padding:20px 22px}
.purchase-intro h2{font-size:18px}.purchase-intro p{max-width:720px;color:var(--muted);line-height:1.6}
.purchase-summary>div{padding:16px 20px}.purchase-table-panel .filter-meta{padding-top:2px}
.campaign-fields{display:grid;grid-template-columns:minmax(0,1fr);gap:16px}.campaign-fields>label{display:grid;gap:7px;min-width:0;color:#555b64;font-size:13px;font-weight:600}.campaign-fields>.wide-field{grid-column:1/-1}.campaign-editor .campaign-preview{margin:0 22px 22px}.campaign-fields>label:last-child{grid-column:1/-1}
.campaign-preview .preview-toolbar{align-items:start;flex-direction:column;gap:6px;line-height:1.5}
.campaign-editor .campaign-actions{margin-top:18px;padding-top:18px;border-top:1px solid var(--line);flex-wrap:wrap}
.campaign-editor .campaign-form{min-width:0}
.recipient-panel .recipient-note{border-top:1px solid var(--line);line-height:1.6;background:#f8f7f4}
.recipient-table input[type=checkbox]{width:18px;height:18px;accent-color:var(--amber)}
.commercial-page .campaign-log{max-width:400px}
.commercial-footnote{line-height:1.65;color:#74777d}
@media(max-width:1000px){.category-revenue-row{grid-template-columns:minmax(0,1fr) auto;gap:6px 14px}.category-revenue-count{grid-column:1;grid-row:2}.category-revenue-value{grid-column:2;grid-row:1/3}.category-revenue-track{grid-column:1/-1;grid-row:3}}
@media(max-width:1100px){.commercial-filters{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:640px){.commercial-filters{grid-template-columns:1fr;padding:16px}.category-revenue-row{grid-template-columns:minmax(0,1fr) auto;gap:8px 14px}.category-revenue-count{grid-column:1;grid-row:2}.category-revenue-value{grid-column:2;grid-row:1/3}.category-revenue-track{grid-column:1/-1;grid-row:3}.commercial-insights>.panel>.section-heading{padding:13px 16px}.commercial-insights .category-revenue-list{padding-inline:16px}.campaign-fields{grid-template-columns:1fr}.campaign-editor .campaign-actions .btn{flex:1 1 100%}.purchase-summary{gap:8px}.purchase-summary>div{padding:12px}.purchase-summary strong{font-size:20px}.commercial-page .list-toolbar{padding:14px 16px}.commercial-page .section-heading{padding:16px}.campaign-form{padding:16px}.campaign-editor .campaign-preview{margin:0 16px 16px}.commercial-compare{align-items:start;flex-wrap:wrap}}
</style>
