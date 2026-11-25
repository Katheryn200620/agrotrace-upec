#!/usr/bin/env bash
# Render ejecuta este archivo en cada despliegue (Build Command: bash build.sh).
# Si algo falla, el despliegue se detiene en lugar de publicar una versión rota.
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

# Reúne CSS, JS e iconos en staticfiles/ para que WhiteNoise los sirva.
python manage.py collectstatic --no-input

# Crea o actualiza las tablas en Supabase.
python manage.py migrate

# Crea las cuentas de prueba y los datos de demostración.
# Es seguro repetirlo: si ya existen, no los duplica.
python manage.py cargar_datos_demo
