
import os, time, traceback, jwt
from functools import wraps
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template, url_for
from flask_cors import CORS
import pymysql
from pymysql.cursors import DictCursor
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

# ==================== CONFIG ====================
load_dotenv()
app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app)

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "root")
DB_PASS = os.getenv("DB_PASS", "root@09091902")
DB_NAME = os.getenv("DB_NAME", "api_agent_tooling")

JWT_SECRET = os.getenv("JWT_SECRET", "dev_secret_change_me")
JWT_ISS = "skillstack"
JWT_EXP_HOURS = int(os.getenv("JWT_EXP_HOURS", "8"))

# ==================== DB ====================
def db():
    return pymysql.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASS, database=DB_NAME,
        cursorclass=DictCursor, autocommit=True
    )

# ==================== AUTH ====================
def encode_jwt(payload: dict) -> str:
    now = datetime.utcnow()
    base = {"iss": JWT_ISS, "iat": int(now.timestamp()), "exp": int((now + timedelta(hours=JWT_EXP_HOURS)).timestamp())}
    return jwt.encode({**base, **payload}, JWT_SECRET, algorithm="HS256")

def decode_jwt(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=["HS256"], options={"require": ["exp","iat","iss"]})

def auth_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        hdr = request.headers.get("Authorization","")
        if not hdr.startswith("Bearer "):
            return jsonify({"error": "Unauthorized"}), 401
        token = hdr.split(" ",1)[1]
        try:
            request.user = decode_jwt(token)  # {id,email,name}
        except Exception:
            return jsonify({"error": "Unauthorized"}), 401
        return fn(*args, **kwargs)
    return wrapper

# ==================== SAFE EXEC ====================
def safe_exec_function(code_str: str, args: dict):
    safe_builtins = {
        "len": len, "sum": sum, "min": min, "max": max, "range": range,
        "abs": abs, "round": round, "enumerate": enumerate, "zip": zip, "sorted": sorted,
        "map": map, "filter": filter, "list": list, "dict": dict, "set": set, "any": any, "all": all
    }
    g = {"__builtins__": safe_builtins}
    l = {}
    try:
        exec(code_str, g, l)
        fn = l.get("api_def")
        if not fn:
            return {"error": "Function 'api_def(args)' not found"}
        return {"result": fn(args)}
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}

# ==================== UI ROUTE ====================
@app.get("/")
def ui():
    return render_template("index.html")

# ==================== AUTH ROUTES ====================
@app.post("/auth/login")
def login():
    data = request.get_json(force=True)
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    if not email or not password:
        return jsonify({"error": "Missing email/password"}), 400
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, email, name, password_hash FROM users WHERE email=%s", (email,))
        user = cur.fetchone()
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid credentials"}), 401
    token = encode_jwt({"id": user["id"], "email": user["email"], "name": user["name"]})
    return jsonify({"token": token, "user": {"id": user["id"], "email": user["email"], "name": user["name"]}})

@app.get("/me")
@auth_required
def me():
    return jsonify({"id": request.user["id"], "email": request.user["email"], "name": request.user["name"]})

# ==================== FUNCTION ROUTES ====================
@app.post("/deploy_function")
@auth_required
def deploy_function():
    data = request.get_json(force=True)
    code = data.get("code", "")
    desc = (data.get("desc") or "")[:255]
    visibility = data.get("visibility") or "private"
    if "def api_def" not in code:
        return jsonify({"error": "Function must define 'api_def(args)'" }), 400
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO api_container (api_def, description, owner_id, visibility) VALUES (%s,%s,%s,%s)",
            (code, desc, request.user["id"], visibility)
        )
        new_id = cur.lastrowid
    return jsonify({"id": new_id}), 201

@app.put("/functions/<int:fn_id>")
@auth_required
def update_function(fn_id):
    data = request.get_json(force=True)
    code = data.get("code")
    desc = data.get("desc")
    visibility = data.get("visibility")
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT owner_id FROM api_container WHERE id=%s", (fn_id,))
        row = cur.fetchone()
        if not row: return jsonify({"error":"Not found"}), 404
        if row["owner_id"] != request.user["id"]:
            return jsonify({"error":"Forbidden"}), 403
        sets, vals = [], []
        if code:
            if "def api_def" not in code: return jsonify({"error":"Function must define 'api_def(args)'" }), 400
            sets.append("api_def=%s"); vals.append(code)
        if desc is not None:
            sets.append("description=%s"); vals.append(desc[:255])
        if visibility in ("private","public"):
            sets.append("visibility=%s"); vals.append(visibility)
        if not sets: return jsonify({"error":"Nothing to update"}), 400
        vals.append(fn_id)
        cur.execute(f"UPDATE api_container SET {', '.join(sets)} WHERE id=%s", tuple(vals))
    return jsonify({"updated": True})

@app.get("/functions")
@auth_required
def list_functions():
    scope = request.args.get("scope","mine")
    with db() as conn, conn.cursor() as cur:
        if scope == "available":
            cur.execute("""
                SELECT f.id, f.description, f.created_at, f.owner_id, u.email AS owner_email
                FROM api_container f
                JOIN users u ON u.id=f.owner_id
                WHERE f.visibility='public' AND f.owner_id != %s
                ORDER BY f.id DESC
            """, (request.user["id"],))
        else:
            cur.execute("""
                SELECT id, description, created_at, visibility, owner_id
                FROM api_container
                WHERE owner_id=%s
                ORDER BY id DESC
            """, (request.user["id"],))
        return jsonify(cur.fetchall())

@app.get("/functions/<int:fn_id>")
@auth_required
def get_function(fn_id):
    with db() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT f.id, f.description, f.api_def, f.created_at, f.visibility, f.owner_id, u.email AS owner_email
            FROM api_container f
            JOIN users u ON u.id=f.owner_id
            WHERE f.id=%s
        """, (fn_id,))
        row = cur.fetchone()
        if not row: return jsonify({"error":"Not found"}), 404
        if row["visibility"] != "public" and row["owner_id"] != request.user["id"]:
            return jsonify({"error":"Forbidden"}), 403
        return jsonify(row)

@app.delete("/functions/<int:fn_id>")
@auth_required
def delete_function(fn_id):
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT owner_id FROM api_container WHERE id=%s", (fn_id,))
        row = cur.fetchone()
        if not row: return jsonify({"deleted": False, "error":"Not found"}), 404
        if row["owner_id"] != request.user["id"]:
            return jsonify({"error":"Forbidden"}), 403
        cur.execute("DELETE FROM api_container WHERE id=%s", (fn_id,))
    return jsonify({"deleted": True})

# Execute by ID + log call
@app.post("/ofa")
@auth_required
def ofa():
    payload = request.get_json(force=True)
    fn_id = payload.get("id")
    args = payload.get("api_args", {})
    if not fn_id: return jsonify({"error": "Missing id"}), 400

    start = time.time()
    ok = False
    error_msg = None
    result_payload = None

    try:
        with db() as conn, conn.cursor() as cur:
            cur.execute("SELECT api_def FROM api_container WHERE id=%s", (fn_id,))
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "Function not found"}), 404

            res = safe_exec_function(row["api_def"], args)
            if "error" in res:
                error_msg = res["error"]
                result_payload = res
            else:
                ok = True
                result_payload = res

            cur.execute(
                "INSERT INTO call_logs (function_id, success, latency_ms, error_message) VALUES (%s,%s,%s,%s)",
                (fn_id, 1 if ok else 0, int((time.time()-start)*1000), (error_msg or "")[:500])
            )
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500

    return jsonify(result_payload)

# Dashboard stats
@app.get("/stats")
@auth_required
def stats():
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS c FROM api_container")
        total_functions = cur.fetchone()["c"]

        cur.execute("SELECT COUNT(*) AS c FROM call_logs WHERE created_at >= NOW() - INTERVAL 1 DAY")
        calls24h = cur.fetchone()["c"]

        cur.execute("SELECT SUM(success) AS s, COUNT(*) AS t FROM call_logs")
        row = cur.fetchone()
        s, t = (row["s"] or 0), (row["t"] or 0)
        success_rate = (s / t) if t else 0.0

        cur.execute("""
            SELECT c.function_id AS id, f.description AS label, COUNT(*) AS calls
            FROM call_logs c
            JOIN api_container f ON f.id=c.function_id
            GROUP BY c.function_id, f.description
            ORDER BY calls DESC
            LIMIT 10
        """)
        by_fn = cur.fetchall()

        cur.execute("SELECT SUM(success) AS s, SUM(1-success) AS e FROM call_logs")
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

# =============== DEV: quick user register (optional) ===============
@app.post("/auth/register")
def register():
    data = request.get_json(force=True)
    email = (data.get("email") or "").strip().lower()
    name = (data.get("name") or "User").strip()
    password = data.get("password") or ""
    if not email or not password:
        return jsonify({"error": "Missing email/password"}), 400
    try:
        with db() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO users (email, name, password_hash) VALUES (%s,%s,%s)",
                        (email, name, generate_password_hash(password)))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.post("/drafts")
@auth_required
def save_draft():
    d = request.get_json(force=True)
    draft_id = d.get("id")
    desc = (d.get("description") or "")[:255]
    code = d.get("code") or ""
    visibility = d.get("visibility") or "private"

    if "def api_def" not in code:
        return jsonify({"error": "Function must define 'api_def(args)'" }), 400

    with db() as conn, conn.cursor() as cur:
        if draft_id:
            # Update only if the caller owns it
            cur.execute(
                "UPDATE api_drafts SET description=%s, code=%s, visibility=%s "
                "WHERE id=%s AND owner_id=%s",
                (desc, code, visibility, draft_id, request.user["id"])
            )
            # If no row updated (not owner or wrong id)
            cur.execute("SELECT ROW_COUNT() AS rc")
            if cur.fetchone()["rc"] == 0:
                return jsonify({"error": "Not found or forbidden"}), 403
        else:
            cur.execute(
                "INSERT INTO api_drafts (owner_id, description, code, visibility) "
                "VALUES (%s,%s,%s,%s)",
                (request.user["id"], desc, code, visibility)
            )
            draft_id = cur.lastrowid

    return jsonify({ "id": draft_id })

@app.post("/drafts/<int:draft_id>:test")
@auth_required
def drafts_test(draft_id):
    payload = request.get_json(force=True) or {}
    args = payload.get("args", {})

    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT owner_id, code FROM api_drafts WHERE id=%s", (draft_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "Draft not found"}), 404
        if row["owner_id"] != request.user["id"]:
            return jsonify({"error": "Forbidden"}), 403

        start = time.time()
        try:
            result = safe_exec_function(row["code"], args)
            latency = int((time.time() - start) * 1000)
            # (Optional) record test logs
            # cur.execute("INSERT INTO draft_test_logs (draft_id, success, latency_ms, error_message) VALUES (%s,%s,%s,%s)",
            #             (draft_id, 1 if "error" not in result else 0, latency, result.get("error", "")))
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
