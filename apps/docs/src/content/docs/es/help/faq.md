---
title: Preguntas frecuentes
description: Respuestas sobre el precio y la licencia de Reelfold, Windows, qué sale de tu Mac, qué IA necesitas, idiomas, fuentes propias, publicación y uso comercial.
---

## ¿Reelfold es gratis?

Sí. Reelfold es de código abierto con licencia MIT: el motor, el skill de Claude Code, la app para Mac y el sitio web. Solo pagas a tu proveedor de IA, si usas una API de pago. Con un modelo local, o con tu Claude Code o Codex CLI con sesión iniciada, no hay factura de API. En una prueba interna, 96 archivos sacados de una clase de 72 minutos costaron 0,73 USD en llamadas a la API.

## ¿Hay una descarga para Mac? ¿Y para Windows?

Sí. La app para Mac (Apple Silicon) está en [GitHub Releases](https://github.com/zyziyun/reelfold/releases/latest), firmada y notarizada: consulta [Instala la app para Mac](/docs/es/start/install-mac/). Una edición para la Mac App Store (Reelfold Lite) usa claves de API o modelos locales para la IA. Windows 10 / 11 (x64) está en vista previa: cada versión incluye también un instalador para Windows sin firmar (SmartScreen muestra un aviso), o compílalo desde el código; consulta [Install on Windows](/docs/start/install-windows/). Las diferencias: [Ediciones](/docs/es/help/editions/). El motor usa allí faster-whisper y el codificador `h264_mf`; la mayoría de las pruebas se hacen en Mac.

## ¿Publica por mí?

Solo cuando tú lo dices. YouTube va por su API oficial (Data API): inicias sesión con Google en tu propio navegador, y Publicar o Programar sube el video, la portada y el texto (una publicación programada sube en privado y YouTube la publica a su hora). En las demás plataformas la publicación es asistida: la app abre la página de subida en su navegador integrado, coloca el video y escribe el título, el texto y las etiquetas; tú lo revisas y pulsas publicar. Los videos programados solo salen solos si activas la publicación automática. Consulta [Publicación](/docs/es/concepts/publishing/).

## ¿Qué sale de mi Mac?

Tu video y tu audio se quedan en tu Mac: la transcripción y el renderizado se ejecutan en local. Al proveedor de IA que elegiste solo va lo que necesita cada paso de IA: texto, como la transcripción, los subtítulos y los títulos, y en algunos pasos hojas de fotogramas fijos. La transcripción alojada recibe audio y la narración alojada recibe el guion. Para mantener el procesamiento de IA local, usa modelos locales en todas las tareas y sus alternativas, transcripción y voces locales, sin generación alojada. Las descargas, actualizaciones y publicaciones son operaciones de red separadas. Consulta [Privacidad](/docs/es/concepts/privacy/).

## ¿Qué IA necesito?

Cualquiera de estas, para cada tarea:

- Tu propio **Claude Code** o **Codex** CLI con sesión iniciada (sin clave de API).
- Otro **agente de código** instalado y con sesión iniciada, por ACP: Gemini CLI, Cursor CLI, GitHub Copilot CLI, OpenCode, Qwen Code, Kimi CLI, CodeBuddy, iFlow CLI.
- Una **clave de API**: Anthropic, OpenAI, DeepSeek, Qwen, Kimi, GLM, Doubao, OpenRouter, Gemini, ElevenLabs. Las claves de Qwen, Kimi, GLM y Doubao usan su punto de acceso de China continental o internacional.
- Un **modelo local**: Ollama, LM Studio, vLLM, llama.cpp, whisper local.

Sin ninguna IA, la planificación de fragmentos recurre a un planificador basado en reglas. Consulta [Proveedores de IA](/docs/es/concepts/ai-providers/).

## ¿Necesito Claude Code?

Para la app para Mac, no: sirve cualquier proveedor de los de arriba. La versión skill de Reelfold se ejecuta dentro de Claude Code, así que para esa sí. Las recetas de videos explicativos y de cursos necesitan un modelo de IA para dibujar sus escenas animadas: sirven Claude Code, Codex, una clave de API o un modelo local.

## ¿En qué se diferencia de Opus Clip, Descript o CapCut?

Son buenas herramientas con otro enfoque. Opus Clip es un servicio en la nube para encontrar clips en videos largos, Descript es un editor basado en la transcripción y CapCut es un editor de línea de tiempo con plantillas. Reelfold está pensado para quienes editan en tanda:

- **Primero lo local.** Tu material se procesa en tu propio Mac.
- **Lote primero, luego revisas las excepciones.** Muchos clips se procesan en paralelo, cada archivo se revisa automáticamente y tú miras lo que se marcó.
- **Una grabación, todas las plataformas.** Lienzo, subtítulos, volumen, portada y texto adaptados a cada una de las 20 plataformas.
- **Usa tu propia IA**, o ninguna.
- **Código abierto** (MIT): puedes leerlo, cambiarlo y ampliarlo.
- **Inglés y chino desde una misma fuente.** Las versiones de YouTube y TikTok en inglés, Xiaohongshu y Bilibili en chino.
- **Funciona con tu editor.** Cualquier clip se exporta a Premiere Pro, DaVinci Resolve, CapCut u OpenTimelineIO.
- **Publicación bajo tu control:** YouTube por su API oficial, las páginas de subida rellenadas para el resto, y nada sale hasta que pulsas Publicar o Programar.

## ¿Qué idiomas admite?

La app está en inglés, chino simplificado y francés. En cuanto al contenido, el chino y el inglés son los más desarrollados: detección de muletillas, reglas de subtítulos, subtítulos bilingües y texto de publicación en ambos idiomas. Whisper transcribe muchos otros idiomas, español incluido, pero esos flujos están menos probados.

## ¿Puedo usar mis propias fuentes y colores de marca?

Sí. En `persona.local.yaml`, apunta cualquier rol de fuente (`cjk`, `cjk-bold`, `serif`, `mono`…) a tu propio archivo y define tus colores de marca, el tema de los paneles, los hashtags predeterminados y las reglas para títulos. Los estudios pueden tener una marca distinta por cliente. Consulta [Temas](/docs/es/concepts/themes/) y la [referencia de persona](/docs/es/reference/persona/).

## ¿Puedo usarlo para trabajo comercial?

La licencia MIT permite el uso comercial, incluido el trabajo para clientes. Hay dos cosas que debes comprobar tú: los términos de tu proveedor de IA (las CLI de suscripción como Claude Code y Codex están pensadas para uso personal; usa una clave de API o un modelo local cuando los términos lo exijan) y las licencias de las fuentes, la música y el material que uses. El motor opcional de recorte RVM para portadas tiene licencia GPL-3.0 y solo se descarga si lo eliges.

## ¿Tengo que etiquetar el contenido generado con IA?

Sigue las normas de cada plataforma. Las plataformas chinas exigen declarar el contenido generado con IA (normas vigentes desde el 1 de septiembre de 2025), y YouTube, TikTok y Meta tienen sus propias etiquetas de IA. Reelfold nunca las marca por ti; la lista de comprobación de publicación y las notas de entrega a clientes te lo recuerdan. El workflow de video con IA planifica una etiqueta por plataforma. Consulta la [referencia de publicación](/docs/es/reference/engine/publishing/).

## ¿Qué pasó con video-studio y Daycut?

Reelfold es el nuevo nombre. El skill y el motor de código abierto se publicaron como **video-studio**, y la app de escritorio se llamaba **Daycut** (日剪). El skill se sigue llamando `video-studio`, el paquete de Python sigue siendo `vstudio` y las instalaciones existentes en `~/.claude/skills/video-studio` siguen funcionando. Solo se movió el repositorio, a [github.com/zyziyun/reelfold](https://github.com/zyziyun/reelfold).

## Relacionado

- [Qué es Reelfold](/docs/es/start/what-is-reelfold/)
- [Solución de problemas](/docs/es/help/troubleshooting/)
- [Contribuir](/docs/es/contributing/)
