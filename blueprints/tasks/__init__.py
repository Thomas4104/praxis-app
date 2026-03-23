from flask import Blueprint

tasks_bp = Blueprint('tasks', __name__, template_folder='templates')

from blueprints.tasks import routes
