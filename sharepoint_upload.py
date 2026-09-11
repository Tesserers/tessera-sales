# -*- coding: utf-8 -*-
"""Sube la ficha en PDF a una carpeta de SharePoint vía Microsoft Graph.

Requiere un app registration de Azure AD (permiso de aplicación de Microsoft
Graph, p. ej. `Sites.Selected` o `Sites.ReadWrite.All`, con consentimiento de
administrador) y estos secretos en `st.secrets` (o variables de entorno):

    SP_TENANT_ID       Tenant ID (o dominio) de Azure AD.
    SP_CLIENT_ID       Application (client) ID del app registration.
    SP_CLIENT_SECRET   Client secret generado para esa app.

Opcionales (si no se indican, apuntan al sitio/carpeta de RRHH ya acordados):

    SP_SITE_HOSTNAME   Host del tenant de SharePoint. Por defecto:
                       "tesseraservices.sharepoint.com".
    SP_SITE_PATH       Ruta del sitio. Por defecto: "/sites/hrteam2".
    SP_FOLDER_PATH     Carpeta destino dentro de la biblioteca "Documentos
                       compartidos". Por defecto:
                       "Data to Action/Altas de Vacante Tessera Sales".

Ver SHAREPOINT_SETUP.md para los pasos de configuración en Azure AD.
"""
import datetime
import io
import random
import re
import time
from urllib.parse import quote

import requests
import streamlit as st
from openpyxl import Workbook, load_workbook

GRAPH = "https://graph.microsoft.com/v1.0"
DEFAULT_SITE_HOSTNAME = "tesseraservices.sharepoint.com"
DEFAULT_SITE_PATH = "/sites/hrteam2"
DEFAULT_FOLDER_PATH = "Data to Action/Altas de Vacante Tessera Sales"

EXCEL_FILENAME = "registro_vacantes.xlsx"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# --- bloqueo para evitar que dos altas simultáneas se pisen al escribir el Excel ---
LOCK_FILENAME = EXCEL_FILENAME + ".lock"
LOCK_TTL_SEGUNDOS = 60      # un lock más viejo que esto se considera huérfano (proceso caído) y se libera solo
LOCK_MAX_INTENTOS = 20      # ~ (20 * 0.5-0.8s) ≈ hasta 16s esperando el turno antes de rendirse
LOCK_ESPERA_SEGUNDOS = 0.5

# prefijo del ID según el tipo de alta; numeración compartida (ver _siguiente_numero)
PREFIJOS_TIPO = {"headhunting": "TSH", "outsourcing": "TSO"}
PREFIJO_DEFECTO = "TSR"
ID_INICIAL = 74  # próximo número a usar si el registro todavía no tiene ninguna fila
_ID_RE = re.compile(r"_(\d+)$")

# (clave en `data`, encabezado de columna). "id", "fecha_alta" y "tipo" son especiales
# (ver _fila_desde_data): no vienen tal cual de `data`.
COLUMNAS = [
    ("id", "ID"),
    ("fecha_alta", "Fecha de alta"),
    ("tipo", "Tipo de alta"),
    ("empresa", "Empresa"),
    ("sector", "Sector"),
    ("web", "Web"),
    ("empresa_resumen", "Sobre la empresa"),
    ("sales_nombre", "Comercial"),
    ("sales_email", "Email del comercial"),
    ("titulo", "Título del puesto/servicio"),
    ("responsabilidades", "Misión y responsabilidades"),
    ("requisitos", "Requisitos"),
    ("idiomas", "Idiomas"),
    ("banda", "Banda salarial fija"),
    ("variable", "Retribución variable"),
    ("beneficios", "Beneficios"),
    ("presupuesto", "Presupuesto mensual"),
    ("duracion", "Duración"),
    ("renovacion", "Renovación/ampliación"),
    ("incorporacion", "Incorporación a plantilla"),
    ("modalidad", "Modalidad"),
    ("dias_presenciales", "Días presenciales/semana"),
    ("ubicacion", "Ubicación"),
    ("horario", "Horario de los empleados"),
    ("accesos", "Equipo y accesos"),
    ("fases", "Fases del proceso"),
    ("interlocutor", "Interlocutor"),
    ("responsable", "Responsable del día a día"),
    ("validacion", "Validación del perfil"),
    ("fecha_inicio", "Fecha objetivo/inicio"),
    ("atraer", "Por qué unirse"),
    ("proyecto", "Proyecto"),
]


def _secret(name, default=None):
    try:
        return st.secrets[name]
    except Exception:
        return default


def _token():
    tenant = st.secrets["SP_TENANT_ID"]
    client_id = st.secrets["SP_CLIENT_ID"]
    client_secret = st.secrets["SP_CLIENT_SECRET"]
    r = requests.post(
        f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
        },
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["access_token"]


@st.cache_resource(ttl=3600)
def _drive_id():
    """Resuelve y cachea el id del drive (biblioteca por defecto) del sitio."""
    token = _token()
    headers = {"Authorization": f"Bearer {token}"}
    hostname = _secret("SP_SITE_HOSTNAME", DEFAULT_SITE_HOSTNAME)
    site_path = _secret("SP_SITE_PATH", DEFAULT_SITE_PATH)

    r = requests.get(f"{GRAPH}/sites/{hostname}:{site_path}", headers=headers, timeout=20)
    r.raise_for_status()
    site_id = r.json()["id"]

    r = requests.get(f"{GRAPH}/sites/{site_id}/drive", headers=headers, timeout=20)
    r.raise_for_status()
    return r.json()["id"]


def subir_a_sharepoint(pdf_bytes, data):
    """Sube el PDF a la carpeta de SharePoint configurada.

    Devuelve (ok: bool, mensaje: str). Nunca lanza excepción: cualquier fallo
    (credenciales no configuradas, permisos, red...) se reporta como (False, motivo)
    para no romper el flujo de envío por email.
    """
    try:
        st.secrets["SP_TENANT_ID"]; st.secrets["SP_CLIENT_ID"]; st.secrets["SP_CLIENT_SECRET"]
    except Exception:
        return False, "La subida a SharePoint no está configurada (faltan los secretos SP_*)."

    vac_id = (data.get("id") or "").strip()
    if vac_id:
        fname = f"{vac_id}.pdf"
    else:
        empresa = data.get("empresa", "") or "Cliente"
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        empresa_limpia = re.sub(r"\W+", "", empresa)
        fname = f"Ficha_{empresa_limpia}_{ts}.pdf"
    folder = _secret("SP_FOLDER_PATH", DEFAULT_FOLDER_PATH).strip("/")

    try:
        drive_id = _drive_id()
        token = _token()
        path = "/".join(quote(seg) for seg in folder.split("/")) + "/" + quote(fname)
        r = requests.put(
            f"{GRAPH}/drives/{drive_id}/root:/{path}:/content",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/pdf"},
            data=pdf_bytes,
            timeout=30,
        )
        r.raise_for_status()
        return True, "Guardado en SharePoint ✅"
    except Exception as e:
        return False, f"No se pudo guardar en SharePoint: {e}"


def _fila_desde_data(data):
    tipo_label = "Headhunting" if data.get("tipo") == "headhunting" else "Outsourcing"
    ahora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    fila = []
    for key, _ in COLUMNAS:
        if key == "id":
            fila.append(data.get("id", ""))
        elif key == "fecha_alta":
            fila.append(ahora)
        elif key == "tipo":
            fila.append(tipo_label)
        else:
            fila.append(str(data.get(key, "") or ""))
    return fila


def _siguiente_numero(ws):
    """Busca en la columna ID (la primera) el número más alto usado hasta ahora, sea
    cual sea el prefijo (TSH/TSO/TSR comparten una única numeración correlativa).
    Si el registro todavía no tiene ninguna fila, empieza en ID_INICIAL."""
    max_num = None
    for fila in ws.iter_rows(min_row=2, max_col=1, values_only=True):
        m = _ID_RE.search(str(fila[0] or ""))
        if m:
            n = int(m.group(1))
            if max_num is None or n > max_num:
                max_num = n
    return (max_num + 1) if max_num is not None else ID_INICIAL


def _lock_path(folder):
    return "/".join(quote(seg) for seg in folder.split("/")) + "/" + quote(LOCK_FILENAME)


def _adquirir_lock(drive_id, token, folder):
    """Crea el archivo de bloqueo de forma atómica: `@microsoft.graph.conflictBehavior=fail`
    hace que la escritura falle (409) si el archivo ya existe, en vez de sobrescribirlo —
    así solo un proceso puede "ganar" la carrera aunque dos altas lleguen a la vez.

    Si el bloqueo ya existe pero es más viejo que LOCK_TTL_SEGUNDOS, se asume huérfano
    (de un proceso anterior que falló sin liberarlo) y se borra para reintentar.

    Devuelve True si se consiguió el bloqueo, False si se agotaron los intentos.
    """
    lock_path = _lock_path(folder)
    auth = {"Authorization": f"Bearer {token}"}
    marca = datetime.datetime.now(datetime.timezone.utc).isoformat().encode()

    for _ in range(LOCK_MAX_INTENTOS):
        r = requests.put(
            f"{GRAPH}/drives/{drive_id}/root:/{lock_path}:/content?@microsoft.graph.conflictBehavior=fail",
            headers={**auth, "Content-Type": "text/plain"},
            data=marca, timeout=20,
        )
        if r.status_code in (200, 201):
            return True
        if r.status_code == 409:
            try:
                meta = requests.get(f"{GRAPH}/drives/{drive_id}/root:/{lock_path}", headers=auth, timeout=20)
                if meta.status_code == 200:
                    modif = meta.json().get("lastModifiedDateTime", "")
                    edad = (datetime.datetime.now(datetime.timezone.utc)
                            - datetime.datetime.fromisoformat(modif.replace("Z", "+00:00"))).total_seconds()
                    if edad > LOCK_TTL_SEGUNDOS:
                        requests.delete(f"{GRAPH}/drives/{drive_id}/root:/{lock_path}", headers=auth, timeout=20)
                        continue  # reintenta inmediatamente tras liberar el lock huérfano
            except Exception:
                pass
            time.sleep(LOCK_ESPERA_SEGUNDOS + random.uniform(0, 0.3))
            continue
        r.raise_for_status()
    return False


def _liberar_lock(drive_id, token, folder):
    try:
        requests.delete(f"{GRAPH}/drives/{drive_id}/root:/{_lock_path(folder)}",
                         headers={"Authorization": f"Bearer {token}"}, timeout=20)
    except Exception:
        pass  # si falla la limpieza, el TTL lo autolimpiará en la siguiente alta


def asignar_id_y_registrar(data):
    """Genera el ID correlativo de la vacante (TSH/TSO/TSR + número, numeración
    compartida entre los tres) y añade la fila con los datos del alta a
    `registro_vacantes.xlsx`, en la misma carpeta de SharePoint que los PDFs.
    Crea el archivo (con cabeceras) si todavía no existe.

    IMPORTANTE: debe llamarse ANTES de generar el PDF — deja el ID asignado en
    `data["id"]` (efecto secundario sobre el dict que se le pasa) para que
    `generar_ficha` y el nombre del archivo puedan usarlo.

    Usa un archivo de bloqueo (`registro_vacantes.xlsx.lock`) para que, si dos
    altas se envían casi a la vez, la segunda espere su turno en vez de
    asignar el mismo número o sobrescribir la fila que acaba de añadir la primera.

    Devuelve (id: str | None, ok: bool, mensaje: str). Nunca lanza excepción.
    """
    try:
        st.secrets["SP_TENANT_ID"]; st.secrets["SP_CLIENT_ID"]; st.secrets["SP_CLIENT_SECRET"]
    except Exception:
        return None, False, "No se pudo generar el ID de la vacante (faltan los secretos SP_*)."

    folder = _secret("SP_FOLDER_PATH", DEFAULT_FOLDER_PATH).strip("/")
    path = "/".join(quote(seg) for seg in folder.split("/")) + "/" + quote(EXCEL_FILENAME)

    try:
        drive_id = _drive_id()
        token = _token()
    except Exception as e:
        return None, False, f"No se pudo generar el ID de la vacante: {e}"

    if not _adquirir_lock(drive_id, token, folder):
        return None, False, ("No se pudo generar el ID de la vacante: otra alta lo estaba "
                              "modificando a la vez y no quedó libre a tiempo. Inténtalo de nuevo.")

    try:
        auth = {"Authorization": f"Bearer {token}"}
        r = requests.get(f"{GRAPH}/drives/{drive_id}/root:/{path}:/content", headers=auth, timeout=30)
        if r.status_code == 200:
            wb = load_workbook(io.BytesIO(r.content))
            ws = wb.active
        elif r.status_code == 404:
            wb = Workbook()
            ws = wb.active
            ws.title = "Registro"
            ws.append([label for _, label in COLUMNAS])
        else:
            r.raise_for_status()

        numero = _siguiente_numero(ws)
        prefijo = PREFIJOS_TIPO.get(data.get("tipo"), PREFIJO_DEFECTO)
        vac_id = f"{prefijo}_{numero:03d}"
        data["id"] = vac_id

        ws.append(_fila_desde_data(data))

        buf = io.BytesIO()
        wb.save(buf)

        r2 = requests.put(
            f"{GRAPH}/drives/{drive_id}/root:/{path}:/content",
            headers={"Authorization": f"Bearer {token}", "Content-Type": XLSX_MIME},
            data=buf.getvalue(),
            timeout=30,
        )
        r2.raise_for_status()
        return vac_id, True, "Registro actualizado en Excel ✅"
    except Exception as e:
        return None, False, f"No se pudo generar el ID / actualizar el Excel: {e}"
    finally:
        _liberar_lock(drive_id, token, folder)
