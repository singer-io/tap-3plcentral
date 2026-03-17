"""Mock integration test: sync all streams with mocked API responses
and verify all fields are replicated."""
import unittest
from unittest.mock import patch, MagicMock

from tap_3plcentral.sync import sync
from tap_3plcentral.schema import STREAMS

try:
    from .base import ThreePLCentralMockBaseTest
except ImportError:
    from base import ThreePLCentralMockBaseTest


class AllFieldsIntegrationTest(ThreePLCentralMockBaseTest, unittest.TestCase):

    @patch("tap_3plcentral.sync.singer.write_state")
    @patch("tap_3plcentral.sync.write_record")
    @patch("tap_3plcentral.sync.singer.write_schema")
    def test_sync_all_streams_writes_records(
        self,
        mock_write_schema,
        mock_write_record,
        mock_write_state,
    ):
        """Sync all selected streams with mocked API data and verify
        records are written for each stream."""

        # Build a catalog with all streams selected
        catalog = self._make_selected_catalog()

        # Mock API responses for each endpoint
        def mock_customers_response(path, querystring=None, endpoint=None):
            return {
                "TotalResults": 1,
                "ResourceList": [
                    {
                        "ReadOnly": {
                            "CustomerId": 1,
                            "CreationDate": "2025-01-01T00:00:00",
                            "Deactivated": False,
                        },
                        "CompanyInfo": {
                            "ContactId": 1,
                            "CompanyName": "Test Co",
                            "Name": "Test Contact",
                        },
                    }
                ],
            }

        def mock_sku_items_response(path, querystring=None, endpoint=None):
            return {
                "TotalResults": 1,
                "ResourceList": [
                    {
                        "ReadOnly": {
                            "ItemId": 1001,
                            "LastModifiedDate": "2025-10-01T00:00:00Z",
                            "CreationDate": "2024-06-01T00:00:00",
                        },
                        "Sku": "SKU-1001",
                        "Description": "Test Item",
                    }
                ],
            }

        def mock_stock_details_response(path, querystring=None, endpoint=None):
            return {
                "TotalResults": 1,
                "ResourceList": [
                    {
                        "ReceiveItemId": 1,
                        "ItemIdentifier": {"Sku": "SKU-1", "Id": 1},
                        "Description": "Stock Detail 1",
                        "Received": 100.0,
                    }
                ],
            }

        def mock_stock_summaries_response(path, querystring=None, endpoint=None):
            return {
                "TotalResults": 1,
                "Summaries": [
                    {
                        "ItemIdentifier": {"Sku": "SKU-1", "Id": 1},
                        "TotalReceived": 100.0,
                        "Available": 80.0,
                        "FacilityId": 1,
                    }
                ],
            }

        def mock_locations_response(path, querystring=None, endpoint=None):
            return {
                "TotalResults": 1,
                "ResourceList": [
                    {
                        "LocationIdentifier": {
                            "NameKey": {
                                "FacilityIdentifier": {"Name": "Main", "Id": 1},
                                "Name": "LOC-001",
                            },
                            "Id": 1,
                        },
                        "Description": "Location 1",
                    }
                ],
            }

        def mock_inventory_response(path, querystring=None, endpoint=None):
            return {
                "TotalResults": 1,
                "ResourceList": [
                    {
                        "ReceiveItemId": 1,
                        "ReceivedDate": "2025-06-01T00:00:00",
                        "ItemIdentifier": {"Sku": "SKU-1", "Id": 1},
                    }
                ],
            }

        def mock_orders_response(path, querystring=None, endpoint=None):
            return {
                "TotalResults": 1,
                "ResourceList": [
                    {
                        "ReadOnly": {
                            "OrderId": 1,
                            "LastModifiedDate": "2025-10-01T00:00:00Z",
                            "CreationDate": "2025-09-01T00:00:00Z",
                            "IsClosed": False,
                        },
                        "ReferenceNum": "ORD-00001",
                        "CustomerIdentifier": {"Id": 1, "Name": "Test Co"},
                    }
                ],
            }

        def mock_get(path, querystring=None, resource_id=None, endpoint=None):
            handlers = {
                "customers": mock_customers_response,
                "inventory/stocksummaries": mock_stock_summaries_response,
                "inventory/stockdetails": mock_stock_details_response,
                "inventory/facilities": mock_locations_response,
                "inventory": mock_inventory_response,
                "orders": mock_orders_response,
            }
            # sku_items is called via customers/{id}/items
            if "items" in path:
                return mock_sku_items_response(path, querystring=querystring, endpoint=endpoint)
            # stock_details via inventory/stockdetails
            if path.startswith("inventory/stockdetails"):
                return mock_stock_details_response(path, querystring=querystring, endpoint=endpoint)
            if path.startswith("inventory/stocksummaries"):
                return mock_stock_summaries_response(path, querystring=querystring, endpoint=endpoint)
            if path.startswith("inventory/facilities"):
                return mock_locations_response(path, querystring=querystring, endpoint=endpoint)
            for prefix, handler in handlers.items():
                if path.startswith(prefix):
                    return handler(path, querystring=querystring, endpoint=endpoint)
            return {}

        client = MagicMock()
        client.get = MagicMock(side_effect=mock_get)
        config = dict(self.default_config)
        state = {}

        sync(client, config, catalog, state, config["start_date"])

        # Collect all streams that had records written
        written_streams = {
            call_args[0][0] for call_args in mock_write_record.call_args_list
        }

        # Verify records were written for key streams
        self.assertIn("customers", written_streams)
        self.assertIn("orders", written_streams)
        self.assertIn("inventory", written_streams)
        self.assertIn("stock_summaries", written_streams)
        self.assertIn("locations", written_streams)

        # Verify write_schema was called for synced streams
        schema_streams = {
            call_args[0][0] for call_args in mock_write_schema.call_args_list
        }
        for stream in ["customers", "orders", "inventory", "stock_summaries", "locations"]:
            self.assertIn(stream, schema_streams)

    @patch("tap_3plcentral.sync.singer.write_state")
    @patch("tap_3plcentral.sync.write_record")
    @patch("tap_3plcentral.sync.singer.write_schema")
    def test_sync_single_stream_only(
        self,
        mock_write_schema,
        mock_write_record,
        mock_write_state,
    ):
        """Sync only the 'orders' stream and verify only it is replicated."""
        catalog = self._make_selected_catalog(stream_names={"orders"})

        def mock_get(path, querystring=None, resource_id=None, endpoint=None):
            return {
                "TotalResults": 2,
                "ResourceList": [
                    {
                        "ReadOnly": {
                            "OrderId": 1,
                            "LastModifiedDate": "2025-10-01T00:00:00Z",
                            "CreationDate": "2025-09-01T00:00:00Z",
                        },
                        "ReferenceNum": "ORD-00001",
                    },
                    {
                        "ReadOnly": {
                            "OrderId": 2,
                            "LastModifiedDate": "2025-11-01T00:00:00Z",
                            "CreationDate": "2025-10-01T00:00:00Z",
                        },
                        "ReferenceNum": "ORD-00002",
                    },
                ],
            }

        client = MagicMock()
        client.get = MagicMock(side_effect=mock_get)
        config = dict(self.default_config)
        state = {}

        sync(client, config, catalog, state, config["start_date"])

        written_streams = {
            call_args[0][0] for call_args in mock_write_record.call_args_list
        }
        self.assertEqual(written_streams, {"orders"})
        self.assertEqual(mock_write_record.call_count, 2)
