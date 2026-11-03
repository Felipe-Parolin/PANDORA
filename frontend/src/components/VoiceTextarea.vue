<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { Check, Mic, Square } from 'lucide-vue-next'
import { aiApi, canUseAI } from '../services/ai'
import { apiError } from '../services/api'
import { useVoiceRecorder } from '../services/voice'

/**
 * Campo de texto livre com ditado por voz. O áudio é transcrito (sem ser guardado) e o texto entra no
 * campo, onde o usuário confere e edita. Com `requireConfirm`, a transcrição precisa ser confirmada
 * antes de ser enviada à IA (RF28); o estado é informado ao pai por `voice-state`.
 */
const props = defineProps({
  modelValue: { type: String, default: '' },
  rows: { type: [Number, String], default: 3 },
  placeholder: { type: String, default: '' },
  id: { type: String, default: undefined },
  ariaLabel: { type: String, default: undefined },
  disabled: Boolean,
  required: Boolean,
  maxlength: { type: [Number, String], default: undefined },
  requireConfirm: Boolean,
})
const emit = defineEmits(['update:modelValue', 'voice-state'])

const voice = useVoiceRecorder()
const busy = ref(false)
const error = ref('')
const source = ref('TEXT')
const confirmed = ref(false)

const showMic = computed(() => canUseAI() && voice.supported && !props.disabled)
const awaiting = computed(() => props.requireConfirm && source.value === 'VOICE' && !confirmed.value)
const timeLabel = computed(() => `${String(Math.floor(voice.seconds.value / 60)).padStart(2, '0')}:${String(voice.seconds.value % 60).padStart(2, '0')}`)

function publish() { emit('voice-state', { source: source.value, confirmed: confirmed.value }) }

function append(text) {
  const current = props.modelValue || ''
  const glue = current && !/\s$/.test(current) ? ' ' : ''
  emit('update:modelValue', `${current}${glue}${text}`.trimStart())
}

async function toggle() {
  error.value = ''
  if (voice.recording.value) {
    const blob = await voice.stop()
    if (!blob?.size) return
    busy.value = true
    try {
      const data = await aiApi.transcribe(blob)
      append(data.text)
      source.value = 'VOICE'
      confirmed.value = !props.requireConfirm
      publish()
    } catch (e) { error.value = apiError(e) } finally { busy.value = false }
  } else {
    await voice.start()
  }
}

function confirm() { confirmed.value = true; publish() }

onBeforeUnmount(() => voice.cancel())
</script>

<template>
  <div class="voice-field">
    <textarea :id="id" :value="modelValue" :rows="rows" :placeholder="placeholder" :disabled="disabled" :required="required" :maxlength="maxlength" :aria-label="ariaLabel" @input="emit('update:modelValue', $event.target.value)" />
    <div v-if="showMic || $slots.actions" class="voice-bar">
      <button v-if="showMic" type="button" class="voice-mic" :class="{ recording: voice.recording.value }" :disabled="busy" :aria-label="voice.recording.value ? 'Parar gravação' : 'Ditar por voz'" @click="toggle">
        <component :is="voice.recording.value ? Square : Mic" :size="16" />{{ voice.recording.value ? `Parar (${timeLabel})` : busy ? 'Transcrevendo…' : 'Ditar' }}
      </button>
      <slot name="actions" />
    </div>
    <div v-if="awaiting" class="ai-notice warn">
      <span>Transcrição inserida. Corrija o texto, se necessário, e confirme que ele representa o relato.</span>
      <button type="button" class="btn secondary" @click="confirm"><Check :size="15" />Confirmar transcrição</button>
    </div>
    <div v-if="voice.error.value || error" class="error-message" role="alert">{{ voice.error.value || error }}</div>
  </div>
</template>
