# Guardar la vacante en el CRM — configuración necesaria

El código ya está listo ([crm_upload.py](crm_upload.py)): cuando se envía una alta,
la vacante se crea directamente en `tesserahc-crm` (Supabase) — ya **no** se lleva
ningún registro en Excel. El propio CRM asigna el código (`TSH_075`, `TSO_076`...)
de forma atómica en la base de datos, así que es la fuente de verdad para la
numeración.

Para que funcione hace falta una **cuenta de servicio**: un usuario en el CRM que
represente a "Tessera Sales" (la app), igual que cualquier persona del equipo.

## 1. Crear el usuario en Supabase Auth

1. Panel de Supabase → proyecto **tessera-crm** → **Authentication → Users → Add user → Create new user**.
2. Email sugerido: `ventas-bot@tesseraservices.com` (o el que prefieras).
3. Genera una contraseña segura y guárdala — hace falta en el paso 3.
4. Marca **Auto Confirm User**.

## 2. Darle acceso en el CRM (pestaña Equipo)

1. Entra al CRM como **maestro**.
2. Pestaña **Equipo** → añade una fila:
   - **Nombre**: `Tessera Sales` (o el que prefieras; solo tiene que ser único).
   - **Email**: el mismo del paso 1.
   - **Rol**: `interno` (necesita poder crear vacantes y empresas).
3. Se vincula solo por el email — igual que dar de alta a una persona nueva del equipo.

## 3. Configurar los secretos en Streamlit

Añadir en `st.secrets` (Streamlit Cloud → App → Settings → Secrets, o
`.streamlit/secrets.toml` en local, **nunca lo subas al repo**):

```toml
CRM_EMAIL    = "ventas-bot@tesseraservices.com"   # el del paso 1
CRM_PASSWORD = "..."                              # la contraseña del paso 1

# Opcionales — solo si cambiara el proyecto de Supabase (por defecto ya apuntan
# al proyecto tessera-crm actual; la clave "anon" es pública por diseño, la
# protegen las reglas de acceso (RLS) del propio CRM, no hace falta mantenerla
# en secreto):
# CRM_SUPABASE_URL      = "https://aupibmqcaksxkwsprvcv.supabase.co"
# CRM_SUPABASE_ANON_KEY = "..."
```

## Qué datos se guardan en el CRM

Desde el formulario de alta se crea (o reutiliza, si ya existe por nombre) la
**empresa**, y se crea la **vacante** con: título, tipo de servicio
(Headhunting/Outsourcing), ubicación, modalidad, banda salarial (solo
headhunting) y el sector de la empresa. En el campo "origen" queda anotado que
viene de Tessera Sales y quién es el comercial.

El resto de campos del formulario (responsabilidades, requisitos, idiomas,
JD generada, condiciones detalladas...) no tienen columna propia en el CRM —
siguen viajando completos en el PDF, que se sube a SharePoint y se envía por
email como hasta ahora.

## Comportamiento

- Si estos secretos no están configurados, o el CRM no responde, **la alta se
  bloquea por completo**: no se genera el PDF ni se envía nada, porque el
  código de la vacante (necesario para el PDF y el nombre de archivo) tiene que
  venir del CRM. Se muestra un error claro explicando qué ha fallado.
- Si la empresa no existía en el CRM, se crea sola con ese nombre.
- La vacante se crea **sin asignar** (sin responsable, comercial ni recruiter):
  el CRM, por defecto, asignaría esos tres campos a quien la crea (aquí, la
  propia cuenta de servicio), así que la app los deja explícitamente en blanco
  justo después para que Operaciones la reparta.
- El sector de la empresa solo se rellena si estaba vacío (no pisa un sector
  que ya se hubiera puesto a mano en el CRM).

## Aprobación de Edward

Toda vacante creada desde Tessera Sales nace **pendiente de aprobación** en el
CRM (esto requiere la parte correspondiente en `tesserahc-crm`, ver su propio
`docs/APROBACION_VACANTES.md`): aparece en el listado con la etiqueta
"Pendiente de aprobar", y en una sección aparte visible solo para Edward, con
botones para aceptarla o rechazarla — **esa decisión se toma siempre dentro
del CRM**, nunca desde el email.

Justo después de crear la vacante, `app.py` le manda un aviso por email a
`edward@tesseraservices.com` (función `enviar_aviso_edward`) con los datos
básicos (código, empresa, puesto, comercial). Es solo un aviso: no lleva
ningún enlace ni botón para decidir desde ahí. Si este email falla, no bloquea
el resto del alta (el PDF y el envío a Operaciones siguen adelante igual) —
solo se muestra un aviso.

Si quieres que el email incluya un enlace directo al CRM, añade el secreto
opcional:

```toml
# CRM_URL = "https://crm.tesseraservices.com"
```
