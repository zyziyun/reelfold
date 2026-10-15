<p align="center">
  <a href="README.md">English</a> · <a href="README.zh-CN.md">简体中文</a> · <a href="README.fr.md">Français</a> · <b>Español</b>
</p>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/brand/wordmark-on-dark.svg">
    <img alt="Reelfold" src="docs/brand/wordmark-on-light.svg" width="340">
  </picture>
</p>

<p align="center"><b>El taller de código abierto para creadores.</b><br>
Una frase convierte tu material en una serie de vídeos listos para publicar en cada plataforma, en inglés y en chino.
Código abierto, gratis y todo en tu Mac.</p>

<p align="center">
  <a href="https://reelfold.com/es/demo/">Ver la demo</a> ·
  <a href="https://reelfold.com/docs/es/">Documentación</a> ·
  <a href="https://github.com/zyziyun/reelfold/releases/latest">Descargar para macOS</a> ·
  <a href="https://reelfold.com">reelfold.com</a> ·
  <a href="LICENSE">MIT</a>
</p>

- **Toda una serie con una frase.** Indica una carpeta o una tarjeta SD y pide «unos 12 vídeos, cada uno con su tema».
  Agrupa el material en historias, planifica la serie que pediste (de 10 a 20 vídeos, por ejemplo) y la hace en piloto
  automático. Cientos de ediciones de una vez; cada decisión queda anotada con su motivo.
- **Cada plataforma, su corte y su idioma.** YouTube, TikTok, Instagram, X y LinkedIn primero, luego Xiaohongshu,
  Douyin, Bilibili y WeChat Channels: 20 plataformas, cada una con su tamaño, duración (un corte largo con capítulos
  para YouTube, cortes breves para Shorts y TikTok), subtítulos, volumen, portada y texto. Inglés para YouTube y
  TikTok, chino para Xiaohongshu y Bilibili.
- **Tu material real, editado con oficio.** Una plantilla por tipo de vídeo, cortes al ritmo (Beat This!), detección
  de planos, color igualado plano a plano, jump cuts suavizados y cámara lenta limpia (RIFE), recorte vertical que
  sigue al sujeto y una biblioteca integrada de 52 temas CC0. La generación con IA solo cubre huecos, después de que
  apruebes el precio.
- **Portadas y controles.** Las portadas eligen un fotograma nítido, recortan al sujeto, lo amplían y dejan el título
  lejos de las caras y los botones, con tres opciones A/B para YouTube. Cada archivo se revisa (parpadeo, encuadre,
  volumen, idioma de los subtítulos, texto en pantalla); solo miras lo marcado.
- **Sigue editando, venga de donde venga.** Importa un vídeo terminado para editarlo otra vez, conserva tus cambios
  cuando la IA vuelve a renderizar, grábate con el teleprompter, añade tu marca de agua y envía cualquier clip a
  Premiere Pro, DaVinci Resolve, CapCut u OpenTimelineIO.
- **Publica desde un calendario.** YouTube sube y programa por su API oficial (Data API); para las demás plataformas,
  Reelfold rellena la página de subida y tú pulsas publicar.
- **Local, privado, gratis, tu IA.** El render, la transcripción y las voces gratis (Kokoro en inglés, Qwen3-TTS en
  chino) funcionan en tu Mac. Claude Code, Codex, agentes de código ACP (Gemini CLI, Qwen Code, Kimi CLI…), claves de
  API, incluidos proveedores que funcionan en China continental, o un modelo local; elige la IA y el modelo por
  petición, o con `/model` en el chat. Licencia MIT.

![Vídeo a cámara · clips de una clase · historia con fotos · vlog al ritmo · pódcast con caras ocultas · vídeo explicativo](docs/demos/strip.jpg)

## Instalación

**App para Mac** (Apple Silicon, gratuita): firmada y notarizada, desde
[Releases](https://github.com/zyziyun/reelfold/releases/latest), o
[compílala desde el código fuente](https://reelfold.com/docs/es/start/install-mac/). En piloto automático, una
frase basta para llegar a los clips terminados, con cada decisión anotada; Windows está en vista previa.

**Skill de Claude Code** (el mismo motor, todavía llamado `video-studio`):

```bash
git clone https://github.com/zyziyun/reelfold ~/.claude/skills/video-studio
~/.claude/skills/video-studio/install.sh
cp ~/.claude/skills/video-studio/persona.example.yaml ~/.claude/skills/video-studio/persona.local.yaml
```

La IA funciona con lo que ya tienes: tu sesión de Claude Code o Codex, otro agente de código ACP, tu propia clave de
API o un modelo local.

**Documentación → [reelfold.com/docs/es](https://reelfold.com/docs/es/)**

## Pídelo así

| Quieres | Di algo como |
|---|---|
| Varios vídeos de una tarjeta | "Haz varios vídeos con mi tarjeta DJI, cada uno con su tema, para YouTube e Instagram" |
| Seguir editando un vídeo terminado | "Este es el vídeo de la semana pasada: ajusta el inicio, portada nueva y una versión vertical para TikTok" |
| Un vídeo a cámara bien ajustado | «Quita las pausas, las muletillas y las repeticiones, acelera a 1,1×, añade subtítulos y una barra de progreso, y expórtalo para TikTok y Shorts» |
| Una clase en clips verticales | «Corta esta clase de 70 minutos en 3 episodios verticales, una idea por episodio, con zoom al código, portadas y textos para publicar» |
| Un clip de pódcast | «Busca el mejor minuto de este pódcast de Zoom, oculta la cara y el nombre del invitado, en vertical» |
| Un vlog de viaje con ritmo | «Haz un vlog rápido, al ritmo de la música, con estas fotos y vídeos de Disneyland: días, lugares, efectos de sonido, 9:16» |
| Un vídeo, varias plataformas | «Expórtalo para Instagram Reels, TikTok y YouTube Shorts, cada uno con sus zonas seguras y su volumen» |

Más ejemplos: [ejemplos de peticiones](https://reelfold.com/docs/es/examples/).

## Más información

[Primeros pasos](https://reelfold.com/docs/es/start/what-is-reelfold/) ·
[Guías](https://reelfold.com/docs/es/guides/talking-head/) ·
[Conceptos](https://reelfold.com/docs/es/concepts/projects/) ·
[Referencia](https://reelfold.com/docs/es/reference/) ·
[Solución de problemas](https://reelfold.com/docs/es/help/troubleshooting/) ·
[Contribuir](https://reelfold.com/docs/es/contributing/)

## Licencia

MIT, incluidas la app (`apps/desk`), la web (`apps/site`) y la documentación (`apps/docs`). Las fuentes y los modelos se
descargan al instalar, con sus propias licencias (SIL OFL 1.1, Apache-2.0). Los flujos de HTML a vídeo usan
[HyperFrames](https://hyperframes.heygen.com).

Antes se llamaba **video-studio** (el skill y el motor) y **Daycut** (la app). Las instalaciones existentes en
`~/.claude/skills/video-studio` siguen funcionando; apúntalas a la nueva dirección con
`git -C ~/.claude/skills/video-studio remote set-url origin https://github.com/zyziyun/reelfold`.
