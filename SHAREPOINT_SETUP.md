# Guardar la ficha PDF en SharePoint — configuración necesaria

El código ya está listo ([sharepoint_upload.py](sharepoint_upload.py)), pero necesita que
alguien con permisos de administrador en Microsoft 365 / Azure AD del tenant
`tesseraservices` cree un **app registration** para que la app pueda escribir en
SharePoint sin un usuario interactivo (la app corre como servicio en Streamlit,
no hay nadie logueado con su cuenta de Microsoft).

## 1. Crear el app registration (Azure Portal → Azure Active Directory)

1. Azure Portal → **Azure Active Directory** → **App registrations** → **New registration**.
2. Nombre sugerido: `Tessera Sales - Ficha PDF SharePoint`.
3. Tipo de cuenta: *Single tenant* (solo el tenant de Tessera).
4. No hace falta Redirect URI (no es login interactivo).

## 2. Generar un client secret

1. En la app creada → **Certificates & secrets** → **New client secret**.
2. Copia el **valor** del secreto en cuanto se genera (no se puede volver a ver después).

## 3. Dar permisos de Microsoft Graph

1. En la app → **API permissions** → **Add a permission** → **Microsoft Graph** → **Application permissions**.
2. Añade uno de estos (recomendado el primero, más restringido):
   - `Sites.Selected` — solo permite acceso a los sitios que se autoricen explícitamente (paso 4).
   - `Sites.ReadWrite.All` — acceso a todo SharePoint del tenant (más simple, pero más permisivo).
3. Pulsa **Grant admin consent for Tessera** (requiere un administrador global o de SharePoint).

## 4. Si usaste `Sites.Selected`: autorizar el sitio concreto

Con `Sites.Selected`, hay que conceder acceso explícito al sitio `hrteam2`. Un
administrador debe ejecutar (con un token de administrador, vía Graph Explorer
o script):

```
POST https://graph.microsoft.com/v1.0/sites/tesseraservices.sharepoint.com:/sites/hrteam2/permissions
{
  "roles": ["write"],
  "grantedToIdentities": [{
    "application": { "id": "<APPLICATION_CLIENT_ID>", "displayName": "Tessera Sales - Ficha PDF SharePoint" }
  }]
}
```

## 5. Configurar los secretos en Streamlit

Añadir en `st.secrets` (Streamlit Cloud → App → Settings → Secrets, o
`.streamlit/secrets.toml` en local, **nunca lo subas al repo**):

```toml
SP_TENANT_ID     = "..."   # Tenant ID (Directory ID) de Azure AD
SP_CLIENT_ID     = "..."   # Application (client) ID del app registration
SP_CLIENT_SECRET = "..."   # El secreto generado en el paso 2

# Opcionales — solo si cambia el destino (por defecto ya apuntan aquí):
# SP_SITE_HOSTNAME = "tesseraservices.sharepoint.com"
# SP_SITE_PATH     = "/sites/hrteam2"
# SP_FOLDER_PATH   = "Data to Action/Altas de Vacante Tessera Sales"
```

## Comportamiento

- Si estos secretos no están configurados, la app sigue funcionando igual que
  antes (genera el PDF y lo envía por email); simplemente se muestra un aviso
  de que no se pudo guardar en SharePoint.
- Cada ficha se sube con el nombre `Ficha_<Empresa>_<fecha><hora>.pdf` para no
  sobrescribir fichas anteriores de la misma empresa.
