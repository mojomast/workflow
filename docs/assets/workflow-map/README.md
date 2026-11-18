# Workflow poster

A single-page map of the current rizzstack workflow, drawn from the code on `main` (Nov 18 2026).

| File | What |
|---|---|
| [workflow-map.png](workflow-map.png) | Raster poster (2560 px wide), used as the README banner |
| [workflow-map.html](workflow-map.html) | HTML/SVG source of the poster. Open it locally; it loads fonts from the `fonts/` folder beside it |
| [render.mjs](render.mjs) | Regenerates the PNG with Playwright: `CHROMIUM=/path/to/chrome node render.mjs` (1280 CSS px at 2x) |
| [workflow-map-v1.html](workflow-map-v1.html) | The earlier poster (mid-October to mid-November 2026), kept for reference |

Each card names the module or document it was checked against, so the poster can be re-verified when the flow changes. It does not add private hosts, tokens or URLs.

## Fonts

The posters embed these SIL Open Font License 1.1 families as `.woff2` files:

- [Syne](https://github.com/bonjour-monde/syne-typefaces), © Bonjour Monde (display, current poster)
- [Geist and Geist Mono](https://github.com/vercel/geist-font), © Vercel (UI and code, current poster)
- [IBM Plex Sans](https://github.com/IBM/plex) and [IBM Plex Mono](https://github.com/IBM/plex), © IBM Corp. (v1 poster)
- [Instrument Serif](https://github.com/googlefonts/instrument-serif), © Rodrigo Fuenzalida (v1 poster)
