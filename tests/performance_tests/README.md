# Persister Performance Test

## Description

This script analyses the average delay to send a message through dojot.

It first verifies the number of messages that arrived in kafka and the number of messages that were saved in mongodb.
By doing this it checks if any message was lost inside dojot.

Then it uses mqtt-beamer to create messages with timestamp t1 and sends them to dojot's iotagent-mqtt.
And just before saving a message in dojot's persister mongodb, it attaches a new timestamp t2 to it.

Then it compares the difference t2-t1 to compute the average travel delay inside dojot for all messages.

## Dependencies

This script uses:

- mqtt-beamer: https://github.com/giovannicuriel/mqtt-beamer
- kafka source download: https://kafka.apache.org/downloads
- python3 libraries: requirements.txt

## Observations

- To use this script you should apply the persister's source code to the deployment. The file [kafkaSubscriber.py] is found in this directory. To do this you may take as an example the docker-compose.yml file located here.
- You can change the file locations for mqtt-beamer and kafka binaries used.
- This script will delete all documents and collections saved in mongodb's device_history database.
- Use a adequate time for sleeping so mongodb can persist all the messages in time.

## To do

- Create and get devices from dojot instead of passing a device id as argument
