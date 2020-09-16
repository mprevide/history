# dojot History service

This service handles all operations related to persisting and retrieving historical device
data. For more information about the usage, check the [API documentation](https://dojot.github.io/history/apiary_latest.html).

## About History

The history service is used when a device historical data needs to be retrieved, but it can also be utilized via HTTP request
employing different filters, like deviceId, number of entries to be listed and starting date, as in the following example:

```shell
http://host:port/device/{device_id}/history?lastN|firstN={lastN|firstN}&attr={attr}&dateFrom={dateFrom}&dateTo={dateTo}
```

### Dependencies

- [falcon](https://falconframework.org/)
- [gunicorn](https://gunicorn.org/)
- [gevent](http://www.gevent.org/)
- [python-dateutil](https://pypi.org/project/python-dateutil/1.4/)


### Configuration

In order to properly start History, the following variables must be set. All
values are the default ones, and they need to be modified to the respective services' address.

Key                         | Purpose                                                      | Default Value
----------------------------|--------------------------------------------------------------|----------------
HISTORY_DB_ADDRESS          |History database's address                                    |"mongodb"
HISTORY_DB_PORT             |History database's port                                       |27017
HISTORY_DB_REPLICA_SET      |History database's replica set address                        |None
AUTH_URL                    |Auth url address                                              |"http://auth:5000"
LOG_LEVEL                   |Define minimum logging level                                  |"INFO"

### How to install

#### Standalone setup

As this service is written in **Python 2.7**, it is recommended that all packages are
installed within a [virtual environment](https://github.com/pypa/virtualenv).
It can be created by:

```shell
virtualenv ./venv
source ./venv/bin/activate
```

Which will create a `venv` folder in current directory and install
basic Python packages there. The second command will set all environment
variables so that new Python packages are installed there as well.

To install all dependencies from Auth, execute the following commands.

```shell
# you may need sudo for those
apt-get install -y python-pip versiontools
# There is a package that is not in PyPI
pip install -r ./requirements/requirements.txt
python setup.py install
```

The last command will generate a .egg file and install it into your virtual
environment.

#### Docker Setup

Another alternative is to use **docker** to run the service. To build the
container, from the repository's root:

```shell
# you may need sudo on your machine:
# https://docs.docker.com/engine/installation/linux/linux-postinstall/
docker build -t <tag-for-history-docker> -f docker/history.docker .
```
### How to run the service

To run the standalone history service, just set all needed environment variables and execute:

```bash
./docker/falcon-docker-entrypoint.sh start
```

To run the service on docker, you can use:
```shell
# may need sudo to run
docker run -i -t <tag-for-history-docker>
```
### API

The API documentation for this service is written as API blueprints.
To generate a simple web page from it, one may run the commands below.

```shell
npm install -g aglio # you may need sudo for this

# static webpage
aglio -i docs/history.apib -o docs/history.html

# serve apis locally
aglio -i docs/history.apib -s
```

### Tests

History has some automated test scripts. We use [Dredd]
(<http://dredd.org/en/latest/>) to execute them.


## About Persister

The persister, as the name suggests, is the responsible for the persistence of the data sent from devices.

### Dependencies

- [falcon](https://falconframework.org/)
- [gunicorn](https://gunicorn.org/)
- [gevent](http://www.gevent.org/)
- [python-dateutil](https://pypi.org/project/python-dateutil/1.4/)
- [pymongo](https://pypi.org/project/pymongo/)

The setup of these dependencies are described in the following section.

### Configuration

In order to properly start Persister, the following variables must be set. All
values are the default ones, and they need to be modified to the services' address.

Key                         | Purpose                                                      | Default Value
----------------------------|--------------------------------------------------------------|----------------
HISTORY_DB_ADDRESS          |History database's address                                    |"mongodb"
HISTORY_DB_PORT             |History database's port                                       |27017
HISTORY_DB_REPLICA_SET      |History database's replica set address                        |None
HISTORY_DB_DATA_EXPIRATION  |Seconds before removing an entry in MongoDB                   |604800
MONGO_SHARD                 |Activate the use of sharding or not                           |False
AUTH_URL                    |Auth url address                                              |"http://auth:5000"
KAFKA_ADDRESS               |Kafta address                                                 |"kafka"
KAFKA_PORT                  |Kafka port                                                    |9092
KAFKA_HOSTS                 |KAFKA_ADDRESS concatenated with KAFKA_PORT                    |"kafka:9092"
KAFKA_GROUP_ID              |Group ID used when creating consumers                         |"history"
DATA_BROKER_URL             |Data Broker address                                           |"http://data-broker"
DEVICE_MANAGER_URL          |Device Manager address                                        |"http://device-manager:5000"
DOJOT_SUBJECT_TENANCY       |Global subject to use when publishing tenancy lifecycle events|"dojot.tenancy"
DOJOT_SUBJECT_DEVICES       |Global subject to use when receiving device lifecycle events  |"dojot.device-manager.device"
DOJOT_SUBJECT_DEVICE_DATA   |Global subject to use when receiving data from devices        |"device-data"
DOJOT_SERVICE_MANAGEMENT    |Global service to use when publishing dojot management events |"dojot-management"
LOG_LEVEL                   |Define minimum logging level                                  |"INFO"
PERSISTER_PORT              |Port to be used by persister sevice's endpoints               |8057


### How to install the service

### Standalone setup

It is recommended that all packages are
installed within a [virtual environment](https://github.com/pypa/virtualenv).
It can be created by:

```shell
virtualenv ./venv
source ./venv/bin/activate
```

Which will create a `venv` folder in current directory and install
basic Python packages there. The second command will set all environment
variables so that new Python packages are installed there as well.

To install all dependencies from Auth, execute the following commands.

```shell
# you may need sudo for those
apt-get install -y python-pip versiontools
# There is a package that is not in PyPI
pip install -r ./requirements/requirements.txt
python setup.py install
```

The last command will generate a .egg file and install it into your virtual
environment.

#### Running the persistent service

To run the Persistent, after setting the environment variables, execute:

```bash
python -m history.subscriber.persister
```

### Docker setup

Another alternative is to use **docker** to run the service. To build the
container, from the repository's root:

```shell
# you may need sudo on your machine:
# https://docs.docker.com/engine/installation/linux/linux-postinstall/
docker build -t <tag-for-persister-docker> -f docker/persister.docker .
```
You can run the built containers using the following commands:

```shell
# may need sudo to run
docker run -i -t <tag-for-persister-docker>
```