from flask import Flask, request, jsonify
from models import db, User
from config import Config
from phi.agent import Agent
from phi.model.google import Gemini
import os,re
from sqlalchemy import text

os.environ['GOOGLE_API_KEY']=os.getenv('GOOGLE_API_KEY')

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

@app.route("/add_user", methods=["POST"])
def add_user():
    data = request.json
    user = User(name=data["name"], email=data["email"])
    db.session.add(user)
    db.session.commit()
    return jsonify({"message": "User added successfully", "user": user.to_dict()})


@app.route("/query", methods=["POST"])
def query_database():
    try:
        if not request.is_json:
            return jsonify({"error": "Request must be JSON"}), 400
        
        data = request.json
        prompt = data.get("query")
        if not prompt:
            return jsonify({"error": "Query parameter is required"}), 400

        # Get all tables
        try:
            all_tables = db.session.execute(text("SHOW TABLES")).fetchall()
        except Exception as e:
            return jsonify({"error": f"Failed to fetch tables: {str(e)}"}), 500

        # Initialize agent and generate SQL query
        sql_agent = Agent(
            name="SQL Query Generator",
            model=Gemini(id="gemini-1.5-flash"),
            role="sql query generator",
            show_tool_calls=True,
            markdown=True,
        )

        agent_answer = Agent(
            name="Answer Generator",
            model=Gemini(id="gemini-1.5-flash"),
            role="Answer generator",
            show_tool_calls=True,
            markdown=True,
        )

        run = sql_agent.run(
            f"Database name is : {os.getenv('MYSQL_DB')}"
            f"Available tables are: {all_tables}"
            f"Generate an SQL query for: {prompt}. "
            f"I want only sql query in response. "
            
        )

        # Extract SQL query using regex
        query_match = re.search(r"```sql\n(.*?)\n```", run.content, re.DOTALL)
        if not query_match:
            return jsonify({"error": "Could not extract SQL query from response"}), 500
        
        extracted_query = query_match.group(1).strip()
        extracted_query = extracted_query.replace('"', '`')

        # Execute query and format results
        try:
            result = db.session.execute(text(extracted_query))
            
            # Proper way to convert SQLAlchemy result to dictionary
            column_names = result.keys()
            result_dict = [
                {column: value for column, value in zip(column_names, row)}
                for row in result.fetchall()
            ]
            answer = agent_answer.run(
            f"Generate a professional human understandable answer using: {result_dict} for the question {prompt}"
         
            )
            
            return jsonify({
                "query": extracted_query,
                "result": result_dict,
                "row_count": len(result_dict),
                "answer":answer.content
            })
            
        except Exception as e:
            return jsonify({
                "error": f"Query execution failed: {str(e)}", 
                "query": extracted_query
            }), 400

    except Exception as e:
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(debug=True)
