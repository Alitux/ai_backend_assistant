# -*- coding: utf-8 -*-
from odoo import fields, models


class AiModelKeyword(models.Model):
    _name = "ai.model.keyword"
    _description = "Alias de modelo de Odoo para el asistente"
    _order = "keyword"

    config_id = fields.Many2one(
        "ai.config", required=True, ondelete="cascade")
    keyword = fields.Char(string="Palabra clave", required=True)
    model_id = fields.Many2one(
        "ir.model",
        string="Modelo Odoo",
        required=True,
        ondelete="cascade",
        domain=[("transient", "=", False)],
    )

    _config_keyword_uniq = models.Constraint(
        "unique(config_id, keyword)",
        "Esa palabra clave ya existe para esta configuración.",
    )
