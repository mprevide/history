import dredd_hooks as hooks
import json

from history.subscriber.persister import Persister


@hooks.before_each
def setup(transaction):

    _create_device = {
        "event": "create",
        "meta": {
            "service": "admin"
        },
        "data": {
            "id": "b374a5",
            "label": "Device 1",
            "templates": [1, 2, 3],
            "attrs": {
            },
            "created": "2018-02-06T10:43:40.890330+00:00"
        }
    }
    persister = Persister()
    persister.init_mongodb()
    persister.handle_event_devices("admin", json.dumps(_create_device))

    _update_data = {
        "metadata": {
            "deviceid": "b374a5",
            "protocol": "mqtt",
            "payload": "json",
            "timestamp": 1528226137452
        },
        "attrs": {
            "temperature": "22.12"
        }
    }
    persister.handle_event_data("admin", json.dumps(_update_data))

    _update_data['attrs']['temperature'] = "23.12"
    persister.handle_event_data("admin", json.dumps(_update_data))

    _new_tenant = {
        "tenant": "admin"
    }

    persister.handle_new_tenant("admin", json.dumps(_new_tenant))

    _notification = {
        "msgID": "12345",
        "timestamp": 1551111524,
        "metaAttrsFilter": {
            "level": 1,
            "shouldPersist": "True"
        },
        "message": "Something went wrong.",
        "subject": "user_notification",
    }

    persister.handle_notification("admin", json.dumps(_notification))
