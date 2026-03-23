from flask import Blueprint

dashboard_bp = Blueprint('dashboard', __name__, template_folder='templates')

from blueprints.dashboard import routes
