
from flask import Flask, jsonify, request, render_template

app = Flask(__name__)


@app.route("/")
def home():
    return jsonify({
        "service": "Unit Converter",
        "status": "running"
    }), 200

#http://127.0.0.1:5000/temp?value=0&from=C&to=F
#http://127.0.0.1:5000/temp?value=32&from=F&to=C
@app.route("/temp")
def temperature():
    value = request.args.get("value")
    from_unit = request.args.get("from")
    to_unit = request.args.get("to")

    # make sure given vals
    if value is None or from_unit is None or to_unit is None:
        return jsonify({
            "error": "value, from, and to are required"
        }), 400

    #get vals
    try:
        value = float(value)
    except ValueError:
        return jsonify({
            "error": "value must be a number"
        }), 400

    # C to F
    if from_unit == "C" and to_unit == "F":
        result = (value * 9 / 5) + 32

    # F to C
    elif from_unit == "F" and to_unit == "C":
        result = (value - 32) * 5 / 9

    else:
        return jsonify({
            "error": "conversion must be C to F or F to C"
        }), 400

    return jsonify({
        "value": value,
        "from": from_unit,
        "to": to_unit,
        "result": round(result, 2)
    })

@app.route("/docs")
def docs():
    return render_template("docs.html")



if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)