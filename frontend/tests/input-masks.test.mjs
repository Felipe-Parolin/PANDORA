import assert from 'node:assert/strict'
import test from 'node:test'
import { canonicalMask, displayMask, maskError } from '../src/services/inputMasks.js'

test('máscaras preservam os valores enviados: CEP, placa e telefones com DDD', () => {
  for (const [mask, raw, formatted] of [
    ['cep','13614032','13614-032'], ['plate','ABC1D23','ABC-1D23'], ['plate','ABC1234','ABC-1234'],
    ['phone','19999999999','(19) 99999-9999'], ['phone','1935711234','(19) 3571-1234'],
    ['phone','+5519999999999','+55 (19) 99999-9999'],
  ]) {
    assert.equal(displayMask(raw,mask),formatted)
    assert.equal(canonicalMask(formatted,mask),raw)
    assert.equal(maskError(raw,mask),'')
  }
  assert.equal(canonicalMask('abc-1d23','plate'),'ABC1D23')
})

test('moeda, percentuais e decimais usam vírgula na tela e ponto nos dados', () => {
  assert.equal(displayMask('1234.56','money'),'R$ 1.234,56')
  assert.equal(canonicalMask('R$ 1.234,56','money'),'1234.56')
  assert.equal(displayMask('12.5','percent'),'12,5%')
  assert.equal(canonicalMask('12,5%','percent'),'12.5')
  assert.equal(displayMask('1250.75','decimal'),'1.250,75')
  assert.equal(canonicalMask('1.250,75','decimal'),'1250.75')
  assert.equal(displayMask('0','money'),'R$ 0,00')
  assert.equal(canonicalMask('','money'),'')
})

test('máscaras não truncam números nem arredondam silenciosamente dados inválidos', () => {
  assert.match(maskError('136140320','cep'),/oito/)
  assert.match(maskError('123','phone'),/DDD/)
  assert.match(maskError('ABCD123','plate'),/placa/)
  assert.match(maskError('1.234','money'),/casas/)
  assert.equal(displayMask('1.234','money'),'R$ 1,234')
  assert.match(maskError('-1','money',{min:0}),/mínimo/)
  assert.match(maskError('101','percent',{min:0,max:100}),/máximo/)
  assert.match(maskError('0.3','decimal',{step:0.25}),/intervalos/)
  assert.equal(maskError('0.5','decimal',{step:0.25}),'')
  assert.match(maskError('R$ inválido','money'),/válido/)
})
