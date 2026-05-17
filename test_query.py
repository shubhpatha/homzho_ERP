from app import create_app
from extensions import db
from models.user import User

app = create_app()
with app.app_context():
    try:
        u = User.query.get(1)
        print("Success query.get")
    except Exception as e:
        print("Error query.get:", type(e), e)
    
    try:
        u = User.query.get_or_404(1)
        print("Success query.get_or_404")
    except Exception as e:
        print("Error query.get_or_404:", type(e), e)
