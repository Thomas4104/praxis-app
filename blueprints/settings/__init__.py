from flask import Blueprint

settings_bp = Blueprint('settings', __name__, template_folder='templates')

from blueprints.settings import routes
