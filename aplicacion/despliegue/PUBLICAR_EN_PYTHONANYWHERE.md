# Publicar AgroTrace-UPEC en internet (enlace para la entrega)

La rúbrica pide el **aplicativo funcionando en un enlace con su base de datos**. PythonAnywhere tiene una cuenta gratuita
que publica aplicaciones Django en `https://SU_USUARIO.pythonanywhere.com`, guarda los archivos (y la base SQLite)
de forma permanente y da **https**, con lo que también funcionan la voz y la cámara en el celular.

> Antes: suba el proyecto a GitHub (ver el mensaje de instrucciones o el Manual de instalación).
> En todo este documento cambie `SU_USUARIO` por su usuario de PythonAnywhere y de GitHub.

## 1. Crear la cuenta
1. Entre a https://www.pythonanywhere.com → **Pricing & signup** → **Create a Beginner account** (gratis).
2. Confirme su correo.

## 2. Descargar el proyecto en PythonAnywhere
En **Consoles → Bash** pegue, una línea a la vez:

```bash
git clone https://github.com/SU_USUARIO/agrotrace-upec.git
cd agrotrace-upec/aplicacion
mkvirtualenv --python=/usr/bin/python3.13 agrotrace
pip install -r requirements.txt
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Copie la clave larga que salió en la última línea.

## 3. Configurar el archivo .env
```bash
nano .env
```
Cambie estas líneas (flechas para moverse; al terminar **Ctrl + O**, Enter y **Ctrl + X**):

```
DJANGO_SECRET_KEY=la-clave-larga-que-copio
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=SU_USUARIO.pythonanywhere.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://SU_USUARIO.pythonanywhere.com
SITE_URL=https://SU_USUARIO.pythonanywhere.com
```

## 4. Crear la base de datos y los archivos estáticos
```bash
python manage.py migrate
python manage.py cargar_datos_demo
python manage.py collectstatic --noinput
```
(Para datos reales, en lugar de `cargar_datos_demo` use `python manage.py createsuperuser`.)

## 5. Crear la aplicación web
1. Pestaña **Web** → **Add a new web app** → Next → **Manual configuration** → **Python 3.13** → Next.
2. En **Virtualenv** escriba: `/home/SU_USUARIO/.virtualenvs/agrotrace`
3. En **Source code**: `/home/SU_USUARIO/agrotrace-upec/aplicacion`
4. Abra **WSGI configuration file**, borre todo y pegue el contenido de `despliegue/pythonanywhere_wsgi.py`
   (cambiando `TU_USUARIO`). Pulse **Save**.
5. En **Static files** agregue dos filas:

| URL | Directory |
|---|---|
| `/static/` | `/home/SU_USUARIO/agrotrace-upec/aplicacion/staticfiles` |
| `/media/` | `/home/SU_USUARIO/agrotrace-upec/aplicacion/media` |

6. Active **Force HTTPS**.
7. Pulse el botón verde **Reload** y abra `https://SU_USUARIO.pythonanywhere.com`.

## 6. Actualizar después de hacer cambios
En su computador: `git add .`, `git commit -m "cambio"`, `git push`. En la consola Bash de PythonAnywhere:

```bash
cd ~/agrotrace-upec/aplicacion
workon agrotrace
git pull
python manage.py migrate
python manage.py collectstatic --noinput
```
y pulse **Reload** en la pestaña Web.

## Tome en cuenta
- La cuenta gratuita pide entrar de vez en cuando y pulsar **«Run until …»** en la pestaña Web para que el sitio no se apague. Hágalo antes de la exposición.
- Las cuentas gratuitas tienen salida a internet limitada: el sitio publicado no podrá conectarse a un Odoo instalado en su computador. Para mostrar la integración con Odoo use el aplicativo en su computador.
- Si sale **«DisallowedHost»** revise `DJANGO_ALLOWED_HOSTS`; si sale **«CSRF verification failed»** revise `DJANGO_CSRF_TRUSTED_ORIGINS`. Después de cambiar el `.env`, pulse **Reload**.
- Si la página se ve sin estilos, revise la fila `/static/` de **Static files** y vuelva a ejecutar `collectstatic`.
