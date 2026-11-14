"""Figuras Lima: arma tu BAF de Marvel Legends (comprador) y fija tu precio de reventa (vendedor)."""
import os
import sys
import tempfile
from pathlib import Path

import folium
import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.parser import parse  # noqa: E402
from backend.matching import (DISTRITOS, catalogo, load_catalog, load_listings, load_reales,  # noqa: E402
                              ofertas_figura, ofertas_importacion, plan_baf)
from backend.pricing import TIPO_CAMBIO, efecto_doble_marginalizacion, retail_usd  # noqa: E402
from backend.waves import load_waves, tabla_wave  # noqa: E402

st.set_page_config(page_title="Figuras Lima", page_icon="🧸", layout="wide")


@st.cache_data
def _datos():
    c = load_catalog()
    return c, load_listings(), ofertas_importacion(c), load_waves(), load_reales()


cat, lst, imp, waves, reales = _datos()
meta = catalogo(cat)
bafs_ord = cat.drop_duplicates("baf").sort_values(["anio", "baf"], ascending=[False, True])
OPCIONES = [f"{r.baf} ({r.anio})" for r in bafs_ord.itertuples()]


def pct(x):
    return "—" if x is None or x != x else f"{x:+.0%}"


def vista_comprador():
    texto = ""
    t_txt, t_voz = st.tabs(["⌨️ Escribir", "🎙️ Hablar"])
    with t_txt:
        texto = st.text_input("¿Qué BAF o figura buscas?", placeholder="Quiero armar el BAF Konshu, vivo en Miraflores") or ""
    with t_voz:
        audio = st.audio_input("Graba tu pedido")
        if audio is not None:
            from ai.transcribe import transcribe

            with st.spinner("Transcribiendo con Whisper (local)…"):
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    f.write(audio.getvalue())
                texto = transcribe(f.name)
                os.unlink(f.name)
            st.info(f"Escuché: “{texto}”")

    c = parse(texto, meta) if texto else None
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
        m = folium.Map(location=centro, zoom_start=11, tiles="cartodbpositron")
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


st.title("🧸 Figuras Lima · Marvel Legends")
st.caption("Arma tu BAF pieza por pieza con vendedores de Lima, o fija tu precio de reventa como vendedor.")
with st.sidebar:
    st.write("Parser: **" + ("Claude (LLM)" if os.getenv("ANTHROPIC_API_KEY") else "Reglas locales (sin API key)") + "**")
    st.caption(f"Catálogo y precios de referencia: Legendsverse (USD). Avisos: **{len(reales)} reales** transcritos de "
               "Marketplace, eBay y Tai Loy, más avisos **simulados** de relleno donde no hay datos reales.")

tab_c, tab_w, tab_v = st.tabs(["🛒 Soy coleccionista", "🔎 Por wave / línea", "🏪 Soy vendedor"])
with tab_c:
    vista_comprador()
with tab_w:
    vista_wave()
with tab_v:
    vista_vendedor()
