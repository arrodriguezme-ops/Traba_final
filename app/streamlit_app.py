"""Figuras Lima: arma tu BAF de Marvel Legends (comprador) y fija tu precio de reventa (vendedor)."""
import os
import sys
import tempfile
from pathlib import Path

import altair as alt
import folium
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.parser import parse  # noqa: E402
from backend.matching import (DISTRITOS, catalogo, load_catalog, load_listings, load_reales,  # noqa: E402
                              ofertas_figura, ofertas_importacion, plan_baf)
from backend.pricing import TIPO_CAMBIO, efecto_doble_marginalizacion, retail_usd  # noqa: E402
from backend.figuras import (buscar, ficha, load_figuras, load_tiendas, normaliza_pedido,  # noqa: E402
                             reales_con_anio, sobreprecio_por_canal)
from backend.estimacion import ajustar, estimar  # noqa: E402
from backend.consolidar import universo  # noqa: E402
from backend.figuras import _norm  # noqa: E402
from backend.waves import load_waves, tabla_wave  # noqa: E402

st.set_page_config(page_title="Figuras Lima", page_icon="🟨", layout="wide")

ESTILO = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Oswald:wght@600;700&display=swap');
:root{--am:#F2B705;--am-osc:#C99700;--gris:#3A3A3A;--gris-cl:#F3F3F1;--borde:#E2E2DE}
header[data-testid="stHeader"]{display:none}
.block-container{padding-top:0!important;max-width:1180px}
.marca{display:flex;align-items:center;justify-content:space-between;padding:22px 0 18px;border-bottom:1px solid var(--borde)}
.marca .logo{font-family:'Oswald',sans-serif;font-weight:700;font-size:2.3rem;letter-spacing:.5px;color:var(--gris);line-height:1}
.marca .logo b{color:var(--am)}
.marca .lema{color:#6b6b6b;font-size:.9rem;text-align:right;max-width:380px}
.marca .logo{white-space:nowrap}
[data-testid="stMainBlockContainer"]>[data-testid="stVerticalBlock"]>[data-testid="stTabs"]>div>[role="tablist"]{background:var(--am);padding:0 8px;margin-bottom:6px}
[data-testid="stMainBlockContainer"]>[data-testid="stVerticalBlock"]>[data-testid="stTabs"]>div>[role="tablist"] [role="tab"]{height:54px;padding:0 22px}
[data-testid="stMainBlockContainer"]>[data-testid="stVerticalBlock"]>[data-testid="stTabs"]>div>[role="tablist"] [role="tab"], [data-testid="stMainBlockContainer"]>[data-testid="stVerticalBlock"]>[data-testid="stTabs"]>div>[role="tablist"] [role="tab"] *{font-weight:700;font-size:1rem;color:#2b2b2b!important}
[data-testid="stMainBlockContainer"]>[data-testid="stVerticalBlock"]>[data-testid="stTabs"]>div>[role="tablist"] [role="tab"][aria-selected="true"]{background:rgba(0,0,0,.09);box-shadow:inset 0 -4px 0 var(--gris)}
.marca .logo span{white-space:nowrap}
h1,h2,h3,h4{color:var(--gris);letter-spacing:-.2px}
h4{border-bottom:2px solid var(--am);padding-bottom:6px;margin-top:1.6rem}
div[data-testid="stMetric"]{background:#fff;border:1px solid var(--borde);border-left:5px solid var(--am);border-radius:2px;padding:14px 16px}
div[data-testid="stMetricLabel"] p{color:#6b6b6b;font-size:.82rem;text-transform:uppercase;letter-spacing:.4px}
div[data-testid="stMetricValue"]{color:var(--gris);font-weight:700}
div[data-testid="stDataFrame"]{border:1px solid var(--borde);border-radius:2px}
.stButton>button,.stDownloadButton>button{background:var(--am);color:#1E1E1E;border:0;border-radius:2px;font-weight:700}
.stButton>button:hover{background:var(--am-osc);color:#fff}
div[data-testid="stAlert"]{border-radius:2px;border-left:5px solid var(--am);background:var(--gris-cl);color:var(--gris)}
section[data-testid="stSidebar"]{background:var(--gris-cl);border-right:1px solid var(--borde)}
div[data-testid="stExpander"]{border:1px solid var(--borde);border-radius:2px}
input,textarea{border-radius:2px!important}
div[data-testid="stImage"] img{border:1px solid var(--borde)}
hr{border-color:var(--borde)}
[role="tab"],[role="tab"] *{color:#2b2b2b!important;transition:none!important}
</style>
"""
st.markdown(ESTILO, unsafe_allow_html=True)


@st.cache_data
def _datos():
    c = load_catalog()
    return c, load_listings(), ofertas_importacion(c), load_waves(), load_reales()


cat, lst, imp, waves, reales = _datos()


@st.cache_data
def _datos_figuras():
    f = load_figuras()
    t = load_tiendas()
    r = reales_con_anio(f)
    return f, t, r, sobreprecio_por_canal(t, r), ajustar(f, r)


figs, tiendas, reales_a, canales, modelo = _datos_figuras()
meta = catalogo(cat)
bafs_ord = cat.drop_duplicates("baf").sort_values(["anio", "baf"], ascending=[False, True])
OPCIONES = [f"{r.baf} ({r.anio})" for r in bafs_ord.itertuples()]


def pct(x):
    return "—" if x is None or x != x else f"{x:+.0%}"


def _texto_busqueda(clave: str, ayuda: str) -> str:
    t_txt, t_voz = st.tabs(["Escribir", "Hablar"])
    texto = ""
    with t_txt:
        texto = st.text_input(ayuda, placeholder="Moon Knight · Wolverine brown suit · Spider-Man 2099 2024",
                              key=f"txt_{clave}") or ""
    with t_voz:
        audio = st.audio_input("Graba tu pedido", key=f"aud_{clave}")
        if audio is not None:
            from ai.transcribe import transcribe

            with st.spinner("Transcribiendo con Whisper (local)…"):
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    f.write(audio.getvalue())
                texto = transcribe(f.name)
                os.unlink(f.name)
            st.info(f"Escuché: “{texto}”")
    return texto


def _soles(x):
    return "—" if x is None or x != x else f"S/ {x:,.0f}"


def _tabla_canales():
    c = canales.copy()
    c["Sobreprecio mediano"] = c["sobreprecio_mediano"].map(pct)
    c["Sobreprecio promedio"] = c["sobreprecio_promedio"].map(pct)
    c["Precio mediano"] = c["precio_mediano_pen"].map(_soles)
    st.dataframe(c[["canal", "Sobreprecio mediano", "Sobreprecio promedio", "Precio mediano", "avisos"]].rename(
        columns={"canal": "Canal", "avisos": "Avisos"}), hide_index=True, use_container_width=True)
    st.caption("Sobreprecio = (Precio_rev − P_retail)/P_retail, con P_retail = retail de Hasbro en USD × "
               f"{TIPO_CAMBIO}. Solo avisos de una figura con año identificado. eBay no incluye envío ni aranceles.")


def vista_figura():
    texto = _texto_busqueda("fig", "¿Qué figura buscas? (con o sin BAF)")
    idx = buscar(texto, figs) if texto else []
    pedido = parse(normaliza_pedido(texto), meta) if texto else None
    if pedido and pedido.baf:
        st.info(f"🧩 **{pedido.baf}** es un BAF: en la pestaña *Armar un BAF* ves sus piezas y dónde conseguirlas.")
    if texto and not idx and not (pedido and pedido.baf):
        st.warning("No encontré esa figura en el catálogo de Marvel Legends. Prueba con el nombre en inglés.")
    if not idx:
        st.markdown("#### Sobreprecio promedio por canal")
        _tabla_canales()
        return
    # Se elige por indice: hay empaques con el mismo nombre y anio (p. ej. dos "Moon Knight (2022)")
    def _etq(i):
        n = int(((figs.loc[idx, "etiqueta"] == figs.at[i, "etiqueta"])).sum())
        extra = f" · pack de {int(figs.at[i, 'n_figuras_pack'])}" if figs.at[i, "n_figuras_pack"] > 1 else ""
        return figs.at[i, "etiqueta"] + extra + (f" · #{figs.at[i, 'id']}" if n > 1 and not extra else "")

    elegido = st.radio("¿Cuál de estas?", idx, format_func=_etq, horizontal=True, key=f"sel_{hash(texto) % 10_000}")
    fila = figs.loc[elegido]
    f = ficha(fila, tiendas, reales_a, cat)
    retail = fila["retail_usd"] if fila["retail_usd"] == fila["retail_usd"] else None
    p_ret = retail * TIPO_CAMBIO if retail else None
    mercado = fila["valor_mercado_usd"] if fila["valor_mercado_usd"] == fila["valor_mercado_usd"] else None
    t, r = f["tiendas"], f["reventa"]

    izq, der = st.columns([1, 3])
    with izq:
        if isinstance(fila["imagen"], str) and fila["imagen"].startswith("http"):
            st.image(fila["imagen"], use_container_width=True)
    with der:
        st.subheader(f"{fila['figura']} · {int(fila['anio'])} · {fila['fabricante']}")
        if len(f["baf"]):
            b = f["baf"].iloc[0]
            st.markdown(f"🧩 Trae la pieza **{b['pieza']}** del BAF **{b['baf']}** (ver pestaña *Armar un BAF*).")
        else:
            st.markdown("Sin pieza de BAF registrada.")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Retail oficial", _soles(p_ret), help=f"US$ {retail:.2f} × {TIPO_CAMBIO}" if retail else "Sin dato")
        k2.metric("Valor en EE. UU.", _soles(mercado * TIPO_CAMBIO) if mercado else "—",
                  help="Ventas completadas en eBay (Legendsverse)" + (f": US$ {mercado:.2f}" if mercado else ""))
        k3.metric("Tiendas en Perú (promedio)", _soles(t["precio_pen"].mean()) if len(t) else "—",
                  delta=(pct((t["precio_pen"].mean() - p_ret) / p_ret) + " vs retail") if len(t) and p_ret else None,
                  delta_color="inverse")
        k4.metric("Reventa (promedio)", _soles(r["precio_pen"].mean()) if len(r) else "—",
                  delta=(pct((r["precio_pen"].mean() - p_ret) / p_ret) + " vs retail") if len(r) and p_ret else None,
                  delta_color="inverse")
        faltan = [n for n, ok in [("retail oficial", p_ret), ("valor en EE. UU.", mercado),
                                  ("precios en tiendas de Perú", len(t)), ("avisos de reventa", len(r))] if not ok]
        if faltan:
            st.info("**No hay datos de " + ", ".join(faltan) + "** para esta figura. "
                    "Abajo tienes el sobreprecio típico por canal como referencia.")

    est_n = est_u = None
    if modelo and p_ret:
        est_n, est_u = estimar(modelo, elegido, True), estimar(modelo, elegido, False)
    if est_n and est_u:
        st.markdown("#### Precio justo estimado en Lima (Marketplace)")
        e1, e2, e3 = st.columns(3)
        e1.metric("Usada / suelta", _soles(est_u["estimado"]), help=f"Rango 80 %: {_soles(est_u['p10'])} – {_soles(est_u['p90'])}")
        e2.metric("Nueva / en caja", _soles(est_n["estimado"]), help=f"Rango 80 %: {_soles(est_n['p10'])} – {_soles(est_n['p90'])}")
        e3.metric("Sobreprecio implícito (nueva)", pct((est_n["estimado"] - p_ret) / p_ret), help="Frente al retail × 3.45")
        st.caption(f"Rango del 80 %: usada {_soles(est_u['p10'])}–{_soles(est_u['p90'])}; nueva {_soles(est_n['p10'])}–"
                   f"{_soles(est_n['p90'])}. Modelo con {modelo['n']} avisos reales (R² {modelo['r2']:.2f}); "
                   f"error medio fuera de muestra S/ {modelo['mae']:.0f} (usar solo la mediana: S/ {modelo['mae_base']:.0f}).")
        with st.expander("Qué covariables usa y cuánto pesa cada una"):
            ef = modelo["efectos"].copy()
            def _txt(nombre, fila):
                if nombre in ("Retail (log)", "Valor de mercado EE. UU. vs retail (log)", "Versiones del personaje (log)"):
                    return f"si sube 10 %, el precio cambia {(1.1 ** fila['coef'] - 1) * 100:+.1f} %"
                if nombre == "Antigüedad (años)":
                    return f"por cada año: {fila['efecto_pct'] * 100:+.1f} %"
                return f"{fila['efecto_pct'] * 100:+.0f} % si aplica"
            ef["Efecto en el precio"] = [_txt(n, r_) for n, r_ in ef.iterrows()]
            st.dataframe(ef[["Efecto en el precio"]], use_container_width=True)
            st.caption("Cada covariable se mide con todas las demás constantes. Es una estimación de referencia, "
                       "no un precio exacto: no mide rareza ni popularidad del personaje, y la muestra viene sobre todo de "
                       "Marketplace.")
    elif p_ret:
        st.info("No hay suficientes datos para estimar el precio justo de esta figura.")

    hist = _historico()
    hf = hist[(hist["_n"] == _norm(fila["figura"])) & (hist["anio"] == int(fila["anio"]))]
    if len(_limpio(hf)) >= 2:
        st.markdown("#### Historial de precios (todas las fuentes)")
        _grafico_historial(hf, p_ret)
        st.caption(f"{len(_limpio(hf))} observaciones entre {_limpio(hf)['fecha'].min():%Y-%m} y {_limpio(hf)['fecha'].max():%Y-%m}. "
                   "Más detalle en la pestaña *Serie histórica*.")

    if len(t):
        st.markdown("#### En tiendas de Perú")
        v = t[["tienda", "titulo", "vendedor", "precio_pen", "precio_lista_pen", "anio", "confianza", "url"]].copy()
        if p_ret:
            v["Sobreprecio"] = ((v["precio_pen"] - p_ret) / p_ret).map(pct)
        st.dataframe(v.rename(columns={"tienda": "Tienda", "titulo": "Producto", "vendedor": "Vendedor",
                                       "precio_pen": "Precio S/", "precio_lista_pen": "Lista S/",
                                       "anio": "Año (estimado)", "confianza": "Coincidencia", "url": "Link"}),
                     hide_index=True, use_container_width=True,
                     column_config={"Link": st.column_config.LinkColumn("Link", display_text="ver")})
        st.caption("Precios observados el 14-11-2026. «Coincidencia baja» = el título trae palabras extra: puede ser "
                   "otra versión del personaje o un pack.")
    if len(r):
        st.markdown("#### Reventa (avisos reales)")
        v = r[["canal", "vendedor", "estado", "precio_pen", "distrito", "linea_interpretada", "notas"]].copy()
        if p_ret:
            v["Sobreprecio"] = ((v["precio_pen"] - p_ret) / p_ret).map(pct)
        st.dataframe(v.rename(columns={"canal": "Canal", "vendedor": "Vendedor", "estado": "Estado",
                                       "precio_pen": "Precio S/", "distrito": "Zona",
                                       "linea_interpretada": "Línea según el aviso", "notas": "Notas"}),
                     hide_index=True, use_container_width=True)
        st.caption("Avisos transcritos de capturas (vendedores anonimizados). Se emparejan por nombre: si el aviso "
                   "no dice la línea, puede ser otra versión del mismo personaje.")
    st.markdown("#### Sobreprecio promedio por canal (todas las figuras)")
    _tabla_canales()


def vista_comprador():
    st.markdown("Si coleccionas un **Build-A-Figure**, marca las piezas que ya tienes y te armamos el plan para "
                "conseguir las que faltan.")
    texto = _texto_busqueda("baf", "¿Qué BAF quieres armar?")

    c = parse(normaliza_pedido(texto), meta) if texto else None
    if c:
        with st.sidebar:
            st.caption("Cómo se interpretó tu pedido")
            st.json(c.model_dump(exclude_none=True))

    idx = 0
    if c and (c.baf or c.figura):
        b = c.baf or cat[cat["figura"] == c.figura].iloc[0]["baf"]
        idx = next((i for i, o in enumerate(OPCIONES) if o.rsplit(" (", 1)[0] == b), 0)
    dist_ini = list(DISTRITOS).index(c.distrito) if c and c.distrito in DISTRITOS else 0

    k = hash(texto) % 10_000
    col1, col2, col3 = st.columns([2, 1, 1])
    baf = col1.selectbox("BAF", OPCIONES, index=idx, key=f"baf_{k}").rsplit(" (", 1)[0]
    distrito = col2.selectbox("Tu distrito", list(DISTRITOS), index=dist_ini, key=f"d_{k}")
    presupuesto = col3.number_input("Presupuesto máx. por pieza (S/)", min_value=0, key=f"p_{k}",
                                    value=int(c.max_precio_pen) if c and c.max_precio_pen else 0)

    if c and c.figura and not c.baf:
        st.info(f"**{c.figura}** viene en el wave de **{baf}**. Abajo, sus ofertas y el BAF completo.")
        o = ofertas_figura(lst, c.figura, distrito, presupuesto or None, baf)
        if o.empty:
            st.warning("No hay avisos de esa figura dentro de tu presupuesto.")
        else:
            st.dataframe(o[["vendedor", "distrito", "condicion", "incluye_pieza", "precio_pen", "envio_pen",
                            "total_pen", "eta_min"]].rename(columns={"incluye_pieza": "Trae pieza BAF"}),
                         hide_index=True, use_container_width=True)

    piezas = cat[cat["baf"] == baf].drop_duplicates("pieza")
    st.subheader(f"{baf} · {int(piezas.iloc[0]['anio'])} · {len(piezas)} piezas")
    st.markdown("**Marca las piezas que ya tienes:**")
    tengo = set()
    for col, p in zip(st.columns(len(piezas)), piezas.itertuples()):
        with col:
            if isinstance(p.imagen_pieza, str) and p.imagen_pieza.startswith("http"):
                st.image(p.imagen_pieza, use_container_width=True)
            else:
                st.markdown("<div style='height:120px;display:flex;align-items:center;justify-content:center;"
                            "border:1px dashed #888;border-radius:8px;color:#888'>sin imagen</div>", unsafe_allow_html=True)
            if st.checkbox(p.pieza, key=f"tengo_{baf}_{p.pieza}"):
                tengo.add(p.pieza)
            st.caption(f"viene con **{p.figura}**")

    plan, res = plan_baf(cat, lst, baf, tengo, distrito, presupuesto or None, imp)
    if plan.empty:
        st.success("🎉 ¡Tienes todas las piezas! Tu BAF está completo.")
        return
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Te faltan", f"{res['faltan']} de {res['total_piezas']}")
    m2.metric("Costo estimado (con envío)", f"S/ {res['costo_pen']:,.0f}")
    m3.metric("Sin oferta en Lima", res["sin_oferta"])
    m4.metric("Piezas con aviso real", f"{res['reales']} de {res['faltan']}")

    izq, der = st.columns([3, 2])
    with izq:
        tabla = plan[["pieza", "figura", "fuente", "vendedor", "distrito", "precio_pen", "envio_pen", "total_pen",
                      "eta_min"]].copy()
        tabla["fuente"] = tabla["fuente"].map({"real": "✅ real", "sintetico": "simulado"}).fillna("—")
        tabla["Sobreprecio vs retail"] = plan["efecto_dm"].map(pct)
        tabla["eBay (S/, sin aranceles)"] = plan["ebay_pen"].map(lambda x: "—" if x is None or x != x else f"{x:,.0f}")
        st.dataframe(tabla.rename(columns={"pieza": "Pieza", "figura": "Figura", "fuente": "Aviso", "vendedor": "Vendedor",
                                           "distrito": "Zona", "precio_pen": "Precio S/", "envio_pen": "Envío S/",
                                           "total_pen": "Total S/", "eta_min": "Min"}),
                     hide_index=True, use_container_width=True)
        st.caption("Oferta más barata por pieza (con la pieza del BAF incluida). Sobreprecio = (Precio_rev − P_retail)/P_retail. "
                   "Aviso ✅ real = transcrito de una captura de Marketplace o de una tienda; «simulado» = dato sintético de relleno. "
                   "Envío y tiempo son un modelo. eBay = precio + envío a Perú si se vio, sin aranceles.")
    with der:
        centro = DISTRITOS[distrito]
        m = folium.Map(location=centro, zoom_start=11, tiles="OpenStreetMap")
        folium.Marker(centro, tooltip=f"Tú ({distrito})", icon=folium.Icon(color="red", icon="home")).add_to(m)
        for r in plan.dropna(subset=["lat"]).itertuples():
            folium.Marker([r.lat, r.lon], tooltip=f"{r.pieza}: {r.figura} · S/ {r.precio_pen:.0f}",
                          icon=folium.Icon(color="blue")).add_to(m)
            folium.PolyLine([[r.lat, r.lon], centro], weight=1, color="gray", opacity=0.5).add_to(m)
        components.html(m._repr_html_(), height=400)


def vista_wave():
    st.markdown("Para figuras **sin BAF** (o de cualquier wave): elige el wave y mira retail, valor en EE. UU. y los avisos "
                "reales de Lima. Un aviso solo cuenta para un wave si el vendedor indica la línea; si no, queda abajo "
                "como «wave sin confirmar» porque nombres como Thor o Spider-Man están en decenas de waves.")
    c1, c2, c3 = st.columns([1, 2, 1])
    solo_sin_baf = c3.checkbox("Solo waves sin BAF", value=True)
    anios = sorted(waves["anio"].dropna().astype(int).unique(), reverse=True)
    anio = c1.selectbox("Año", anios, index=anios.index(2026) if 2026 in anios else 0, key="w_anio")
    w = waves[waves["anio"] == anio]
    con_baf = set(cat["wave"].dropna()) | set(cat["baf"])
    if solo_sin_baf:
        w = w[~w["wave"].isin(con_baf)]
    if w.empty:
        st.info("No hay waves de ese tipo ese año.")
        return
    nombre = c2.selectbox("Wave / línea", list(w["wave"]), key=f"w_{anio}_{solo_sin_baf}")
    fila = w[w["wave"] == nombre].iloc[0]
    tabla, retail = tabla_wave(nombre, int(fila["anio"]), fila["retail_prom_usd"], cat)
    k1, k2, k3 = st.columns(3)
    k1.metric("Figuras en el wave", len(tabla))
    k2.metric("Retail (USD)", f"{retail:.2f}" if retail else "—")
    k3.metric("Con aviso real confirmado", int((tabla["avisos"] > 0).sum()))
    ver = tabla[["figura", "mercado_usd", "avisos", "mejor_pen", "donde", "fuente"]].copy()
    ver["Sobreprecio vs retail"] = tabla["efecto_dm"].map(pct)
    ver["mercado_usd"] = ver["mercado_usd"].map(lambda x: "—" if x != x else f"{x:,.2f}")
    st.dataframe(ver.rename(columns={"figura": "Figura", "mercado_usd": "Valor EE. UU. (USD)", "avisos": "Avisos",
                                     "mejor_pen": "Mejor precio S/", "donde": "Zona", "fuente": "Fuente"}),
                 hide_index=True, use_container_width=True)
    st.caption(f"Valor EE. UU. = ventas completadas en eBay (Legendsverse). Sobreprecio = (Precio_rev − P_retail)/P_retail "
               f"con P_retail = USD {retail or 0:.2f} × {TIPO_CAMBIO}. Línea: {fila['url_wave']}")
    with st.expander(f"Todos los avisos reales ({len(reales)}), incluidos eBay y los de wave sin confirmar"):
        r = reales[["figura", "linea_interpretada", "estado", "precio_pen", "distrito", "fuente"]].sort_values("figura")
        st.dataframe(r.rename(columns={"figura": "Figura", "linea_interpretada": "Línea según vendedor/captura",
                                       "estado": "Estado", "precio_pen": "Precio S/", "distrito": "Zona",
                                       "fuente": "Fuente"}), hide_index=True, use_container_width=True)


def vista_vendedor():
    st.markdown("Elige la figura, pon tu **precio ofrecido** y mira cuánto te estás separando del retail oficial.")
    c1, c2 = st.columns(2)
    sel = c1.selectbox("BAF", OPCIONES, key="v_baf")
    baf = sel.rsplit(" (", 1)[0]
    piezas = cat[cat["baf"] == baf].drop_duplicates("pieza")
    figura = c2.selectbox("Figura", list(piezas["figura"]), key=f"v_fig_{baf}")
    fila = piezas[piezas["figura"] == figura].iloc[0]
    anio = int(fila["anio"])

    r_def = retail_usd(anio)
    c3, c4, c5 = st.columns(3)
    precio = c3.number_input("Tu precio ofrecido, Precio_rev (S/)", min_value=0.0, value=100.0, step=5.0, key="v_precio")
    retail = c4.number_input(f"P_retail en USD ({anio})", min_value=0.0, step=0.5, key=f"v_ret_{anio}",
                             value=r_def or 0.0, help="Precio de lista de Hasbro. Antes de 2012 no hay dato: ingrésalo.")
    tc = c5.number_input("Tipo de cambio (S/ por USD)", min_value=1.0, value=float(TIPO_CAMBIO), step=0.05, key="v_tc")
    if not r_def:
        st.warning(f"No tengo retail de referencia para {anio}. Ingresa el P_retail para calcular.")

    efecto = efecto_doble_marginalizacion(precio, retail, tc)
    if efecto is None:
        return
    p_retail_pen = retail * tc
    k1, k2, k3 = st.columns(3)
    k1.metric("P_retail (S/)", f"{p_retail_pen:,.2f}", help=f"${retail:.2f} × {tc}")
    k2.metric("Tu Precio_rev (S/)", f"{precio:,.2f}", delta=f"{precio - p_retail_pen:+,.2f} S/")
    k3.metric("Efecto (Prev − Pretail) / Pretail", f"{efecto:+.1%}")

    ref_usd = fila["precio_figura_usd"]
    ref_pen = ref_usd * tc if ref_usd == ref_usd else None
    comp = lst[(lst["figura"] == figura) & (lst["baf"] == baf)]
    st.markdown("**Cómo te comparas:**")
    lineas = [f"- Retail oficial: S/ {p_retail_pen:,.0f} ({retail:.2f} USD)."]
    if ref_pen:
        lineas.append(f"- Valor de mercado en EE. UU. (ventas en eBay): S/ {ref_pen:,.0f} ({ref_usd:.2f} USD), "
                      f"o sea {(ref_pen - p_retail_pen) / p_retail_pen:+.0%} vs retail.")
    if len(comp):
        med = comp["precio_pen"].median()
        nreal = int((comp["fuente"] == "real").sum())
        lineas.append(f"- Otros vendedores en Lima: mediana S/ {med:,.0f} "
                      f"({efecto_doble_marginalizacion(med, retail, tc):+.0%} vs retail), {len(comp)} avisos "
                      f"({nreal} reales, {len(comp) - nreal} simulados).")
    st.markdown("\n".join(lineas))
    if efecto > 0.5:
        st.warning("Tu sobreprecio es alto: el comprador puede preferir importar directamente.")
    elif efecto < 0:
        st.info("Estás por debajo del retail: vende rápido pero con margen negativo sobre el precio de lista.")
    else:
        st.success("Sobreprecio moderado sobre el retail.")


st.markdown("<div class='marca'><div class='logo'>FIGURAS<b>LIMA</b> <span style='font-size:1rem;color:#6b6b6b;"
            "font-family:sans-serif;font-weight:600;letter-spacing:1px'>MARVEL LEGENDS</span></div>"
            "<div class='lema'>Retail, precio en tiendas de Perú y reventa en Lima, y cuánto sobreprecio cobra cada canal.</div></div>",
            unsafe_allow_html=True)
with st.sidebar:
    st.write("Parser: **" + ("Claude (LLM)" if os.getenv("ANTHROPIC_API_KEY") else "Reglas locales (sin API key)") + "**")
    st.caption(f"Catálogo y precios de referencia: Legendsverse (USD). Avisos: **{len(reales)} reales** transcritos de "
               "Marketplace, eBay, Tai Loy (incluye su histórico de Wayback Machine), más avisos **simulados** de relleno donde no hay datos reales.")

EXCL_GRAFICO = "custom|lote|pack|accesorio|pieza_suelta|no_legends|precio_dudoso|incompleto|subasta|sin_identificar|replica"


@st.cache_data
def _historico():
    d = pd.read_csv(Path(__file__).resolve().parent.parent / "data" / "observaciones_precios.csv", parse_dates=["fecha"])
    d["_n"] = d["figura"].map(lambda x: _norm(x) if isinstance(x, str) else None)
    return d


def _limpio(d):
    return d[~d["marca_calidad"].fillna("").str.contains(EXCL_GRAFICO) & d["precio_pen"].notna() & d["fecha"].notna()]


def _grafico_historial(h, retail_pen=None):
    h = _limpio(h)
    if len(h) < 2:
        return False
    base = alt.Chart(h).encode(
        x=alt.X("fecha:T", title="Fecha de la observación"),
        y=alt.Y("precio_pen:Q", title="Precio (S/)"),
        color=alt.Color("canal:N", title="Canal", scale=alt.Scale(scheme="set2")),
        tooltip=["fecha:T", "canal", "vendedor", alt.Tooltip("precio_pen:Q", title="Precio S/"), "titulo_original"])
    capas = [base.mark_line(strokeWidth=1.5, opacity=.5) + base.mark_point(size=70, filled=True)]
    if retail_pen:
        capas.append(alt.Chart(pd.DataFrame({"y": [retail_pen]})).mark_rule(color="#3A3A3A", strokeDash=[6, 4]).encode(y="y:Q"))
    st.altair_chart(alt.layer(*capas).properties(height=320).interactive(), use_container_width=True)
    if retail_pen:
        st.caption(f"Línea punteada = retail oficial × {TIPO_CAMBIO} (S/ {retail_pen:,.0f}).")
    return True


@st.cache_data
def _passthrough():
    from backend.passthrough import tabla
    return tabla(_historico(), B=150)


def vista_passthrough():
    st.markdown("#### Pass-through: ¿cuánto del precio en USD llega al precio final en Lima?")
    t = _passthrough()
    if t.empty:
        return
    v = t.copy()
    f = lambda a, lo, hi: f"{a:.2f} [{lo:.2f}; {hi:.2f}]"
    v["Elasticidad al precio de lista"] = [f(a, b, c) for a, b, c in zip(v.b_lista, v.b_lista_lo, v.b_lista_hi)]
    v["Pass-through del tipo de cambio"] = [f(a, b, c) for a, b, c in zip(v.b_tc, v.b_tc_lo, v.b_tc_hi)]
    v["Pendiente en niveles (S/ por S/)"] = [f(a, b, c) for a, b, c in zip(v.niv, v.niv_lo, v.niv_hi)]
    v["Efecto popular"] = v.b_pop.map(lambda a: f"{a:+.2f}" if a == a else "—")
    v["Efecto deluxe"] = v.b_dlx.map(lambda a: f"{a:+.2f}" if a == a else "—")
    st.dataframe(v[["modelo", "n", "figuras", "Elasticidad al precio de lista", "Pass-through del tipo de cambio",
                    "Pendiente en niveles (S/ por S/)", "Efecto popular", "Efecto deluxe"]].rename(columns={"modelo": "Especificación", "n": "Obs.", "figuras": "Figuras"}),
                 hide_index=True, use_container_width=True)
    st.caption("Log-log con efectos fijos de canal, solo figuras estándar de 6\" (retail US$14.99-29.99). IC 95% por bootstrap agrupado por figura. "
               "Elasticidad ≈ 1: el precio final sube proporcionalmente al precio de lista. El tipo de cambio NO está identificado "
               "(intervalos enormes): varía casi solo entre épocas (2010-11 vs 2022-26) y se confunde con cambios de canal y fabricante. "
               "La pendiente en niveles (≈2.4) indica que cada S/ 1 de costo de lista se traduce en ~S/ 2.4 de precio final: un multiplicador de márgenes, "
               "no comparable directamente con los benchmarks de demanda lineal (1 competencia, 0.5 monopolio, 0.25 doble marginalización). "
               "Popular = X-Men, Spider-verso (no de películas), Avengers clásicos, 4 Fantásticos, Strange; deluxe = línea Maximum, Deluxe o Retro. Resultado exploratorio: el precio de lista no es un shifter de costo puro (los deluxe y populares son endógenos).")


def vista_historico():
    d = _historico()
    u = universo(d)
    st.markdown("#### Cobertura: ¿cuántas figuras únicas llevamos?")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Figuras únicas en el catálogo", f"{u['catalogo_figuras_unicas']:,}",
              help=f"Figura + año, sin packs. El catálogo tiene {u['catalogo_empaques']:,} empaques y {u['nombres_unicos']:,} nombres distintos.")
    k2.metric("Con al menos una observación", f"{u['con_observaciones']:,}",
              delta=f"{u['con_observaciones'] / u['catalogo_figuras_unicas']:.0%} del universo", delta_color="off")
    k3.metric("Observaciones de precio", f"{u['filas']:,}")
    k4.metric("Observaciones sin cruzar", f"{u['sin_cruzar']:,}", help="Títulos que no se pudieron emparejar con una figura del catálogo.")
    por = d.groupby("fuente_dato").agg(observaciones=("precio_pen", "size"), desde=("fecha", "min"), hasta=("fecha", "max")).reset_index()
    por["figuras_unicas"] = por["fuente_dato"].map(u["por_fuente"]).fillna(0).astype(int)
    por["desde"], por["hasta"] = por["desde"].dt.strftime("%Y-%m"), por["hasta"].dt.strftime("%Y-%m")
    st.dataframe(por[["fuente_dato", "observaciones", "figuras_unicas", "desde", "hasta"]].rename(
        columns={"fuente_dato": "Fuente", "observaciones": "Observaciones", "figuras_unicas": "Figuras únicas", "desde": "Desde", "hasta": "Hasta"}),
        hide_index=True, use_container_width=True)
    st.caption("Fuentes: avisos reales transcritos, tiendas peruanas (14-11-2026) y series de Wayback Machine (Tai Loy, Seven Figuarts, "
               "Toys Master, MercadoLibre Perú 2010–2011). Una figura = nombre + año de lanzamiento; los packs se cuentan aparte.")

    st.markdown("#### Sobreprecio mediano por año y canal")
    c = _limpio(d[d["sobreprecio_tc_epoca"].notna()])
    c = c[c["sobreprecio_tc_epoca"].between(-.9, 5)]
    g = c.groupby(["anio_obs", "canal"]).agg(n=("precio_pen", "size"), sobreprecio=("sobreprecio_tc_epoca", "median")).reset_index()
    g = g[g["n"] >= 3]
    if len(g):
        st.altair_chart(alt.Chart(g).mark_line(point=True).encode(
            x=alt.X("anio_obs:O", title="Año"), y=alt.Y("sobreprecio:Q", title="Sobreprecio mediano", axis=alt.Axis(format="%")),
            color=alt.Color("canal:N", title="Canal", scale=alt.Scale(scheme="set2")),
            tooltip=["anio_obs", "canal", alt.Tooltip("sobreprecio:Q", format="+.0%"), "n"]).properties(height=320), use_container_width=True)
        st.caption("Sobreprecio frente al retail de lista × tipo de cambio promedio del año de la observación (aprox.). "
                   "Solo canal-año con 3 o más observaciones.")

    st.markdown("#### Historial por figura")
    n_obs = _limpio(d[d["figura"].notna()]).groupby(["_n", "anio"]).agg(figura=("figura", "first"), obs=("precio_pen", "size")).reset_index()
    n_obs = n_obs[n_obs["obs"] >= 2].sort_values("obs", ascending=False)
    n_obs["etq"] = n_obs["figura"] + " (" + n_obs["anio"].astype(int).astype(str) + ") · " + n_obs["obs"].astype(str) + " obs."
    if n_obs.empty:
        st.info("Todavía no hay figuras con 2 o más observaciones.")
        return
    sel = st.selectbox("Figura con historial", n_obs["etq"].tolist(), key="hist_sel")
    fila = n_obs[n_obs["etq"] == sel].iloc[0]
    h = d[(d["_n"] == fila["_n"]) & (d["anio"] == fila["anio"])]
    ret = h["retail_usd"].dropna()
    _grafico_historial(h, float(ret.iloc[0]) * TIPO_CAMBIO if len(ret) else None)
    v = h[["fecha", "canal", "vendedor", "precio_pen", "estado", "sobreprecio_tc_epoca", "titulo_original"]].sort_values("fecha").copy()
    v["fecha"] = v["fecha"].dt.strftime("%Y-%m-%d")
    v["sobreprecio_tc_epoca"] = v["sobreprecio_tc_epoca"].map(lambda x: pct(x) if x == x else "—")
    st.dataframe(v.rename(columns={"fecha": "Fecha", "canal": "Canal", "vendedor": "Vendedor", "precio_pen": "Precio S/", "estado": "Estado",
                                   "sobreprecio_tc_epoca": "Sobreprecio", "titulo_original": "Título original"}),
                 hide_index=True, use_container_width=True)


tab_f, tab_b, tab_w, tab_h, tab_v = st.tabs(["Buscar figura", "Armar un BAF", "Por wave / línea",
                                             "Serie histórica", "Soy vendedor"])
with tab_f:
    vista_figura()
with tab_b:
    vista_comprador()
with tab_w:
    vista_wave()
with tab_h:
    vista_historico()
    vista_passthrough()
with tab_v:
    vista_vendedor()
