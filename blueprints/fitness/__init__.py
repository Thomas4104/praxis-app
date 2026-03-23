from flask import Blueprint

fitness_bp = Blueprint('fitness', __name__, template_folder='templates')

from blueprints.fitness import routes
