# AI Backend Assistant

Asistente de IA para el backend de Odoo, integrado en el chat interno
(Discuss). Permite consultar datos de Odoo mediante lenguaje natural usando
proveedores LLM con tool calling.

## Características

- Soporte para OpenAI, Anthropic, DeepSeek y APIs compatibles con OpenAI.
- Modelos LLM habilitados explícitamente por configuración.
- Lista configurable de modelos de Odoo permitidos para consultar.
- Herramientas genéricas de búsqueda y conteo de registros.
- Configuración del nombre y la imagen del bot.

## Configuración

1. Ir a **Ajustes > Asistente IA > Configuración de Modelos**.
2. Crear un proveedor, cargar la API Key y, si corresponde, la Base URL.
3. Agregar el modelo LLM y el proveedor.
4. Seleccionar los modelos de Odoo permitidos.
5. Marcar la configuración como predeterminada.

## Licencia

LGPL-3. Autor: Alitux <alitux@disroot.org>.
