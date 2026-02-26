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
def safe_exec_function(code_str: str, args: dict):
    # Determine the context allowed for the dynamic function
    safe_builtins = {
        "__import__": __import__,  # Required to allow importing modules
        "len": len, "sum": sum, "min": min, "max": max, "range": range,
        "abs": abs, "round": round, "enumerate": enumerate, "zip": zip, "sorted": sorted,
        "map": map, "filter": filter, "list": list, "dict": dict, "set": set, "any": any, "all": all,
        "Exception": Exception, "ValueError": ValueError, "TypeError": TypeError,
        "KeyError": KeyError, "IndexError": IndexError, "AttributeError": AttributeError,
        "isinstance": isinstance, "str": str, "int": int, "float": float, "bool": bool
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
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    if not email or not password:
        return jsonify({"error": "Missing email/password"}), 400
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id, email, name, password_hash FROM users WHERE email=?", (email,))
    user = cur.fetchone()
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid credentials"}), 401
    token = encode_jwt({"id": user["id"], "email": user["email"], "name": user["name"]})
    return jsonify({"token": token, "user": {"id": user["id"], "email": user["email"], "name": user["name"]}})

@app.post("/auth/register")
def register():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    name = (data.get("name") or "User").strip()
    password = data.get("password") or ""
    if not email or not password:
        return jsonify({"error": "Missing email/password"}), 400
    try:
        db = get_db()
        cur = db.cursor()
        cur.execute("INSERT INTO users (email, name, password_hash) VALUES (?,?,?)",
                    (email, name, generate_password_hash(password)))
        db.commit()
        return jsonify({"ok": True})
    except sqlite3.IntegrityError:
        return jsonify({"error": "Email already exists"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.get("/me")
@ui_auth_required
def me():
    return jsonify({"id": request.user["id"], "email": request.user["email"], "name": request.user["name"]})

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
    data = request.get_json() or {}
    name = (data.get("name") or "My Project").strip()
    db = get_db()
    cur = db.cursor()
    cur.execute("INSERT INTO projects (user_id, name) VALUES (?,?)", (request.user["id"], name))
    # generate a default token for the project immediately
    proj_id = cur.lastrowid
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
    cur.execute("SELECT id FROM projects WHERE id=? AND user_id=?", (proj_id, request.user["id"]))
    if not cur.fetchone(): return jsonify({"error": "Forbidden"}), 403

    raw_token = "sk_" + secrets.token_hex(20)
    cur.execute("INSERT INTO api_tokens (project_id, token) VALUES (?,?)", (proj_id, raw_token))
    db.commit()
    return jsonify({"id": cur.lastrowid, "token": raw_token})

# ==================== FUNCTION ROUTES ====================
@app.post("/deploy_function")
@ui_auth_required
def deploy_function():
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
    if row["owner_id"] != request.user["id"]: return jsonify({"error":"Forbidden"}), 403
    
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
        cur.execute("""
            SELECT f.id, f.description, f.created_at, f.visibility, f.owner_id, f.project_id, p.name AS project_name
            FROM api_container f
            LEFT JOIN projects p ON p.id=f.project_id
            WHERE f.owner_id=?
            ORDER BY f.id DESC
        """, (request.user["id"],))
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
    if row["visibility"] != "public" and row["owner_id"] != request.user["id"]:
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
    if row["owner_id"] != request.user["id"]: return jsonify({"error":"Forbidden"}), 403
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
        cur.execute("SELECT api_def FROM api_container WHERE id=?", (fn_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "Function not found"}), 404

        res = safe_exec_function(row["api_def"], args)
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
    cur.execute("SELECT owner_id, code FROM api_drafts WHERE id=?", (draft_id,))
    row = cur.fetchone()
    if not row: return jsonify({"error": "Draft not found"}), 404
    if row["owner_id"] != request.user["id"]: return jsonify({"error": "Forbidden"}), 403

    start = time.time()
    try:
        result = safe_exec_function(row["code"], args)
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
            "topFunction": (by_fn[0]["label"] if by_fn else None)
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
