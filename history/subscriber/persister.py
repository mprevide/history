import base64
import json
import falcon
import time
import pymongo
from datetime import datetime
from dateutil.parser import parse
from history import conf, Logger
from dojot.module import Messenger, Config, Auth
from wsgiref import simple_server  # NOQA
import os

LOGGER = Logger.Log(conf.log_level).color_log()


class Persister:

    def __init__(self):
        self.db = None
        self.client = None

    def init_mongodb(self, collection_name=None):
        """
        MongoDB initialization

        :type collection_name: str
        :param collection_name: collection to create index
        """
        try:
            self.client = pymongo.MongoClient(
                conf.db_host, replicaSet=conf.db_replica_set)
            self.db = self.client['device_history']
            if collection_name:
                self.create_indexes(collection_name)
            LOGGER.info("db initialized")
        except Exception as error:
            LOGGER.warn("Could not init mongo db client: %s" % error)

    def create_indexes(self, collection_name):
        """
        Create index given a collection

        :type collection_name: str
        :param collection_name: collection to create index
        """
        self.db[collection_name].create_index([('ts', pymongo.DESCENDING)])
        self.db[collection_name].create_index(
            [('attr', pymongo.DESCENDING), ('ts', pymongo.DESCENDING)])
        self.db[collection_name].create_index(
            'ts', expireAfterSeconds=conf.db_expiration)

    def create_indexes_for_notifications(self, tenants):
        LOGGER.debug(f"Creating indexes for tenants: {tenants}")
        for tenant in tenants:
            self.create_index_for_tenant(tenant)

    def create_index_for_tenant(self, tenant):
        collection_name = "{}_{}".format(tenant, "notifications")
        self.create_indexes(collection_name)

    def enable_collection_sharding(self, collection_name):
        """
        Create index given a collection

        :type collection_name: str
        :param collection_name: collection to create index
        """
        self.db[collection_name].create_index([('attr', pymongo.HASHED)])
        self.client.admin.command('enableSharding', self.db.name)
        self.client.admin.command(
            'shardCollection', self.db[collection_name].full_name, key={'attr': 'hashed'})

    def parse_message(self, data):
        """
        Formats message to save in MongoDB

        :type data: dict
        :param data: data that will be parsed to a format
        """
        parsed_message = dict()
        parsed_message['attrs'] = data['data']['attrs']
        parsed_message['metadata'] = dict()

        if data['meta']['timestamp'] is None:
            parsed_message['metadata']['timestamp'] = int(time.time() * 1000)
        else:
            parsed_message['metadata']['timestamp'] = data['meta']['timestamp']

        parsed_message['metadata']['deviceid'] = data['data']['id']
        parsed_message['metadata']['tenant'] = data['meta']['service']
        LOGGER.info("new message is: %s" % parsed_message)
        return json.dumps(parsed_message)

    def parse_datetime(self, timestamp):
        """
        Parses date time

        :type timestamp: string
        :param timestamp: timestamp
        """
        if timestamp is None:
            return datetime.utcnow()
        try:
            val = int(timestamp)
            if timestamp > ((2**31)-1):
                return datetime.utcfromtimestamp(val/1000)
            return datetime.utcfromtimestamp(float(timestamp))
        except ValueError as error:
            LOGGER.error(
                "Failed to parse timestamp ({})\n{}".format(timestamp, error))
        try:
            return datetime.utcfromtimestamp(float(timestamp)/1000)
        except ValueError as error:
            LOGGER.error(
                "Failed to parse timestamp ({})\n{}".format(timestamp, error))
        try:
            return parse(timestamp)
        except TypeError as error:
            raise TypeError(
                'Timestamp could not be parsed: {}\n{}'.format(timestamp, error))

    def handle_event_data(self, tenant, message):
        """
            Given a device data event, persist it to mongo

            :type tenant: str
            :param tenant: tenant related to the event

            :type message: str
            :param message: A device data event
        """
        data = None
        try:
            data = json.loads(message)
            LOGGER.info("Received data: %s" % data)
        except Exception as error:
            LOGGER.error(
                'Received event is not valid JSON. Ignoring.\n%s', error)
            return
        LOGGER.debug('got data event %s', message)
        metadata = data.get('metadata', None)
        if metadata is None:
            LOGGER.error(
                'Received event has no metadata associated with it. Ignoring')
            return
        device_id = metadata.get('deviceid', None)
        if device_id is None:
            LOGGER.error(
                'Received event cannot be traced to a valid device. Ignoring')
            return
        attrs = data.get('attrs', None)
        if attrs is None:
            LOGGER.error(
                'Received event has no attrs associated with it. Ignoring')
            return
        del metadata['deviceid']
        timestamp = self.parse_datetime(metadata.get('timestamp', None))
        if "timestamp" in metadata:
            del metadata['timestamp']

        if metadata.get('tenant', None) != None:
            del metadata['tenant']
        docs = []
        if type(data["attrs"]) is dict:
            for attr in data.get('attrs', {}).keys():
                docs.append({
                    'attr': attr,
                    'value': data['attrs'][attr],
                    'device_id': device_id,
                    'ts': timestamp,
                    'metadata': metadata
                })
            if docs:
                try:
                    collection_name = "{}_{}".format(tenant, device_id)
                    self.db[collection_name].insert_many(docs)
                except Exception as error:
                    LOGGER.warn(
                        'Failed to persist received information.\n%s', error)
        else:
            LOGGER.warning(
                f"Expected attribute dictionary, got {type(data['attrs'])}")
            LOGGER.warning("Bailing out")

    def handle_event_devices(self, tenant, message):
        """
            Given a device management event, create (if not alredy existent) proper indexes
            to suppor the new device

            :type tenant: str
            :param tenant: tenant related to the event

            :type message: str
            :param message Device lifecyle message, as produced by device manager
        """
        try:
            data = json.loads(message)
            LOGGER.info('got device event %s', data)
            if data['event'] == 'create' or data['event'] == 'update':
                if "meta" in data and "data" in data:
                    collection_name = "{}_{}".format(
                        data['meta']['service'], data['data']['id'])
                    self.create_indexes(collection_name)
            elif data['event'] == 'configure':
                new_message = self.parse_message(data)
                self.handle_event_data(tenant, new_message)
        except Exception as error:
            LOGGER.warning('Failed to persist device event: %s', error)

    def handle_new_tenant(self, tenant, message):
        data = json.loads(message)
        new_tenant = data['tenant']
        LOGGER.debug(
            f"Received a new tenant: {new_tenant}. Will create index for it.")
        self.create_index_for_tenant(new_tenant)

    def handle_notification(self, tenant, message):
        try:
            notification = json.loads(message)
            LOGGER.debug(
                f"Received a notification: {notification}. Will check if it will be persisted.")
        except Exception as error:
            LOGGER.debug(f"Invalid JSON: {error}")
            return
        notification['ts'] = self.parse_datetime(notification.get("timestamp"))
        del notification['timestamp']
        if('shouldPersist' in notification['metaAttrsFilter']):
            if(notification['metaAttrsFilter']['shouldPersist']):
                LOGGER.debug("Notification should be persisted.")
                try:
                    collection_name = "{}_{}".format(tenant, "notifications")
                    self.db[collection_name].insert_one(notification)
                except Exception as error:
                    LOGGER.debug(f"Failed to persist notification:\n{error}")
            else:
                LOGGER.debug(
                    f"Notification should not be persisted. Discarding it.")
        else:
            LOGGER.debug(
                f"Notification should not be persisted. Discarding it.")


class LoggingInterface(object):
    @staticmethod
    def on_get(req, resp):
        """
        Returns the level attribute value of the LOGGER variable
        """
        response = {"log_level": Logger.Log.levelToName[LOGGER.level]}
        resp.body = json.dumps(response)
        resp.status = falcon.HTTP_200

    @staticmethod
    def on_put(req, resp):
        """
        Set a new value to the level attribute of the LOGGER variable
        """
        if 'level' in req.params.keys() and req.params['level'].upper() in Logger.Log.levelToName.values():
            LOGGER.setLevel(req.params['level'].upper())
            for handler in LOGGER.handlers:
                handler.setLevel(req.params['level'].upper())

            response = {"new_log_level": Logger.Log.levelToName[LOGGER.level]}
            resp.body = json.dumps(response)
            resp.status = falcon.HTTP_200
        else:
            raise falcon.HTTPInvalidParam(
                'Logging level must be DEBUG, INFO, WARNING, ERROR or CRITICAL!', 'level')


def main():
    """
    Main, inits mongo, messenger, create channels read channels for device
    and device-data topics and add callbacks to events related to that subjects
    """
    config = Config()
    auth = Auth(config)
    LOGGER.debug("Initializing persister...")
    persister = Persister()
    persister.init_mongodb()
    persister.create_indexes_for_notifications(auth.get_tenants())
    LOGGER.debug("... persister was successfully initialized.")
    LOGGER.debug("Initializing dojot messenger...")
    messenger = Messenger("Persister", config)
    messenger.init()
    messenger.create_channel(config.dojot['subjects']['devices'], "r")
    messenger.create_channel(config.dojot['subjects']['device_data'], "r")
    # TODO: add notifications to config on dojot-module-python
    messenger.create_channel("dojot.notifications", "r")
    messenger.on(config.dojot['subjects']['devices'],
                 "message", persister.handle_event_devices)
    messenger.on(config.dojot['subjects']['device_data'],
                 "message", persister.handle_event_data)
    messenger.on(config.dojot['subjects']['tenancy'],
                 "message", persister.handle_new_tenant)
    messenger.on("dojot.notifications", "message",
                 persister.handle_notification)
    LOGGER.debug("... dojot messenger was successfully initialized.")

    # Create falcon app
    app = falcon.API()
    app.add_route('/persister/log', LoggingInterface())
    httpd = simple_server.make_server(
        '0.0.0.0', os.environ.get("PERSISTER_PORT", 8057), app)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
