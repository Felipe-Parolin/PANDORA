<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { AlertTriangle, Check, History, Lock, ShieldCheck, Sparkles } from 'lucide-vue-next'
import { aiApi, confidenceLabel } from '../services/ai'
import { api, apiError, can, rows } from '../services/api'
import AISourceList from './AISourceList.vue'
import RecurrenceBadge from './RecurrenceBadge.vue'
import VoiceTextarea from './VoiceTextarea.vue'

const props = defineProps({
  equipmentId: { type: [Number, String], default: null },
  order: { type: Object, default: null },
  initialSymptoms: { type: String, default: '' },
})
const emit = defineEmits(['applied'])

const symptoms = ref(props.initialSymptoms)
const result = ref(null)
const busy = ref(false)
const error = ref('')
const highlight = ref('')
const sourceTab = ref('service_order')
const history = ref([])
const decided = ref(null)
const choice = reactive({ decision: 'ACCEPTED', reason: '', finalText: '', apply: false, hypothesis: 0, finalTests: '', partsUsed: '' })
const voiceState = ref({ source: 'TEXT', confirmed: false })
const terminal = ['COMPLETED', 'CANCELLED']

const hypotheses = computed(() => result.value?.analysis?.hypotheses || [])
const ordersFound = computed(() => (result.value?.sources || []).filter(item => item.kind === 'service_order'))
const manualsFound = computed(() => (result.value?.sources || []).filter(item => item.kind === 'manual'))
const canApply = computed(() => Boolean(props.order && can('maintenance.manage') && !terminal.includes(props.order.status)))
const needsText = computed(() => choice.decision !== 'REJECTED')
const awaitingVoice = computed(() => voiceState.value.source === 'VOICE' && !voiceState.value.confirmed)
const canConsult = computed(() => Boolean(props.equipmentId || props.order) && (symptoms.value.trim().length >= 3 || props.order) && !awaitingVoice.value)
// OS encerrada: a IA fica travada e só mostra a resposta que foi adotada na OS.
const locked = computed(() => Boolean(props.order && terminal.includes(props.order.status)))
const adopted = computed(() => {
  for (const consultation of history.value) {
    const decision = (consultation.decisions || []).find(item => item.decision !== 'REJECTED' && item.applied_to_order)
      || (consultation.decisions || []).find(item => item.decision !== 'REJECTED')
    if (decision) return { consultation, decision }
  }
  return null
})
const stampedNotes = computed(() => (props.order?.diagnosis || '').split(/\n{2,}/).map(item => item.trim()).filter(item => item.startsWith('[Apoio de IA validado')))

watch(() => props.initialSymptoms, value => { if (!result.value) symptoms.value = value })
watch(() => choice.hypothesis, fillFromHypothesis)
watch(() => choice.decision, () => { choice.apply = choice.decision !== 'REJECTED' && canApply.value })

function fillFromHypothesis() {
  const item = hypotheses.value[choice.hypothesis]
  choice.finalText = item ? `${item.title}. ${item.rationale}`.trim() : ''
  // Sugestão de testes a partir de "O que verificar"; o técnico edita antes de autorizar.
  choice.finalTests = (result.value?.analysis?.verifications || []).map(line => `• ${line}`).join('\n')
}

async function loadHistory() {
  if (!props.order) return
  try { history.value = rows(await aiApi.consultations({ service_order: props.order.id })) } catch { history.value = [] }
}

async function consult() {
  busy.value = true; error.value = ''; decided.value = null
  try {
    result.value = await aiApi.diagnose({
      equipment: props.equipmentId || undefined, service_order: props.order?.id,
      symptoms: symptoms.value.trim() || undefined, input_source: voiceState.value.source, transcription_confirmed: voiceState.value.confirmed,
    })
    Object.assign(choice, { decision: 'ACCEPTED', reason: '', apply: canApply.value, hypothesis: 0, partsUsed: '' })
    fillFromHypothesis()
    sourceTab.value = ordersFound.value.length || !manualsFound.value.length ? 'service_order' : 'manual'
    await loadHistory()
  } catch (e) { error.value = apiError(e) } finally { busy.value = false }
}

function jumpTo(id) {
  highlight.value = id
  const source = result.value.sources.find(item => item.id === id)
  if (source) sourceTab.value = source.kind
  window.setTimeout(() => document.getElementById(`ai-source-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 50)
}

async function submitDecision() {
  busy.value = true; error.value = ''
  try {
    decided.value = await aiApi.decide(result.value.consultation_id, {
      decision: choice.decision, reason: choice.reason, final_text: needsText.value ? choice.finalText : '', apply_to_order: choice.apply && needsText.value,
      ...(choice.apply && needsText.value ? { final_tests: choice.finalTests, parts_used: choice.partsUsed } : {}),
    })
    await loadHistory()
    if (decided.value.applied_to_order) emit('applied')
  } catch (e) { error.value = apiError(e) } finally { busy.value = false }
}

const decisionLabel = { ACCEPTED: 'Aceita', CORRECTED: 'Corrigida', REJECTED: 'Rejeitada' }
onMounted(loadHistory)
</script>

<template>
  <section class="ai-panel" aria-label="Assistente de IA">
    <header class="ai-panel-head">
      <span class="ai-badge"><Sparkles :size="15" />IA</span>
      <div><strong>Assistente técnico</strong><small>Sugere hipóteses a partir de casos e manuais autorizados. A decisão é sempre do técnico.</small></div>
    </header>

    <div v-if="locked" class="ai-locked">
      <div class="ai-notice ok"><Lock :size="16" /><span><strong>OS encerrada: consulta travada.</strong> Abaixo está a resposta da IA que foi adotada e registrada nesta OS.</span></div>
      <article v-if="adopted" class="ai-adopted">
        <header><strong>{{ decisionLabel[adopted.decision.decision] }} por {{ adopted.decision.decided_by_name || 'técnico' }}</strong><small>{{ new Date(adopted.decision.created_at).toLocaleString('pt-BR') }}</small></header>
        <p v-if="adopted.consultation.response?.analysis?.summary" class="ai-summary">{{ adopted.consultation.response.analysis.summary }}</p>
        <div v-if="adopted.decision.final_text"><h4>Texto adotado</h4><p>{{ adopted.decision.final_text }}</p></div>
        <div><h4>Motivo da decisão</h4><p>{{ adopted.decision.reason }}</p></div>
        <small v-if="adopted.decision.applied_to_order" class="ai-hint">Este conteúdo foi registrado no diagnóstico da OS.</small>
      </article>
      <template v-else-if="stampedNotes.length"><article v-for="note in stampedNotes" :key="note" class="ai-adopted"><p>{{ note }}</p></article></template>
      <p v-else class="ai-empty">Nenhuma recomendação da IA foi adotada nesta OS.</p>
    </div>
    <template v-else>
    <div class="form-field">
      <label :for="`ai-symptoms-${order?.id || 'x'}`">Problema a analisar<span class="required-mark" aria-hidden="true" v-if="!order"> *</span></label>
      <VoiceTextarea :id="`ai-symptoms-${order?.id || 'x'}`" v-model="symptoms" :rows="3" :required="!order" require-confirm placeholder="Descreva o sintoma: quando ocorre, ruídos, o que já foi testado…" @voice-state="voiceState = $event" />
    </div>
    <div class="ai-actions">
      <button type="button" class="btn primary" :disabled="busy || !canConsult" @click="consult"><Sparkles :size="16" />{{ busy && !decided ? 'Consultando…' : result ? 'Consultar novamente' : 'Consultar IA' }}</button>
      <small>Dados pessoais são removidos antes do envio. Cada consulta fica registrada na auditoria.</small>
    </div>
    <div v-if="error" class="error-message" role="alert">{{ error }}</div>

    <template v-if="result">
      <div v-if="result.notice" class="ai-notice warn"><AlertTriangle :size="16" />{{ result.notice }}</div>
      <RecurrenceBadge v-if="result.recurrence" :assessment="result.recurrence" detailed />

      <div v-if="result.analysis" class="ai-analysis">
        <p v-if="result.analysis.summary" class="ai-summary">{{ result.analysis.summary }}</p>
        <div v-if="result.analysis.insufficient_data" class="ai-notice warn"><AlertTriangle :size="16" /><span><strong>Dados insuficientes.</strong> {{ result.analysis.limitations }}</span></div>

        <h4>Hipóteses</h4>
        <ol class="ai-hypotheses">
          <li v-for="item in hypotheses" :key="item.title">
            <div class="ai-hyp-head"><strong>{{ item.title }}</strong><span class="ai-confidence" :class="item.confidence">{{ confidenceLabel[item.confidence] }}</span></div>
            <p>{{ item.rationale }}</p>
            <div class="ai-hyp-sources">
              <button v-for="id in item.source_ids" :key="id" type="button" class="ai-source-chip" @click="jumpTo(id)">{{ id }}</button>
              <small v-if="!item.grounded">Sem fonte nos registros: raciocínio geral do modelo.</small>
            </div>
          </li>
          <li v-if="!hypotheses.length" class="ai-empty">A IA não apresentou hipóteses com base nos dados disponíveis.</li>
        </ol>

        <div class="ai-two-col">
          <div v-if="result.analysis.verifications.length"><h4>O que verificar</h4><ul class="ai-list"><li v-for="item in result.analysis.verifications" :key="item">{{ item }}</li></ul></div>
          <div v-if="result.analysis.possible_actions.length"><h4>Ações possíveis</h4><ul class="ai-list"><li v-for="item in result.analysis.possible_actions" :key="item">{{ item }}</li></ul></div>
        </div>
        <p v-if="result.analysis.limitations && !result.analysis.insufficient_data" class="ai-limits"><strong>Limites:</strong> {{ result.analysis.limitations }}</p>
      </div>

      <div class="ai-sources-wrap">
        <div class="ai-tabs" role="tablist">
          <button type="button" role="tab" :aria-selected="sourceTab === 'service_order'" :class="{ active: sourceTab === 'service_order' }" @click="sourceTab = 'service_order'">Casos semelhantes ({{ ordersFound.length }})</button>
          <button type="button" role="tab" :aria-selected="sourceTab === 'manual'" :class="{ active: sourceTab === 'manual' }" @click="sourceTab = 'manual'">Manuais ({{ manualsFound.length }})</button>
        </div>
        <AISourceList v-if="sourceTab === 'service_order'" :sources="ordersFound" :highlight="highlight" empty="Nenhuma OS anterior semelhante nos registros que você pode consultar." />
        <AISourceList v-else :sources="manualsFound" :highlight="highlight" empty="Nenhum trecho de manual relacionado. Envie o PDF do manual na tela do equipamento." />
      </div>

      <div class="ai-decision">
        <header><ShieldCheck :size="18" /><div><strong>Sua decisão</strong><small>Registrada no histórico e na auditoria, junto com o motivo.</small></div></header>
        <div v-if="decided" class="ai-notice ok"><Check :size="16" />Decisão registrada: {{ decisionLabel[decided.decision] }}.<template v-if="decided.applied_to_order"> Campos da OS preenchidos (Diagnóstico<template v-if="choice.finalTests.trim()">, Testes finais</template><template v-if="choice.partsUsed.trim()">, Peças</template>). Revise e clique em salvar.</template></div>
        <template v-else>
          <div class="ai-choice" role="radiogroup" aria-label="Decisão sobre a recomendação">
            <label :class="{ on: choice.decision === 'ACCEPTED' }"><input v-model="choice.decision" type="radio" value="ACCEPTED">Aceitar</label>
            <label :class="{ on: choice.decision === 'CORRECTED' }"><input v-model="choice.decision" type="radio" value="CORRECTED">Corrigir</label>
            <label :class="{ on: choice.decision === 'REJECTED' }"><input v-model="choice.decision" type="radio" value="REJECTED">Rejeitar</label>
          </div>
          <div v-if="needsText && hypotheses.length > 1" class="form-field"><label>Hipótese adotada</label><AppSelect v-model.number="choice.hypothesis"><option v-for="(item, index) in hypotheses" :key="item.title" :value="index">{{ item.title }}</option></AppSelect></div>
          <div v-if="needsText" class="form-field"><label>{{ choice.decision === 'CORRECTED' ? 'Diagnóstico corrigido pelo técnico' : 'Diagnóstico validado' }}<span class="required-mark" aria-hidden="true" v-if="choice.decision === 'CORRECTED'"> *</span></label><VoiceTextarea v-model="choice.finalText" :rows="3" :required="choice.decision === 'CORRECTED'" /></div>
          <div class="form-field"><label>Motivo da decisão<span class="required-mark" aria-hidden="true"> *</span></label><VoiceTextarea v-model="choice.reason" :rows="2" required placeholder="Ex.: confirmei com o multímetro; o caso anterior não se aplica a este modelo." /></div>
          <label v-if="canApply && needsText" class="check-line"><input v-model="choice.apply" type="checkbox">Autorizo preencher os campos da OS abaixo com este conteúdo (com identificação do técnico)</label>
          <template v-if="canApply && needsText && choice.apply">
            <div class="form-field"><label>Testes finais (a partir de “O que verificar”)</label><VoiceTextarea v-model="choice.finalTests" :rows="3" /></div>
            <div class="form-field"><label>Peças utilizadas (opcional)</label><VoiceTextarea v-model="choice.partsUsed" :rows="2" placeholder="A IA não sugere peças: informe só o que realmente foi usado." /></div>
          </template>
          <div class="ai-actions"><button type="button" class="btn secondary" :disabled="busy || choice.reason.trim().length < 3 || (choice.decision === 'CORRECTED' && !choice.finalText.trim())" @click="submitDecision">{{ choice.apply && needsText ? 'Registrar decisão e preencher a OS' : 'Registrar decisão' }}</button></div>
        </template>
      </div>
      <p class="ai-disclaimer">{{ result.disclaimer }}</p>
    </template>
    </template>

    <details v-if="history.length" class="ai-history">
      <summary><History :size="15" />Consultas anteriores desta OS ({{ history.length }})</summary>
      <ul>
        <li v-for="item in history" :key="item.id">
          <strong>{{ new Date(item.created_at).toLocaleString('pt-BR') }}</strong> · {{ item.kind_label }} · {{ item.user_name || 'Usuário' }}
          <span v-if="item.decisions.length"> → {{ decisionLabel[item.decisions[0].decision] }}: {{ item.decisions[0].reason }}</span>
          <span v-else> → sem decisão registrada</span>
        </li>
      </ul>
    </details>
  </section>
</template>
