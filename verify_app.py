import requests
import sys

BASE_URL = "http://127.0.0.1:5000"
s = requests.Session()

def register(username, password, avatar):
    print(f"Registering {username}...")
    res = s.post(f"{BASE_URL}/register", data={
        "username": username,
        "password": password,
        "avatar": avatar
    })
    if res.url.endswith("/login"):
        print("Registration successful (redirected to login).")
    else:
        print(f"Registration failed. URL: {res.url}")
        # print(res.text)

def login(username, password):
    print(f"Logging in {username}...")
    res = s.post(f"{BASE_URL}/login", data={
        "username": username,
        "password": password
    })
    if res.url.strip('/').endswith("5000") or res.url.endswith("/"):
        print("Login successful (redirected to index).")
    else:
        print(f"Login failed. URL: {res.url}")

def post_message(content):
    print(f"Posting message: '{content}'...")
    res = s.post(f"{BASE_URL}/post_message", data={
        "content": content
    })
    if res.status_code == 200:
        print("Post successful.")
        if content in res.text:
            print("Content found in response.")
        else:
            print("Content NOT found in response.")
        if "DEADED" in res.text:
            print("'DEADED' badge found.")
        else:
            print("'DEADED' badge NOT found.")
    else:
        print(f"Post failed. Status: {res.status_code}")

def main():
    try:
        # Check if app is up
        try:
            requests.get(BASE_URL)
        except requests.exceptions.ConnectionError:
            print("App is not running. Please start it first.")
            sys.exit(1)

        username = "testbee"
        password = "password123"
        avatar = "🐝"

        register(username, password, avatar)
        login(username, password)
        post_message("I forgot to buy milk!")

        print("\nVerification Complete.")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
