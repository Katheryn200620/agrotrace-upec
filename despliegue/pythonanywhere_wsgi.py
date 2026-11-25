# Contenido para el archivo WSGI de PythonAnywhere (pestaña Web → «WSGI configuration file»).
# Borre todo lo que tenga ese archivo y pegue esto. Cambie TU_USUARIO por su usuario de PythonAnywhere.
import os
import sys

ruta = "/home/TU_USUARIO/agrotrace-upec"
if ruta not in sys.path:
    sys.path.insert(0, ruta)

os.environ["DJANGO_SETTINGS_MODULE"] = "agrotrace.settings"

from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()
