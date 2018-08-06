from __future__ import division
import base64
import logging
import json
import time
from datetime import datetime
from dateutil.parser import parse
from multiprocessing import Process, active_children

import requests
from kafka import KafkaConsumer
from kafka.errors import KafkaTimeoutError
import pymongo

from history import conf

LOGGER = logging.getLogger('history.' + __name__)
LOGGER.addHandler(logging.StreamHandler())
LOGGER.setLevel(logging.INFO)

class ConfigurationError(Exception):
    pass


class KafkaEventHandler(object):
    """
        Base callback structure for kafka events callbacks
    """
    def handle_event(self, message):
        """
            Handles a given kafka received message
            :param message The message that has been received
        """
        raise NotImplementedError("Abstract method called")

class TenancyHandler(KafkaEventHandler):

    def __init__(self):
        pass

    @staticmethod
    def _spawn_watcher(service, subject, handler):
        topic = get_topic(service, subject)
        watcher = KafkaListener(topic, handler, name=(subject + "-watcher"))
        watcher.start()
        return watcher

    def tenants_bootstrap(self):
        LOGGER.debug('will bootstrap')
        target = "{}/admin/tenants".format(conf.auth_url)
        response = requests.get(target, timeout=3)
        if 200 <= response.status_code < 300:
            payload = response.json()
            LOGGER.debug('Got list of tenants %s', payload)
            for tenant in payload['tenants']:
                LOGGER.debug('initializing tenant %s', tenant)
                TenancyHandler._spawn_watcher(tenant, conf.dojot_subject_device, DeviceHandler())
                TenancyHandler._spawn_watcher(tenant, conf.dojot_subject_device_data, DataHandler(tenant))
        else:
            LOGGER.error('Failed to retrieve list of existing tenants (%d)', response.status_code)
            exit(1)

        return None

    def handle_event(self, message):
        """
            Given a tenancy livecyle event, spawn the needed consumers to hanle its data
            :param message Tenant lifecyle message as produced by Auth
        """
        data = json.loads(message)
        LOGGER.debug('got tenancy event for tenant: %s', data['tenant'])

        tenant = data['tenant']
        TenancyHandler._spawn_watcher(tenant, conf.dojot_subject_device, DeviceHandler())
        TenancyHandler._spawn_watcher(tenant, conf.dojot_subject_device_data, DataHandler(tenant))


class DeviceHandler(KafkaEventHandler):
    def __init__(self):
        self.db = None

    def handle_event(self, message):
        """
            Given a device management event, create (if not alredy existent) proper indexes
            to suppor the new device
            :param message Device lifecyle message, as produced by device manager
        """
        data = json.loads(message)
        LOGGER.debug('got device event %s', message)

        if self.db is None:
            self.db = pymongo.MongoClient(conf.db_host, replicaSet=conf.db_replica_set)
            self.db = self.db['device_history']

        collection_name = "{}_{}".format(data['meta']['service'], data['data']['id'])
        self.db[collection_name].create_index([('ts', pymongo.DESCENDING),
                                               ('attr', pymongo.DESCENDING)],
                                              unique=True)
        self.db[collection_name].create_index('ts', expireAfterSeconds=conf.db_expiration)


class DataHandler(KafkaEventHandler):
    def __init__(self, service):
        self.service = service
        self.db = None

    def _get_collection(self, message):
        if self.db is None:
            self.db = pymongo.MongoClient(conf.db_host, replicaSet=conf.db_replica_set)
        collection_name = "{}_{}".format(self.service, message['metadata']['deviceid'])
        return self.db['device_history'][collection_name]

    @staticmethod
    def parse_datetime(timestamp=None):
        if timestamp is None:
            return datetime.utcnow()

        try:
            val = int(timestamp)
            if timestamp > ((2**31)-1):
                return datetime.utcfromtimestamp(val/1000)
            else:
                return datetime.utcfromtimestamp(float(timestamp))
        except ValueError as error:
            LOGGER.error("Failed to parse timestamp ({})\n{}".format(timestamp, error))

        try:
            return datetime.utcfromtimestamp(float(timestamp)/1000)
        except ValueError as error:
            LOGGER.error("Failed to parse timestamp ({})\n{}".format(timestamp, error))

        try:
            return parse(timestamp)
        except TypeError as error:
            raise TypeError('Timestamp could not be parsed: {}\n{}'.format(timestamp, error))


    def handle_event(self, message):
        """
            Given a device data event, persist it to mongo
            :param message A device data event
        """
        data = None
        try:
            data = json.loads(message)
        except Exception as error:
            LOGGER.error('Received event is not valid JSON. Ignoring\n%s', error)
            return

        LOGGER.debug('got data event %s', message)

        metadata = data.get('metadata', None)
        if metadata is None:
            LOGGER.error('Received event has no metadata associated with it. Ignoring')
            return
        device_id = metadata.get('deviceid', None)
        if device_id is None:
            LOGGER.error('Received event cannot be traced to a valid device. Ignoring')
            return

        # timestamp of when data was sent from device
        timestamp = DataHandler.parse_datetime(metadata.get('timestamp', None))

        docs = []
        for attr in data.get('attrs', {}).keys():
            docs.append({
                'attr': attr,
                'value': data['attrs'][attr],
                'device_id': device_id,
                'ts': timestamp
            })

        # Persist device status history as well
        device_status = metadata.get('status', None)
        if device_status is not None:
            docs.append({
                'status': device_status,
                'device_id': device_id,
                'ts': timestamp
            })

        if len(docs) > 0:
            try:
                # timestamp of when data was saved to db
                saved_timestamp = DataHandler.parse_datetime()
                for d in docs:
                    d['saved_ts'] = saved_timestamp
                mongo = self._get_collection(data)
                mongo.insert_many(docs)
            except Exception as error:
                LOGGER.warn('Failed to persist received information.\n%s', error)
        else:
            LOGGER.info('Got empty event from device [%s] - ignoring', device_id)


class KafkaListener(Process):
    """
        Threaded abstraction for a kafka consumer
    """

    def __init__(self, topic, callback, name=None):
        """
            Constructor.
            :param callback Who to call when a new message arrives. Must be an instance of
                            KafkaEventHandler
        """
        Process.__init__(self, name=name)

        self.topic = topic
        self.broker = [conf.kafka_host]
        self.group_id = conf.kafka_group_id
        self.consumer = None

        # Callback must be of type KafkaEventHandler
        self.callback = callback

    def wait_init(self):
        done = False
        while not done:
            try:
                # make sure we process initial partition assignment messages
                self.consumer.poll()
                self.consumer.seek_to_end()
                done = True
            except AssertionError as error:
                LOGGER.debug('ignoring assertion error [%s] %s', self.topic, error)
                # give kafka some time to assign us a partition
                time.sleep(1)


    def run(self):
        start = time.time()
        LOGGER.info('will create consumer %s %s %s', self.broker, self.group_id, self.topic)
        self.consumer = KafkaConsumer(bootstrap_servers=self.broker, group_id=self.group_id)
        self.consumer.subscribe(topics=[self.topic])
        self.wait_init()
        LOGGER.info('kafka consumer created %s - %s', self.topic, time.time() - start)
        for message in self.consumer:
            start = time.time()
            LOGGER.debug("Got kafka event [%s] %s", self.topic, message)
            try:
                self.callback.handle_event(message.value)
            except Exception as error:
                LOGGER.warn('Data handler raised an unknown exception. Ignoring. \n%s', error)

            LOGGER.debug('done %s', time.time() - start)


def _get_token(service):
    """
        Given a service, return an internal token, for usage with data-broker
        :param service          Service (tenancy context) whoose subject topic is to be retrieved
        :return string          JWT token (internal)
    """
    userinfo = {
        "username": "history",
        "service": service
    }

    return "{}.{}.{}".format(base64.b64encode("model"),
                             base64.b64encode(json.dumps(userinfo)),
                             base64.b64encode("signature"))

def get_topic(service, subject, global_subject=False):
    """
        Given a service and a subject, retrieve its associated kakfa topic
        :param  service             Service (tenancy context) whoose subject topic is to be
                                    retrieved
        :param  subject             Subject that is to be retrieved
        :param  global_subject      Whether the subject is not attached to any specific tenant
        :raises ConfigurationError  If broker could not be reached
    """
    start = time.time()
    opts = "?global=true" if global_subject else ""
    target = "{}/topic/{}{}".format(conf.data_broker_url, subject, opts)
    jwt = _get_token(service)
    response = requests.get(target, headers={"authorization": jwt}, timeout=3)
    if 200 <= response.status_code < 300:
        payload = response.json()
        LOGGER.debug('topic acquisition took %s [%s]', time.time() - start, payload['topic'])
        return payload['topic']

    raise ConfigurationError("Topic retrieval error: {} {}".format(response.status_code,
                                                                   response.reason))

if __name__ == '__main__':
    # Spawns tenancy management thread
    try:
        tenancy_topic = get_topic(conf.dojot_service_management, conf.dojot_subject_tenancy, True)
        handler = TenancyHandler()
        tenant_watcher = KafkaListener(tenancy_topic, handler, name="tenancy-watcher")
        tenant_watcher.start()
        handler.tenants_bootstrap()
        tenant_watcher.join()
    except Exception as error:
        children = active_children()
        for child in children:
            LOGGER.warn("Terminating [{}] ...".format(child.name))
            child.terminate()
        LOGGER.error("Failed to bootstrap tenants's consumers:\n{}".format(error))
        LOGGER.critical("Exiting.")
        exit(1)
