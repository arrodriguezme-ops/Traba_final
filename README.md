# Figuras Lima

## 1. One-liner
Ayudamos a coleccionistas de Marvel Legends en Lima a completar sus Build-A-Figures pieza por pieza, con precio total y tiempo de entrega, mediante búsqueda por voz o texto con IA.

## 2. Founder
> **TODO (Angelo):** nombre, foto, una línea sobre ti. Ser coleccionista tú mismo es tu ventaja: conoces el problema desde adentro. Explica cómo cubres producto, ingeniería, diseño y ventas con agentes de IA.

## 3. Problema
Hoy los coleccionistas de Lima buscan figuras en grupos de Facebook, WhatsApp y tiendas sueltas: no hay catálogo único, los precios no son comparables y no se sabe cuánto cuesta ni cuánto demora el envío hasta que se negocia.
Cómo lo resuelven hoy: scroll en grupos, mensajes uno a uno, WhatsApp.

> **TODO:** notas de 3 conversaciones con usuarios en [`docs/research/`](docs/research/). Sin ellas el problema es solo una hipótesis.

## 4. Solución e insight
El coleccionista dice lo que quiere ("Goku Ultra Instinto nuevo, hasta 300 soles, vivo en Miraflores"). El sistema lo convierte en una búsqueda estructurada, rankea avisos de vendedores y calcula el costo y tiempo de entrega con repartidores independientes.
> **TODO:** tu insight propio (qué ves tú como coleccionista que otros no).

## 5. Why now
Whisper corre local y barato en una laptop; los LLM extraen datos estructurados de lenguaje natural con pocas líneas; hace tres años esto requería entrenar modelos propios.

## 6. Demo
```bash
pip install -r requirements.txt
python data/scrape_legendsverse.py  # opcional: vuelve a bajar el catálogo (3 s entre peticiones)
python data/make_listings.py        # regenera los avisos sintéticos de Lima
streamlit run app/streamlit_app.py
```
- URL pública: **TODO (Streamlit Community Cloud)**
- Capturas y diagrama: **TODO** en `docs/`
- Modelos: Whisper `small` vía faster-whisper, local, porque los audios del usuario no deben salir de su equipo. Claude (`claude-haiku-5-5`) con tool use para extraer la búsqueda; si no hay `ANTHROPIC_API_KEY` se usa un parser por reglas offline.

```
voz/texto → [Whisper local] → [Claude o reglas → Busqueda] → matching (rapidfuzz) → envío (haversine) → tabla + mapa Folium
```

**Datos:**
- **Catálogo real:** 92 BAF y 631 piezas de Marvel Legends (2005–2025) desde [Legendsverse](https://legendsverse.com): qué figura trae cada pieza, imagen de la pieza y valor de mercado en USD (ventas en eBay). Scraper de bajo volumen: `data/scrape_legendsverse.py`.
- **Retail por año:** `data/retail_por_anio.csv`, de la guía de precios de Legendsverse (2012+).
- **Avisos de vendedores de Lima: sintéticos** (`data/make_listings.py`) sobre figuras reales, con supuestos de tipo de cambio (3.45) y recargo de importación (1.35).

## 7. Modelo de negocio
> **TODO:** decidir quién paga (¿comisión al vendedor?, ¿suscripción del coleccionista para alertas?) y un precio concreto en soles, máximo tres planes. Calcular costo por usuario (tokens, servidor, APIs).
**Efecto de doble marginalización (sobreprecio de reventa):** `(Precio_rev − P_retail) / P_retail`, con P_retail = retail de Hasbro en USD × tipo de cambio. El vendedor ve cómo se separa del retail y del mercado (`backend/pricing.py`, pestaña *Soy vendedor*).
Supuestos de envío del modelo (a validar con repartidores): S/ 6 base + S/ 1.2 por km, ~15 km/h (`backend/delivery.py`).

## 8. Herramientas del curso
| Herramienta | Dónde |
|---|---|
| Voz a texto con Whisper (sesión 13) | [`ai/transcribe.py`](ai/transcribe.py) |
| LLM con salidas estructuradas (sesión 8) | [`ai/parser.py`](ai/parser.py) |
| Mapas con Folium (sesión 6) | [`app/streamlit_app.py`](app/streamlit_app.py) |

## 9. Qué hizo el agente
Claude Code generó el esqueleto del repo, el generador de datos sintéticos, el motor de matching, el parser y la app Streamlit, en sesiones con el founder, que definió el problema y el flujo y revisa cada parte.
> **TODO:** actualizar al final con detalle honesto.
