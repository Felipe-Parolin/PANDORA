# Arquitetura inicial

## Visão de contexto

```text
Usuário interno
      │ HTTPS + JWT
      ▼
Vue 3 / Vite ───────► Django REST API ───────► PostgreSQL
                              │
                              ├── armazenamento de arquivos (MEDIA_ROOT no MVP)
                              └── serviço de IA/transcrição (integração futura e opcional)
```

A locação e a manutenção não dependem da disponibilidade de IA. Uma futura integração deve consultar apenas conteúdo autorizado, indicar fontes e manter a decisão final com o técnico.

## Módulos de domínio

| Módulo | Responsabilidade |
|---|---|
| `accounts` | usuário interno, grupos ACL configuráveis, JWT e permissões |
| `customers` | cliente PF/PJ, documento, contato e situação |
| `assets` | categoria, equipamento, QR token e acervo de mídias |
| `maintenance` | plano, alertas, ordem de serviço, atividades e liberação |
| `rentals` | orçamento, reserva, inspeções, entrega, prorrogação, devolução e disponibilidade |
| `core` | dashboard, auditoria e configuração compartilhada |

## Regras críticas implementadas

1. Um cliente deve possuir CPF ou CNPJ compatível com seu tipo.
2. Número de série, código interno e token de QR Code são únicos.
3. Uma mídia pertence a exatamente um equipamento, OS, orçamento ou inspeção.
4. Um orçamento aprovado bloqueia sobreposições do mesmo equipamento.
5. OS aberta ou manutenção crítica vencida impede a aprovação de nova reserva.
6. A liberação técnica exige OS concluída, teste final e técnico responsável.
7. Valores do orçamento são recalculados no backend; o frontend não é a fonte de verdade.
8. A mesma permissão ACL controla a rota da API e a ação exibida na interface.
9. Exclusões com vínculos protegidos retornam conflito em vez de remover histórico operacional.
10. O QR Code aponta para a consulta autenticada do equipamento e pode ser baixado em PNG.
11. Um chamado abandonado exige justificativa, mantém o equipamento bloqueado e fica disponível para redistribuição.
12. A seleção de locação antecipa a mesma regra de disponibilidade reaplicada na aprovação.
13. Cada equipamento reservado abre uma OS de pré-locação na Manutenção, vinculada à inspeção. A própria OS pendente não bloqueia sua reserva; outras OS abertas continuam bloqueando.
14. A entrega exige checklist pré-locação aprovado e OS liberada para todos os itens. Falha crítica mantém a OS aberta e o equipamento bloqueado.
15. A prorrogação repete a verificação de disponibilidade e preserva o histórico de datas e condições.
16. A devolução mantém o equipamento indisponível até a inspeção final; avarias geram OS pós-locação.
17. Planos podem vencer por data ou horas de uso, com faixas de aviso configuráveis.

## Ciclo da locação

```text
Rascunho/Enviado → Reservado → Em locação → Devolvido/em inspeção → Concluído
        │              │
        └──────────────┴──→ Cancelado (antes da entrega)
```

Cada transição operacional registra usuário, data, condições e `AuditLog`. Inspeções são individuais por equipamento e usam o modelo configurado em sua categoria.

## Padrões criacionais da modelagem

- **Singleton:** `core.patterns.AISettings` usa cache de instância para configuração imutável por processo. Dados de usuário não são guardados nela.
- **Builder:** `maintenance.patterns.ServiceOrderBuilder` monta a abertura da OS por etapas e reinicia o estado após cada construção.
- **Factory Method:** `ReportProcessorFactory` seleciona processadores de texto e, futuramente, áudio/transcrição.
- **Abstract Factory:** `MaintenanceKitFactory` entrega checklist e roteiro compatíveis com manutenção preventiva ou corretiva.

Esses padrões ficam no serviço de aplicação, sem duplicar as entidades de domínio.

A correspondência detalhada entre os diagramas acadêmicos e as classes Python está em [Rastreabilidade dos padrões](PATTERN_TRACEABILITY.md).

## Evolução recomendada

- trocar `MEDIA_ROOT` por armazenamento de objetos com verificação antimalware;
- adicionar trilha automática para CRUD genérico por middleware, complementando os eventos de locação;
- criar PDF versionado do orçamento e fluxo de aceite;
- adotar tarefas assíncronas para relatórios, transcrição e IA;
- incluir OpenAPI/Swagger, testes de integração concorrente e CI no GitHub Actions.
