import { reactive } from 'vue'

export const NOTICE_DURATION = 5000
export const notices = reactive([])
const timers = new Map()
let serial = 0
export function dismissNotice(id, invoke = true) {
  clearTimeout(timers.get(id)); timers.delete(id)
  const index = notices.findIndex(item => item.id === id)
  if (index < 0) return
  const [item] = notices.splice(index,1)
  if (invoke) item.onClose?.()
}
export function showNotice(message, type = 'success', options = {}) {
  const id = ++serial
  notices.push({id, message:String(message), type, ...options})
  timers.set(id,setTimeout(() => dismissNotice(id),NOTICE_DURATION))
  while (notices.length > 3) dismissNotice(notices[0].id)
  return id
}
export function mutationMessage(url, method = 'get') {
  if (!['post','put','patch','delete'].includes(method.toLowerCase())) return ''
  const path = String(url).replace(/^https?:\/\/[^/]+/,'').replace(/^\/api/,'').split('?')[0]
  if (/^\/receivables\/settle\/$/.test(path)) return 'Pagamento registrado. O recibo está disponível para download.'
  if (/^\/receivables\/\d+\/$/.test(path)) return 'Condições da conta atualizadas.'
  const entity = {customers:'Cliente', users:'Funcionário', 'access-groups':'Grupo de permissão', equipment:'Equipamento', categories:'Categoria', vehicles:'Veículo', 'service-orders':'Ordem de serviço', 'maintenance-plans':'Plano de revisão', packages:'Pacote', 'marketing-campaigns':'Campanha', media:'Arquivo', 'rental-quotes':'Orçamento', notifications:'Notificação'}
  const match = path.match(/^\/([^/]+)\/(\d+\/)?$/)
  if (match && entity[match[1]]) {
    // Estas operações já fornecem uma mensagem e seus atalhos de navegação.
    if (match[1] === 'notifications' && method.toLowerCase() !== 'delete') return ''
    const action = method.toLowerCase() === 'delete' ? 'excluído' : method.toLowerCase() === 'post' ? 'cadastrado' : 'atualizado'
    const noun = entity[match[1]], feminine = ['Categoria','Ordem de serviço','Campanha','Notificação'].includes(noun)
    return `${noun} ${feminine ? action.slice(0,-1)+'a' : action}.`
  }
  if (/^\/rental-inspections\/\d+\/$/.test(path)) return 'Inspeção salva.'
  if (/\/documents\/$/.test(path)) return 'Documento gerado.'
  if (/\/maintenance-plans\/\d+\/clone\/$/.test(path)) return 'Planos de revisão criados.'
  if (/^\/(?:purchase-recommendations|ai\/consultations)\/\d+\/decision\/$/.test(path)) return 'Decisão registrada.'
  if (/^\/purchase-recommendations\/analyze\/$/.test(path)) return 'Análise concluída.'
  if (/^\/marketing-campaigns\/\d+\/prepare\/$/.test(path)) return 'Campanha preparada.'
  if (/^\/marketing-campaigns\/\d+\/send\/$/.test(path)) return 'Envio da campanha concluído.'
  return ''
}
