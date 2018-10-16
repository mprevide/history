import subprocess
import threading
import argparse
import json
import time
import re

import numpy as np
import requests
import pymongo

def execute(cmd):
    out = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    stdout, stderr = out.communicate()
    if stdout:
        return stdout
    elif stderr:
        return 'ERROR: %s' % stderr
    return 'Unknown error in executing bash command'

def to_str(s):
    try:
        s = s.decode('utf8').strip()
    except AttributeError:
        pass
    try:
        return json.loads(s)
    except:
        return s

def get_kafka_messages(KAFKA_ENDPOINT, TOPIC):
    return re.sub(r'.*:', '', to_str(execute('kafka/bin/kafka-run-class.sh kafka.tools.GetOffsetShell --broker-list ' + KAFKA_ENDPOINT + ' --topic ' + TOPIC + ' --time -1')))

def delete_messages_mongodb(db):
    collections = db.list_collection_names()
    for coll in collections:
        db[coll].delete_many({'_id':{'$ne':0}})

def main(tenant, messages, frequency, deviceid, n_threads, sleep):
    print('starting...')
    KAFKA_ENDPOINT = to_str(execute('docker inspect -f "{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}" dojot_kafka_1')) + ':9092'

    MONGODB_ENDPOINT = to_str(execute('docker inspect -f "{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}" dojot_mongodb_1'))

    DATA_BROKER_ENDPOINT = to_str(execute('docker inspect -f "{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}" dojot_data-broker_1'))

    JWT = to_str(execute('node token.js'))

    TOPIC = to_str(requests.get('http://' + DATA_BROKER_ENDPOINT + '/topic/device-data', headers={'Authorization': 'Bearer ' + JWT}).text)['topic']

    db = pymongo.MongoClient(MONGODB_ENDPOINT, 27017).device_history
    delete_messages_mongodb(db)

    print('checking kafka topics')
    kafka_messages = get_kafka_messages(KAFKA_ENDPOINT, TOPIC)

    print('checking mongodb')
    mongo_messages = db.command('dbstats')['objects']

    cmd = './mqtt-beamer/src/mqtt-beamer %s %s %s %s' % (tenant, deviceid, int(frequency/n_threads), int(messages/n_threads))
    threads = []
    for i in range(n_threads):
        threads.append(threading.Thread(target=execute, args=[cmd]))
        
    for i in range(n_threads):
        print("sending messages %s/%s" % (i+1, n_threads))
        threads[i].start()

    for thread in threads:
        thread.join()

    print('waiting for mongodb to receive messages')
    execute('sleep %s' % sleep)

    print('checking kafka topics')
    kafka_messages_after = get_kafka_messages(KAFKA_ENDPOINT, TOPIC)

    print('checking mongodb')
    mongo_messages_after = db.command('dbstats')['objects']

    print('total messages received in kafka: %s' % (int(kafka_messages_after) - int(kafka_messages)))
    print('total messages received in mongodb: %s' % (mongo_messages_after - mongo_messages))

    s = 0
    delays = np.array([])
    collections = db.list_collection_names()
    for coll in collections:
        cursor = db[coll].find()
        for c in cursor:
            if 'attr' in c:
                delays = np.append(delays, c['saved_ts'] - c['value'])

    delays /= 1000 # converts to seconds
    print("average delay per message: %.4f ± %.4f s" % (np.average(delays), np.std(delays)))

def createArgsParser():
    parser = argparse.ArgumentParser()
    parser.add_argument('-t', '--tenant', default='admin', help="tenant of device")
    parser.add_argument('-m', '--messages', required=True, type=int, help="number of messages to send")
    parser.add_argument('-f', '--frequency', required=True, type=int, help='frequency to send messages')
    parser.add_argument('-d', '--deviceid', required=True, help='device id whose messages are being sent to')
    parser.add_argument('-n', '--threads', default=1, type=int, help='number of threads (devices) to send messages')
    parser.add_argument('-s', '--sleep', default=0, type=int, help='time to sleep')
    return parser.parse_args()

if __name__ == '__main__':
    args = createArgsParser()
    main(args.tenant, args.messages, args.frequency, args.deviceid, args.threads, args.sleep)
