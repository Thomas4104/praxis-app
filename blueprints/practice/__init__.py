from flask import Blueprint

practice_bp = Blueprint('practice', __name__, template_folder='templates')

from blueprints.practice import routes
