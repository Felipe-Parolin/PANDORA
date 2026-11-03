import { ref } from 'vue'

const CANDIDATES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus']

/** Gravação de voz no navegador (MediaRecorder). O áudio vai apenas para a transcrição; nada é guardado no servidor. */
export function useVoiceRecorder() {
  const supported = typeof window !== 'undefined' && Boolean(navigator.mediaDevices?.getUserMedia) && typeof MediaRecorder !== 'undefined'
  const recording = ref(false)
  const seconds = ref(0)
  const error = ref('')
  let recorder = null
  let stream = null
  let chunks = []
  let timer = null

  async function start() {
    error.value = ''
    if (!supported) { error.value = 'Este navegador não permite gravar áudio. Digite o relato.'; return false }
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch {
      error.value = 'Permita o uso do microfone para gravar o relato.'
      return false
    }
    const mimeType = CANDIDATES.find(type => MediaRecorder.isTypeSupported?.(type)) || ''
    recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
    chunks = []
    recorder.ondataavailable = event => { if (event.data.size) chunks.push(event.data) }
    recorder.start()
    recording.value = true
    seconds.value = 0
    timer = window.setInterval(() => { seconds.value += 1; if (seconds.value >= 120) stop() }, 1000)
    return true
  }

  function stop() {
    return new Promise((resolve) => {
      window.clearInterval(timer)
      if (!recorder || recorder.state === 'inactive') { recording.value = false; resolve(null); return }
      recorder.onstop = () => {
        stream?.getTracks().forEach(track => track.stop())
        recording.value = false
        resolve(new Blob(chunks, { type: recorder.mimeType || 'audio/webm' }))
      }
      recorder.stop()
    })
  }

  function cancel() {
    window.clearInterval(timer)
    if (recorder && recorder.state !== 'inactive') { recorder.onstop = null; recorder.stop() }
    stream?.getTracks().forEach(track => track.stop())
    recording.value = false
  }

  return { supported, recording, seconds, error, start, stop, cancel }
}
