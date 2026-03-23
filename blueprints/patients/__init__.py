from flask import Blueprint

patients_bp = Blueprint('patients', __name__, template_folder='templates')

from blueprints.patients import routes
