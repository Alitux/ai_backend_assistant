# -*- coding: utf-8 -*-
import logging

from odoo import models

_logger = logging.getLogger(__name__)


class DiscussChannel(models.Model):
    _inherit = "discuss.channel"

    def message_post(self, **kwargs):
        message = super().message_post(**kwargs)
        try:
            self._maybe_ai_reply(message)
        except Exception:
            _logger.exception("Error en el hook del asistente IA")
        return message

    def _maybe_ai_reply(self, message):
        if message.message_type != "comment" or not message.author_id:
            return
        bot_partner = self.env.ref(
            "ai_backend_assistant.partner_ai_assistant",
            raise_if_not_found=False,
        )
        if not bot_partner or message.author_id.id == bot_partner.id:
            return
        body = message.body or ""
        body = body.replace("&nbsp;", " ")
        is_dm = (
            self.channel_type == "chat"
            and bot_partner in self.channel_partner_ids
        )
        mentioned = ("@" + (bot_partner.name or "")) in body
        if not (is_dm or mentioned):
            return
        self.env["ai.agent.service"].sudo().reply(self, message)
