from flask import Flask
import json
app = Flask(__name__)

resp_json = {
    "attrs": {
        "1": [
            {
                "created": "2018-08-02T12:52:14.569559+00:00",
                "id": 1,
                "label": "temperature",
                "static_value": "",
                "template_id": "1",
                "type": "dynamic",
                "value_type": "float"
            },
            {
                "created": "2018-08-02T12:52:14.605001+00:00",
                "id": 4,
                "label": "protocol",
                "static_value": "MQTT",
                "template_id": "1",
                "type": "meta",
                "value_type": "string"
            },
            {
                "created": "2018-08-02T12:52:14.569559+00:00",
                "id": 5,
                "label": "pressure",
                "static_value": "",
                "template_id": "1",
                "type": "dynamic",
                "value_type": "float"
            },
        ]
    },
    "created": "2018-08-02T12:52:29.310182+00:00",
    "id": "b374a5",
    "label": "MyAwesomeDevice",
    "templates": [
        1
    ]
}
@app.route('/device/<device_id>')
def get_device(device_id):
    return json.dumps(resp_json)
