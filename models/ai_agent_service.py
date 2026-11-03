# -*- coding: utf-8 -*-
import html
import json
import logging
import re
from datetime import datetime, time, timedelta
from time import sleep

import requests

from odoo import _, fields, models

_logger = logging.getLogger(__name__)


TOOLS = [
    {
        "name": "search_odoo_model",
        "description": "Consulta registros de un modelo de Odoo permitido.",
        "parameters": {
            "type": "object",
            "properties": {
                "model": {"type": "string", "description": "Nombre técnico, ej. res.partner."},
                "domain": {"type": "array", "description": "Dominio Odoo, ej. [[\"name\",\"ilike\",\"Juan\"]].", "items": {}},
                "fields": {"type": "array", "description": "Campos a devolver.", "items": {"type": "string"}},
                "limit": {"type": "integer", "description": "Máximo de registros (máx. 50)."},
            },
            "required": ["model"],
        },
    },
    {
        "name": "count_records",
        "description": "Cuenta registros de un modelo permitido por texto (nombres, relaciones o etiquetas) y rango de fechas opcional. Usar para preguntas de 'cuántos ... en <mes>'.",
        "parameters": {
            "type": "object",
            "properties": {
                "model": {"type": "string", "description": "Nombre técnico, ej. medical.emergency."},
                "text": {"type": "string", "description": "Texto a buscar, ej. verde."},
                "date_from": {"type": "string", "description": "Fecha desde YYYY-MM-DD."},
                "date_to": {"type": "string", "description": "Fecha hasta YYYY-MM-DD."},
                "date_field": {"type": "string", "description": "Campo de fecha opcional; si se omite se detecta."},
            },
            "required": ["model"],
        },
    },
    {
        "name": "count_odoo_records",
        "description": "Cuenta registros de un modelo Odoo permitido. Usar para preguntas de 'cuántos'.",
        "parameters": {
            "type": "object",
            "properties": {
                "model": {"type": "string", "description": "Nombre técnico, ej. res.partner."},
                "domain": {"type": "array", "description": "Dominio Odoo, ej. [[\"name\",\"ilike\",\"Alejandro\"]].", "items": {}},
            },
            "required": ["model"],
        },
    },
    {
        "name": "count_contacts",
        "description": "Cuenta contactos cuyo nombre o apellido contiene el texto. Usar para preguntas sobre contactos, nombres o apellidos.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Nombre o apellido a buscar."},
            },
            "required": ["text"],
        },
    },
    {
        "name": "find_records",
        "description": "Busca registros de un modelo Odoo permitido por texto libre en sus campos de texto. Usar para nombres, apellidos, emails, teléfonos o códigos.",
        "parameters": {
            "type": "object",
            "properties": {
                "model": {"type": "string", "description": "Nombre técnico, ej. res.partner."},
                "text": {"type": "string", "description": "Texto a buscar."},
                "fields": {"type": "array", "description": "Campos a devolver.", "items": {"type": "string"}},
            },
            "required": ["model", "text"],
        },
    },
    {
        "name": "get_model_fields",
        "description": "Lista los campos disponibles de un modelo de Odoo permitido.",
        "parameters": {
            "type": "object",
            "properties": {
                "model": {"type": "string", "description": "Nombre técnico del modelo."},
            },
            "required": ["model"],
        },
    },
    {
        "name": "get_unpaid_invoices",
        "description": "Lista facturas de cliente impagas, vencidas o en pago parcial.",
        "parameters": {
            "type": "object",
            "properties": {
                "partner_name": {"type": "string"},
                "days_overdue": {"type": "integer"},
            },
        },
    },
    {
        "name": "get_invoice_summary_by_period",
        "description": "Obtiene montos facturados o adeudados en un rango de fechas.",
        "parameters": {
            "type": "object",
            "properties": {
                "date_from": {"type": "string"},
                "date_to": {"type": "string"},
                "state": {"type": "string"},
            },
            "required": ["date_from", "date_to"],
        },
    },
]


class AiAgentService(models.AbstractModel):
    _name = "ai.agent.service"
    _description = "Servicio de agente IA"

    def _bot_partner(self):
        return self.env.ref(
            "ai_backend_assistant.partner_ai_assistant",
            raise_if_not_found=False,
        )

    def _get_config(self):
        return self.env["ai.config"].sudo().search(
            [("active", "=", True)], order="is_default desc, id", limit=1)

    def _get_model(self, config):
        models = config.model_ids.filtered(lambda model: model.active)
        return models.filtered("is_default")[:1] or models[:1]

    def _allowed(self, config, model_name):
        return model_name in config.allowed_model_ids.mapped("model")

    def _system_prompt(self, config):
        allowed = ", ".join(config.allowed_model_ids.mapped("model")) or "ninguno"
        return (
            "Sos un asistente interno. Respondé SIEMPRE en español, en una o dos frases, "
            "sin preguntas de aclaración y sin pedir confirmación. "
            "Si podés responder con una herramienta, usala y contestá el resultado directo. "
            "Nunca preguntes qué modelo de Odoo usar: inferilo del pedido. "
            "Modelos Odoo permitidos: %s. "
            "Para contactos usá res.partner. Para facturas usá account.move. "
            "Si preguntan 'cuántos', usá count_records o count_contacts. "
            "Para 'cuántos ... en <mes>' usá count_records con date_from y date_to; "
            "no inventes dominios ni nombres de campos. "
            "Para contactos, nombres o apellidos usá count_contacts con el texto exacto. "
            "Para pedir datos de una persona o contacto, usá find_records con model='res.partner' y text=<nombre>. "
            "Nunca respondas 'no tengo permiso' sin haber ejecutado una herramienta. "
            "Si la herramienta devuelve datos, contestá con el dato; no preguntes nada más. "
            "Si el dato no está permitido, decí 'No tengo permiso para consultar X' en una línea. "
            "No des explicaciones largas ni listes opciones." % allowed
        )

    def _clean_body(self, body):
        text = re.sub(r"<[^>]+>", " ", body or "")
        text = html.unescape(text).replace("\xa0", " ")
        return re.sub(r"\s+", " ", text).strip()

    def _chat_with_fallback(self, config, user, prompt):
        models = config.model_ids.filtered(lambda model: model.active)
        models = models.sorted(key=lambda model: not model.is_default)
        for model in models:
            try:
                if config.provider == "anthropic":
                    answer = self._anthropic_chat(config, model, user, prompt)
                else:
                    answer = self._openai_chat(config, model, user, prompt)
                if answer and answer != _("No pude completar la consulta."):
                    return answer
            except requests.exceptions.HTTPError as error:
                _logger.error(
                    "Modelo IA %s falló: %s", model.name, error)
            except Exception:
                _logger.exception("Error del modelo IA %s", model.name)
        return _("No pude procesar la consulta en este momento.")

    def reply(self, channel, message):
        author = message.author_id
        if not author:
            return False
        user = self.env["res.users"].sudo().search(
            [("partner_id", "=", author.id)], limit=1)
        if not user:
            return False
        config = self._get_config()
        if not config or not config.api_key:
            return False
        prompt = self._clean_body(message.body)
        if not prompt:
            return False
        answer = self._chat_with_fallback(config, user, prompt)
        if answer:
            channel.sudo().message_post(
                body=answer,
                author_id=self._bot_partner().id,
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
        return True

    def _tools_openai(self):
        return [{
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["parameters"],
            },
        } for tool in TOOLS]

    def _tools_anthropic(self):
        return [{
            "name": tool["name"],
            "description": tool["description"],
            "input_schema": tool["parameters"],
        } for tool in TOOLS]

    def _base_url(self, config):
        if config.base_url:
            return config.base_url.rstrip("/")
        defaults = {
            "openai": "https://api.openai.com/v1",
            "deepseek": "https://api.deepseek.com/v1",
            "anthropic": "https://api.anthropic.com/v1",
        }
        return defaults.get(config.provider, "")

    def _looks_like_refusal(self, text):
        text = (text or "").lower()
        markers = (
            "no tengo permiso", "sin permiso", "no permission",
            "no estoy autorizado", "no puedo acceder", "no tengo acceso",
        )
        return any(marker in text for marker in markers)

    def _openai_chat(self, config, model, user, prompt):
        url = self._base_url(config) + "/chat/completions"
        headers = {
            "Authorization": "Bearer %s" % config.api_key,
            "Content-Type": "application/json",
        }
        messages = [
            {"role": "system", "content": self._system_prompt(config)},
            {"role": "user", "content": prompt},
        ]
        tool_choice = "auto"
        forced = False
        retried = False
        for _iteration in range(5):
            payload = {
                "model": model.name,
                "messages": messages,
                "temperature": 0.2,
                "max_tokens": 1000,
                "tools": self._tools_openai(),
                "tool_choice": tool_choice,
            }
            if "openrouter.ai" in url:
                payload["provider"] = {"allow_fallbacks": True}
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            try:
                response.raise_for_status()
            except requests.exceptions.HTTPError:
                _logger.error(
                    "Error del proveedor IA %s: %s",
                    response.status_code,
                    response.text[:1000],
                )
                if not retried and response.status_code in (
                    400, 429, 500, 502, 503, 504,
                ):
                    retried = True
                    sleep(1)
                    continue
                raise
            data = response.json()
            message = data["choices"][0]["message"]
            calls = message.get("tool_calls") or []
            if not calls:
                content = message.get("content") or ""
                if not forced and self._looks_like_refusal(content):
                    forced = True
                    messages.append(message)
                    messages.append({
                        "role": "system",
                        "content": "Tenés permiso para consultar los modelos habilitados. "
                                   "No respondas 'no tengo permiso'. Usá una herramienta y devolvé el dato.",
                    })
                    continue
                return content
            messages.append(message)
            for call in calls:
                function = call.get("function") or {}
                try:
                    args = json.loads(function.get("arguments") or "{}")
                except ValueError:
                    args = {}
                result = self._execute_tool(
                    function.get("name"), args, user, config)
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id"),
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                })
        return _("No pude completar la consulta.")

    def _anthropic_chat(self, config, model, user, prompt):
        url = self._base_url(config) + "/messages"
        headers = {
            "x-api-key": config.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        messages = [{"role": "user", "content": prompt}]
        tool_choice = {"type": "auto"}
        forced = False
        for _iteration in range(5):
            payload = {
                "model": model.name,
                "max_tokens": 1000,
                "temperature": 0.2,
                "system": self._system_prompt(config),
                "messages": messages,
                "tools": self._tools_anthropic(),
                "tool_choice": tool_choice,
            }
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()
            blocks = data.get("content") or []
            text = "".join(
                block.get("text", "")
                for block in blocks
                if block.get("type") == "text"
            )
            tool_uses = [block for block in blocks if block.get("type") == "tool_use"]
            if not tool_uses:
                if not forced and self._looks_like_refusal(text):
                    forced = True
                    messages.append({"role": "assistant", "content": blocks})
                    messages.append({
                        "role": "user",
                        "content": "Tenés permiso para consultar los modelos habilitados. "
                                   "No respondas 'no tengo permiso'. Usá una herramienta y devolvé el dato.",
                    })
                    continue
                return text
            messages.append({"role": "assistant", "content": blocks})
            results = []
            for block in tool_uses:
                result = self._execute_tool(
                    block.get("name"), block.get("input") or {}, user, config)
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.get("id"),
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                })
            messages.append({"role": "user", "content": results})
        return _("No pude completar la consulta.")

    def _execute_tool(self, name, args, user, config):
        args = args or {}
        try:
            if name == "search_odoo_model":
                return self._search_odoo_model(args, user, config)
            if name == "count_odoo_records":
                return self._count_odoo_records(args, user, config)
            if name == "count_records":
                return self._count_records(args, user, config)
            if name == "count_contacts":
                return self._count_contacts(args, user, config)
            if name == "find_records":
                return self._find_records(args, user, config)
            if name == "get_model_fields":
                return self._get_model_fields(args, user, config)
            if name == "get_unpaid_invoices":
                return self._get_unpaid_invoices(
                    user, config, args.get("partner_name"), args.get("days_overdue"))
            if name == "get_invoice_summary_by_period":
                return self._get_invoice_summary(
                    user, config, args.get("date_from"),
                    args.get("date_to"), args.get("state"))
            return {"error": "Herramienta desconocida: %s" % name}
        except Exception as error:
            _logger.exception("Error ejecutando herramienta IA %s", name)
            return {"error": str(error)}

    def _count_contacts(self, args, user, config):
        if not self._allowed(config, "res.partner"):
            return {"error": "El modelo res.partner no está habilitado."}
        text = (args.get("text") or args.get("name") or "").strip()
        if not text:
            return {"error": "Falta el nombre o apellido."}
        count = self.env["res.partner"].with_user(user).search_count(
            [("name", "ilike", text)])
        return {"text": text, "count": count}

    def _default_fields(self, model):
        names = ["display_name"]
        for candidate in ("name", "email", "phone", "mobile", "vat", "ref", "code"):
            if (candidate in model._fields
                    and model._fields[candidate].store
                    and candidate not in names):
                names.append(candidate)
        return names

    def _text_domain(self, model, text):
        words = [word for word in re.split(r"\s+", text or "") if word]
        if not words:
            return []
        word_domains = []
        for word in words:
            term_domains = []
            for name, field in model._fields.items():
                if field.type in ("char", "text") and field.store and not field.compute and not field.related:
                    term_domains.append((name, "ilike", word))
                elif field.type == "selection" and isinstance(
                        field.selection, (list, tuple)):
                    for key, label in field.selection:
                        if (word.lower() in (label or "").lower()
                                or word.lower() == str(key).lower()):
                            term_domains.append((name, "=", key))
                elif (field.type == "many2one" and field.comodel_name and field.store
                      and not field.compute and not field.related):
                    if name in ("create_uid", "write_uid"):
                        continue
                    comodel = self.env[field.comodel_name]
                    name_field = comodel._fields.get("name")
                    if name_field and name_field.store:
                        ids = comodel.sudo().search(
                            [("name", "ilike", word)], limit=20).ids
                        if ids:
                            term_domains.append((name, "in", ids))
            if term_domains:
                word_domains.append(
                    ["|"] * (len(term_domains) - 1) + term_domains)
        if not word_domains:
            return []
        domain = ["&"] * (len(word_domains) - 1)
        for word_domain in word_domains:
            domain.extend(word_domain)
        return domain

    def _pick_date_field(self, model):
        for name in (
            "date", "reception_date", "appointment_date",
            "invoice_date", "create_date",
        ):
            field = model._fields.get(name)
            if field and field.type in ("date", "datetime"):
                return name
        for name, field in model._fields.items():
            if field.type in ("date", "datetime") and field.store:
                return name
        return None

    def _count_records(self, args, user, config):
        model_name = args.get("model")
        if not model_name:
            return {"error": "Falta el modelo."}
        if not self._allowed(config, model_name):
            return {"error": "El modelo %s no está habilitado." % model_name}
        model = self.env[model_name].with_user(user)
        text = (args.get("text") or "").strip()
        domain = self._text_domain(model, text) if text else []
        date_from = args.get("date_from")
        date_to = args.get("date_to")
        if date_from or date_to:
            date_field = args.get("date_field") or self._pick_date_field(model)
            if not date_field:
                return {"error": "El modelo no tiene un campo de fecha usable."}
            field = model._fields[date_field]
            if date_from:
                day_from = fields.Date.to_date(date_from)
                start = (datetime.combine(day_from, time.min)
                         if field.type == "datetime" else day_from)
                domain.append((date_field, ">=", start))
            if date_to:
                day_to = fields.Date.to_date(date_to)
                if field.type == "datetime":
                    end = datetime.combine(day_to + timedelta(days=1), time.min)
                    domain.append((date_field, "<", end))
                else:
                    domain.append((date_field, "<=", day_to))
        count = model.search_count(domain)
        return {"model": model_name, "text": text, "count": count}

    def _find_records(self, args, user, config):
        model_name = args.get("model")
        text = (args.get("text") or "").strip()
        if not model_name or not text:
            return {"error": "Falta el modelo o el texto."}
        if not self._allowed(config, model_name):
            return {"error": "El modelo %s no está habilitado." % model_name}
        model = self.env[model_name].with_user(user)
        domain = self._text_domain(model, text)
        if not domain:
            return {"error": "No encontré campos para buscar ese texto."}
        fields_list = args.get("fields") or self._default_fields(model)
        records = model.search_read(domain, fields=fields_list, limit=20)
        return {
            "model": model_name,
            "total_count": model.search_count(domain),
            "records": records,
        }

    def _count_odoo_records(self, args, user, config):
        model_name = args.get("model")
        if not model_name:
            return {"error": "Falta el modelo."}
        if not self._allowed(config, model_name):
            return {"error": "El modelo %s no está habilitado." % model_name}
        domain = args.get("domain") or []
        if not isinstance(domain, list):
            return {"error": "El dominio debe ser una lista."}
        total = self.env[model_name].with_user(user).search_count(domain)
        return {"model": model_name, "count": total}

    def _search_odoo_model(self, args, user, config):
        model_name = args.get("model")
        if not model_name:
            return {"error": "Falta el modelo."}
        if not self._allowed(config, model_name):
            return {"error": "El modelo %s no está habilitado." % model_name}
        domain = args.get("domain") or []
        if not isinstance(domain, list):
            return {"error": "El dominio debe ser una lista."}
        fields_list = args.get("fields") or ["display_name"]
        if not isinstance(fields_list, list):
            return {"error": "fields debe ser una lista."}
        limit = min(int(args.get("limit") or 20), 50)
        model = self.env[model_name].with_user(user)
        total = model.search_count(domain)
        records = model.search_read(domain, fields=fields_list, limit=limit)
        return {
            "model": model_name,
            "total_count": total,
            "returned": len(records),
            "records": records,
        }

    def _get_model_fields(self, args, user, config):
        model_name = args.get("model")
        if not model_name:
            return {"error": "Falta el modelo."}
        if not self._allowed(config, model_name):
            return {"error": "El modelo %s no está habilitado." % model_name}
        model = self.env[model_name].with_user(user)
        result = []
        for name, field in model._fields.items():
            result.append({
                "name": name,
                "type": field.type,
                "relation": field.comodel_name if field.relational else None,
                "required": field.required,
                "readonly": field.readonly,
            })
        return {"model": model_name, "fields": result}

    def _get_unpaid_invoices(self, user, config, partner_name=None, days_overdue=None):
        if not self._allowed(config, "account.move"):
            return {"error": "El modelo account.move no está habilitado."}
        domain = [
            ("move_type", "=", "out_invoice"),
            ("payment_state", "in", ["not_paid", "partial"]),
        ]
        if partner_name:
            domain.append(("partner_id.name", "ilike", partner_name))
        if days_overdue:
            due = fields.Date.today() - timedelta(days=int(days_overdue))
            domain += [
                ("invoice_date_due", "!=", False),
                ("invoice_date_due", "<", fields.Date.to_string(due)),
            ]
        moves = self.env["account.move"].with_user(user).search_read(
            domain,
            fields=[
                "name", "partner_id", "invoice_date", "invoice_date_due",
                "amount_total", "amount_residual", "currency_id", "payment_state",
            ],
            limit=50,
            order="invoice_date_due asc",
        )
        return {"count": len(moves), "invoices": moves}

    def _get_invoice_summary(self, user, config, date_from, date_to, state=None):
        if not self._allowed(config, "account.move"):
            return {"error": "El modelo account.move no está habilitado."}
        day_from = fields.Date.to_date(date_from)
        day_to = fields.Date.to_date(date_to)
        domain = [
            ("move_type", "=", "out_invoice"),
            ("invoice_date", ">=", day_from),
            ("invoice_date", "<=", day_to),
        ]
        if state:
            domain.append(("state", "=", state))
        moves = self.env["account.move"].with_user(user).search(domain)
        return {
            "count": len(moves),
            "amount_total": sum(moves.mapped("amount_total")),
            "amount_residual": sum(moves.mapped("amount_residual")),
            "currency": self.env.company.currency_id.name,
        }
