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

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_here'
login_manager = LoginManager(app)
login_manager.login_view = 'login'
socketio = SocketIO(app)

# Database setup
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect('dead_bee_society.db')
    return db
    
@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             username TEXT UNIQUE NOT NULL,
             password TEXT NOT NULL,
             avatar TEXT)
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             user_id INTEGER,
             content TEXT NOT NULL,
             image_data TEXT,
             timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
             FOREIGN KEY (user_id) REFERENCES users (id))
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS comments
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             user_id INTEGER,
             message_id INTEGER,
             content TEXT NOT NULL,
             timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
             FOREIGN KEY (user_id) REFERENCES users (id),
             FOREIGN KEY (message_id) REFERENCES messages (id))
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reactions
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             message_id INTEGER,
             user_id INTEGER,
             reaction TEXT,
             FOREIGN KEY (message_id) REFERENCES messages (id),
             FOREIGN KEY (user_id) REFERENCES users (id),
             UNIQUE(message_id, user_id, reaction))
        ''')
        
        db.commit()

init_db()

class User(UserMixin):
    def __init__(self, id, username, avatar):
        self.id = id
        self.username = username
        self.avatar = avatar

@login_manager.user_loader
def load_user(user_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    if user:
        return User(user[0], user[1], user[3])
    return None

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
    
    # Modify the prompt to always include a bee
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
        # Test API connectivity
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
        logger.debug(f"API Response Content: {response.text[:1000]}...")  # Log first 1000 characters

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
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        SELECT messages.id, messages.content, messages.image_data, messages.timestamp, users.username, users.avatar
        FROM messages
        JOIN users ON messages.user_id = users.id
        ORDER BY messages.timestamp DESC
    ''')
    messages = cursor.fetchall()
    
    for i, message in enumerate(messages):
        cursor.execute('''
            SELECT comments.content, comments.timestamp, users.username, users.avatar
            FROM comments
            JOIN users ON comments.user_id = users.id
            WHERE comments.message_id = ?
            ORDER BY comments.timestamp ASC
        ''', (message[0],))
        comments = cursor.fetchall()
        
        cursor.execute('''
            SELECT reaction, COUNT(*) as count
            FROM reactions
            WHERE message_id = ?
            GROUP BY reaction
        ''', (message[0],))
        reactions = dict(cursor.fetchall())
        
        messages[i] = message + (comments, reactions)
    
    logger.debug(f"Rendering index with {len(messages)} messages")
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

        db = get_db()
        cursor = db.cursor()
        cursor.execute("INSERT INTO messages (user_id, content, image_data) VALUES (?, ?, ?)",
                       (current_user.id, content, image_data))
        message_id = cursor.lastrowid
        db.commit()
        
        cursor.execute('''
            SELECT messages.id, messages.content, messages.image_data, messages.timestamp, users.username, users.avatar
            FROM messages
            JOIN users ON messages.user_id = users.id
            WHERE messages.id = ?
        ''', (message_id,))
        new_message = cursor.fetchone()
        
        logger.debug(f"New message posted with ID: {message_id}")
        socketio.emit('new_message', {
            'id': new_message[0],
            'content': new_message[1],
            'image_data': new_message[2],
            'timestamp': new_message[3],
            'username': new_message[4],
            'avatar': new_message[5],
            'reactions': {}
        })
    return redirect(url_for('index'))

@app.route('/post_comment/<int:message_id>', methods=['POST'])
@login_required
def post_comment(message_id):
    logger.debug(f"Posting new comment for message ID: {message_id}")
    content = request.form.get('content')
    if content:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("INSERT INTO comments (user_id, message_id, content) VALUES (?, ?, ?)",
                       (current_user.id, message_id, content))
        comment_id = cursor.lastrowid
        db.commit()
        
        cursor.execute('''
            SELECT comments.content, comments.timestamp, users.username, users.avatar
            FROM comments
            JOIN users ON comments.user_id = users.id
            WHERE comments.id = ?
        ''', (comment_id,))
        new_comment = cursor.fetchone()
        
        logger.debug(f"New comment posted with ID: {comment_id}")
        socketio.emit('new_comment', {
            'message_id': message_id,
            'content': new_comment[0],
            'timestamp': new_comment[1],
            'username': new_comment[2],
            'avatar': new_comment[3]
        })
    return redirect(url_for('index'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        logger.debug(f"Login attempt for user: {username}")
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        if user and check_password_hash(user[2], password):
            user_obj = User(user[0], user[1], user[3])
            login_user(user_obj)
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
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            logger.warning(f"Registration failed: Username {username} already exists")
            return "Username already exists"
        cursor.execute("INSERT INTO users (username, password, avatar) VALUES (?, ?, ?)",
                       (username, generate_password_hash(password), avatar))
        db.commit()
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
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id, username, avatar FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    if user is None:
        logger.warning(f"Profile not found for user: {username}")
        return "User not found", 404
    
    cursor.execute('''
        SELECT messages.id, messages.content, messages.image_data, messages.timestamp
        FROM messages
        WHERE messages.user_id = ?
        ORDER BY messages.timestamp DESC
    ''', (user[0],))
    messages = cursor.fetchall()
    
    logger.debug(f"Rendering profile for user {username} with {len(messages)} messages")
    return render_template_string(PROFILE_HTML, user=user, messages=messages)

@app.route('/add_reaction/<int:message_id>/<reaction>')
@login_required
def add_reaction(message_id, reaction):
    logger.debug(f"Adding reaction {reaction} to message ID: {message_id}")
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute('''
            INSERT INTO reactions (message_id, user_id, reaction)
            VALUES (?, ?, ?)
            ON CONFLICT(message_id, user_id, reaction) DO UPDATE SET reaction = excluded.reaction
        ''', (message_id, current_user.id, reaction))
        db.commit()
        
        cursor.execute('''
            SELECT reaction, COUNT(*) as count
            FROM reactions
            WHERE message_id = ?
            GROUP BY reaction
        ''', (message_id,))
        reactions = dict(cursor.fetchall())
        
        logger.debug(f"Reaction added successfully. Current reactions: {reactions}")
        socketio.emit('reaction_update', {
            'message_id': message_id,
            'reactions': reactions
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
            <div class="message" data-message-id="{{ message[0] }}">
                <div class="message-content">{{ message[1] }}</div>
                <img src="data:image/png;base64,{{ message[2] }}" alt="Dead Bee" class="dead-bee-image">
                <div class="message-meta">
                    <span class="avatar">{{ message[5] }}</span>
                    Posted by <a href="{{ url_for('profile', username=message[4]) }}">{{ message[4] }}</a> on {{ message[3] }}
                </div>
                <div class="reactions">
                    {% for reaction, count in message[7].items() %}
                        <button onclick="addReaction({{ message[0] }}, '{{ reaction }}')">{{ reaction }} {{ count }}</button>
                    {% endfor %}
                </div>
                {% if message[6] %}
                    <div class="comments-section">
                        <h3>Comments:</h3>
                        {% for comment in message[6] %}
                            <div class="comment">
                                <div class="comment-content">{{ comment[0] }}</div>
                                <div class="comment-meta">
                                    <span class="avatar">{{ comment[3] }}</span>
                                    Posted by <a href="{{ url_for('profile', username=comment[2]) }}">{{ comment[2] }}</a> on {{ comment[1] }}
                                </div>
                            </div>
                        {% endfor %}
                    </div>
                {% endif %}
                {% if current_user.is_authenticated %}
                    <form action="{{ url_for('post_comment', message_id=message[0]) }}" method="post">
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
    <title>{{ user[1] }}'s Profile - Dead Bee Society</title>
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
        <h1>{{ user[1] }}'s Profile</h1>
        <p><span class="avatar">{{ user[2] }}</span> {{ user[1] }}</p>
        <h2>Messages</h2>
        {% for message in messages %}
            <div class="message">
                <div class="message-content">{{ message[1] }}</div>
                <img src="data:image/png;base64,{{ message[2] }}" alt="Dead Bee" class="dead-bee-image">
                <div class="message-meta">Posted on {{ message[3] }}</div>
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