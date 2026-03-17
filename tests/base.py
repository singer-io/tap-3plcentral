"""
Base test class for mock integration tests, modeled on tap-referral-saasquatch.

These tests run the real tap code against mocked API responses — no external
tap-tester dependency required.
"""
import unittest
from unittest.mock import MagicMock, patch

from tap_3plcentral.schema import get_schemas, STREAMS
from tap_3plcentral.discover import discover


class ThreePLCentralMockBaseTest:
    """Shared helpers and metadata expectations for mock integration tests."""

    default_start_date = "2019-01-01T00:00:00Z"
    PRIMARY_KEYS = "primary_keys"
    REPLICATION_METHOD = "replication_method"
    REPLICATION_KEYS = "replication_keys"
    OBEYS_START_DATE = "obeys_start_date"
    API_LIMIT = "api_limit"

    default_config = {
        "base_url": "http://localhost:8765",
        "client_id": "test_client_id",
        "client_secret": "test_client_secret",
        "tpl_key": "test_tpl_key",
        "user_login_id": "1",
        "user_agent": "tap-3plcentral <test@test.com>",
        "customer_id": "50",
        "facility_id": "1",
        "start_date": "2019-01-01T00:00:00Z",
    }

    @classmethod
    def expected_metadata(cls):
        return {
            "customers": {
                cls.PRIMARY_KEYS: {"customer_id"},
                cls.REPLICATION_METHOD: "FULL_TABLE",
                cls.REPLICATION_KEYS: set(),
                cls.OBEYS_START_DATE: False,
                cls.API_LIMIT: 100,
            },
            "sku_items": {
                cls.PRIMARY_KEYS: {"item_id"},
                cls.REPLICATION_METHOD: "INCREMENTAL",
                cls.REPLICATION_KEYS: {"last_modified_date"},
                cls.OBEYS_START_DATE: True,
                cls.API_LIMIT: 100,
            },
            "stock_details": {
                cls.PRIMARY_KEYS: {"receive_item_id"},
                cls.REPLICATION_METHOD: "FULL_TABLE",
                cls.REPLICATION_KEYS: set(),
                cls.OBEYS_START_DATE: False,
                cls.API_LIMIT: 100,
            },
            "stock_summaries": {
                cls.PRIMARY_KEYS: {"facility_id", "item_id"},
                cls.REPLICATION_METHOD: "FULL_TABLE",
                cls.REPLICATION_KEYS: set(),
                cls.OBEYS_START_DATE: False,
                cls.API_LIMIT: 200,
            },
            "locations": {
                cls.PRIMARY_KEYS: {"facility_id", "location_id"},
                cls.REPLICATION_METHOD: "FULL_TABLE",
                cls.REPLICATION_KEYS: set(),
                cls.OBEYS_START_DATE: False,
                cls.API_LIMIT: 200,
            },
            "inventory": {
                cls.PRIMARY_KEYS: {"receive_item_id"},
                cls.REPLICATION_METHOD: "FULL_TABLE",
                cls.REPLICATION_KEYS: set(),
                cls.OBEYS_START_DATE: False,
                cls.API_LIMIT: 200,
            },
            "orders": {
                cls.PRIMARY_KEYS: {"order_id"},
                cls.REPLICATION_METHOD: "INCREMENTAL",
                cls.REPLICATION_KEYS: {"last_modified_date"},
                cls.OBEYS_START_DATE: True,
                cls.API_LIMIT: 200,
            },
        }

    @staticmethod
    def _make_selected_catalog(stream_names=None):
        """Build a real catalog with selected=True for the given streams.
        If stream_names is None, select all streams."""
        catalog = discover()
        from singer import metadata
        for entry in catalog.streams:
            mdata = metadata.to_map(entry.metadata)
            if stream_names is None or entry.tap_stream_id in stream_names:
                mdata = metadata.write(mdata, (), "selected", True)
                for prop in entry.schema.to_dict().get("properties", {}).keys():
                    mdata = metadata.write(
                        mdata, ("properties", prop), "selected", True
                    )
            else:
                mdata = metadata.write(mdata, (), "selected", False)
            entry.metadata = metadata.to_list(mdata)
        return catalog

    @staticmethod
    def _mock_client_get(responses):
        """Create a mock TPLClient whose get() returns from a response map.

        responses: dict mapping endpoint path prefixes to either:
          - a callable(path, querystring=..., endpoint=...) -> dict
          - a static dict
        """
        def mock_get(path, querystring=None, resource_id=None, endpoint=None):
            for prefix, response in responses.items():
                if path.startswith(prefix) or (endpoint and endpoint == prefix):
                    if callable(response):
                        return response(path, querystring=querystring, endpoint=endpoint)
                    return response
            return {}
        client = MagicMock()
        client.get = MagicMock(side_effect=mock_get)
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)
        return client
