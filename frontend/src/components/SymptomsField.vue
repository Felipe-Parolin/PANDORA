<script setup>
import { computed, ref } from 'vue'
import { Check, Sparkles, X } from 'lucide-vue-next'
import { aiApi, canUseAI } from '../services/ai'
import { apiError } from '../services/api'
import VoiceTextarea from './VoiceTextarea.vue'

/**
 * Campo "o que precisa ser feito?" do novo chamado. O técnico escreve ou dita; se quiser, a IA reformula
 * o texto considerando o equipamento escolhido (manuais e casos anteriores). A sugestão só entra no campo
 * depois que o usuário aceitar.
 */
const props = defineProps({
  modelValue: { type: String, default: '' },
  id: { type: String, default: undefined },
  equipmentId: { type: [Number, String], default: null },
  maintenanceType: { type: String, default: 'CORRECTIVE' },
  placeholder: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue', 'hints'])

const busy = ref(false)
const error = ref('')
const notice = ref('')
const suggestion = ref(null)
const voiceState = ref({ source: 'TEXT', confirmed: false })

const awaiting = computed(() => voiceState.value.source === 'VOICE' && !voiceState.value.confirmed)
const canRefine = computed(() => props.modelValue.trim().length >= 3 && !busy.value && !awaiting.value)
const manuals = computed(() => (suggestion.value?.sources || []).filter(item => item.kind === 'manual').length)
const cases = computed(() => (suggestion.value?.sources || []).filter(item => item.kind === 'service_order').length)

function compose(extraction) {
  return [extraction.symptoms, extraction.location && `Local: ${extraction.location}`, ...(extraction.additional_info || []).map(item => `• ${item}`)].filter(Boolean).join('\n')
}

async function refine() {
  busy.value = true; error.value = ''; notice.value = ''; suggestion.value = null
  try {
    const data = await aiApi.extractReport({
      text: props.modelValue, input_source: voiceState.value.source, transcription_confirmed: voiceState.value.confirmed,
      equipment: props.equipmentId || undefined, maintenance_type: props.maintenanceType || undefined,
    })
    notice.value = data.notice || ''
    suggestion.value = { text: compose(data.extraction), missing: data.extraction.missing_info || [], sources: data.sources || [], aiAvailable: data.ai_available }
    emit('hints', data)
  } catch (e) { error.value = apiError(e) } finally { busy.value = false }
}

function accept() {
  emit('update:modelValue', suggestion.value.text)
  suggestion.value = null
}
</script>

<template>
  <div class="symptoms-field">
    <VoiceTextarea :id="id" :model-value="modelValue" :rows="4" required require-confirm :placeholder="placeholder" @update:model-value="emit('update:modelValue', $event)" @voice-state="voiceState = $event">
      <template #actions>
        <button v-if="canUseAI()" type="button" class="voice-mic ai" :disabled="!canRefine" @click="refine"><Sparkles :size="14" />{{ busy ? 'Reformulando…' : 'Melhorar com IA' }}</button>
        <small v-if="canUseAI() && !equipmentId" class="ai-hint">Escolha o equipamento antes para a IA considerar os manuais dele.</small>
      </template>
    </VoiceTextarea>
    <div v-if="error" class="error-message" role="alert">{{ error }}</div>
    <div v-if="notice" class="ai-notice warn">{{ notice }}</div>
    <div v-if="suggestion" class="ai-suggestion">
      <header><span class="ai-badge"><Sparkles :size="14" />IA</span><strong>Sugestão de texto</strong></header>
      <p class="ai-suggestion-text">{{ suggestion.text }}</p>
      <small v-if="suggestion.aiAvailable" class="ai-hint">{{ manuals || cases ? `Considerou ${manuals} trecho(s) de manual e ${cases} caso(s) anterior(es) deste equipamento.` : 'Sem manuais ou casos deste equipamento nos registros: apenas o seu relato foi reorganizado.' }}</small>
      <div v-if="suggestion.missing.length" class="ai-missing"><strong>Vale informar também:</strong><ul><li v-for="item in suggestion.missing" :key="item">{{ item }}</li></ul></div>
      <div class="ai-actions">
        <button type="button" class="btn primary" @click="accept"><Check :size="15" />Usar este texto</button>
        <button type="button" class="btn secondary" @click="suggestion = null"><X :size="15" />Manter o meu</button>
      </div>
    </div>
  </div>
</template>
