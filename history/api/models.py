# -*- coding: utf-8 -*-
"""
Exposes device information using dojot's modelling
"""
import json
import base64
import re
import dateutil.parser
import falcon
import pymongo
import requests
from history import conf, Logger

logger = Logger.Log(conf.log_level).color_log()


class AuthMiddleware(object):
    """
        Middleware used to populate context with relevant JWT-sourced information.
        Also used to validate and refuse requests that do not contain valid tokens associated
        with them.
    """     

    def process_request(self, req, resp):
        logger.debug('AuthMiddleware.process_request [start]')

        challenges = ['Token type="JWT"']
        token = req.get_header('authorization')
        if token is None:
            description = 'Please provide an auth token as part of the request.'
            logger.debug('Authentication required ' + description)
            raise falcon.HTTPUnauthorized('Authentication required', description, challenges)

        req.context['related_service'] = self._parse_token(token)
        if req.context['related_service'] is None:
            description = ('The provided auth token is not valid. '
                           'Please request a new token and try again.')
            logger.debug('Authentication required ' + description)
            raise falcon.HTTPUnauthorized('Authentication required', description, challenges)

        logger.debug('AuthMiddleware.process_request [passed]')

    @staticmethod
    def _decode_base64(data):
        """
            Decode base64, padding being optional.
            :param data: Base64 data as an ASCII byte string
            :returns: The decoded byte string.
        """
        missing_padding = len(data) % 4
        if missing_padding != 0:
            data += '=' * (4 - missing_padding)
        return base64.decodestring(data.encode('utf-8'))

    def _parse_token(self, token):
        """
            Parses the authorization token, returning the service to be used as tenant id

            :param token: JWT token to be parsed
            :returns: Service to be used on API calls, or None if token is invalid
        """
        if not token or len(token) == 0:
            return None

        payload = token.split('.')[1]
        try:
            data = json.loads(AuthMiddleware._decode_base64(payload))
            return data['service']
        except Exception as exception:
            logger.error(exception)
            return None


class HistoryUtil(object):

    db = pymongo.MongoClient(conf.db_host, replicaSet=conf.db_replica_set)

    @staticmethod
    def get_db():
        return HistoryUtil.db['device_history']

    @staticmethod
    def get_collection(service, item):
        db = HistoryUtil.get_db()
        collection_name = "%s_%s" % (service, item)
        if collection_name in db.collection_names():
            return db["%s_%s" % (service, item)]
        else:
            raise falcon.HTTPNotFound(title="Device not found",
                                      description="No data for the given device could be found")
    
    @staticmethod
    def check_type(arg):
        logger.debug(arg)
        res = re.search(r'^".*"$', arg)
        if res:  # its a string
            return "string"
        return "int"

    @staticmethod
    def model_value(value, type_arg):
        if type_arg == "int":
            return int(value)
        elif type_arg == "string":
            ret = ""
            for l in value:
                if l != '"':
                    ret = ret + l
            return ret


class DeviceHistory(object):
    """Service used to retrieve a given device historical data"""

    @staticmethod
    def parse_request(request, attr):
        """ returns mongo compatible query object, based on the query params provided """
        logger.debug('DeviceHistory.parse_request [start]')

        limit_val = False
        sort = [('ts', pymongo.DESCENDING)]

        if 'firstN' in request.params.keys():
            try:
                limit_val = int(request.params['firstN'])
                sort = [('ts', pymongo.ASCENDING)]
            except ValueError as e:
                logger.error(e)
                raise falcon.HTTPInvalidParam('Must be integer.', 'firstN')
        elif 'lastN' in request.params.keys():
            try:
                limit_val = int(request.params['lastN'])
            except ValueError as e:
                logger.error(e)
                raise falcon.HTTPInvalidParam('Must be integer.', 'lastN')
        elif 'hLimit' in request.params.keys():
            try:
                limit_val = int(request.params['hLimit'])
            except ValueError as e:
                logger.error(e)
                raise falcon.HTTPInvalidParam('Must be integer.', 'hLimit')

        if attr:
            query = {'attr': attr, 'value': {'$ne': ' '}}

        ts_filter = {}
        if 'dateFrom' in request.params.keys():
            ts_filter['$gte'] = dateutil.parser.parse(request.params['dateFrom'])
        if 'dateTo' in request.params.keys():
            ts_filter['$lte'] = dateutil.parser.parse(request.params['dateTo'])
        if len(ts_filter.keys()) > 0:
            query['ts'] = ts_filter

        ls_filter = {"_id": False, '@timestamp': False, '@version': False}
        req = {'query': query, 'limit': limit_val, 'filter': ls_filter, 'sort': sort}

        logger.debug('DeviceHistory.parse_request [return]')
        logger.debug(req)

        return req

    @staticmethod
    def get_attrs(device_id, token):
        """Requests infos of the device to device-manager then get all the attrs related to the device"""
        logger.debug('DeviceHistory.get_attrs [start]')

        response = requests.get(conf.device_manager_url+'/device/'+device_id, headers={'Authorization': token})
        attrs_list = []
        json_data = json.loads(response.text)

        for k in json_data['attrs']:
            for d in json_data['attrs'][k]:
                if 'label' in d:
                    attrs_list.append(d['label'])

        logger.debug('DeviceHistory.get_attrs [return]')
        logger.debug(attrs_list)

        return attrs_list

    @staticmethod
    def get_single_attr(collection, query):
        logger.debug('DeviceHistory.get_single_attr [start]')

        cursor = collection.find(query['query'],
                                 query['filter'],
                                 sort=query['sort'],
                                 limit=query['limit'])
        history = []
        for d in cursor:
            d['ts'] = d['ts'].isoformat() + 'Z'
            history.append(d)

        logger.debug('DeviceHistory.get_single_attr [return]')
        logger.debug(history)

        return history
        
    @staticmethod
    def on_get(req, resp, device_id):
        logger.debug('DeviceHistory.on_get [start]')

        collection = HistoryUtil.get_collection(req.context['related_service'], device_id)

        if 'attr' in req.params.keys():
            if isinstance(req.params['attr'], list):
                logger.info('got list of attrs')
                history = {}
                for attr in req.params['attr']:
                    query = DeviceHistory.parse_request(req, attr)
                    history[attr] = DeviceHistory.get_single_attr(collection, query)
            else:
                logger.info('got single attr')
                history = DeviceHistory.get_single_attr(
                    collection, DeviceHistory.parse_request(req, req.params['attr']))
                if len(history) == 0:
                    msg = "No data for the given attribute could be found"
                    raise falcon.HTTPNotFound(title="Attr not found", description=msg)
        else:
            logger.info('will return all the attrs')
            history = {}
            token = req.get_header('authorization')
            attrs_list = DeviceHistory.get_attrs(device_id, token)
            for attr in attrs_list:
                query = DeviceHistory.parse_request(req, attr)
                history[attr] = DeviceHistory.get_single_attr(collection, query)

        logger.debug('DeviceHistory.on_get [return]')
        logger.debug(history)

        resp.status = falcon.HTTP_200
        resp.body = json.dumps(history)


class NotificationHistory(object):

    @staticmethod
    def on_get(req, resp):
        """
        Handles get method
        """
        logger.debug('NotificationHistory.on_get [start]')

        collection = HistoryUtil.get_collection(req.context['related_service'], "notifications")
        history = {}
        logger.info("Will retrieve notifications")
        filter_query = req.params
        query = NotificationHistory.get_query(filter_query)      
        history['notifications'] = NotificationHistory.get_notifications(collection, query)

        logger.debug('NotificationHistory.on_get [return]')
        logger.debug(history)

        resp.status = falcon.HTTP_200
        resp.body = json.dumps(history)

    @staticmethod
    def get_query(filter_query):
        logger.debug('NotificationHistory.get_query [start]')

        query = {}
        if filter_query:
            for field in filter_query.keys():
                value = filter_query[field]

                if field != "subject":
                    field = "metaAttrsFilter." + field
                
                value = HistoryUtil.model_value(value, HistoryUtil.check_type(value))
                query[field] = value 

        sort = [('ts', pymongo.DESCENDING)]
        ls_filter = {"_id": False, '@timestamp': False, '@version': False}

        result = {"query": query, "limit_val": 10, "sort": sort, "filter": ls_filter}

        logger.debug('NotificationHistory.get_query [return]')
        logger.debug(result)

        return result
    
    @staticmethod
    def get_notifications(collection, query):
        logger.debug('NotificationHistory.get_notifications [start]')

        docs = collection.find(query['query'], query['filter'], limit=query['limit_val'], sort=query['sort'])

        history = []
        for d in docs:
            d['ts'] = d['ts'].isoformat() + 'Z'
            history.append(d)

        logger.debug('NotificationHistory.get_notifications [return]')
        logger.debug(history)

        return history


class STHHistory(object):
    """ Deprecated: implements STH's NGSI-like historical view of data """

    @staticmethod
    def on_get(req, resp, device_type, device_id, attr):
        logger.debug('STHHistory.on_get [start]')

        collection = HistoryUtil.get_collection(req.context['related_service'], device_id)

        query = DeviceHistory.parse_request(req, attr)
        cursor = collection.find(query['query'],
                                 query['filter'],
                                 sort=query['sort'],
                                 limit=query['limit'])
        history = []
        for d in cursor:
            history.insert(0, {
                "attrType": device_type,
                "attrValue": d['value'],
                "recvTime": d['ts'].isoformat() + 'Z'
            })

        ngsi_body = {
            "contextResponses": [
                {
                    "contextElement": {
                        "attributes": [{
                            "name": attr,
                            "values": history
                        }],
                        "id": device_id,
                        "isPattern": False,
                        "type": device_type
                    },
                    "statusCode": {"code": "200", "reasonPhrase": "OK"}
                }
            ]
        }

        logger.debug('STHHistory.on_get [return]')
        logger.debug(ngsi_body)

        resp.status = falcon.HTTP_200
        resp.body = json.dumps(ngsi_body)


class LoggingInterface(object):
    """ Retreives and sets value of the logger variable """
    @staticmethod
    def on_get(req, resp):
        logger.debug('LoggingInterface.on_get [start]')

        response = {"log_level": Logger.Log.levelToName[logger.level]}

        logger.debug('LoggingInterface.on_get [return]')
        logger.debug(response)

        resp.body = json.dumps(response)
        resp.status = falcon.HTTP_200

    @staticmethod
    def on_put(req, resp):
        if 'level' in req.params.keys() and req.params['level'].upper() in Logger.Log.levelToName.values():

            logger.setLevel(req.params['level'].upper())
            for handler in logger.handlers:
                handler.setLevel(req.params['level'].upper())

            response = {"new_log_level": Logger.Log.levelToName[logger.level]}
            resp.body = json.dumps(response)
            resp.status = falcon.HTTP_200
        else:
            raise falcon.HTTPInvalidParam('Logging level must be DEBUG, INFO, WARNING, ERROR or CRITICAL!', 'level')
