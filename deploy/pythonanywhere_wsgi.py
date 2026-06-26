"""
PythonAnywhere WSGI template.

Copy this into the WSGI file linked from the PythonAnywhere Web tab, then
replace YOUR_USERNAME with your PythonAnywhere username.
"""
import os
import sys


path = "/home/YOUR_USERNAME/money-manager"
if path not in sys.path:
    sys.path.insert(0, path)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "money_manager.settings")

from django.core.wsgi import get_wsgi_application


application = get_wsgi_application()

