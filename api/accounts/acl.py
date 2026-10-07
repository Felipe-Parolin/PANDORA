PERMISSION_CATALOG = [
    {"code": "dashboard.view", "label": "Visualizar painel", "module": "Visão geral"},
    {"code": "accounts.users.view", "label": "Consultar funcionários", "module": "Pessoas e acessos"},
    {"code": "accounts.users.manage", "label": "Cadastrar, editar e excluir funcionários", "module": "Pessoas e acessos"},
    {"code": "accounts.groups.manage", "label": "Configurar grupos e permissões", "module": "Pessoas e acessos"},
    {"code": "customers.view", "label": "Consultar clientes", "module": "Clientes"},
    {"code": "customers.manage", "label": "Cadastrar, editar e excluir clientes", "module": "Clientes"},
    {"code": "assets.view", "label": "Consultar equipamentos", "module": "Equipamentos"},
    {"code": "assets.manage", "label": "Cadastrar, editar e excluir equipamentos", "module": "Equipamentos"},
    {"code": "media.view", "label": "Consultar documentos e mídias", "module": "Equipamentos"},
    {"code": "media.manage", "label": "Cadastrar e excluir documentos e mídias", "module": "Equipamentos"},
    {"code": "maintenance.view", "label": "Consultar manutenção e ordens", "module": "Manutenção"},
    {"code": "maintenance.manage", "label": "Cadastrar, editar e excluir manutenções", "module": "Manutenção"},
    {"code": "maintenance.release", "label": "Liberar equipamento após manutenção", "module": "Manutenção"},
    {"code": "logistics.view", "label": "Consultar viagens e veículos", "module": "Transporte"},
    {"code": "logistics.manage", "label": "Planejar viagens e cadastrar veículos", "module": "Transporte"},
    {"code": "rentals.view", "label": "Consultar orçamentos e locações", "module": "Locações"},
    {"code": "rentals.manage", "label": "Cadastrar, editar e excluir orçamentos", "module": "Locações"},
    {"code": "rentals.approve", "label": "Aprovar orçamento e reservar equipamento", "module": "Locações"},
    {"code": "rentals.inspect", "label": "Realizar inspeção de devolução", "module": "Locações"},
    {"code": "rentals.dispatch", "label": "Registrar entrega de equipamentos", "module": "Locações"},
    {"code": "rentals.extend", "label": "Prorrogar locações", "module": "Locações"},
    {"code": "rentals.return", "label": "Registrar e concluir devoluções", "module": "Locações"},
]

VALID_PERMISSIONS = {item["code"] for item in PERMISSION_CATALOG}

DEFAULT_GROUPS = {
    "ADMIN": {
        "name": "Administrador",
        "description": "Acesso completo à configuração e à operação.",
        "permissions": ["*"],
    },
    "SALES": {
        "name": "Vendedor",
        "description": "Clientes, equipamentos, mídias e locações.",
        "permissions": [
            "dashboard.view", "accounts.users.view", "customers.view", "customers.manage",
            "assets.view", "media.view", "media.manage", "rentals.view", "rentals.manage",
            "rentals.approve", "rentals.inspect", "rentals.dispatch", "rentals.extend", "rentals.return",
            "logistics.view", "logistics.manage",
        ],
    },
    "MAINTENANCE": {
        "name": "Manutenção",
        "description": "Equipamentos, mídias, planos, ordens e liberação técnica.",
        "permissions": [
            "dashboard.view", "accounts.users.view", "assets.view", "media.view", "media.manage",
            "maintenance.view", "maintenance.manage", "maintenance.release", "rentals.view", "rentals.inspect",
            "rentals.return", "logistics.view",
        ],
    },
}
