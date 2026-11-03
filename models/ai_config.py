# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AiConfig(models.Model):
    _name = "ai.config"
    _description = "Configuración del Asistente IA"
    _order = "is_default desc, name"

    name = fields.Char(string="Nombre", required=True)
    provider = fields.Selection(
        [
            ("openai", "OpenAI"),
            ("anthropic", "Anthropic"),
            ("deepseek", "DeepSeek"),
            ("openai_compatible", "OpenAI compatible"),
        ],
        string="Proveedor",
        required=True,
        default="openai",
    )
    api_key = fields.Char(
        string="API Key", required=True, copy=False,
    )
    base_url = fields.Char(
        string="Base URL",
        help="Opcional. Ej. DeepSeek: https://api.deepseek.com/v1. "
             "Si se deja vacío se usa el default del proveedor.",
    )
    active = fields.Boolean(default=True)
    is_default = fields.Boolean(string="Configuración por defecto")
    bot_name = fields.Char(string="Nombre del bot", default="Asistente IA")
    bot_image = fields.Binary(string="Imagen del bot", attachment=True)
    model_ids = fields.One2many(
        "ai.llm.model", "config_id", string="Modelos LLM habilitados",
    )
    allowed_model_ids = fields.Many2many(
        "ir.model",
        string="Modelos Odoo permitidos",
        domain=[("transient", "=", False)],
        help="Solo estos modelos de Odoo puede consultar la IA.",
    )
    keyword_ids = fields.One2many(
        "ai.model.keyword", "config_id", string="Alias de modelos",
    )

    def _sync_bot_partner(self):
        self.ensure_one()
        partner = self.env.ref(
            "ai_backend_assistant.partner_ai_assistant",
            raise_if_not_found=False,
        )
        if not partner:
            return
        values = {}
        if self.bot_name:
            values["name"] = self.bot_name
        if self.bot_image:
            values["image_1920"] = self.bot_image
        if values:
            partner.sudo().write(values)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if record.active and record.is_default:
                record._sync_bot_partner()
        return records

    def write(self, vals):
        result = super().write(vals)
        for record in self:
            if record.active and record.is_default:
                record._sync_bot_partner()
        return result
