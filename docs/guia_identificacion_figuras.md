# Guía para identificar figuras Marvel Legends a partir de capturas

Criterios usados al transcribir `data/listings_reales.csv`, de más a menos confiable.
Cada uno dice qué tan seguro es el resultado y cómo se anota.

## 1. Texto visible (confianza alta)
- **Caja o tarjeta:** el nombre impreso (p. ej. "Typhoid Mary", "Ravager Thor"). Si la caja se ve completa, la identidad es segura.
- **Etiqueta de BAF en la parte de arriba de la caja** ("Build-A-Figure: Khonshu"). Da el wave y, con el catálogo, el año.
- **Línea o película en la caja** (Secret Invasion, What If…?, Deadpool & Wolverine, Marvel Rivals). Acota el año.
- **Código Hasbro** (G2054, F0261/F0170 ASST.). Sirve para confirmar el producto; no se traduce solo a año.
- **Título del aviso y descripción del vendedor.** Se respetan tal cual, pero **no se asumen correctos** (los vendedores abrevian o se equivocan: "modelo 70", "MCU", "Spider-Man").

## 2. Catálogo (confianza alta si coincide una sola entrada)
- Cruzar el nombre con `marvel_legends_baf.csv` (BAF, pieza, año, wave) y `marvel_legends_retail_historico.csv` (año, retail en USD).
- Si el nombre existe en **un solo año**, el año queda fijado. Si existe en varios (Wolverine, Spider-Man, Iron Man), **no se asigna año por nombre**: se necesita otra pista.
- **Tolerancia de ±1 año** entre la guía de precios y la guía de BAF (Legendsverse a veces los fecha distinto).
- Los empaques dobles se comparan con el retail del **empaque doble**, no con el de una figura.

## 3. Pistas visuales cuando no hay caja (confianza media)
Se usan en este orden, y se anotan como "no confirmado" en `notas`:
1. **Diseño distintivo** del personaje (collar y garras de Black Panther, lanza de Proxima Midnight, escudo de Taskmaster).
2. **Accesorios incluidos** (efectos de energía, cabezas intercambiables, manos extra, la pieza de BAF).
3. **Pieza de BAF visible** (torso, pierna, brazo) → identifica el wave.
4. **Otras figuras del mismo aviso o del mismo vendedor**: suelen ser del mismo wave.
5. **Estilo de escultura y pintura** (las figuras de 2013 se ven distintas a las de 2022).

Límites reconocidos: figuras parecidas entre años (War Machine, Star-Lord, Symbiote Spider-Man) y personajes poco comunes. En esos casos queda **sin año** y **sin comparación con el retail**.

## 4. Qué se hace cuando no hay certeza
- Campo `figura` genérico o "Sin identificar (descripción corta)".
- `marca_calidad = sin_identificar`; precio guardado pero **sin sobreprecio**.
- Nunca se inventa año. `anio_estimado` solo se llena si la caja, el BAF o el nombre único lo permiten.
- La nota dice qué se vio y qué falta confirmar.

## 5. Errores que ya ocurrieron (para no repetirlos)
- "Symbiote Spider-Man" era **Superior Spider-Man simbionte** (lo corrigió el founder).
- "Moon Knight vaquero" era **Phantom Rider** (lo corrigió el founder).
- Una figura de piel oscura con tela kente se puede confundir entre Black Panther, T'Chaka y otros; queda sin año.
- Conclusión: **la identificación visual sin caja es una hipótesis**, y el founder es quien la confirma.

## 6. Lo que NO se identifica por la imagen
- Estado real (sellado, usado, completo): se toma del aviso o de la caja.
- Autenticidad (réplicas o bootlegs): se marca `posible_replica` solo si el aviso o el precio lo sugieren.
- Año exacto de producción sin caja ni BAF.

## 7. Fechas y contexto del aviso
- **Fecha de publicación** (`fecha_publicacion`): exacta si la captura muestra día y mes (se asume el año de la captura cuando no trae año); aproximada si solo dice "hace N semanas" (se resta de la fecha de la captura); `sin dato` si no aparece.
- **Vendedor:** se anonimiza (iniciales o tipo de tienda). Nunca se guardan nombres completos de personas.
- **Distrito:** el que muestra el aviso; si es una tienda sin distrito, se usa Lima Centro y se anota.

## 8. Qué se excluye del sobreprecio por canal
Compras históricas del founder, lotes, packs sin retail de pack, customs, preventas, líneas ambiguas, "no Legends" (McFarlane, etc.), réplicas, fotos de catálogo y precios muy altos.

## Checklist rápido para una captura nueva
1. ¿Hay caja con nombre? → figura y wave fijos.
2. ¿Hay etiqueta de BAF? → anotar wave y año.
3. ¿El nombre existe en un solo año en el catálogo? → año fijo.
4. Si no: ¿hay accesorios, pieza de BAF o vendedor repetido que lo confirmen? → hipótesis, marcar.
5. Si sigue la duda → "sin identificar", precio sin sobreprecio, preguntar al founder.
6. Anotar fecha de publicación, estado, extras y precio exacto.
