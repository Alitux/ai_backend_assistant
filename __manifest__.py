# -*- coding: utf-8 -*-
{
    "name": "AI Backend Assistant",
    "version": "19.0.1.7.0",
    "summary": "Asistente IA para el backend de Odoo con tool calling",
    "description": """
        Asistente virtual para el backend de Odoo. Responde consultas sobre
        datos del sistema desde el chat interno usando proveedores LLM
        (OpenAI, Anthropic, DeepSeek y APIs compatibles con OpenAI) con
        tool calling y permisos configurables por modelo.
    """,
    "author": "Alitux <alitux@disroot.org>",
    "website": "https://github.com/Alitux",
    "license": "LGPL-3",
    "category": "Productivity",
    "depends": ["base", "mail", "account"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/bot_partner_data.xml",
        "views/ai_config_views.xml",
        "views/menu_views.xml",
    ],
    "installable": True,
    "application": False,
}
