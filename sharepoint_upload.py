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
import re
from urllib.parse import quote

import requests
import streamlit as st

GRAPH = "https://graph.microsoft.com/v1.0"
DEFAULT_SITE_HOSTNAME = "tesseraservices.sharepoint.com"
DEFAULT_SITE_PATH = "/sites/hrteam2"
DEFAULT_FOLDER_PATH = "Data to Action/Altas de Vacante Tessera Sales"


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
