import sqlite3

def migrate_username():
    conn = sqlite3.connect('skillstack.db')
    cursor = conn.cursor()
    
    # Check if username column exists
    cursor.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if 'username' not in columns:
        print("Adding 'username' column to 'users' table...")
        # Step 1: Add the column allowing NULLs temporarily
        cursor.execute("ALTER TABLE users ADD COLUMN username TEXT")
        
        # Step 2: Populate the new column using the prefix of the email address
        cursor.execute("SELECT id, email FROM users")
        users = cursor.fetchall()
        for user_id, email in users:
            prefix = email.split('@')[0] if '@' in email else email
            
            # Ensure uniqueness by appending ID if necessary 
            # In a real system, more robust logic might be needed, but this is fine for a migration
            cursor.execute("SELECT id FROM users WHERE username = ? AND id != ?", (prefix, user_id))
            if cursor.fetchone():
               prefix = f"{prefix}_{user_id}"
            
            cursor.execute("UPDATE users SET username = ? WHERE id = ?", (prefix, user_id))
            
        print("Creating default admin account 'admin:admin123' at admin@nokia.com if it doesn't exist...")
        # Add a default admin if we don't have one specifically named admin
        cursor.execute("SELECT id FROM users WHERE username = 'admin'")
        if not cursor.fetchone():
            from werkzeug.security import generate_password_hash
            # We must use generate_password_hash to create the password_hash
            pwd_hash = generate_password_hash("admin123")
            # If email already exists, just update role to admin and username to admin
            cursor.execute("SELECT id FROM users WHERE email = 'admin@nokia.com'")
            existing_admin = cursor.fetchone()
            if existing_admin:
                cursor.execute("UPDATE users SET username = 'admin', password_hash = ?, role = 'admin' WHERE id = ?", (pwd_hash, existing_admin[0]))
            else:
                cursor.execute("""
                    INSERT INTO users (email, name, password_hash, role, username) 
                    VALUES ('admin@nokia.com', 'System Administrator', ?, 'admin', 'admin')
                """, (pwd_hash,))
        
        # We can't easily ADD CONSTRAINT UNIQUE or Alter column to NOT NULL in sqlite without recreating table
        # We'll rely on a manual unique index instead and application level checks
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username)")
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)")

        conn.commit()
        print("Migration successful.")
    else:
        print("'username' column already exists.")
        
    conn.close()

if __name__ == '__main__':
    migrate_username()
