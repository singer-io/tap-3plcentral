import os
import unittest
from datetime import datetime as dt

from tap_tester import connections, menagerie, runner
from tap_tester.logger import LOGGER
from tap_tester.base_suite_tests.base_case import BaseCase


class ThreePLCentralBaseTest(BaseCase):
    """Setup expectations for test sub classes.

    Metadata describing streams. A bunch of shared methods that are used
    in tap-tester tests. Shared tap-specific methods (as needed).
    """
    start_date = "2019-01-01T00:00:00Z"
    PARENT_TAP_STREAM_ID = "parent-tap-stream-id"

    @staticmethod
    def tap_name():
        """The name of the tap."""
        return "tap-3plcentral"

    @staticmethod
    def get_type():
        """The expected connector type."""
        return "platform.3plcentral"

    @classmethod
    def expected_metadata(cls):
        """The expected streams and metadata about the streams."""
        return {
            "customers": {
                cls.PRIMARY_KEYS: {"customer_id"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.REPLICATION_KEYS: set(),
                cls.OBEYS_START_DATE: False,
                cls.API_LIMIT: 100,
            },
            "sku_items": {
                cls.PRIMARY_KEYS: {"item_id"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"last_modified_date"},
                cls.OBEYS_START_DATE: True,
                cls.API_LIMIT: 100,
                cls.PARENT_TAP_STREAM_ID: "customer",
            },
            "stock_details": {
                cls.PRIMARY_KEYS: {"receive_item_id"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.REPLICATION_KEYS: set(),
                cls.OBEYS_START_DATE: False,
                cls.API_LIMIT: 100,
                cls.PARENT_TAP_STREAM_ID: "customer",
            },
            "stock_summaries": {
                cls.PRIMARY_KEYS: {"facility_id", "item_id"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.REPLICATION_KEYS: set(),
                cls.OBEYS_START_DATE: False,
                cls.API_LIMIT: 200,
            },
            "locations": {
                cls.PRIMARY_KEYS: {"facility_id", "location_id"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.REPLICATION_KEYS: set(),
                cls.OBEYS_START_DATE: False,
                cls.API_LIMIT: 200,
            },
            "inventory": {
                cls.PRIMARY_KEYS: {"receive_item_id"},
                cls.REPLICATION_METHOD: cls.FULL_TABLE,
                cls.REPLICATION_KEYS: set(),
                cls.OBEYS_START_DATE: False,
                cls.API_LIMIT: 200,
            },
            "orders": {
                cls.PRIMARY_KEYS: {"order_id"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"last_modified_date"},
                cls.OBEYS_START_DATE: True,
                cls.API_LIMIT: 200,
            },
        }

    @staticmethod
    def get_credentials():
        """Authentication information for the test account."""
        return {
            "client_id": os.getenv("TAP_3PLCENTRAL_CLIENT_ID"),
            "client_secret": os.getenv("TAP_3PLCENTRAL_CLIENT_SECRET"),
            "tpl_key": os.getenv("TAP_3PLCENTRAL_TPL_KEY"),
        }

    def get_properties(self, original: bool = True):
        """Configuration of properties required for the tap."""
        return {
            "base_url": os.getenv("TAP_3PLCENTRAL_BASE_URL", "https://secure-wms.com"),
            "user_login_id": os.getenv("TAP_3PLCENTRAL_USER_LOGIN_ID", "1"),
            "user_agent": os.getenv("TAP_3PLCENTRAL_USER_AGENT", "tap-3plcentral <test@test.com>"),
            "customer_id": os.getenv("TAP_3PLCENTRAL_CUSTOMER_ID", "50"),
            "facility_id": os.getenv("TAP_3PLCENTRAL_FACILITY_ID", "1"),
            "start_date": self.start_date,
        }

    def expected_parent_tap_stream(self, stream=None):
        """Return a dictionary with key of table name and value of parent stream."""
        parent_stream = {
            table: properties.get(self.PARENT_TAP_STREAM_ID, None)
            for table, properties in self.expected_metadata().items()
        }
        if stream:
            return parent_stream.get(stream)
        return parent_stream
