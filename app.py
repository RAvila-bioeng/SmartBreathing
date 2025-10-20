from flask import Flask, render_template, jsonify, request
import random

app = Flask(__name__, template_folder="frontend")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/routine/current')
def routine():
    routine_data = {
        "name": "Rutina de respiración guiada",
        "duration": 30,
        "intensity": "Moderada",
        "nextExercise": "Inhalación profunda"
    }
    return jsonify(routine_data)

@app.route('/submit', methods=['POST'])
def submit():
    # Print form data to console
    print("=== Form Data Received ===")
    for key, value in request.form.items():
        print(f"{key}: {value}")
    print("=========================")
    
    # Return a simple response
    return jsonify({"status": "success", "message": "Data received"})

@app.route('/api/metrics')
def metrics():
    metrics_data = {
        "spo2": round(random.uniform(95, 100), 1),
        "co2": round(random.uniform(400, 600), 1),
        "hr": round(random.uniform(60, 100), 1)
    }
    return jsonify(metrics_data)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
