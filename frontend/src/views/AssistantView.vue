<script setup>
import { matchesSearch, sortRecords, dateValue } from '../services/listFilters'
import { usePagination } from '../services/pagination'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { AlertTriangle, BookOpen, Check, History, Search, RefreshCw, Wrench } from 'lucide-vue-next'
import AIConsultPanel from '../components/AIConsultPanel.vue'
import AISourceList from '../components/AISourceList.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { aiApi } from '../services/ai'
import { api, apiError, rows, fetchAll } from '../services/api'

const route = useRoute()
const tab = ref(route.query.mode === 'ask' ? 'ask' : 'diagnose')
const equipment = ref([])
const equipmentId = ref(route.query.equipment ? Number(route.query.equipment) : '')
const status = ref(null)
const question = ref('')
const answer = ref(null)
const history = ref([])
const busy = ref(false)
const error = ref('')
const loadError = ref('')
const historySearch = ref(''), historyKind = ref(''), historyOrdering = ref('-created'), historyLoading = ref(false)
const filteredHistory = computed(() => sortRecords(history.value.filter(item => (!historyKind.value || item.kind === historyKind.value) && matchesSearch(historySearch.value, item.equipment_name, item.order_number, item.user_name, item.kind_label, ...item.decisions.map(decision => decision.reason))), historyOrdering.value, { created: item => dateValue(item.created_at), equipment: item => item.equipment_name }))
const historyKinds = computed(() => [...new Map(history.value.map(item => [item.kind, item.kind_label])).entries()])
const prompts = [{ label: 'Revisões', text: 'Quais revisões e verificações estão previstas no manual?' }, { label: 'Lubrificação', text: 'Quais são os pontos e intervalos de lubrificação indicados no manual?' }, { label: 'Segurança', text: 'Quais cuidados de segurança devo seguir antes de operar este equipamento?' }]
let askRequest = 0

const selected = computed(() => equipment.value.find(item => item.id === equipmentId.value))
const banner = computed(() => {
  if (!status.value) return null
  if (!status.value.configured) return 'A IA generativa não está disponível neste ambiente. A busca de casos e manuais continua funcionando.'
  if (!status.value.available) return 'O serviço de IA está temporariamente indisponível. A busca de casos e manuais continua funcionando.'
  return null
})
const statusTone = { OK: 'success', DEGRADED: 'warning', ERROR: 'danger' }
const decisionLabel = { ACCEPTED: 'Aceita', CORRECTED: 'Corrigida', REJECTED: 'Rejeitada' }

async function ask() {
  if (busy.value || question.value.trim().length < 3) return
  busy.value = true; error.value = ''; answer.value = null
  const request = ++askRequest
  try { const result = await aiApi.ask({ question: question.value.trim(), equipment: equipmentId.value || undefined }); if (request === askRequest) answer.value = result }
  catch (e) { if (request === askRequest) error.value = apiError(e) } finally { busy.value = false }
}
async function loadHistory() {
  historyLoading.value = true
  try { history.value = rows((await fetchAll('/ai/consultations/')).data) } catch (e) { error.value = apiError(e) }
  finally { historyLoading.value = false }
}
function selectTab(key) {
  tab.value = key; error.value = ''
  if (key === 'history') loadHistory()
}
const sourceById = id => answer.value?.sources.find(item => item.id === id)

watch([equipmentId, question], () => { askRequest += 1; answer.value = null; error.value = '' }, { flush: 'sync' })
watch(() => route.query.equipment, value => { if (value) equipmentId.value = Number(value) })
onMounted(async () => {
  try {
    const [list, state] = await Promise.all([fetchAll('/equipment/'), aiApi.status()])
    equipment.value = rows(list.data)
    status.value = state
  } catch (e) { loadError.value = apiError(e) }
})

const { page: historyPage, items: historyRows } = usePagination(filteredHistory, [historySearch, historyKind, historyOrdering])
</script>

<template>
  <div class="page assistant-page">
    <header class="page-heading compact"><div><span class="eyebrow">APOIO TÉCNICO</span><h1>Assistente de IA</h1><p>Consulte manuais e avalie hipóteses para o equipamento em atendimento.</p></div></header>
    <div v-if="banner" class="ai-notice warn page-notice"><AlertTriangle :size="16" />{{ banner }}</div>
    <GeneralError v-if="loadError" :message="loadError" @close="loadError = ''" />
    <div class="tabs assistant-tabs" role="tablist" aria-label="Modos do assistente">
      <button role="tab" :aria-selected="tab === 'diagnose'" :class="{ active: tab === 'diagnose' }" @click="selectTab('diagnose')"><Wrench :size="18" />Diagnóstico assistido</button>
      <button role="tab" :aria-selected="tab === 'ask'" :class="{ active: tab === 'ask' }" @click="selectTab('ask')"><BookOpen :size="18" />Perguntar aos manuais</button>
      <button role="tab" :aria-selected="tab === 'history'" :class="{ active: tab === 'history' }" @click="selectTab('history')"><History :size="18" />Histórico de consultas</button>
    </div>
    <section v-if="tab !== 'history'" class="panel assistant-workspace">
      <div class="form-field assistant-equipment-field"><label for="assistant-equipment">{{ tab === 'ask' ? 'Equipamento (opcional)' : 'Equipamento' }}<span class="required-mark" aria-hidden="true" v-if="tab === 'diagnose'"> *</span></label><AppSelect :required="tab === 'diagnose'" id="assistant-equipment" searchable v-model="equipmentId"><option value="">{{ tab === 'ask' ? 'Todos os manuais autorizados' : 'Buscar equipamento...' }}</option><option v-for="item in equipment" :key="item.id" :value="item.id">{{ item.internal_code }} · {{ item.name }}</option></AppSelect></div>
        <template v-if="tab === 'diagnose'">
          <AIConsultPanel v-if="equipmentId" :key="equipmentId" :equipment-id="equipmentId" />
          <p v-else class="assistant-select-hint">Selecione um equipamento acima para iniciar o diagnóstico.</p>
        </template>
        <template v-else>
          <div class="assistant-section-title"><BookOpen :size="20" /><h2>Consulta aos manuais</h2></div>
          <form class="assistant-question-form" @submit.prevent="ask"><div class="form-field"><label for="assistant-question">O que você precisa conferir?<span class="required-mark" aria-hidden="true"> *</span></label><textarea id="assistant-question" v-model="question" rows="4" required minlength="3" placeholder="Ex.: Qual é o intervalo de lubrificação da coroa da betoneira?" /></div><div class="assistant-query-tools"><div class="assistant-prompt-list"><span>Preencher pergunta:</span><button v-for="prompt in prompts" :key="prompt.label" type="button" @click="question = prompt.text">{{ prompt.label }}</button></div><button class="btn primary" :disabled="busy || question.trim().length < 3"><Search :size="17" />{{ busy ? 'Consultando...' : 'Perguntar aos manuais' }}</button></div><small v-if="selected" class="muted-text">Fontes de {{ selected.name }} e modelos iguais.</small><div v-if="error" class="error-message" role="alert">{{ error }}</div></form>
          <section v-if="answer" class="assistant-answer" aria-label="Resultado da consulta">
            <div v-if="answer.notice" class="ai-notice warn"><AlertTriangle :size="16" />{{ answer.notice }}</div>
            <div v-if="answer.analysis?.answer" class="ai-answer"><h3>Resposta</h3><p>{{ answer.analysis.answer }}</p><ul v-if="answer.analysis.citations.length" class="ai-citations"><li v-for="item in answer.analysis.citations" :key="item.source_id + item.quote"><strong>{{ item.source_id }}</strong> “{{ item.quote }}” <span v-if="sourceById(item.source_id)" class="ai-cite-from">— {{ sourceById(item.source_id).manual_name || sourceById(item.source_id).title }}<template v-if="sourceById(item.source_id).page">, p. {{ sourceById(item.source_id).page }}</template></span><em v-if="!item.verified" class="ai-unverified">trecho não confirmado na fonte</em></li></ul></div>
            <div v-if="answer.analysis?.insufficient_data" class="ai-notice warn"><AlertTriangle :size="16" /><span><strong>Base insuficiente.</strong> {{ answer.analysis.limitations || 'Confira diretamente nas fontes.' }}</span></div><h3>Fontes consultadas</h3><AISourceList :sources="answer.sources" empty="Nenhum manual ou caso autorizado relacionado." /><p class="ai-disclaimer">{{ answer.disclaimer }}</p>
          </section>
        </template>
    </section>
    <section v-else class="panel assistant-history">
      <header class="assistant-history-heading"><div><h2>Consultas registradas</h2><p>{{ filteredHistory.length }} consulta(s)</p></div><button class="btn secondary" :disabled="historyLoading" @click="loadHistory"><RefreshCw :size="17" />Atualizar histórico</button></header>
      <GeneralError v-if="error" :message="error" @close="error = ''" />
      <ListToolbar><template #search><label class="list-control list-search"><span>Pesquisar</span><span class="search-box"><Search :size="17" /><input v-model="historySearch" type="search" placeholder="Equipamento, OS ou responsável" /></span></label></template><template #filters><label class="list-control"><span>Tipo de consulta</span><AppSelect v-model="historyKind"><option value="">Todos</option><option v-for="[value, label] in historyKinds" :key="value" :value="value">{{ label }}</option></AppSelect></label><ListOrdering v-model="historyOrdering" :options="[['-created', 'Mais recentes'], ['created', 'Mais antigas'], ['equipment', 'Equipamento A–Z']]" /></template></ListToolbar>
      <p v-if="historyLoading" class="assistant-loading" role="status">Carregando consultas...</p>
      <div class="table-wrap"><table><thead><tr><th>Data</th><th>Tipo</th><th>Usuário</th><th>Equipamento / OS</th><th>Resultado</th><th>Decisão humana</th></tr></thead><tbody><tr v-for="item in historyRows" :key="item.id"><td>{{ new Date(item.created_at).toLocaleString('pt-BR') }}</td><td>{{ item.kind_label }}</td><td>{{ item.user_name || '—' }}</td><td>{{ item.equipment_name || '—' }}<template v-if="item.order_number"> · {{ item.order_number }}</template></td><td><StatusBadge :value="item.status === 'OK' ? 'APPROVED' : item.status === 'DEGRADED' ? 'PENDING' : 'BLOCKED'" :label="item.status_label" /></td><td><template v-if="item.decisions.length"><Check :size="14" /> {{ decisionLabel[item.decisions[0].decision] }} — {{ item.decisions[0].reason }}</template><template v-else>—</template></td></tr><tr v-if="!filteredHistory.length && !historyLoading"><td colspan="6" class="empty-cell">Nenhuma consulta encontrada.</td></tr></tbody></table></div><PaginationBar v-model="historyPage" :total="filteredHistory.length" />
    </section>
  </div>
</template>
