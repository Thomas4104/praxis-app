from flask import Blueprint

treatment_bp = Blueprint('treatment', __name__, template_folder='templates')

from blueprints.treatment import routes
