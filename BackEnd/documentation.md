# OFA (One For All) API Backend Documentation

## 1. Introduction
The **OFA API Backend** is a Flask-based application acting as a dynamic function execution engine, often referred to as "SkillStack." It securely stores, manages, and executes Python code snippets dynamically based on user requests, while providing a robust authentication and isolation layer.

This documentation serves as both a **Project Guide** (for developers maintaining the system) and a **User Guide** (for how to interface and use the API).

---

## 2. Technical Stack
- **Framework**: Flask (`app.py`)
- **Database**: SQLite (`skillstack.db`) using `schema.sql`
- **Authentication**: JWT (JSON Web Tokens) and API Tokens
- **Execution Environment**: Python `exec()` with a restricted `__builtins__` dictionary to sandbox execution.
- **AI Integration**: Internal `NokiaGPT_Client.py` utility for generating function code from text prompts. (Replacing OpenAI).

---

## 3. Database Architecture
The backend uses a standard normalized SQLite database structure with the following key tables:

- `users`: Core user accounts (email, name, hashed password).
- `projects`: Logical grouping for environments and API tokens.
- `api_tokens`: Application-specific tokens mapping to a `project_id`.
- `env_vars`: Environment variables securely passed into the dynamic execution sandbox, scoped by user and project.
- `api_container`: Approved, published python functions ready for execution.
- `api_drafts`: Work-in-progress function code.
- `function_templates`: Reusable baseline code blocks.
- `call_logs`: Audit trail of every function execution, tracking latency, success/failure, and errors.

---

## 4. User Guide: How to Use the API

### 4.1. Core Concepts
*   **Dynamic Functions:** You write a Python script defining a function named `api_def(args)`. You deploy this to the backend. It receives a unique ID.
*   **Execution (`/ofa` endpoint):** You hit the `/ofa` POST endpoint with the function's unique ID and arguments in a JSON payload. The backend executes your Python code dynamically and returns the result.
*   **Environment Variables:** You can set variables (like Secret Keys, API Keys) in the system that your dynamic code can access securely via `args["env"]["VARIABLE_NAME"]`.

### 4.2. Authentication Methods
The API supports two methods of authentication, depending on the endpoint:
1.  **JWT Authentication (UI/Dashboard usage):** 
    Pass a JWT token received from `/auth/login` in the Header to access management endpoints (creating projects, editing code).
    *   `Authorization: Bearer <jwt_token>`
2.  **API Token Authentication (System-to-System):** 
    Used for machine-to-machine calls specifically to execute functions via `/ofa`. 
    *   `Authorization: Bearer <sk_token_from_project>`

---

## 5. API Reference (Key Endpoints)

### 5.1. User & Authentication
*   **POST `/auth/register`**: Register a new user (`email`, `name`, `password`).
*   **POST `/auth/login`**: Authenticate and receive a JWT token.
*   **GET `/me`**: Get current logged-in user details.

### 5.2. Projects & Tokens
*   **GET/POST `/projects`**: List or create a new project grouping.
*   **GET/POST `/projects/<id>/tokens`**: Manage API tokens for a specific project. 

### 5.3. Managing Functions (The "API Container")
*   **POST `/deploy_function`**: Publish a new function.
    *   Payload: `{"code": "def api_def(args): return {}", "desc": "My func", "project_id": 1, "visibility": "private"}`
*   **GET `/functions`**: List all functions owned by you.
*   **PUT `/functions/<id>`**: Update existing function code or metadata.
*   **DELETE `/functions/<id>`**: Delete a function.

### 5.4. Execution (The OFA Engine)
*   **POST `/ofa`**: Execute a dynamic Python function.
    *   **Requires Authorization**: JWT or API Token.
    *   **Payload Example**:
        ```json
        {
          "id": 12, 
          "api_args": {"user_id": 100, "action": "delete"}
        }
        ```
    *   **Returns**: The result of the python script, latency, and success status.

### 5.5. AI Function Generation
*   **POST `/generate_function`**: Uses NokiaGPT to automatically generate the Python `api_def(args)` code based on a plain-English `prompt` provided in the payload.

### 5.6 Environment Variables
*   **GET/POST/PUT/DELETE `/env_vars`**: Manage secure environment variables scoped to your `user_id` and specific `project_id`. These variables are automatically injected into the `env` dictionary inside your `api_def(args)` function during execution.

### 5.7 Logs & Analytics
*   **GET `/stats`**: Get aggregated metrics on your function calls (success rates, total functions, calls in the last 24h).
*   **GET `/logs`**: Retrieves the trailing 50 call executions, including latency and detailed error traces for debugging failed executions.

---

## 6. Writing a Safe Function (Developer Guide)

When deploying code via `/deploy_function`, your script **must** contain a function signature exactly like this:

```python
def api_def(args):
    # args is a dictionary containing the payload sent to /ofa
    # args["env"] contains your injected environment variables
    
    my_var = args.get("my_input_parameter")
    secret_key = args["env"].get("AWS_KEY")
    
    # Do logic...
    
    return {"status": "success", "result": my_var}
```

**Security Restrictions (Sandbox):**
The `safe_exec_function()` engine removes potentially dangerous Python built-ins (like standard file system access or system commands) to ensure the server remains secure. You do have access to standard types (`dict`, `list`), math operations, and safe built-ins.
