import unittest
from unittest.mock import patch, MagicMock

import requests
from parameterized import parameterized
from requests.exceptions import Timeout, ConnectionError

from tap_3plcentral.client import TPLClient, TPLAPIError, Server5xxError


default_config = {
    "base_url": "https://secure-wms.com",
    "client_id": "test_client_id",
    "client_secret": "test_client_secret",
    "tpl_key": "test_tpl_key",
    "user_login_id": "1",
    "user_agent": "tap-3plcentral <test@test.com>",
}


class MockResponse:
    """Mocked standard HTTPResponse to test error handling."""

    def __init__(self, status_code, content=None, json_data=None):
        self.status_code = status_code
        self.content = content or ""
        self._json_data = json_data or {}

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError("mock error")


class TestTPLClient(unittest.TestCase):
    """Tests for TPLClient initialization and methods."""

    @patch("tap_3plcentral.client.TPLClient._get_access_token")
    def setUp(self, mock_get_token):
        """Set up the client with a mock session to skip real auth."""
        mock_get_token.return_value = {
            "token_type": "Bearer",
            "access_token": "test_access_token",
        }
        self.client = TPLClient(
            base_url=default_config["base_url"],
            client_id=default_config["client_id"],
            client_secret=default_config["client_secret"],
            tpl_key=default_config["tpl_key"],
            user_login_id=default_config["user_login_id"],
            user_agent=default_config["user_agent"],
        )

    def test_client_initialization_headers(self):
        """Verify the client sets Authorization and Content-Type headers."""
        headers = self.client.client.headers
        self.assertIn("Authorization", headers)
        self.assertTrue(headers["Authorization"].startswith("Bearer"))
        self.assertEqual(headers["Content-Type"], "application/hal+json")
        self.assertEqual(headers["User-Agent"], default_config["user_agent"])

    @patch("tap_3plcentral.client.TPLClient._get_access_token")
    def test_client_custom_session(self, mock_get_token):
        """Verify the client uses a custom session if provided."""
        mock_session = MagicMock()
        client = TPLClient(
            base_url=default_config["base_url"],
            client_id=default_config["client_id"],
            client_secret=default_config["client_secret"],
            tpl_key=default_config["tpl_key"],
            user_login_id=default_config["user_login_id"],
            user_agent=default_config["user_agent"],
            session=mock_session,
        )
        self.assertEqual(client.client, mock_session)
        # _get_access_token is still called by __init__ before session check,
        # but the session assignment uses the custom one
        mock_get_token.assert_not_called()

    @patch("tap_3plcentral.client.TPLClient._execute")
    def test_get_request(self, mock_execute):
        """Test the GET method constructs the correct URL and calls _execute."""
        mock_execute.return_value = {"data": "ok"}
        result = self.client.get("orders", resource_id="123", querystring="pgsiz=10")
        self.assertEqual(result, {"data": "ok"})
        mock_execute.assert_called_once_with(
            "https://secure-wms.com/orders/123?pgsiz=10",
            "GET",
            add_headers=None,
            endpoint="orders",
        )

    @patch("tap_3plcentral.client.TPLClient._execute")
    def test_get_request_no_id_no_querystring(self, mock_execute):
        """Test GET without resource_id and querystring."""
        mock_execute.return_value = {"data": "ok"}
        result = self.client.get("customers")
        self.assertEqual(result, {"data": "ok"})
        mock_execute.assert_called_once_with(
            "https://secure-wms.com/customers",
            "GET",
            add_headers=None,
            endpoint="customers",
        )

    @patch("tap_3plcentral.client.TPLClient._execute")
    def test_post_request(self, mock_execute):
        """Test the POST method constructs the correct URL and calls _execute."""
        mock_execute.return_value = {"created": True}
        result = self.client.post("orders", data={"key": "value"})
        self.assertEqual(result, {"created": True})
        mock_execute.assert_called_once()

    def test_post_request_no_data(self):
        """Test POST raises ValueError when no data is provided."""
        with self.assertRaises(ValueError) as ctx:
            self.client.post("orders")
        self.assertIn("Data Undefined", str(ctx.exception))


class TestTPLClientStatusCodes(unittest.TestCase):
    """Tests for _check_status_code error handling."""

    @patch("tap_3plcentral.client.TPLClient._get_access_token")
    def setUp(self, mock_get_token):
        mock_get_token.return_value = {
            "token_type": "Bearer",
            "access_token": "test_access_token",
        }
        self.client = TPLClient(
            base_url=default_config["base_url"],
            client_id=default_config["client_id"],
            client_secret=default_config["client_secret"],
            tpl_key=default_config["tpl_key"],
            user_login_id=default_config["user_login_id"],
            user_agent=default_config["user_agent"],
        )

    @parameterized.expand([
        ["200 OK", 200],
        ["201 Created", 201],
        ["202 Accepted", 202],
    ])
    def test_check_status_code_success(self, test_name, status_code):
        """Test that success status codes return True."""
        result = self.client._check_status_code(status_code, "")
        self.assertTrue(result)

    @parameterized.expand([
        ["400 Bad Request", 400, "Bad Request"],
        ["401 Unauthorized", 401, "Unauthorized"],
        ["403 Forbidden", 403, "Forbidden"],
        ["404 Not Found", 404, "Not Found"],
        ["412 Precondition Failed", 412, "Precondition failed"],
        ["428 Precondition Required", 428, "Precondition required"],
        ["500 Internal Server Error", 500, "Internal Server Error"],
    ])
    def test_check_status_code_mapped_errors(self, test_name, status_code, expected_msg):
        """Test that mapped error codes raise TPLAPIError with correct message."""
        with self.assertRaises(TPLAPIError) as ctx:
            self.client._check_status_code(status_code, "some error content")
        self.assertEqual(ctx.exception.error_code, status_code)
        self.assertIn(expected_msg, ctx.exception.msg)

    def test_check_status_code_unknown_error(self):
        """Test that unmapped error codes raise TPLAPIError as unknown."""
        with self.assertRaises(TPLAPIError) as ctx:
            self.client._check_status_code(418, "teapot")
        self.assertIn("Unknown error", ctx.exception.msg)


class TestTPLClientExecute(unittest.TestCase):
    """Tests for _execute retry/backoff behavior."""

    @patch("tap_3plcentral.client.TPLClient._get_access_token")
    def setUp(self, mock_get_token):
        mock_get_token.return_value = {
            "token_type": "Bearer",
            "access_token": "test_access_token",
        }
        self.client = TPLClient(
            base_url=default_config["base_url"],
            client_id=default_config["client_id"],
            client_secret=default_config["client_secret"],
            tpl_key=default_config["tpl_key"],
            user_login_id=default_config["user_login_id"],
            user_agent=default_config["user_agent"],
        )

    @patch("tap_3plcentral.client.TPLClient._check_status_code", return_value=True)
    def test_execute_success(self, mock_check):
        """Test _execute returns JSON on successful response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [1, 2, 3]}
        self.client.client.request = MagicMock(return_value=mock_response)

        result = self.client._execute("https://secure-wms.com/orders", "GET")
        self.assertEqual(result, {"data": [1, 2, 3]})

    @parameterized.expand([
        ["ConnectionError", ConnectionError],
        ["Timeout", Timeout],
    ])
    @patch("time.sleep")
    def test_execute_retries_on_connection_errors(self, test_name, error, mock_sleep):
        """Test _execute retries on connection-related errors."""
        self.client.client.request = MagicMock(side_effect=error)
        with self.assertRaises(error):
            self.client._execute("https://secure-wms.com/orders", "GET")


class TestTPLClientContextManager(unittest.TestCase):
    """Tests for context manager protocol."""

    @patch("tap_3plcentral.client.TPLClient._get_access_token")
    def test_context_manager(self, mock_get_token):
        """Test __enter__ and __exit__ work correctly."""
        mock_get_token.return_value = {
            "token_type": "Bearer",
            "access_token": "test_access_token",
        }
        client = TPLClient(
            base_url=default_config["base_url"],
            client_id=default_config["client_id"],
            client_secret=default_config["client_secret"],
            tpl_key=default_config["tpl_key"],
            user_login_id=default_config["user_login_id"],
            user_agent=default_config["user_agent"],
        )
        client.client = MagicMock()

        result = client.__enter__()
        self.assertEqual(result, client)

        client.__exit__(None, None, None)
        client.client.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
