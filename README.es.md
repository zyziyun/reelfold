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
Crea, edita y publica vídeos para cada plataforma en una sola app, en tu Mac. Pensado para creadores y docentes,
cientos de vídeos a la vez. Gratis, MIT.</p>

<p align="center">
  <a href="https://reelfold.com/docs/es/">Documentación</a> ·
  <a href="https://github.com/zyziyun/reelfold/releases/latest">Descargar para macOS</a> ·
  <a href="https://reelfold.com">reelfold.com</a> ·
  <a href="LICENSE">MIT</a>
</p>

- **Crea a partir de notas o un tema.** Dale apuntes de clase, una página de Notion exportada o solo un tema, y obtén
  un vídeo explicativo, un short con IA o un vídeo de lanzamiento, con narración y animación. Toda generación con IA
  de pago espera tu aprobación.
- **Edita tu propio material.** Suelta lo que grabaste (una charla, una clase grabada, una tarjeta SD de un viaje) o
  un vídeo terminado que quieras seguir editando, y di lo que quieres con tus palabras. Una clase se convierte en
  episodios y shorts, con el código y las diapositivas legibles.
- **Cientos de vídeos de una vez.** Un taller profesional, no un editor de un clip a la vez: planifica los vídeos,
  agrupa una carpeta en historias y los hace en piloto automático en tu propio Mac, con modelos locales si quieres.
  Cada archivo se comprueba; tú solo miras lo marcado, y actúas sobre cientos de proyectos a la vez en Todos los
  proyectos.
- **Publica en todas partes desde un calendario.** Primero YouTube, TikTok, Instagram, X y LinkedIn, luego
  Xiaohongshu, Douyin, Bilibili y WeChat Channels: 20 plataformas, cada una con su tamaño, subtítulos, volumen, portada
  y texto. Planifica la semana en el calendario de publicación; Reelfold rellena cada página de subida y tú publicas.

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

La IA funciona con lo que ya tienes: tu sesión de Claude Code o Codex, tu propia clave de API o un modelo local.

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
