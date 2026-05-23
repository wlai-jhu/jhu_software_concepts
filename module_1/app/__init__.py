from flask import Flask


def create_app():
    """Create and configure the Module 1 Flask application."""
    app = Flask(__name__)
    app.config["TEMPLATES_AUTO_RELOAD"] = True

    from app.routes.pages import pages

    app.register_blueprint(pages)
    return app
