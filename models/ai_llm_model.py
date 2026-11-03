# -*- coding: utf-8 -*-
from odoo import fields, models


class AiLlmModel(models.Model):
    _name = "ai.llm.model"
    _description = "Modelo de IA habilitado"
    _order = "config_id, name"

    name = fields.Char(
        string="ID del modelo",
        required=True,
        help="Identificador técnico que espera el proveedor. Ej: deepseek-chat, gpt-4o-mini.",
    )
    label = fields.Char(string="Nombre visible")
    config_id = fields.Many2one(
        "ai.config", string="Proveedor", required=True, ondelete="cascade",
    )
    active = fields.Boolean(default=True)
    is_default = fields.Boolean(string="Predeterminado del proveedor")

    _config_name_uniq = models.Constraint(
        "unique(config_id, name)",
        "Ese modelo ya está cargado para este proveedor.",
    )
