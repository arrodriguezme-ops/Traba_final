# Fuentes de datos (revisadas el 14-11-2026)

Criterio: usar primero fuentes abiertas que permiten el acceso (robots.txt y términos), a bajo volumen (3 s entre peticiones, User-Agent genérico, caché local, parada ante 403/429) y guardar solo datos derivados. Si una fuente bloquea o lo prohíbe, no se fuerza: se usa una fuente secundaria o se transcribe a mano.

| Fuente | Qué aporta | Acceso | Archivo |
|---|---|---|---|
| Legendsverse (checklist, waves, price guide) | 1,692 empaques Marvel Legends 1997–2027: **retail oficial por figura**, año, valor de mercado (ventas completadas en eBay), foto; 92 BAF y 631 piezas; 172 waves | ✅ Permitido; el retail viene embebido en las páginas de la guía de precios | `marvel_legends_retail_historico.csv`, `marvel_legends_baf.csv`, `marvel_legends_waves*.csv`, `marvel_legends_figuras.csv` |
| Falabella Perú | 279 productos Legends con precio (213 de un solo vendedor del marketplace, Play Mall All) | ✅ robots.txt solo bloquea carrito y cuenta | `tiendas_pe.csv` |
| Plaza Vea / Oechsle (VTEX) | Productos Legends con precio, stock y **código de barras EAN**; son marketplaces (vendedores como TOYSMASTER, Pequeñas Travesuras) | ✅ API pública de catálogo, no bloqueada por robots.txt | `tiendas_pe.csv` |
| Tai Loy | 15 productos Legends con precio lista y oferta | ✅ robots.txt sin reglas para otros agentes | `tiendas_pe.csv` |
| Veritrade (partida 9503, 2019–nov 2026) | Importaciones formales: volumen y FOB por año e importador | Licencia paga, descargada por el founder; **los archivos no se suben** | solo el agregado `importaciones_ml_resumen.csv` |
| Capturas de Facebook Marketplace, eBay, Tai Loy y tiendas de Lima | 68 avisos reales de reventa (vendedores anonimizados) | Transcripción manual | `listings_reales.csv` |
| **Facebook Marketplace (scraping)** | — | ❌ Requiere sesión y sus términos prohíben la recolección automatizada sin permiso escrito | se usan capturas |
| **Mercado Libre Perú** | — | ❌ El listado redirige a verificación de cuenta y la API de búsqueda responde 403 sin token de una app registrada | pendiente: crear app de desarrollador (decisión del founder) |
| **Ripley** | — | ❌ robots.txt prohíbe `/search/` | no usado |
| **ActionFigure411** | UPC y precios por figura | ❌ 403 a clientes automáticos | no usado |

## Hasta dónde cruzan las fuentes
- **Tienda → figura:** el título se cruza con el catálogo de Legendsverse con una regla conservadora (todas las palabras del nombre deben estar en el título y no pueden sobrar palabras que no sean de línea/empaque). 109 de 337 productos quedan con confianza alta; solo esos tienen sobreprecio calculado.
- **Tienda → importación:** el EAN de Plaza Vea/Oechsle aparece en una sola fila de Veritrade. Las DUA describen surtidos ("AVN LEGENDS AST", códigos Hasbro como F0167), no figuras, así que el cruce es por **año y línea**, no por figura.
- **Importador → tienda:** Hasbro Perú es el importador principal de Legends. Tai Loy, Saga Falabella, Tottus y Tiendas Peruanas importan juguetes Marvel pero no Legends con ese nombre: probablemente compran Legends al distribuidor local.

## Resultados clave (`cruce_mercado.py`)
- **FOB declarado por Hasbro Perú: US$3.4–5.6 por unidad** frente a un retail en EE. UU. de US$20–28. Parece precio de transferencia entre empresas del grupo, no costo mayorista real: es un piso, no el costo.
- **Sobreprecio sobre el retail (mediana, figuras individuales con confianza alta):** Tai Loy +45 %, Oechsle/Plaza Vea +75 %, Falabella +199 % (dominada por un revendedor del marketplace). En Facebook Marketplace la mediana de los avisos reales es S/125.
- Cadena de precios: FOB (~US$5) → retail EE. UU. (US$24.99–27.99 ≈ S/86–97) → tienda en Perú (S/170–350) → reventa entre coleccionistas (≈ S/125, a veces bajo el precio de tienda).

## Tai Loy histórico (Wayback Machine)
`data/tailoy_wayback_historico.csv`: 49 capturas mensuales de 2022–2026 de 25 páginas de producto de Marvel Legends (Black Widow, Black Panther, Spider-Man Retro, etc.). Se bajaron con el índice CDX de archive.org, User-Agent genérico y 3 s de espera. Limitaciones: pocas figuras, precios de lista o de oferta según el día (p. ej. wave Black Widow S/139 en 2022–2023 y S/27.8–41.7 en capturas de liquidación; wave Black Panther S/149 → S/104.3 → S/57.9–59.6 en 2024), y no hay página para la mayoría de figuras. Las capturas de 2017–2018 no traen precio legible.

## eBay (captura del 14-nov-2026)
31 avisos nuevos de modelos en caja, con precio en S/ según eBay y envío a Perú por separado. Sin envío ni aranceles el sobreprecio mediano es +9 %; el envío (S/120–370) lo cambia por completo.
