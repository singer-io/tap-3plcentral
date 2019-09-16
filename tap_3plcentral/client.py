# Client Reference: https://github.com/dvdhinesh/python-tpl

import json
from datetime import datetime, timedelta

import urllib.parse
import base64
import backoff
import requests
import singer
from requests.exceptions import ConnectionError
from singer import metrics
from singer import utils

LOGGER = singer.get_logger()


class Server5xxError(Exception):
    pass

class TPLBaseError(Exception):
    """Generic base exception class for 3PLCentral"""
    pass


class TPLAPIError(TPLBaseError):
    """Raised when 3PLCentral returns fault code"""

    def __init__(self, msg, error_code=None, tpl_error_msg=''):
        """Initialize the API error.
        :param msg: HTTP status message returned by the server.
        :param error_code: HTTP status code returned by the server.
        :param tpl_error_msg: Custom error msg returned by the server.
        """
        self.msg = msg
        self.error_code = error_code
        self.tpl_error_msg = tpl_error_msg

    def __str__(self):
        """Include custom msg"""
        return repr(self.msg + self.tpl_error_msg)


class TPLClient(object):
    """Generic API for 3PLCentral"""

    def __init__(
        self,
        base_url='https://secure-wms.com',
        auth_path='AuthServer/api/Token',
        client_id=None,
        client_secret=None,
        tpl_key=None,
        grant_type='client_credentials',
        user_login_id=None,
        user_agent=None,
        session=None,
        verify_ssl=True):
        
        """
        Create an instance, get access token and update the headers
        :param base_url: base url to the 3PLCentral instance.
        :param auth_path: authentication service path.
        :param client_id: client id of 3PLCentral app user.
        :param client_secret: client secret key of 3PLCentral app user.
        :param tpl_key: WH specific 3PLCentral key.
        :param grant_type: by default 'client_credentials'.
        :param user_login_id: 3PLCentral user id.
        :param user_agent: agent-name <email@address.com>.
        :param session: pass a custom requests Session.
        :param verify_ssl: skip SSL validation.
        
        :Example:
            from tpl import TPLClient
            api = TPLClient(base_url, auth_path, client_id, client_secret, tpl_key,
                            grant_type, user_login_id, session, verify_ssl)
            api.get("orders", "13654")
            
            payload = {}
            api.post("orders", data=payload)
        """
        self.__base_url = base_url
        self.__auth_path = auth_path
        self.__client_id = client_id
        self.__client_secret = client_secret
        self.__tpl_key = tpl_key
        self.__grant_type = grant_type
        self.__user_login_id = user_login_id
        self.__user_agent = user_agent
        self.__verify_ssl = verify_ssl

        if session is None:
            self.client = requests.Session()
            response = self._get_access_token()
            headers = {
                "Authorization": "%s %s" % (response['token_type'], response['access_token']),
                "Content-Type": "application/hal+json",
                "User-Agent": self.__user_agent
            }
            self.client.headers.update(headers)
        else:
            self.client = session

    def __enter__(self):
        self._get_access_token()
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        self.client.close()

    @backoff.on_exception(backoff.expo,
                          Server5xxError,
                          max_tries=5,
                          factor=2)
    def _get_access_token(self):
        """Get access token from server and returns it.
        :return: access token from the server.
        """
        key_string = "%s:%s" % (self.__client_id, self.__client_secret)
        key_bytes = key_string.encode("utf-8")
        auth = base64.b64encode(key_bytes)
        authorization = 'Basic {}'.format(auth.decode('utf-8'))
        headers = {
            "Content-Type": "application/json",
            "Authorization": authorization,
            "User-Agent": self.__user_agent
        }
        data = {
            "grant_type": self.__grant_type,
            "tpl": "{%s}" % (self.__tpl_key,),
            "user_login_id": self.__user_login_id
        }
        return self.post(self.__auth_path, data=data, add_headers=headers)

    def _parse_error(self, content):
        """Take the content and return as it is.
        :param content: content returned by the 3PLCentral server as string.
        :return: content.
        """
        return content

    def _check_status_code(self, status_code, content):
        """Take the status code and check it.
        Throw an exception if the server didn't return 200 or 201 or 202 code.
        :param status_code: status code returned by the server.
        :param content: content returned by the server.
        :return: True or raise an exception TPLAPIError.
        """
        message_by_code = {
            400: 'Bad Request',
            401: 'Unauthorized',
            403: 'Forbidden',
            404: 'Not Found',
            412: 'Precondition failed',
            428: 'Precondition required',
            500: 'Internal Server Error',
        }

        if status_code in (200, 201, 202):
            return True
        elif status_code in message_by_code:
            tpl_error_msg = self._parse_error(content)
            raise TPLAPIError(
                message_by_code[status_code], status_code, tpl_error_msg=tpl_error_msg)
        else:
            tpl_error_msg = self._parse_error(content)
            raise TPLAPIError('Unknown error', status_code,
                           tpl_error_msg=tpl_error_msg)

    @backoff.on_exception(backoff.expo,
                          (Server5xxError, ConnectionError),
                          max_tries=5,
                          factor=2)
    @utils.ratelimit(400, 60)
    def _execute(self, url, method, data=None, add_headers=None, endpoint=None):
        """Perform the HTTP request and return the response back.
        :param url: full url to call.
        :param method: GET, POST.
        :param data: POST (add) only.
        :param add_headers: additional headers merged into instance's headers.
        :return: response in json format.
        """
        if add_headers is None:
            add_headers = {}

        if endpoint is None:
            endpoint = url

        LOGGER.info('URL = {}'.format(url))
        request_headers = self.client.headers.copy()
        request_headers.update(add_headers)
        with metrics.http_request_timer(endpoint) as timer:
            response = self.client.request(
                method,
                url,
                data=data,
                verify=self.__verify_ssl,
                headers=request_headers) 
            timer.tags[metrics.Tag.http_status_code] = response.status_code
            self._check_status_code(response.status_code, response.content)
        
        return response.json()

    def get(self, resource_path, resource_id=None, querystring=None, add_headers=None, endpoint=None):
        """Retrieve (GET) a resource.
        :param resource_path: path of resource to retrieve.
        :param resource_id: optional resource id to retrieve.
        :param querystring: optional RQL querystring.
        :param add_headers: additional headers merged into instance's headers.
        :return: response in json format.
        """
        if endpoint is None:
            endpoint = resource_path
        full_url = "%s/%s" % (self.__base_url, resource_path)
        if resource_id is not None:
            full_url += "/%s" % (resource_id,)
        if querystring is not None:
            full_url += "?%s" % (querystring,)
        response = self._execute(full_url, 'GET', add_headers=add_headers, endpoint=endpoint)
        return response
    

    def post(self, resource_path, data=None, add_headers=None, endpoint=None):
        """Add (POST) a resource.
        :param resource_path: path of resource to create.
        :param data: full payload as dict of new resource.
        :param add_headers: additional headers merged into instance's headers.
        :return: response in json format.
        """
        if endpoint is None:
            endpoint = resource_path
        if data is None:
            raise ValueError('Data Undefined.')
        full_url = "%s/%s" % (self.__base_url, resource_path)
        response = self._execute(full_url, 'POST', data=json.dumps(data), add_headers=add_headers, endpoint=endpoint)
        return response
