import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { compileScript, parse } from '@vue/compiler-sfc'
import * as vue from 'vue'
import * as notifications from '../src/services/notices.js'
const {notices,showNotice,dismissNotice,mutationMessage}=notifications
const clear=()=>notices.slice().forEach(item=>dismissNotice(item.id,false))

test('avisos ficam por cinco segundos, permitem fechar e não deixam temporizadores ativos',t=>{
  t.mock.timers.enable({apis:['setTimeout']});clear();t.after(clear)
  let closed=0
  showNotice('Cliente salvo.','success',{onClose:()=>closed++})
  t.mock.timers.tick(4999);assert.equal(notices.length,1)
  t.mock.timers.tick(1);assert.equal(notices.length,0);assert.equal(closed,1)
  const id=showNotice('Não foi possível salvar.','error',{onClose:()=>closed++})
  dismissNotice(id);t.mock.timers.tick(5000)
  assert.equal(notices.length,0);assert.equal(closed,2)
})

test('erro atualizado não é apagado pelo temporizador da mensagem anterior',async t=>{
  t.mock.timers.enable({apis:['setTimeout']});clear();t.after(clear)
  const source=readFileSync(new URL('../src/components/GeneralError.vue',import.meta.url),'utf8')
  let code=compileScript(parse(source).descriptor,{id:'notice-test'}).content
  code=code.replace(/import\s+\{([^}]+)\}\s+from\s+'([^']+)'/g,(_,names,path)=>`const {${names}} = dependencies.${path==='vue'?'vue':'notifications'}`)
  const component=new Function('dependencies',code.replace('export default','return'))({vue,notifications})
  component.render=()=>null
  const message=vue.ref('Erro inicial');let closed=0
  const renderer=vue.createRenderer({createComment:()=>({}),insert(){},remove(){},parentNode(){},nextSibling(){}})
  const app=renderer.createApp({render:()=>vue.h(component,{message:message.value,onClose:()=>closed++})})
  app.mount({});t.after(()=>app.unmount())
  t.mock.timers.tick(1000);message.value='Novo erro';await vue.nextTick()
  t.mock.timers.tick(4000);assert.equal(closed,0);assert.equal(notices[0].message,'Novo erro')
  t.mock.timers.tick(1000);assert.equal(closed,1)
})

test('sucessos correspondem a gravações, sem avisar em pesquisas, login ou consultas de IA',()=>{
  assert.equal(mutationMessage('/customers/','post'),'Cliente cadastrado.')
  assert.equal(mutationMessage('/categories/10/','patch'),'Categoria atualizada.')
  assert.equal(mutationMessage('/notifications/10/','delete'),'Notificação excluída.')
  for(const [path,method] of [['/customers/','get'],['/auth/login/','post'],['/ai/ask/','post'],['/rental-quotes/availability/','get']]) assert.equal(mutationMessage(path,method),'')
})
