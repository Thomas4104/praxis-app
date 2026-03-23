from flask import Blueprint

reporting_bp = Blueprint('reporting', __name__, template_folder='templates')

from blueprints.reporting import routes
