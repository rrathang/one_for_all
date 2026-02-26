from flask import Flask, request, jsonify
import pymysql
import pandas as pd

app = Flask(__name__)

class OFA:

    def use_packages(self):
        pass

    def __initialize__(self, args):
        self.args = args
        self.packages = []
        self.use_packages()
        self.import_packages(self.packages)

    def get(self, key, defaultValue=None):
        return self.args.get(key, defaultValue)
    
    def buildResponse(self, code, data):
        return {'responseCode': code, 'responseData': data}
        
    def import_package(self, package):
        exec(f"import {package}", globals())
        
    def import_packages(self, packages):
        for package in packages:
            self.import_package(package)


# The call function as provided
def call(context):
    api_id = context.get('id')
    api_args = context.get('api_args')
    response = ""
    connection = pymysql.connect(host='localhost',user='root',password='root',database='ofa_test_db')
    try:
        query = "SELECT api_def FROM ofa_api_container_1 WHERE id = %s"
        with connection.cursor() as cursor:
            cursor.execute(query, (api_id,))
            result = cursor.fetchone()
            if result:
                api_def_str = result[0]
                api_def_str = api_def_str.decode('utf-8')
                local_scope = {}
                exec(api_def_str, globals(), local_scope)
                if 'API' in local_scope:
                    # Version 2 - Code - OOPS concept
                    
                    APIClass = local_scope['API']
                    api_instance = APIClass()
                    api_instance.__initialize__(api_args)
                    response = api_instance.api_def()
                else:
                    # Version 1 - Code - functional
                    exec(api_def_str, {}, local_scope)
                    api_def = local_scope.get('api_def')
                    if api_def:
                        response = api_def(api_args)
                    else:
                        response = "api_def not found in scope"
            else:
                response = "API definition not found"
    except Exception as e:
        response = f"Error: {str(e)}"
    finally:
        connection.close()
    return response

# Flask route to handle POST requests
@app.route('/ofa', methods=['POST'])
def ofa():
    try:
        # Parse JSON request
        context = request.get_json()
        if not context or 'id' not in context or 'api_args' not in context:
            return jsonify({"error": "Invalid request format, 'id' and 'api_args' required"}), 400
        
        # Call the function with the context
        result = call(context)
        
        # Return the result as a JSON response
        return jsonify({"result": result}), 200
    
    except Exception as e:
        print(e)
        return jsonify({"error": str(e)}), 500
    
@app.route('/ofa', methods=['GET'])
def ofa_info():
    context = request.get_json()
    print(context)
    return jsonify({"result": {'hi':'Hello'}}), 200

if __name__ == '__main__':
    app.run(host='10.136.178.127', debug=True)
