from flask import Blueprint

employees_bp = Blueprint('employees', __name__, template_folder='templates')

from blueprints.employees import routes
