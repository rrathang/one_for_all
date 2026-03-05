import requests
import sqlite3
import time

def test_auth_changes():
    try:
        # 1. Login as default admin
        print("Logging in as default admin (admin:admin123)...")
        res = requests.post('http://127.0.0.1:5000/auth/login', json={
            "username": "admin",
            "password": "admin123"
        })
        if res.status_code != 200:
            print("Admin login failed:", res.json())
            return
        
        admin_token = res.json().get('token')
        print("Admin login successful. Token received.")

        # 2. Try to create a user with duplicate email (admin@nokia.com already exists)
        print("Testing duplicate email protection...")
        res = requests.post('http://127.0.0.1:5000/admin/users', headers={'Authorization': f'Bearer {admin_token}'}, json={
            "name": "Another Admin",
            "email": "admin@nokia.com",
            "username": "admin2",
            "password": "password123",
            "role": "developer"
        })
        if res.status_code == 400:
            print("Duplicate email successfully blocked:", res.json())
        else:
            print(f"Error: duplicate email was not blocked properly. Got {res.status_code}", res.text)
            return

        # 3. Create a valid new user
        import math
        random_suffix = int(time.time() * 1000) % 100000
        new_username = f"testdev_{random_suffix}"
        new_email = f"testdev_{random_suffix}@example.com"
        
        print(f"Creating new user {new_username}...")
        res = requests.post('http://127.0.0.1:5000/admin/users', headers={'Authorization': f'Bearer {admin_token}'}, json={
            "name": "Test Developer",
            "email": new_email,
            "username": new_username,
            "password": "password123",
            "role": "developer"
        })
        
        if res.status_code == 200:
            print("New user created successfully.")
        else:
            print(f"Error creating user: HTTP {res.status_code}", res.text)
            return

        # 4. Login with new user's username
        print(f"Logging in with new username: {new_username}...")
        res = requests.post('http://127.0.0.1:5000/auth/login', json={
            "username": new_username,
            "password": "password123"
        })
        if res.status_code == 200:
            print("Login with correct username and password succeeded.")
        else:
            print("Login failed:", res.json())
            return

        # 5. Fetch all users as admin to verify username column is returned
        print("Verifying /admin/users returns username...")
        res = requests.get('http://127.0.0.1:5000/admin/users', headers={'Authorization': f'Bearer {admin_token}'})
        users = res.json()
        print(f"Total users fetched: {len(users)}")
        if users and 'username' in users[0]:
            print("Validation successful! 'username' field is present in the admin response.")
        else:
            print("Error: 'username' field missing from admin users response.")
            print(users[0] if users else "Empty list")

    except Exception as e:
        print("An exception occurred:", e)

if __name__ == '__main__':
    test_auth_changes()
