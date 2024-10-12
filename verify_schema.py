from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect
from config import Config

app = Flask(__name__)
app.config.from_object(Config)
db = SQLAlchemy(app)

def verify_post_schema():
    with app.app_context():
        inspector = inspect(db.engine)
        columns = inspector.get_columns('post')
        for column in columns:
            if column['name'] == 'image_url':
                print(f"Column 'image_url' type: {column['type']}")
                return

if __name__ == '__main__':
    verify_post_schema()
