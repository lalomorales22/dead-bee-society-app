import os
from flask import Flask, request, render_template_string, redirect, url_for, g, jsonify
from dotenv import load_dotenv
import sqlite3
from flask_socketio import SocketIO, emit
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime
import requests
import base64
import logging
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_here'
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
socketio = SocketIO(app)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    avatar = db.Column(db.String(10))

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    image_data = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message_id = db.Column(db.Integer, db.ForeignKey('message.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Reaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey('message.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    reaction = db.Column(db.String(10), nullable=False)
    __table_args__ = (db.UniqueConstraint('message_id', 'user_id', 'reaction'),)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def generate_dead_bee_image(prompt):
    logger.debug(f"Generating dead bee image with prompt: {prompt}")
    api_key = os.getenv("STABILITY_API_KEY")
    logger.debug(f"API Key: {api_key[:5]}...{api_key[-5:]} (length: {len(api_key)})")
    if not api_key:
        logger.error("Stability API key not set")
        return None, "Stability API key not set"

    url = "https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/text-to-image"
    logger.debug(f"API Endpoint: {url}")
    
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    bee_prompt = f"A detailed illustration of a bee in the following scene or context: {prompt}. The bee should be the main focus of the image."
    
    payload = {
        "text_prompts": [{"text": bee_prompt}],
        "cfg_scale": 7,
        "height": 1024,
        "width": 1024,
        "samples": 1,
        "steps": 30,
    }
    logger.debug(f"API Request Payload: {payload}")

    try:
        try:
            test_response = requests.get("https://api.stability.ai/v1/engines/list", headers=headers)
            logger.debug(f"API Connectivity Test: {test_response.status_code}")
            if test_response.status_code == 401:
                logger.error("API Key is invalid or expired")
                return None, "API Key is invalid or expired"
        except requests.exceptions.RequestException as e:
            logger.error(f"API Connectivity Test Failed: {str(e)}")

        logger.debug("Sending request to Stability AI API")
        response = requests.post(url, headers=headers, json=payload)
        logger.debug(f"API Response Status: {response.status_code}")
        logger.debug(f"API Response Headers: {response.headers}")
        logger.debug(f"API Response Content: {response.text[:1000]}...")

        response.raise_for_status()
        data = response.json()
        logger.debug(f"API Response JSON: {data}")

        image_data = data["artifacts"][0]["base64"]
        logger.debug(f"Successfully generated image. Image data length: {len(image_data)}")
        return image_data, None
    except requests.exceptions.RequestException as e:
        logger.error(f"API Request Exception: {str(e)}")
        logger.error(f"API Error Response: {e.response.text if e.response else 'No response'}")
        return None, f"API error: {str(e)}"
    except KeyError as e:
        logger.error(f"KeyError while parsing API response: {str(e)}")
        return None, f"Error parsing API response: {str(e)}"
    except Exception as e:
        logger.error(f"Unexpected error in generate_dead_bee_image: {str(e)}")
        return None, f"Unexpected error: {str(e)}"

@app.route('/')
def index():
    logger.debug("Accessing index route")
    messages = Message.query.order_by(Message.timestamp.desc()).all()
    return render_template_string(BASE_HTML, messages=messages)

@app.route('/post_message', methods=['POST'])
@login_required
def post_message():
    logger.debug("Posting new message")
    content = request.form.get('content')
    
    if content:
        logger.debug(f"Generating image for message: {content}")
        image_data, error = generate_dead_bee_image(content)
        if error:
            logger.error(f"Error generating image: {error}")
            return f"Error generating image: {error}", 500

        new_message = Message(user_id=current_user.id, content=content, image_data=image_data)
        db.session.add(new_message)
        db.session.commit()
        
        logger.debug(f"New message posted with ID: {new_message.id}")
        socketio.emit('new_message', {
            'id': new_message.id,
            'content': new_message.content,
            'image_data': new_message.image_data,
            'timestamp': new_message.timestamp.isoformat(),
            'username': current_user.username,
            'avatar': current_user.avatar,
            'reactions': {}
        })
    return redirect(url_for('index'))

@app.route('/post_comment/<int:message_id>', methods=['POST'])
@login_required
def post_comment(message_id):
    logger.debug(f"Posting new comment for message ID: {message_id}")
    content = request.form.get('content')
    if content:
        new_comment = Comment(user_id=current_user.id, message_id=message_id, content=content)
        db.session.add(new_comment)
        db.session.commit()
        
        logger.debug(f"New comment posted with ID: {new_comment.id}")
        socketio.emit('new_comment', {
            'message_id': message_id,
            'content': new_comment.content,
            'timestamp': new_comment.timestamp.isoformat(),
            'username': current_user.username,
            'avatar': current_user.avatar
        })
    return redirect(url_for('index'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        logger.debug(f"Login attempt for user: {username}")
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            logger.debug(f"User {username} logged in successfully")
            return redirect(url_for('index'))
        logger.warning(f"Failed login attempt for user: {username}")
        return "Invalid username or password"
    return render_template_string(LOGIN_HTML)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        avatar = request.form.get('avatar')
        logger.debug(f"Registration attempt for user: {username}")
        if User.query.filter_by(username=username).first():
            logger.warning(f"Registration failed: Username {username} already exists")
            return "Username already exists"
        new_user = User(username=username, password=generate_password_hash(password), avatar=avatar)
        db.session.add(new_user)
        db.session.commit()
        logger.debug(f"User {username} registered successfully")
        return redirect(url_for('login'))
    return render_template_string(REGISTER_HTML)

@app.route('/logout')
@login_required
def logout():
    logger.debug(f"User {current_user.username} logged out")
    logout_user()
    return redirect(url_for('index'))

@app.route('/profile/<username>')
def profile(username):
    logger.debug(f"Accessing profile for user: {username}")
    user = User.query.filter_by(username=username).first()
    if user is None:
        logger.warning(f"Profile not found for user: {username}")
        return "User not found", 404
    
    messages = Message.query.filter_by(user_id=user.id).order_by(Message.timestamp.desc()).all()
    
    logger.debug(f"Rendering profile for user {username} with {len(messages)} messages")
    return render_template_string(PROFILE_HTML, user=user, messages=messages)

@app.route('/add_reaction/<int:message_id>/<reaction>')
@login_required
def add_reaction(message_id, reaction):
    logger.debug(f"Adding reaction {reaction} to message ID: {message_id}")
    try:
        existing_reaction = Reaction.query.filter_by(message_id=message_id, user_id=current_user.id, reaction=reaction).first()
        if existing_reaction:
            db.session.delete(existing_reaction)
        else:
            new_reaction = Reaction(message_id=message_id, user_id=current_user.id, reaction=reaction)
            db.session.add(new_reaction)
        db.session.commit()
        
        reactions = Reaction.query.filter_by(message_id=message_id).group_by(Reaction.reaction).with_entities(Reaction.reaction, db.func.count(Reaction.id)).all()
        reactions_dict = dict(reactions)
        
        logger.debug(f"Reaction added successfully. Current reactions: {reactions_dict}")
        socketio.emit('reaction_update', {
            'message_id': message_id,
            'reactions': reactions_dict
        })
        
        return 'OK', 200
    except Exception as e:
        logger.error(f"Error adding reaction: {str(e)}")
        return 'Error', 500

BASE_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dead Bee Society</title>
    <style>
        body {
            font-family: 'Arial', sans-serif;
            background-color: #f0e68c;
            color: #333;
            margin: 0;
            padding: 20px;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
            background-color: #fff;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 0 10px rgba(0,0,0,0.1);
        }
        h1, h2 {
            color: #8b4513;
        }
        .message {
            border: 2px solid #deb887;
            padding: 15px;
            margin-bottom: 20px;
            border-radius: 5px;
        }
        .message-content {
            margin-bottom: 10px;
        }
        .message-meta {
            font-size: 0.8em;
            color: #777;
        }
        form {
            margin-bottom: 20px;
        }
        input[type="text"], textarea {
            width: 100%;
            padding: 10px;
            margin-bottom: 10px;
            border: 1px solid #deb887;
            border-radius: 5px;
        }
        input[type="submit"] {
            background-color: #8b4513;
            color: #fff;
            border: none;
            padding: 10px 20px;
            cursor: pointer;
            border-radius: 5px;
        }
        .nav {
            margin-bottom: 20px;
        }
        .nav a {
            color: #8b4513;
            margin-right: 10px;
            text-decoration: none;
        }
        .comments-section {
            margin-top: 10px;
            padding-top: 10px;
            border-top: 1px solid #deb887;
        }
        .avatar {
            font-size: 1.5em;
            margin-right: 5px;
        }
        .dead-bee-image {
            max-width: 100%;
            height: auto;
            margin-top: 10px;
            border-radius: 5px;
        }
    </style>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <script>
        var socket = io();
        
        socket.on('new_message', function(message) {
            console.log('New message received:', message);
            var messagesContainer = document.querySelector('.container');
            var newMessageElement = document.createElement('div');
            newMessageElement.className = 'message';
            newMessageElement.innerHTML = `
                <div class="message-content">${message.content}</div>
                <img src="data:image/png;base64,${message.image_data}" alt="Dead Bee" class="dead-bee-image">
                <div class="message-meta">
                    <span class="avatar">${message.avatar}</span>
                    Posted by ${message.username} on ${message.timestamp}
                </div>
                <div class="comments-section"></div>
                <form action="/post_comment/${message.id}" method="post">
                    <input type="text" name="content" placeholder="Add a comment" required>
                    <input type="submit" value="Post Comment">
                </form>
            `;
            messagesContainer.insertBefore(newMessageElement, messagesContainer.firstChild);
        });
        
        socket.on('new_comment', function(comment) {
            console.log('New comment received:', comment);
            var messageElement = document.querySelector(`[data-message-id="${comment.message_id}"]`);
            if (messageElement) {
                var commentsSection = messageElement.querySelector('.comments-section');
                var newCommentElement = document.createElement('div');
                newCommentElement.className = 'comment';
                newCommentElement.innerHTML = `
                    <div class="comment-content">${comment.content}</div>
                    <div class="comment-meta">
                        <span class="avatar">${comment.avatar}</span>
                        Posted by ${comment.username} on ${comment.timestamp}
                    </div>
                `;
                commentsSection.appendChild(newCommentElement);
            }
        });

        socket.on('reaction_update', function(data) {
            console.log('Reaction update received:', data);
            var messageElement = document.querySelector(`[data-message-id="${data.message_id}"]`);
            if (messageElement) {
                var reactionsElement = messageElement.querySelector('.reactions');
                if (reactionsElement) {
                    reactionsElement.innerHTML = '';
                    for (var reaction in data.reactions) {
                        reactionsElement.innerHTML += `<button onclick="addReaction(${data.message_id}, '${reaction}')">${reaction} ${data.reactions[reaction]}</button>`;
                    }
                }
            }
        });

        function addReaction(messageId, reaction) {
            console.log('Adding reaction:', messageId, reaction);
            fetch(`/add_reaction/${messageId}/${reaction}`, {method: 'GET'})
                .then(response => {
                    if (!response.ok) {
                        throw new Error('Network response was not ok');
                    }
                })
                .catch(error => console.error('Error:', error));
        }
    </script>
</head>
<body>
    <div class="container">
        <div class="nav">
            <a href="{{ url_for('index') }}">Home</a>
            {% if current_user.is_authenticated %}
                <a href="{{ url_for('logout') }}">Logout</a>
                <a href="{{ url_for('profile', username=current_user.username) }}">Profile</a>
            {% else %}
                <a href="{{ url_for('login') }}">Login</a>
                <a href="{{ url_for('register') }}">Register</a>
            {% endif %}
        </div>
        <h1>Dead Bee Society</h1>
        {% if current_user.is_authenticated %}
            <form action="{{ url_for('post_message') }}" method="post">
                <textarea name="content" placeholder="Share your 'dead bee' here..." required></textarea>
                <input type="submit" value="Post Message">
            </form>
        {% endif %}
        {% for message in messages %}
            <div class="message" data-message-id="{{ message.id }}">
                <div class="message-content">{{ message.content }}</div>
                <img src="data:image/png;base64,{{ message.image_data }}" alt="Dead Bee" class="dead-bee-image">
                <div class="message-meta">
                    <span class="avatar">{{ message.user.avatar }}</span>
                    Posted by <a href="{{ url_for('profile', username=message.user.username) }}">{{ message.user.username }}</a> on {{ message.timestamp }}
                </div>
                <div class="reactions">
                    {% for reaction in message.reactions %}
                        <button onclick="addReaction({{ message.id }}, '{{ reaction.reaction }}')">{{ reaction.reaction }} {{ reaction.count }}</button>
                    {% endfor %}
                </div>
                {% if message.comments %}
                    <div class="comments-section">
                        <h3>Comments:</h3>
                        {% for comment in message.comments %}
                            <div class="comment">
                                <div class="comment-content">{{ comment.content }}</div>
                                <div class="comment-meta">
                                    <span class="avatar">{{ comment.user.avatar }}</span>
                                    Posted by <a href="{{ url_for('profile', username=comment.user.username) }}">{{ comment.user.username }}</a> on {{ comment.timestamp }}
                                </div>
                            </div>
                        {% endfor %}
                    </div>
                {% endif %}
                {% if current_user.is_authenticated %}
                    <form action="{{ url_for('post_comment', message_id=message.id) }}" method="post">
                        <input type="text" name="content" placeholder="Add a comment" required>
                        <input type="submit" value="Post Comment">
                    </form>
                {% endif %}
            </div>
        {% endfor %}
    </div>
</body>
</html>
'''

LOGIN_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - Dead Bee Society</title>
    <style>
        body {
            font-family: 'Arial', sans-serif;
            background-color: #f0e68c;
            color: #333;
            margin: 0;
            padding: 20px;
        }
        .container {
            max-width: 400px;
            margin: 0 auto;
            background-color: #fff;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 0 10px rgba(0,0,0,0.1);
        }
        h1 {
            color: #8b4513;
        }
        form {
            margin-top: 20px;
        }
        input[type="text"], input[type="password"] {
            width: 100%;
            padding: 10px;
            margin-bottom: 10px;
            border: 1px solid #deb887;
            border-radius: 5px;
        }
        input[type="submit"] {
            background-color: #8b4513;
            color: #fff;
            border: none;
            padding: 10px 20px;
            cursor: pointer;
            border-radius: 5px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Login</h1>
        <form action="{{ url_for('login') }}" method="post">
            <input type="text" name="username" placeholder="Username" required>
            <input type="password" name="password" placeholder="Password" required>
            <input type="submit" value="Login">
        </form>
    </div>
</body>
</html>
'''

REGISTER_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Register - Dead Bee Society</title>
    <style>
        body {
            font-family: 'Arial', sans-serif;
            background-color: #f0e68c;
            color: #333;
            margin: 0;
            padding: 20px;
        }
        .container {
            max-width: 400px;
            margin: 0 auto;
            background-color: #fff;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 0 10px rgba(0,0,0,0.1);
        }
        h1 {
            color: #8b4513;
        }
        form {
            margin-top: 20px;
        }
        input[type="text"], input[type="password"], select {
            width: 100%;
            padding: 10px;
            margin-bottom: 10px;
            border: 1px solid #deb887;
            border-radius: 5px;
        }
        input[type="submit"] {
            background-color: #8b4513;
            color: #fff;
            border: none;
            padding: 10px 20px;
            cursor: pointer;
            border-radius: 5px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Register</h1>
        <form action="{{ url_for('register') }}" method="post">
            <input type="text" name="username" placeholder="Username" required>
            <input type="password" name="password" placeholder="Password" required>
            <select name="avatar" required>
                <option value="">Select Avatar</option>
                <option value="🐝">🐝</option>
                <option value="🌻">🌻</option>
                <option value="🍯">🍯</option>
                <option value="🌼">🌼</option>
                <option value="🐞">🐞</option>
            </select>
            <input type="submit" value="Register">
        </form>
    </div>
</body>
</html>
'''

PROFILE_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ user.username }}'s Profile - Dead Bee Society</title>
    <style>
        body {
            font-family: 'Arial', sans-serif;
            background-color: #f0e68c;
            color: #333;
            margin: 0;
            padding: 20px;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
            background-color: #fff;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 0 10px rgba(0,0,0,0.1);
        }
        h1, h2 {
            color: #8b4513;
        }
        .message {
            border: 2px solid #deb887;
            padding: 15px;
            margin-bottom: 20px;
            border-radius: 5px;
        }
        .message-content {
            margin-bottom: 10px;
        }
        .message-meta {
            font-size: 0.8em;
            color: #777;
        }
        .avatar {
            font-size: 2em;
            margin-right: 10px;
        }
        .nav {
            margin-bottom: 20px;
        }
        .nav a {
            color: #8b4513;
            margin-right: 10px;
            text-decoration: none;
        }
        .dead-bee-image {
            max-width: 100%;
            height: auto;
            margin-top: 10px;
            border-radius: 5px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="nav">
            <a href="{{ url_for('index') }}">Home</a>
            <a href="{{ url_for('logout') }}">Logout</a>
        </div>
        <h1>{{ user.username }}'s Profile</h1>
        <p><span class="avatar">{{ user.avatar }}</span> {{ user.username }}</p>
        <h2>Messages</h2>
        {% for message in messages %}
            <div class="message">
                <div class="message-content">{{ message.content }}</div>
                <img src="data:image/png;base64,{{ message.image_data }}" alt="Dead Bee" class="dead-bee-image">
                <div class="message-meta">Posted on {{ message.timestamp }}</div>
            </div>
        {% endfor %}
    </div>
</body>
</html>
'''

@socketio.on('connect')
def handle_connect():
    logger.debug('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    logger.debug('Client disconnected')

if __name__ == '__main__':
    logger.info('Starting Dead Bee Society app')
    socketio.run(app, debug=True)