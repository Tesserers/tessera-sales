# -*- coding: utf-8 -*-
"""Tessera · Alta de vacante/servicio (Sales) → genera ficha + JD y la envía a Operaciones."""
import os, base64, smtplib, re
from email.message import EmailMessage
import requests
import streamlit as st
import anthropic
from PIL import Image
from ficha_pdf import generar_ficha
from _brand import render_wordmark, FONTS

st.set_page_config(page_title="Tessera · Alta de vacante", page_icon="📝", layout="centered")
MODEL = "claude-sonnet-4-6"
OPS_EMAIL_DEFAULT = "talent.operations@tesseraservices.com"

def ruta(*p): return os.path.join(os.path.dirname(os.path.abspath(__file__)), *p)

def _b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

def wordmark_b64():
    p = ruta("fonts", "wm_sales.png")
    if not os.path.exists(p):
        render_wordmark("TESSERA", (240, 232, 222, 255), p, tracking=10)
    return _b64(p)

# ---------- estilos + hero ----------
def header():
    wm = wordmark_b64()
    st.markdown(f"""
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Raleway:wght@300;400;500;600;700;800&display=swap');
      html, body, .stApp, button, input, textarea {{ font-family:'Raleway',sans-serif; }}
      .stApp {{ background:#F4F1EA; }}
      .block-container {{ padding-top:2rem; max-width:820px; }}
      [data-testid="stHeader"] {{ background:transparent; }}
      h1,h2,h3,h4, .stMarkdown p, .stMarkdown li, [data-testid="stWidgetLabel"] p, .stRadio label p {{ color:#20202C !important; }}
      [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] * {{ color:#7A7A82 !important; }}
      hr {{ border-color:#DED7C8 !important; }}
      .stTextInput input, .stTextArea textarea, [data-baseweb="select"]>div, .stDateInput input {{
        background:#FFFFFF!important;color:#20202C!important;border-radius:8px!important;border:1px solid #CFC7B6!important; }}
      .stTextInput input:focus, .stTextArea textarea:focus {{ border-color:#202031!important;box-shadow:0 0 0 2px rgba(32,32,49,.15)!important; }}
      [data-baseweb="select"] * {{ color:#20202C; }}
      .stButton button, .stDownloadButton button {{ border-radius:8px;font-weight:700;padding:.5rem 1.2rem;transition:all .16s ease; }}
      .stButton button[kind="primary"], .stDownloadButton button[kind="primary"] {{ background:#202031;border:1px solid #202031;color:#F0E8DE; }}
      .stButton button[kind="primary"]:hover, .stDownloadButton button[kind="primary"]:hover {{ background:#0F1A38;border-color:#0F1A38;color:#FFFFFF; }}
      .stButton button[kind="secondary"] {{ background:#FFFFFF;border:1px solid #CFC7B6;color:#20202C; }}
      .stButton button[kind="secondary"]:hover {{ border-color:#202031; }}
      .hdr {{ background:#202031;border-radius:10px;padding:22px 28px;margin-bottom:22px;
              display:flex;align-items:center;justify-content:space-between; }}
      .hdr img {{ height:34px; }}
      .hdr .t {{ color:#C8CBD6;font-size:12px;font-weight:600;letter-spacing:.5px;text-align:right; }}
      .hdr .t b {{ color:#F0E8DE;display:block;font-size:13px;letter-spacing:1.5px; }}
    </style>
    <div class="hdr">
      <img src="data:image/png;base64,{wm}"/>
      <div class="t"><b>ALTA DE VACANTE / SERVICIO</b>Sales → Operaciones</div>
    </div>
    """, unsafe_allow_html=True)

# ---------- password ----------
def check_password():
    pw = ""
    try: pw = st.secrets.get("APP_PASSWORD", "")
    except Exception: pw = ""
    if not pw:
        return True
    if st.session_state.get("auth"):
        return True
    header()
    c = st.text_input("Contraseña", type="password")
    if c and c == pw:
        st.session_state["auth"] = True; st.rerun()
    elif c:
        st.error("Contraseña incorrecta.")
    return False

# ---------- helpers IA ----------
def _client():
    return anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])

def _candidatos_url(u):
    u = u.strip().strip("/").replace(" ", "")
    u = re.sub(r"^https?://", "", u, flags=re.I)      # quita protocolo si lo puso
    u = re.sub(r"^www\.", "", u, flags=re.I)          # quita www
    if "." in u:                                       # ya trae dominio (empresa.com)
        base = [u]
    else:                                              # solo el nombre → probamos dominios
        base = [u + ".com", u + ".es", u + ".io", u + ".net"]
    out = []
    for b in base:
        out += ["https://" + b, "https://www." + b]
    return out

SECTORES = ["Tecnología","Software / SaaS","Telecomunicaciones","Finanzas","Banca","Seguros","Fintech",
    "Consultoría","Servicios profesionales","Legal","RRHH y Personas","Marketing y Medios","Publicidad",
    "Ventas / Comercial","Retail / E-commerce","Gran consumo (FMCG)","Alimentación y bebidas","Hostelería y turismo",
    "Ingeniería","Construcción","Inmobiliario","Industrial / Manufactura","Automoción","Aeroespacial y Defensa",
    "Energía y Renovables","Utilities","Química","Farmacéutico","Sanidad y salud","Biotecnología",
    "Logística y transporte","Distribución","Educación y formación","Deporte y ocio","Moda y textil",
    "Agroalimentario","Medioambiente","Administración pública","ONG / Tercer sector","Startup","Otro"]

def resumir_empresa(url):
    """Devuelve (resumen, sector_sugerido) a partir de la web. sector puede ser '' si no encaja."""
    if not url.strip():
        return "", ""
    texto = ""
    for cand in _candidatos_url(url):
        try:
            r = requests.get(cand, timeout=12, headers={"User-Agent": "Mozilla/5.0"}, allow_redirects=True)
            if r.status_code < 400 and r.text:
                t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", r.text, flags=re.S)
                t = re.sub(r"<[^>]+>", " ", t)
                t = re.sub(r"\s+", " ", t).strip()
                if len(t) > 120:
                    texto = t[:3500]; break
        except Exception:
            continue
    if not texto:
        return ("(No pude acceder a la web. Revisa el enlace: pon la dirección completa, "
                "por ejemplo https://www.alimerka.es)", "")
    import json as _json
    msg = _client().messages.create(model=MODEL, max_tokens=400,
        system=("A partir del texto de la web de una empresa, devuelve SOLO un JSON válido, sin vallas de código: "
                '{"resumen": str, "sector": str}. "resumen" = 2-3 frases (español de España, sobrio, sin inventar) '
                "sobre qué hace la empresa y su tamaño si se deduce. "
                f'"sector" = elige EXACTAMENTE uno de esta lista: {SECTORES}. Si ninguno encaja, usa "Otro".'),
        messages=[{"role": "user", "content": texto}])
    raw = "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", None) == "text").strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    try:
        s, e = raw.find("{"), raw.rfind("}")
        obj = _json.loads(raw[s:e+1])
        sec = obj.get("sector", "")
        if sec not in SECTORES:
            sec = ""
        return obj.get("resumen", "").strip(), sec
    except Exception:
        return raw, ""

QUIENES = ("En Tessera acompañamos a compañías en su crecimiento desde una visión integral de personas, negocio y "
    "estructura. Trabajamos como partners en la construcción de equipos y en la toma de decisiones importantes, "
    "combinando talento y estrategia para profesionalizar procesos críticos allí donde más impacto se genera. "
    "Creemos en construir better decisions, together, colaborando de forma cercana con compañías y profesionales "
    "para conectar talento con proyectos en momentos clave de crecimiento.")
NOTA = ("En Tessera gestionamos el proceso de selección en colaboración con la compañía, acompañando tanto al cliente "
    "como a los profesionales durante todas las fases, con un enfoque cercano, transparente y profesional.")

def generar_jd(data):
    sistema = (
        "Redactas ofertas de empleo (JD) de Tessera Human Capital en español de España. Usa EXACTAMENTE esta "
        "estructura y estos encabezados, en este orden:\n"
        "Quiénes somos\n(texto fijo que te doy, cópialo tal cual)\n\nEl reto\n(2-3 frases + viñetas de responsabilidades)\n\n"
        "Requisitos\n(viñetas)\n\nSerá un plus si\n(viñetas)\n\nQué se ofrece\n(viñetas)\n\nNota sobre el proceso\n"
        "(texto fijo que te doy, cópialo tal cual).\n"
        "Reglas: viñetas con guion '-'; no uses la palabra 'clave' (usa 'críticos' o 'importantes'); no inventes datos "
        "que no estén; no menciones el nombre del cliente; sin em dashes; tono cercano y profesional. Devuelve solo la JD.")
    payload = {"quienes_somos_fijo": QUIENES, "nota_proceso_fijo": NOTA,
               "rol": data.get("titulo", ""), "empresa_tipo_sector": data.get("sector", ""),
               "ubicacion_modalidad": " ".join([data.get("ubicacion", ""), data.get("modalidad", "")]).strip(),
               "responsabilidades": data.get("responsabilidades", ""), "requisitos": data.get("requisitos", ""),
               "idiomas": data.get("idiomas", ""),
               "que_se_ofrece": " · ".join([x for x in [data.get("banda", ""), data.get("variable", ""),
                    data.get("beneficios", ""), data.get("modalidad", ""), data.get("presupuesto", ""),
                    data.get("duracion", "")] if x]),
               "atraer": data.get("atraer", "")}
    import json
    msg = _client().messages.create(model=MODEL, max_tokens=1500, system=sistema,
        messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}])
    return "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", None) == "text").strip()

CAMPOS_ES = {
    "empresa": "Empresa", "sector": "Sector", "web": "Web", "empresa_resumen": "Sobre la empresa",
    "sales_nombre": "Comercial", "sales_email": "Email del comercial",
    "titulo": "Título del puesto/servicio", "responsabilidades": "Misión y responsabilidades",
    "requisitos": "Requisitos", "idiomas": "Idiomas",
    "banda": "Banda salarial fija", "variable": "Retribución variable", "beneficios": "Beneficios",
    "modalidad": "Modalidad", "dias_presenciales": "Días presenciales/semana", "ubicacion": "Ubicación", "horario": "Horario de los empleados",
    "fases": "Fases del proceso", "pruebas": "Pruebas técnicas", "interlocutor": "Interlocutor",
    "fecha_inicio": "Fecha objetivo/inicio", "atraer": "Por qué unirse",
    "presupuesto": "Presupuesto mensual", "duracion": "Duración", "renovacion": "Renovación/ampliación",
    "incorporacion": "Incorporación a plantilla", "accesos": "Equipo y accesos",
    "responsable": "Responsable del día a día", "validacion": "Validación del perfil", "proyecto": "Proyecto",
}

def _respuestas_texto(data):
    orden = ["empresa","sector","web","empresa_resumen","sales_nombre","sales_email","titulo","responsabilidades",
             "requisitos","idiomas","banda","variable","beneficios","presupuesto","duracion","renovacion",
             "incorporacion","modalidad","dias_presenciales","ubicacion","horario","accesos","fases","pruebas","interlocutor",
             "responsable","validacion","fecha_inicio","atraer","proyecto"]
    lineas = []
    for k in orden:
        v = str(data.get(k, "") or "").strip()
        if v:
            lineas.append(f"{CAMPOS_ES.get(k,k)}:\n{v}\n")
    return "\n".join(lineas)

def _smtp():
    host = st.secrets["SMTP_HOST"]; port = int(st.secrets.get("SMTP_PORT", 587))
    user = st.secrets["SMTP_USER"]; pwd = st.secrets["SMTP_PASSWORD"]
    return host, port, user, pwd

def enviar_email(pdf_bytes, data):
    """Envía el PDF a Operaciones y una copia de las respuestas al comercial. Devuelve (ok, mensaje)."""
    try:
        host, port, user, pwd = _smtp()
    except Exception:
        return False, "El envío por email no está configurado (faltan los secretos SMTP). Descarga el PDF y envíalo a mano."
    dest = st.secrets.get("TALENT_OPS_EMAIL", OPS_EMAIL_DEFAULT)
    remite = st.secrets.get("SMTP_FROM", user)
    tipo = "Headhunting" if data.get("tipo") == "headhunting" else "Outsourcing"
    empresa = data.get("empresa", ""); titulo = data.get("titulo", "")
    fname = "Ficha_" + re.sub(r"\W+", "", empresa or "Cliente") + ".pdf"

    # 1) Operaciones (PDF completo)
    ops = EmailMessage()
    ops["Subject"] = f"[Alta {tipo}] {empresa} · {titulo}"
    ops["From"] = remite; ops["To"] = dest
    if data.get("sales_email"): ops["Reply-To"] = data["sales_email"]
    ops.set_content(f"Nueva ficha de {tipo}.\n\nEmpresa: {empresa}\nPuesto/servicio: {titulo}\n"
                    f"Comercial: {data.get('sales_nombre','')} ({data.get('sales_email','')})\n\n"
                    "Adjunto la ficha completa con la JD en PDF.")
    ops.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename=fname)

    # 2) Copia al comercial (solo sus respuestas, sin JD)
    com = None
    if data.get("sales_email", "").strip():
        com = EmailMessage()
        com["Subject"] = f"Copia de tu alta · {empresa} · {titulo}"
        com["From"] = remite; com["To"] = data["sales_email"].strip()
        com.set_content("Gracias por tu colaboración. Te contactaremos para avanzar con la vacante.\n\n"
                        "Estas son las respuestas que has enviado:\n\n" + _respuestas_texto(data))
    try:
        with smtplib.SMTP(host, port, timeout=30) as s:
            s.starttls(); s.login(user, pwd)
            s.send_message(ops)
            if com is not None:
                s.send_message(com)
        extra = " (y copia a tu email)" if com is not None else ""
        return True, f"Enviado a Operaciones{extra} ✅"
    except Exception as e:
        return False, f"No se pudo enviar el email: {e}"

@st.dialog("¡Gracias por tu colaboración!")
def _gracias_dialog():
    st.write("Hemos recibido la ficha. **Te contactaremos para avanzar con la vacante.**")
    st.caption("Se ha enviado a Operaciones y tienes una copia de tus respuestas en tu correo.")


# ==================== UI ====================
if not check_password():
    st.stop()
header()

MESES = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"]
def _fecha_es(d):
    return f"{d.day} de {MESES[d.month-1]} de {d.year}" if d else ""

def _lineas_inputs(titulo, kp, ph, ini=3):
    st.markdown(f"**{titulo}**")
    st.caption("Una por casilla. Pulsa «Añadir» si necesitas más.")
    n_key = f"{kp}_n"
    if n_key not in st.session_state:
        st.session_state[n_key] = ini
    n = st.session_state[n_key]
    out = []
    for i in range(n):
        v = st.text_input(f"{kp}_{i}", key=f"{kp}_{i}", label_visibility="collapsed",
                          placeholder=f"{ph} {i+1}")
        if v.strip():
            out.append("• " + v.strip())
    if st.button(f"➕ Añadir {ph.lower()}", key=f"{kp}_add"):
        st.session_state[n_key] = n + 1
        st.rerun()
    return "\n".join(out)

def _idiomas_selector():
    LANGS = ["Español","Inglés","Francés","Alemán","Italiano","Portugués","Catalán","Gallego","Euskera",
             "Chino","Árabe","Ruso","Neerlandés","Sueco","Otro"]
    NIVELES = ["Básico (A1-A2)","Intermedio (B1-B2)","Avanzado (C1)","Nativo/Bilingüe (C2)"]
    st.markdown("**Idiomas necesarios**")
    sel = st.multiselect("Idiomas", LANGS, key="idiomas_sel", label_visibility="collapsed")
    out = []
    for i, lang in enumerate(sel):
        cA, cB = st.columns([1, 1.4])
        cA.markdown(f"<div style='padding-top:6px'>{lang}</div>", unsafe_allow_html=True)
        niv = cB.selectbox(f"Nivel {lang}", NIVELES, index=1, key=f"niv_{i}_{lang}", label_visibility="collapsed")
        out.append(f"{lang} — {niv}")
    return "; ".join(out)

HORAS = [f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 30)]
def _horario_selector(kp):
    st.markdown("**Horario de los empleados**")
    h1, h2, h3 = st.columns([1, 1, 1.3])
    ini = h1.selectbox("Entrada", HORAS, index=16, key=f"{kp}_hini")   # 08:00
    fin = h2.selectbox("Salida", HORAS, index=34, key=f"{kp}_hfin")    # 17:00
    jornada = h3.selectbox("Jornada", ["Completa","Parcial","Intensiva","Turnos","Flexible"], key=f"{kp}_jornada")
    return f"{ini} a {fin} · {jornada}"

BANDAS = ["18k","20k","22k","24k","26k","28k","30k","33k","36k","40k","45k","50k","55k","60k","70k","80k","90k","100k+"]
PPTO = ["1.500€","2.000€","2.500€","3.000€","3.500€","4.000€","5.000€","6.000€","7.000€","8.000€","10.000€","12.000€+"]
FASES_OPC = ["Entrevista con Tessera","Entrevista con Sales","Entrevista con el cliente",
             "Entrevista con el manager del cliente","Prueba técnica","Dinámica de grupo",
             "2ª entrevista con cliente","3ª entrevista con cliente","Oferta"]
ATRAER_OPC = ["Ambiente flexible","Equipo joven","Crecimiento profesional","Proyecto en expansión",
              "Formación continua","Flexibilidad horaria","Teletrabajo","Buen ambiente de trabajo",
              "Estabilidad","Plan de carrera","Retribución competitiva","Impacto real en el negocio",
              "Cultura cercana","Autonomía"]

st.markdown("### Tipo de alta")
tipo_sel = st.segmented_control("Tipo de alta", ["Headhunting", "Outsourcing"],
                                default="Headhunting", label_visibility="collapsed", key="tipo")
tipo = "headhunting" if (tipo_sel or "Headhunting") == "Headhunting" else "outsourcing"
st.divider()

def cargar_empresas():
    p = ruta("empresas.txt")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        nombres = [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]
    # únicas y ordenadas alfabéticamente (sin distinguir mayúsculas/acentos)
    vistas, out = set(), []
    for n in sorted(nombres, key=lambda s: s.lower()):
        if n.lower() not in vistas:
            vistas.add(n.lower()); out.append(n)
    return out

st.markdown("**Empresa y contacto**")
_empresas = cargar_empresas()
c1, c2 = st.columns(2)
NUEVA = "➕ Añadir empresa nueva…"
if _empresas:
    sel_emp = c1.selectbox("Empresa (del roadmap)", _empresas + [NUEVA], key="empresa_sel")
    if sel_emp == NUEVA:
        empresa = c1.text_input("Nombre de la empresa nueva", key="empresa_nueva")
    else:
        empresa = sel_emp
else:
    empresa = c1.text_input("Empresa", key="empresa")
sector = c2.selectbox("Sector", ["— Selecciona —"] + SECTORES, key="sector_sel")
sector = "" if sector == "— Selecciona —" else sector
web = st.text_input("Web de la empresa (pega el enlace y pulsa el botón)", key="web", placeholder="https://…")
if st.button("🔎 Traer info de la empresa desde la web", key="btn_web"):
    if not web.strip():
        st.warning("Pega antes el enlace de la web.")
    else:
        with st.spinner("Leyendo la web…"):
            try:
                _resumen, _sector = resumir_empresa(web)
                st.session_state["empresa_resumen_ed"] = _resumen
                if _sector in SECTORES:
                    st.session_state["sector_sel"] = _sector   # rellena el sector solo
                st.rerun()
            except Exception as e:
                st.error(f"No pude leer la web: {e}")
resumen_emp = st.text_area("Sobre la empresa (se rellena solo desde la web; editable)", height=90, key="empresa_resumen_ed")
c3, c4 = st.columns(2)
sales_nombre = c3.text_input("Tu nombre (comercial)", key="sales_nombre")
sales_email = c4.text_input("Tu email (recibirás una copia)", key="sales_email")

st.divider()
titulo = st.text_input("Título del puesto o servicio", key="titulo")
responsabilidades = _lineas_inputs("Misión y responsabilidades", "resp", "Responsabilidad", ini=3)
requisitos = _lineas_inputs("Requisitos imprescindibles", "req", "Requisito", ini=3)
idiomas = _idiomas_selector()

data = {"tipo": tipo, "empresa": empresa, "sector": sector, "web": web,
        "empresa_resumen": resumen_emp, "sales_nombre": sales_nombre, "sales_email": sales_email,
        "titulo": titulo, "responsabilidades": responsabilidades, "requisitos": requisitos, "idiomas": idiomas}

st.divider()
if tipo == "headhunting":
    st.markdown("**Condiciones de contratación**")
    d1, d2 = st.columns(2)
    desde = d1.selectbox("Banda salarial · desde", BANDAS, index=1, key="banda_min")
    hasta = d2.selectbox("Banda salarial · hasta", BANDAS, index=3, key="banda_max")
    data["banda"] = f"{desde} - {hasta}"
    d3, d4 = st.columns(2)
    data["variable"] = d3.selectbox("Retribución variable", ["No","Bonus anual","Comisiones","Bonus + comisiones","Variable por objetivos"], key="variable")
    data["modalidad"] = d4.selectbox("Modalidad", ["Presencial","Híbrido","Remoto"], key="mod")
    data["dias_presenciales"] = st.selectbox("Días presenciales/semana", ["—","1","2","3","4","5"], key="dias")
    data["beneficios"] = st.text_input("Beneficios (opcional)", key="benef", placeholder="Ej. Seguro médico, ticket restaurante")
    data["ubicacion"] = st.text_input("Ubicación de la oficina", key="ubi")
    data["horario"] = _horario_selector("hh")
    st.markdown("**El proceso**")
    st.caption("Selecciona las fases en el orden en que ocurrirán (el orden de selección se respeta).")
    fases_sel = st.multiselect("Fases de entrevista", FASES_OPC, key="fases_sel")
    data["fases"] = " → ".join(fases_sel)
    f1 = st.date_input("Fecha objetivo de incorporación", value=None, format="DD/MM/YYYY", key="fecha")
    data["fecha_inicio"] = _fecha_es(f1)
    data["interlocutor"] = st.text_input("Interlocutor del proceso (nombre, cargo, email)", key="interloc")
    st.markdown("**Para atraer al candidato**")
    atr = st.multiselect("Por qué unirse (elige o añade)", ATRAER_OPC, key="atraer_sel")
    atr_extra = st.text_input("Añadir algo más (opcional)", key="atraer_extra")
    data["atraer"] = ", ".join(atr + ([atr_extra.strip()] if atr_extra.strip() else []))
else:
    st.markdown("**Condiciones del servicio**")
    e1, e2 = st.columns(2)
    pmin = e1.selectbox("Presupuesto mensual · desde", PPTO, index=1, key="ppto_min")
    pmax = e2.selectbox("Presupuesto mensual · hasta", PPTO, index=4, key="ppto_max")
    data["presupuesto"] = f"{pmin} - {pmax}"
    e3, e4 = st.columns(2)
    data["duracion"] = e3.selectbox("Duración prevista", ["1-3 meses","3-6 meses","6-12 meses","+12 meses","Indefinida"], key="dur")
    f2 = e4.date_input("Fecha de inicio deseada", value=None, format="DD/MM/YYYY", key="fecha")
    data["fecha_inicio"] = _fecha_es(f2)
    e5, e6 = st.columns(2)
    data["renovacion"] = e5.selectbox("Renovación/ampliación", ["Sí","No"], key="renov")
    data["incorporacion"] = e6.selectbox("Incorporación a plantilla al final", ["Sí","No"], key="incorp")
    e7, e8 = st.columns(2)
    data["modalidad"] = e7.selectbox("Modalidad", ["Presencial","Híbrido","Remoto"], key="mod")
    data["dias_presenciales"] = e8.selectbox("Días presenciales/semana", ["—","1","2","3","4","5"], key="dias")
    data["ubicacion"] = st.text_input("Ubicación aplicable", key="ubi")
    data["horario"] = _horario_selector("out")
    data["accesos"] = st.text_input("Equipo y accesos proporcionados", key="accesos")
    st.markdown("**Organización del día a día**")
    data["responsable"] = st.text_input("Responsable del día a día en vuestro equipo", key="resp_dia")
    data["validacion"] = st.text_input("Validación del perfil antes de incorporar (opcional)", key="valid")
    data["interlocutor"] = st.text_input("Interlocutor del acuerdo (nombre, cargo, email)", key="interloc")
    data["proyecto"] = st.text_area("Descripción breve del proyecto o necesidad", height=80, key="proyecto")

st.divider()
st.caption("Al enviar, la oferta (JD) se redacta automáticamente y se incluye en el PDF. No la escribáis vosotros.")
if st.button("Enviar información al equipo", type="primary", key="btn_enviar"):
    if not empresa.strip() or not titulo.strip() or not responsabilidades.strip():
        st.warning("Necesito al menos empresa, título y una responsabilidad.")
    else:
        with st.spinner("Montando la ficha y enviándola…"):
            try:
                try:
                    data["jd"] = generar_jd(data)
                except Exception:
                    data["jd"] = ""
                pdf = generar_ficha(data)
                st.session_state["ficha_pdf"] = pdf
                st.session_state["ficha_data"] = data
                ok, m = enviar_email(pdf, data)
            except Exception as e:
                ok, m = False, f"Error generando la ficha: {e}"
        if ok:
            _gracias_dialog()
        else:
            st.error(m)
            st.info("Puedes descargar el PDF aquí abajo y enviarlo a mano mientras tanto.")

# descarga de respaldo (solo si ya se ha generado)
if "ficha_pdf" in st.session_state:
    fname = "Ficha_" + re.sub(r"\W+", "", empresa or "Cliente") + ".pdf"
    st.download_button("⬇️ Descargar PDF (opcional)", data=st.session_state["ficha_pdf"],
                       file_name=fname, mime="application/pdf", key="dl")
