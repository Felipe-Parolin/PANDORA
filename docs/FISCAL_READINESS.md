# Preparação fiscal configurável

O PANDORA oferece uma área **Fiscal** para preparar os dados de uma futura integração. Nenhum CNPJ, razão social, regime, UF ou município é preenchido automaticamente. O emitente começa vazio e é configurado pela empresa que instalar o sistema. Esta etapa contempla um emitente por instalação; não implementa isolamento de múltiplas empresas na mesma base.

## O que está implementado

- Cadastro do emitente: razão social, CNPJ numérico/alfanumérico, regime tributário, situação perante o ICMS, inscrições, CNAE, contato e endereço estruturado.
- Dados fiscais complementares de clientes, sem converter o endereço livre antigo em endereço fiscal por suposição.
- NCM e valor do bem por equipamento, separados do preço da diária e do custo de aquisição.
- Conferência de pendências por locação e exportação JSON no formato `pandora-fiscal-preparation-v1`.
- Permissões `fiscal.view`, `fiscal.manage` e `fiscal.configure`. Administradores com `*` têm acesso; outros grupos precisam receber as permissões apropriadas.
- Auditoria das alterações cadastrais. Consultas não criam cadastros automaticamente.

A conferência valida preenchimento e formato básico. Não consulta situação cadastral na Receita, validade de NCM na tabela vigente, código IBGE em cadastro oficial, inscrições estaduais ou enquadramento tributário. `data_ready: true` significa apenas que os dados básicos foram preenchidos. A API sempre retorna `can_issue: false`, `fiscal_document: false` e `taxes_calculated: false`.

Não há provedor, certificado, assinatura digital, transmissão, numeração fiscal, autorização, cancelamento ou XML fiscal nesta entrega. A prévia JSON e os PDFs comerciais não são notas fiscais. Concluir locações e viagens continua sendo uma ação operacional.

## Integração a realizar

1. Confirmar com a contabilidade o enquadramento da empresa, o documento de cobrança da locação e os documentos de movimentação física dos bens, conforme UF, destinatário e operação.
2. Selecionar e integrar o emissor (API de provedor ou integração com o autorizador) com ambientes e credenciais separados. Segredos e certificados devem ficar em armazenamento seguro, fora do Git; a área atual não os coleta.
3. Mapear os campos exigidos pelos leiautes vigentes, CFOP, códigos de tributação e regras de IBS/CBS sem confundir cobrança da locação, frete e valor do bem.
4. Implementar uma fila transacional com idempotência, consulta de status, retentativas, recepção autenticada de eventos, cancelamento e guarda de XML/protocolos.
5. Homologar os cenários aplicáveis e, depois, habilitar produção de forma explícita.

## Referências oficiais consultadas em 29/10/2026

- [Receita Federal: cronograma dos documentos fiscais da Reforma Tributária](https://www.gov.br/receitafederal/pt-br/assuntos/noticias/2026/julho/receita-federal-e-comite-gestor-do-ibs-publicam-o-cronograma-de-implementacao-dos-documentos-fiscais-eletronicos-da-reforma-tributaria-do-consumo): informa NFS-e para locação de bens móveis no cronograma de 01/12/2026; a aplicação concreta depende do enquadramento e das regras de transição.
- [Portal NFS-e: Nota Técnica 009](https://www.gov.br/nfse/pt-br/noticias/publicada-a-nota-tecnica-009-da-nfs-e/): atualiza, entre outros, o grupo de bens móveis. Os leiautes precisam ser conferidos novamente ao implementar o emissor.
- [SEFAZ-SP: RC 33850/2026](https://legislacao.fazenda.sp.gov.br/Paginas/RC33850_2026.aspx): exemplo paulista de tratamento documental da remessa/retorno de equipamentos; não é uma regra pré-configurada para todas as empresas ou UFs.
- [STF: Súmula Vinculante 31](https://portal.stf.jus.br/jurisprudencia/sumariosumulas.asp?base=26&sumula=1286): trata da não incidência de ISS sobre locação de bens móveis, o que não elimina automaticamente outras obrigações fiscais/documentais.
- [Receita Federal: cálculo do DV do CNPJ alfanumérico](https://www.gov.br/receitafederal/pt-br/centrais-de-conteudo/publicacoes/documentos-tecnicos/cnpj): referência para a validação compartilhada do cadastro de clientes e do emitente.
