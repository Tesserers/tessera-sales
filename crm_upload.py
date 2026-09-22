# -*- coding: utf-8 -*-
"""Crea la vacante directamente en el CRM interno (tesserahc-crm, Supabase) en vez
de llevar un registro en Excel. El CRM asigna el código (TSH_074, TSO_075...) de
forma atómica en la propia base de datos (función `siguiente_codigo`, con
`pg_advisory_xact_lock`), así que aquí no hace falta ningún archivo de bloqueo
ni leer ningún Roadmap: la fuente de verdad es el propio CRM.

Requiere una cuenta de servicio: un usuario de Supabase Auth (email + contraseña)
dado de alta en la tabla `equipo` del CRM con rol "interno" (o "maestro"), para
que las reglas RLS le dejen crear vacantes — igual que a cualquier persona del
equipo. Ver CRM_SETUP.md para darla de alta.

Secretos en `st.secrets`:
    CRM_EMAIL       Email de la cuenta de servicio en Supabase Auth.
    CRM_PASSWORD    Su contraseña.

Opcionales (por defecto, los del proyecto tessera-crm — la clave "anon" es
pública por diseño: la protegen las reglas RLS, no hace falta mantenerla en
secreto, pero se puede sobreescribir si el proyecto cambiara):
    CRM_SUPABASE_URL       Por defecto: "https://aupibmqcaksxkwsprvcv.supabase.co".
    CRM_SUPABASE_ANON_KEY  Clave "anon" del proyecto (Project Settings → API).
"""
import re

import requests
import streamlit as st

DEFAULT_SUPABASE_URL = "https://aupibmqcaksxkwsprvcv.supabase.co"
DEFAULT_SUPABASE_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImF1cGlibXFjYWtzeGt3c3BydmN2Iiwicm9sZSI6"
    "ImFub24iLCJpYXQiOjE3ODI0OTYwNjQsImV4cCI6MjA5ODA3MjA2NH0.qjE5SxjRlt5bg0eDmdiMwD58ebC2WBgfD0pyN-RF5Ps"
)

SERVICIO_TIPO = {"headhunting": "Headhunting", "outsourcing": "Outsourcing"}
MODALIDAD_CRM = {"Presencial": "presencial", "Híbrido": "hibrido", "Remoto": "remoto"}


def _secret(name, default=None):
    try:
        return st.secrets[name]
    except Exception:
        return default


def _supabase_url():
    return _secret("CRM_SUPABASE_URL", DEFAULT_SUPABASE_URL).rstrip("/")


def _anon_key():
    return _secret("CRM_SUPABASE_ANON_KEY", DEFAULT_SUPABASE_ANON_KEY)


def _token():
    """Inicia sesión con la cuenta de servicio y devuelve el access_token (JWT).
    Sin caché: el volumen de altas es bajo y así no hay que preocuparse de la
    caducidad del token (los de Supabase duran ~1h)."""
    email = st.secrets["CRM_EMAIL"]
    password = st.secrets["CRM_PASSWORD"]
    r = requests.post(
        f"{_supabase_url()}/auth/v1/token?grant_type=password",
        headers={"apikey": _anon_key(), "Content-Type": "application/json"},
        json={"email": email, "password": password},
        timeout=20,
    )
    if r.status_code >= 400:
        # Supabase manda el motivo real en el cuerpo (contraseña incorrecta, email sin
        # confirmar...); sin esto solo se ve "400 Bad Request", que no dice nada.
        try:
            detalle = r.json().get("error_description") or r.json().get("msg") or r.text
        except Exception:
            detalle = r.text
        raise RuntimeError(f"Supabase Auth rechazó el login ({r.status_code}): {detalle}")
    return r.json()["access_token"]


def _parse_banda(valor):
    """'40k' -> 40000. Devuelve None si no tiene ese formato (p. ej. vacío)."""
    if not valor:
        return None
    m = re.match(r"\s*(\d+)\s*k", valor, re.I)
    return int(m.group(1)) * 1000 if m else None


def _parse_banda_rango(valor):
    """'40k - 50k' -> (40000, 50000)."""
    if not valor:
        return None, None
    partes = [p.strip() for p in valor.split("-")]
    smin = _parse_banda(partes[0]) if len(partes) > 0 else None
    smax = _parse_banda(partes[1]) if len(partes) > 1 else None
    return smin, smax


def crear_vacante(data):
    """Crea la vacante en el CRM (y la empresa, si no existía ya) llamando a la
    función `guardar_vacante` del CRM. El propio CRM asigna el código.

    IMPORTANTE: debe llamarse ANTES de generar el PDF — deja el código asignado
    en `data["id"]` (efecto secundario sobre el dict que se le pasa) para que
    `generar_ficha` y el nombre del archivo puedan usarlo.

    Devuelve (codigo: str | None, ok: bool, mensaje: str). Nunca lanza excepción.
    """
    try:
        st.secrets["CRM_EMAIL"]; st.secrets["CRM_PASSWORD"]
    except Exception:
        return None, False, "El guardado en el CRM no está configurado (faltan los secretos CRM_EMAIL/CRM_PASSWORD)."

    try:
        token = _token()
    except Exception as e:
        return None, False, f"No se pudo iniciar sesión en el CRM: {e}"

    headers = {
        "apikey": _anon_key(),
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    url = _supabase_url()

    p = {
        "titulo": data.get("titulo", ""),
        "empresa": data.get("empresa", ""),
        "servicio": SERVICIO_TIPO.get(data.get("tipo"), "Headhunting"),
        "ubicacion": data.get("ubicacion", ""),
        "origen": f"Alta desde Tessera Sales · {data.get('sales_nombre', '')} ({data.get('sales_email', '')})".strip(),
        # Queda pendiente de que Edward la acepte o la rechace desde el propio CRM.
        "aprobacion": "pendiente",
    }
    modalidad_crm = MODALIDAD_CRM.get(data.get("modalidad"))
    if modalidad_crm:
        p["modalidad"] = modalidad_crm
    if data.get("tipo") == "headhunting":
        smin, smax = _parse_banda_rango(data.get("banda", ""))
        if smin is not None:
            p["salario_min"] = smin
        if smax is not None:
            p["salario_max"] = smax

    try:
        r = requests.post(f"{url}/rest/v1/rpc/guardar_vacante", headers=headers,
                           json={"p_vacante": None, "p": p}, timeout=30)
        r.raise_for_status()
        vacante_id = r.json()
        if isinstance(vacante_id, list):  # por si PostgREST lo devolviera envuelto en lista
            vacante_id = vacante_id[0]
        if not vacante_id:
            return None, False, "El CRM no devolvió la vacante creada."

        r2 = requests.get(f"{url}/rest/v1/vacantes", headers=headers,
                           params={"id": f"eq.{vacante_id}", "select": "codigo,empresa_id"}, timeout=20)
        r2.raise_for_status()
        filas = r2.json()
        if not filas or not filas[0].get("codigo"):
            return None, False, "La vacante se creó en el CRM pero no se pudo leer su código."
        codigo = filas[0]["codigo"]
        data["id"] = codigo

        # guardar_vacante no toca el sector de la empresa; lo completamos aparte si hace falta
        # (no crítico: si falla, la vacante ya está creada de todos modos).
        if data.get("sector"):
            try:
                empresa_id = filas[0].get("empresa_id")
                if empresa_id:
                    requests.patch(f"{url}/rest/v1/empresas", headers=headers,
                                    params={"id": f"eq.{empresa_id}", "sector": "is.null"},
                                    json={"sector": data["sector"]}, timeout=20)
            except Exception:
                pass

        # guardar_vacante asigna responsable/comercial/recruiter a quien la crea (aquí, esta
        # misma cuenta de servicio) si no se indica lo contrario. La vacante tiene que quedar
        # SIN ASIGNAR para que Operaciones la reparta, así que se limpia aparte justo después
        # (no crítico para el alta: si falla, la vacante ya está creada, solo quedaría asignada
        # al bot en vez de sin asignar).
        try:
            requests.patch(f"{url}/rest/v1/vacantes_interno", headers=headers,
                            params={"vacante_id": f"eq.{vacante_id}"},
                            json={"responsable_id": None, "comercial_id": None, "recruiter_id": None},
                            timeout=20)
        except Exception:
            pass

        return codigo, True, "Vacante creada en el CRM ✅"
    except Exception as e:
        return None, False, f"No se pudo guardar la vacante en el CRM: {e}"
