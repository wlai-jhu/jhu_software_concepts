from flask import Flask


def create_app():
    """Create and configure the Module 1 Flask application."""
    app = Flask(__name__)

    from app.routes.pages import pages

    app.register_blueprint(pages)
    return app
