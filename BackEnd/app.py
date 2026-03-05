import os, time, traceback, jwt, json, re, sqlite3, secrets
from functools import wraps
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template, g
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

from flask_cors import CORS
from NokiaGPT_Client import Client

# ==================== CONFIG ====================
load_dotenv()
app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app)

DB_PATH = os.path.join(os.path.dirname(__file__), "skillstack.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")

JWT_SECRET = os.getenv("JWT_SECRET", "dev_secret_change_me")
JWT_ISS = "skillstack"
JWT_EXP_HOURS = int(os.getenv("JWT_EXP_HOURS", "8"))

# ==================== LLM CONFIG ====================
# Migrated to NokiaGPT_Client


# ==================== DB ====================
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        if os.path.exists(SCHEMA_PATH):
            with open(SCHEMA_PATH, 'r') as f:
                db.executescript(f.read())
        db.commit()

with app.app_context():
    init_db()

# ==================== AUTH ====================
def encode_jwt(payload: dict) -> str:
    now = datetime.utcnow()
    base = {"iss": JWT_ISS, "iat": int(now.timestamp()), "exp": int((now + timedelta(hours=JWT_EXP_HOURS)).timestamp())}
    return jwt.encode({**base, **payload}, JWT_SECRET, algorithm="HS256")

def decode_jwt(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=["HS256"], options={"require": ["exp","iat","iss"]})

def ui_auth_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        hdr = request.headers.get("Authorization","")
        if not hdr.startswith("Bearer "):
            return jsonify({"error": "Unauthorized"}), 401
        token = hdr.split(" ",1)[1]
        try:
            request.user = decode_jwt(token)
        except Exception:
            return jsonify({"error": "Unauthorized"}), 401
        return fn(*args, **kwargs)
    return wrapper

def token_or_jwt_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        hdr = request.headers.get("Authorization","")
        if not hdr.startswith("Bearer "):
            return jsonify({"error": "Unauthorized"}), 401
        token = hdr.split(" ",1)[1]
        try:
            request.user = decode_jwt(token)
            request.auth_type = "jwt"
            return fn(*args, **kwargs)
        except Exception:
            pass

        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT id, project_id FROM api_tokens WHERE token=?", (token,))
        row = cur.fetchone()
        if row:
            request.auth_type = "api_token"
            request.token_id = row["id"]
            request.project_id = row["project_id"]
            return fn(*args, **kwargs)
        return jsonify({"error": "Unauthorized"}), 401
    return wrapper

# ==================== SAFE EXEC ====================
def safe_exec_function(code_str: str, args: dict, env: dict = None):
    if env is None: env = {}
    args["env"] = env
    # Determine the context allowed for the dynamic function
    safe_builtins = {
        "__import__": __import__,  # Required to allow importing modules
        "len": len, "sum": sum, "min": min, "max": max, "range": range,
        "abs": abs, "round": round, "enumerate": enumerate, "zip": zip, "sorted": sorted,
        "map": map, "filter": filter, "list": list, "dict": dict, "set": set, "any": any, "all": all,
        "Exception": Exception, "ValueError": ValueError, "TypeError": TypeError,
        "KeyError": KeyError, "IndexError": IndexError, "AttributeError": AttributeError,
        "isinstance": isinstance, "str": str, "int": int, "float": float, "bool": bool,
        "getattr": getattr, "hasattr": hasattr, "bytes": bytes, "bytearray": bytearray,
        "tuple": tuple
    }
    g = {"__builtins__": safe_builtins}
    l = {}
    try:
        exec(code_str, g, l)
        fn = l.get("api_def")
        if not fn:
            return {"error": "Function 'api_def(args)' not found"}
        return {"result": fn(args), "success": True}
    except Exception as e:
        return {"error": str(e), "success": False, "traceback": traceback.format_exc()}

# ==================== UI ROUTE ====================
@app.get("/")
def ui():
    return render_template("index.html")

# ==================== USER/AUTH ROUTES ====================
@app.post("/auth/login")
def login():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        return jsonify({"error": "Missing username/password"}), 400
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id, email, username, name, password_hash, role FROM users WHERE username=?", (username,))
    user = cur.fetchone()
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid credentials"}), 401
    
    role = user["role"] or "viewer" # Fallback if null
    token = encode_jwt({"id": user["id"], "email": user["email"], "username": user["username"], "name": user["name"], "role": role})
    return jsonify({"token": token, "user": {"id": user["id"], "email": user["email"], "username": user["username"], "name": user["name"], "role": role}})

@app.get("/me")
@ui_auth_required
def me():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT role FROM users WHERE id=?", (request.user["id"],))
    row = cur.fetchone()
    role = row["role"] if row else "viewer"
    
    return jsonify({
        "id": request.user["id"], 
        "email": request.user["email"], 
        "name": request.user["name"],
        "role": role
    })

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        # We assume ui_auth_required runs before this or we check the token identically
        if getattr(request, "user", {}).get("role") != "admin":
            # Extra safety check to db just in case token is stale
            db = get_db()
            cur = db.cursor()
            cur.execute("SELECT role FROM users WHERE id=?", (request.user["id"],))
            db_row = cur.fetchone()
            if not db_row or db_row["role"] != "admin":
                return jsonify({"error": "Admin privileges required"}), 403
            else:
                request.user["role"] = "admin" # Update session state
        return fn(*args, **kwargs)
    return wrapper

# ==================== NEW: PROJECTS & TOKENS ====================
@app.get("/projects")
@ui_auth_required
def list_projects():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id, name, created_at FROM projects WHERE user_id=? ORDER BY id DESC", (request.user["id"],))
    projects = [dict(r) for r in cur.fetchall()]
    return jsonify(projects)

@app.post("/projects")
@ui_auth_required
def create_project():
    if request.user.get("role") == "viewer":
        return jsonify({"error": "Viewers cannot create projects"}), 403

    data = request.get_json() or {}
    name = (data.get("name") or "My Project").strip()
    db = get_db()
    cur = db.cursor()
    cur.execute("INSERT INTO projects (user_id, name) VALUES (?,?)", (request.user["id"], name))
    # generate a default token for the project immediately
    proj_id = cur.lastrowid
    
    # Auto-assign the creator to this project
    try:
        cur.execute("INSERT INTO project_members (project_id, user_id) VALUES (?,?)", (proj_id, request.user["id"]))
    except:
        pass

    raw_token = "sk_" + secrets.token_hex(20)
    cur.execute("INSERT INTO api_tokens (project_id, token) VALUES (?,?)", (proj_id, raw_token))
    
    db.commit()
    return jsonify({"id": proj_id, "name": name, "token": raw_token})

@app.get("/projects/<int:proj_id>/tokens")
@ui_auth_required
def list_tokens(proj_id):
    db=get_db()
    cur=db.cursor()
    cur.execute("SELECT id FROM projects WHERE id=? AND user_id=?", (proj_id, request.user["id"]))
    if not cur.fetchone(): return jsonify({"error": "Forbidden"}), 403

    cur.execute("SELECT id, token, created_at FROM api_tokens WHERE project_id=?", (proj_id,))
    tokens = [dict(r) for r in cur.fetchall()]
    return jsonify(tokens)

@app.post("/projects/<int:proj_id>/tokens")
@ui_auth_required
def create_token(proj_id):
    db=get_db()
    cur=db.cursor()
    
    # Allow admins to bypass
    is_admin = request.user.get("role") == "admin"
    
    # Check if creator or member
    cur.execute("""
        SELECT p.id FROM projects p
        LEFT JOIN project_members pm ON p.id = pm.project_id
        WHERE p.id=? AND (p.user_id=? OR pm.user_id=?)
    """, (proj_id, request.user["id"], request.user["id"]))
    
    if not is_admin and not cur.fetchone(): 
        return jsonify({"error": "Forbidden"}), 403

    raw_token = "sk_" + secrets.token_hex(20)
    cur.execute("INSERT INTO api_tokens (project_id, token) VALUES (?,?)", (proj_id, raw_token))
    db.commit()
    return jsonify({"id": cur.lastrowid, "token": raw_token})

# ==================== NEW: ADMIN ROUTES ====================
@app.get("/admin/users")
@ui_auth_required
@admin_required
def admin_get_users():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id, username, email, name, role, created_at FROM users ORDER BY id DESC")
    return jsonify([dict(r) for r in cur.fetchall()])

@app.post("/admin/users")
@ui_auth_required
@admin_required
def admin_create_user():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    username = (data.get("username") or "").strip()
    name = (data.get("name") or "User").strip()
    password = data.get("password") or ""
    role = data.get("role") or "viewer"

    if not email or not username or not password:
        return jsonify({"error": "Missing email, username, or password"}), 400

    try:
        db = get_db()
        cur = db.cursor()
        
        cur.execute("SELECT id FROM users WHERE email=?", (email,))
        if cur.fetchone():
            return jsonify({"error": "User already created for this email"}), 400

        cur.execute("SELECT id FROM users WHERE username=?", (username,))
        if cur.fetchone():
            return jsonify({"error": "Username already exists"}), 400

        cur.execute("INSERT INTO users (email, username, name, password_hash, role) VALUES (?,?,?,?,?)",
                    (email, username, name, generate_password_hash(password), role))
        db.commit()
        return jsonify({"ok": True, "id": cur.lastrowid})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.put("/admin/users/<int:u_id>")
@ui_auth_required
@admin_required
def admin_update_user(u_id):
    data = request.get_json() or {}
    role = data.get("role")
    new_name = data.get("name")
    
    if role not in ["admin", "developer", "viewer"]:
        return jsonify({"error": "Invalid role"}), 400
        
    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE users SET role = COALESCE(?, role), name = COALESCE(?, name) WHERE id = ?", (role, new_name, u_id))
    db.commit()
    return jsonify({"updated": True})

@app.delete("/admin/users/<int:u_id>")
@ui_auth_required
@admin_required
def admin_delete_user(u_id):
    db = get_db()
    cur = db.cursor()
    # Prevent admin from deleting themselves
    if u_id == request.user["id"]:
        return jsonify({"error": "You cannot delete your own account"}), 400
        
    cur.execute("DELETE FROM users WHERE id = ?", (u_id,))
    if cur.rowcount == 0:
        return jsonify({"error": "User not found"}), 404
        
    db.commit()
    return jsonify({"deleted": True})

@app.post("/admin/project_assign")
@ui_auth_required
@admin_required
def admin_assign_project():
    data = request.get_json() or {}
    user_id = data.get("user_id")
    project_id = data.get("project_id")
    action = data.get("action", "assign") # assign or remove
    
    if not user_id or not project_id:
        return jsonify({"error": "user_id and project_id required"}), 400
        
    db = get_db()
    cur = db.cursor()
    
    if action == "assign":
        try:
            cur.execute("INSERT INTO project_members (project_id, user_id) VALUES (?, ?)", (project_id, user_id))
            db.commit()
            return jsonify({"assigned": True})
        except sqlite3.IntegrityError:
            return jsonify({"error": "User already assigned"}), 400
    else:
        cur.execute("DELETE FROM project_members WHERE project_id = ? AND user_id = ?", (project_id, user_id))
        db.commit()
        return jsonify({"removed": True})

@app.get("/admin/projects")
@ui_auth_required
@admin_required
def admin_get_projects():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT p.id, p.name, u.email as owner FROM projects p JOIN users u ON u.id = p.user_id ORDER BY p.id DESC")
    return jsonify([dict(r) for r in cur.fetchall()])

# ==================== NEW: ENV VARS ====================
@app.get("/env_vars")
@ui_auth_required
def list_env_vars():
    proj_id = request.args.get("project_id")
    db=get_db()
    cur=db.cursor()
    if proj_id:
        cur.execute("SELECT id, name, value, project_id, created_at FROM env_vars WHERE user_id=? AND project_id=? ORDER BY id DESC", (request.user["id"], proj_id))
    else:
        cur.execute("SELECT id, name, value, project_id, created_at FROM env_vars WHERE user_id=? ORDER BY id DESC", (request.user["id"],))
    return jsonify([dict(r) for r in cur.fetchall()])

@app.post("/env_vars")
@ui_auth_required
def create_env_var():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    value = (data.get("value") or "").strip()
    proj_id = data.get("project_id")
    if proj_id == "": proj_id = None
    
    if not name or not value:
        return jsonify({"error": "Name and value required"}), 400
        
    db=get_db()
    cur=db.cursor()
    try:
        cur.execute("INSERT INTO env_vars (user_id, project_id, name, value) VALUES (?,?,?,?)", (request.user["id"], proj_id, name, value))
        db.commit()
        return jsonify({"id": cur.lastrowid, "name": name, "value": value, "project_id": proj_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.put("/env_vars/<int:var_id>")
@ui_auth_required
def update_env_var(var_id):
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    value = (data.get("value") or "").strip()
    proj_id = data.get("project_id")
    if proj_id == "" or proj_id == "null": proj_id = None
    
    if not name or not value:
        return jsonify({"error": "Name and value required"}), 400
        
    db=get_db()
    cur=db.cursor()
    
    cur.execute("SELECT user_id FROM env_vars WHERE id=?", (var_id,))
    row = cur.fetchone()
    if not row: return jsonify({"error": "Not found"}), 404
    if row["user_id"] != request.user["id"]: return jsonify({"error": "Forbidden"}), 403
    
    if proj_id:
        cur.execute("SELECT id FROM projects WHERE id=? AND user_id=?", (proj_id, request.user["id"]))
        if not cur.fetchone(): return jsonify({"error": "Invalid project"}), 400
        
    try:
        cur.execute("UPDATE env_vars SET project_id=?, name=?, value=? WHERE id=?", 
                    (proj_id, name, value, var_id))
        db.commit()
        return jsonify({"updated": True, "id": var_id, "name": name, "value": value, "project_id": proj_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.delete("/env_vars/<int:var_id>")
@ui_auth_required
def delete_env_var(var_id):
    db=get_db()
    cur=db.cursor()
    cur.execute("SELECT user_id FROM env_vars WHERE id=?", (var_id,))
    row = cur.fetchone()
    if not row: return jsonify({"error": "Not found"}), 404
    if row["user_id"] != request.user["id"]: return jsonify({"error": "Forbidden"}), 403
    
    cur.execute("DELETE FROM env_vars WHERE id=?", (var_id,))
    db.commit()
    return jsonify({"deleted": True})

# ==================== NEW: FUNCTION TEMPLATES ====================
@app.get("/templates")
@ui_auth_required
def list_templates():
    db=get_db()
    cur=db.cursor()
    # ALL users can view all templates (Making templates fully public across the system)
    cur.execute("""
        SELECT t.id, t.title, t.description, t.code, t.created_at, t.owner_id, u.email as owner_email
        FROM function_templates t
        JOIN users u ON u.id = t.owner_id
        ORDER BY t.id DESC
    """)
    return jsonify([dict(r) for r in cur.fetchall()])

@app.post("/templates")
@ui_auth_required
def create_template():
    data = request.get_json() or {}
    title = (data.get("title") or "New Template").strip()
    desc = (data.get("description") or "").strip()
    code = (data.get("code") or "").strip()
    
    if not title or not code:
        return jsonify({"error": "Title and code are required"}), 400
        
    db=get_db()
    cur=db.cursor()
    try:
        cur.execute("INSERT INTO function_templates (owner_id, title, description, code) VALUES (?,?,?,?)", (request.user["id"], title, desc, code))
        db.commit()
        return jsonify({"id": cur.lastrowid, "title": title, "description": desc, "code": code})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.put("/templates/<int:tpl_id>")
@ui_auth_required
def update_template(tpl_id):
    data = request.get_json() or {}
    title = (data.get("title") or "").strip()
    desc = (data.get("description") or "").strip()
    code = (data.get("code") or "").strip()
    
    if not title or not code:
        return jsonify({"error": "Title and code are required"}), 400
        
    db=get_db()
    cur=db.cursor()
    cur.execute("SELECT owner_id FROM function_templates WHERE id=?", (tpl_id,))
    row = cur.fetchone()
    if not row: return jsonify({"error": "Not found"}), 404
    
    is_admin = request.user.get("role") == "admin"
    if row["owner_id"] != request.user["id"] and not is_admin: 
        return jsonify({"error": "Forbidden - You do not own this template"}), 403
    
    cur.execute("UPDATE function_templates SET title=?, description=?, code=? WHERE id=?", (title, desc, code, tpl_id))
    db.commit()
    return jsonify({"updated": True})

@app.delete("/templates/<int:tpl_id>")
@ui_auth_required
def delete_template(tpl_id):
    db=get_db()
    cur=db.cursor()
    cur.execute("SELECT owner_id FROM function_templates WHERE id=?", (tpl_id,))
    row = cur.fetchone()
    if not row: return jsonify({"error": "Not found"}), 404
    
    is_admin = request.user.get("role") == "admin"
    if row["owner_id"] != request.user["id"] and not is_admin: 
        return jsonify({"error": "Forbidden - You do not own this template"}), 403
    
    cur.execute("DELETE FROM function_templates WHERE id=?", (tpl_id,))
    db.commit()
    return jsonify({"deleted": True})

@app.post("/templates/<int:tpl_id>:clone")
@ui_auth_required
def clone_template(tpl_id):
    db=get_db()
    cur=db.cursor()
    cur.execute("SELECT owner_id, title, description, code FROM function_templates WHERE id=?", (tpl_id,))
    row = cur.fetchone()
    if not row: return jsonify({"error": "Not found"}), 404
    if row["owner_id"] != request.user["id"]: return jsonify({"error": "Forbidden"}), 403
    
    new_title = f"Copy of {row['title']}"
    cur.execute("INSERT INTO function_templates (owner_id, title, description, code) VALUES (?,?,?,?)", 
                (request.user["id"], new_title, row["description"], row["code"]))
    db.commit()
    return jsonify({"id": cur.lastrowid, "title": new_title})

# ==================== FUNCTION ROUTES ====================
@app.post("/deploy_function")
@ui_auth_required
def deploy_function():
    if request.user.get("role") == "viewer":
        return jsonify({"error": "Viewers cannot create APIs"}), 403

    data = request.get_json() or {}
    code = data.get("code", "")
    desc = (data.get("desc") or "")[:255]
    visibility = data.get("visibility") or "private"
    proj_id = data.get("project_id")
    if proj_id == "": proj_id = None
    
    if "def api_def" not in code:
        return jsonify({"error": "Function must define 'api_def(args)'" }), 400
    db=get_db()
    cur=db.cursor()
    cur.execute(
        "INSERT INTO api_container (api_def, description, owner_id, project_id, visibility) VALUES (?,?,?,?,?)",
        (code, desc, request.user["id"], proj_id, visibility)
    )
    db.commit()
    return jsonify({"id": cur.lastrowid}), 201

@app.put("/functions/<int:fn_id>")
@ui_auth_required
def update_function(fn_id):
    data = request.get_json() or {}
    code = data.get("code")
    desc = data.get("desc")
    visibility = data.get("visibility")
    proj_id = data.get("project_id")
    if proj_id == "": proj_id = None
    
    db=get_db()
    cur=db.cursor()
    cur.execute("SELECT owner_id FROM api_container WHERE id=?", (fn_id,))
    row = cur.fetchone()
    if not row: return jsonify({"error":"Not found"}), 404
    
    is_admin = request.user.get("role") == "admin"
    if row["owner_id"] != request.user["id"] and not is_admin: 
        return jsonify({"error":"Forbidden. Only the owner can modify this API."}), 403
    
    sets, vals = [], []
    if code:
        if "def api_def" not in code: return jsonify({"error":"Function must define"}), 400
        sets.append("api_def=?"); vals.append(code)
    if desc is not None:
        sets.append("description=?"); vals.append(desc[:255])
    if visibility in ("private","public"):
        sets.append("visibility=?"); vals.append(visibility)
    if proj_id is not None or "project_id" in data:
        sets.append("project_id=?"); vals.append(proj_id)
        
    if not sets: return jsonify({"error":"Nothing to update"}), 400
    vals.append(fn_id)
    cur.execute(f"UPDATE api_container SET {', '.join(sets)} WHERE id=?", tuple(vals))
    db.commit()
    return jsonify({"updated": True})

@app.get("/functions")
@ui_auth_required
def list_functions():
    scope = request.args.get("scope","mine")
    db=get_db()
    cur=db.cursor()
    
    # NEW LOGIC: Users can view functions where:
    # 1. They are the owner
    # 2. Or the function is assigned to a project they are a member of
    # 3. Or it is public (if available view)
    
    if scope == "available":
        cur.execute("""
            SELECT f.id, f.description, f.created_at, f.owner_id, u.email AS owner_email, p.name AS project_name
            FROM api_container f
            JOIN users u ON u.id=f.owner_id
            LEFT JOIN projects p ON p.id=f.project_id
            WHERE f.visibility='public' AND f.owner_id != ?
            ORDER BY f.id DESC
        """, (request.user["id"],))
    else:
        # Mine + Shared Projects
        cur.execute("""
            SELECT DISTINCT f.id, f.description, f.created_at, f.visibility, f.owner_id, f.project_id, p.name AS project_name
            FROM api_container f
            LEFT JOIN projects p ON p.id=f.project_id
            LEFT JOIN project_members pm ON pm.project_id = f.project_id
            WHERE f.owner_id=? OR pm.user_id=?
            ORDER BY f.id DESC
        """, (request.user["id"], request.user["id"]))
    return jsonify([dict(r) for r in cur.fetchall()])

@app.get("/functions/<int:fn_id>")
@ui_auth_required
def get_function(fn_id):
    db=get_db()
    cur=db.cursor()
    cur.execute("""
        SELECT f.id, f.description, f.api_def, f.created_at, f.visibility, f.owner_id, f.project_id, u.email AS owner_email
        FROM api_container f
        JOIN users u ON u.id=f.owner_id
        WHERE f.id=?
    """, (fn_id,))
    row = cur.fetchone()
    if not row: return jsonify({"error":"Not found"}), 404
    
    is_admin = request.user.get("role") == "admin"
    
    # Check if they are a project member
    is_project_member = False
    if row["project_id"]:
        cur.execute("SELECT id FROM project_members WHERE project_id=? AND user_id=?", (row["project_id"], request.user["id"]))
        is_project_member = cur.fetchone() is not None
        
    if row["visibility"] != "public" and row["owner_id"] != request.user["id"] and not is_admin and not is_project_member:
        return jsonify({"error":"Forbidden"}), 403
    return jsonify(dict(row))

@app.delete("/functions/<int:fn_id>")
@ui_auth_required
def delete_function(fn_id):
    db=get_db()
    cur=db.cursor()
    cur.execute("SELECT owner_id FROM api_container WHERE id=?", (fn_id,))
    row = cur.fetchone()
    if not row: return jsonify({"deleted": False, "error":"Not found"}), 404
    
    is_admin = request.user.get("role") == "admin"
    if row["owner_id"] != request.user["id"] and not is_admin: 
        return jsonify({"error":"Forbidden. Only the owner can delete this API."}), 403
    cur.execute("DELETE FROM api_container WHERE id=?", (fn_id,))
    db.commit()
    return jsonify({"deleted": True})

# =============== EXECUTION LOGIC ===============
@app.post("/ofa")
@token_or_jwt_auth
def ofa():
    payload = request.get_json(force=True)
    fn_id = payload.get("id")
    args = payload.get("api_args", {})
    if not fn_id: return jsonify({"error": "Missing id"}), 400

    start = time.time()
    ok = False
    error_msg = None

    db=get_db()
    cur=db.cursor()
    try:
        cur.execute("SELECT api_def, owner_id, project_id FROM api_container WHERE id=?", (fn_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "Function not found"}), 404

        # Fetch environment variables for this function's owner and project
        cur.execute("SELECT name, value FROM env_vars WHERE user_id=? AND (project_id IS NULL OR project_id=?)", (row["owner_id"], row["project_id"]))
        env_vars = {r["name"]: r["value"] for r in cur.fetchall()}

        res = safe_exec_function(row["api_def"], args, env=env_vars)
        if res.get("error"):
            error_msg = res["error"]
        else:
            ok = True

        latency = int((time.time()-start)*1000)
        res["latency_ms"] = latency
        
        token_id = getattr(request, "token_id", None)
        
        cur.execute(
            "INSERT INTO call_logs (function_id, token_id, success, latency_ms, error_message) VALUES (?,?,?,?,?)",
            (fn_id, token_id, 1 if ok else 0, latency, (error_msg or "")[:500])
        )
        db.commit()
        return jsonify(res)
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500

# =============== DRAFTS ===============
@app.post("/drafts")
@ui_auth_required
def save_draft():
    d = request.get_json(force=True)
    draft_id = d.get("id")
    desc = (d.get("description") or "")[:255]
    code = d.get("code") or ""
    visibility = d.get("visibility") or "private"
    proj_id = d.get("project_id")
    if proj_id == "": proj_id = None

    if "def api_def" not in code:
        return jsonify({"error": "Function must define 'api_def(args)'" }), 400

    db=get_db()
    cur=db.cursor()
    if draft_id:
        cur.execute(
            "UPDATE api_drafts SET description=?, code=?, visibility=?, project_id=? WHERE id=? AND owner_id=?",
            (desc, code, visibility, proj_id, draft_id, request.user["id"])
        )
        if cur.rowcount == 0:
            return jsonify({"error": "Not found or forbidden"}), 403
    else:
        cur.execute(
            "INSERT INTO api_drafts (owner_id, project_id, description, code, visibility) VALUES (?,?,?,?,?)",
            (request.user["id"], proj_id, desc, code, visibility)
        )
        draft_id = cur.lastrowid
    db.commit()
    return jsonify({ "id": draft_id })

@app.post("/drafts/<int:draft_id>:test")
@ui_auth_required
def drafts_test(draft_id):
    payload = request.get_json(force=True) or {}
    args = payload.get("args", {})
    db=get_db()
    cur=db.cursor()
    cur.execute("SELECT owner_id, code, project_id FROM api_drafts WHERE id=?", (draft_id,))
    row = cur.fetchone()
    if not row: return jsonify({"error": "Draft not found"}), 404
    if row["owner_id"] != request.user["id"]: return jsonify({"error": "Forbidden"}), 403

    start = time.time()
    try:
        cur.execute("SELECT name, value FROM env_vars WHERE user_id=? AND (project_id IS NULL OR project_id=?)", (row["owner_id"], row["project_id"]))
        env_vars = {r["name"]: r["value"] for r in cur.fetchall()}

        result = safe_exec_function(row["code"], args, env=env_vars)
        result["latency_ms"] = int((time.time() - start) * 1000)
        result["draft_id"] = draft_id
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.post("/drafts/<int:draft_id>:promote")
@ui_auth_required
def promote_draft(draft_id):
    user_id = request.user["id"]
    db=get_db()
    cur=db.cursor()
    cur.execute("SELECT owner_id, project_id, description, code, visibility FROM api_drafts WHERE id=?", (draft_id,))
    row = cur.fetchone()
    if not row: return jsonify({"error": "Draft not found"}), 404
    if row["owner_id"] != user_id: return jsonify({"error": "Forbidden"}), 403
        
    cur.execute(
        "INSERT INTO api_container (api_def, description, owner_id, project_id, visibility) VALUES (?,?,?,?,?)",
        (row["code"], row["description"], user_id, row["project_id"], row["visibility"])
    )
    new_id = cur.lastrowid
    cur.execute("DELETE FROM api_drafts WHERE id=?", (draft_id,))
    db.commit()
    return jsonify({"id": new_id}), 201

# =============== LOGS & STATS ===============
@app.get("/stats")
@ui_auth_required
def stats():
    db=get_db()
    cur=db.cursor()
    cur.execute("SELECT COUNT(*) AS c FROM api_container WHERE owner_id=?", (request.user["id"],))
    total_functions = cur.fetchone()["c"]

    cur.execute("""
        SELECT COUNT(*) AS c FROM call_logs c 
        JOIN api_container f ON c.function_id = f.id 
        WHERE f.owner_id=? AND c.created_at >= datetime('now', '-1 day')
    """, (request.user["id"],))
    calls24h = cur.fetchone()["c"]

    cur.execute("""
        SELECT SUM(c.success) AS s, COUNT(c.id) AS t 
        FROM call_logs c
        JOIN api_container f ON c.function_id = f.id
        WHERE f.owner_id=?
    """, (request.user["id"],))
    row = cur.fetchone()
    s, t = (row["s"] or 0), (row["t"] or 0)
    success_rate = (s / t) if t else 0.0

    cur.execute("""
        SELECT c.function_id AS id, f.description AS label, COUNT(*) AS calls
        FROM call_logs c
        JOIN api_container f ON f.id=c.function_id
        WHERE f.owner_id=?
        GROUP BY c.function_id, f.description
        ORDER BY calls DESC
        LIMIT 10
    """, (request.user["id"],))
    by_fn = [dict(r) for r in cur.fetchall()]

    cur.execute("""
        SELECT SUM(c.success) AS s, SUM(1-c.success) AS e 
        FROM call_logs c
        JOIN api_container f ON f.id=c.function_id
        WHERE f.owner_id=?
    """, (request.user["id"],))
    row2 = cur.fetchone()
    outcomes = {"success": int(row2["s"] or 0), "error": int(row2["e"] or 0)}

    return jsonify({
        "totals": {
            "functions": total_functions,
            "calls24h": calls24h,
            "successRate": round(success_rate, 2),
            "topFunction": (f"#{by_fn[0]['id']}" if by_fn else None)
        },
        "byFunction": by_fn,
        "outcomes": outcomes
    })

@app.get("/logs")
@ui_auth_required
def get_logs():
    db=get_db()
    cur=db.cursor()
    cur.execute("""
        SELECT c.id, c.success, c.latency_ms, c.error_message, c.created_at, 
               f.description AS function_name, p.name AS project_name
        FROM call_logs c
        JOIN api_container f ON f.id=c.function_id
        LEFT JOIN api_tokens t ON t.id=c.token_id
        LEFT JOIN projects p ON p.id=t.project_id
        WHERE f.owner_id=?
        ORDER BY c.id DESC LIMIT 50
    """, (request.user["id"],))
    return jsonify([dict(r) for r in cur.fetchall()])


# =============== GENERATOR ===============
@app.post("/generate_function")
@ui_auth_required
def generate_function():
    try:
        data = request.get_json()
        prompt = data.get('prompt', '').strip()
        current_code = data.get('current_code', '').strip()

        if not prompt:
            return jsonify({"error": "No prompt provided"}), 400

        # --- System + User messages for code generation ---
        final_prompt = (
            "You are a world-class Python assistant. "
            "You write clean, production-ready Python functions "
            "based on the user's description. "
            "function name should always be api_def(args): parameter should always be args nothing else, modify the function body accordingly. "
            "Along with the function, you also write a short description "
            "Any imports should only be inside the function "
            "that follows this template strictly:\n\n"
            "Template:\n"
            "\"<one-line summary of purpose>. description should always start with 'tool to' and the description should mention what keys to be used in the parameter supplied. "
            "Takes in parameters like '<comma-separated parameter names>' "
            "and performs '<main action>'.\"\n\n"
            "Output your answer as valid JSON with two fields:\n"
            "{ \"code\": \"<python code>\", \"description\": \"<short description>\" }\n\n"
            f"User Description:\n{prompt}\n\n"
            f"Current Code:\n{current_code if current_code else '(empty)'}\n\n"
            "Write or update the Python function accordingly. "
            "Follow the JSON output format strictly."
        )

        # --- Call LLM to generate both code + description ---
        print(f"DEBUG: Starting LLM call using NokiaGPT_Client for prompt: {prompt[:50]}...")
        try:
            gpt_client = Client()
            intent_response = gpt_client.get_gpt_response(prompt=final_prompt)
            print("DEBUG: LLM call completed successfully.")
        except Exception as e:
            print(f"DEBUG: LLM Connection/Request Error: {e}")
            raise e

        raw_output = intent_response.strip()

        # --- Extract JSON (in case model outputs extra formatting) ---
        try:
            json_match = re.search(r'\{.*\}', raw_output, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(0))
                generated_code = result.get("code", "").strip()
                description = result.get("description", "").strip()
            else:
                # fallback: treat entire output as code if JSON missing
                generated_code = re.sub(r"^```(?:python)?\s*|```$", "", raw_output, flags=re.MULTILINE).strip()
                description = "(No structured description returned)"
        except Exception as e:
            generated_code = re.sub(r"^```(?:python)?\s*|```$", "", raw_output, flags=re.MULTILINE).strip()
            description = f"(Parsing error: {e})"

        return jsonify({
            "code": generated_code,
            "description": description
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
