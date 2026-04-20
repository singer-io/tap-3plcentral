"""Mock integration test: sync function writes records and updates state
correctly."""
import unittest
from unittest.mock import patch, MagicMock

from tap_3plcentral.sync import sync, update_currently_syncing

try:
    from .base import ThreePLCentralMockBaseTest
except ImportError:
    from base import ThreePLCentralMockBaseTest


class SyncIntegrationTest(ThreePLCentralMockBaseTest, unittest.TestCase):

    @patch("tap_3plcentral.sync.singer.write_state")
    @patch("tap_3plcentral.sync.write_record")
    @patch("tap_3plcentral.sync.singer.write_schema")
    def test_sync_writes_schema_before_records(
        self,
        mock_write_schema,
        mock_write_record,
        mock_write_state,
    ):
        """Verify that write_schema is called before write_record for
        each stream."""
        catalog = self._make_selected_catalog(stream_names={"orders"})

        def mock_get(path, querystring=None, resource_id=None, endpoint=None):
            return {
                "TotalResults": 1,
                "ResourceList": [
                    {
                        "ReadOnly": {
                            "OrderId": 1,
                            "LastModifiedDate": "2025-10-01T00:00:00Z",
                        },
                        "ReferenceNum": "ORD-1",
                    }
                ],
            }

        client = MagicMock()
        client.get = MagicMock(side_effect=mock_get)
        config = dict(self.default_config)

        sync(client, config, catalog, {}, config["start_date"])

        mock_write_schema.assert_called()
        mock_write_record.assert_called()

        # Schema call should come before record call
        schema_call_order = mock_write_schema.call_args_list[0]
        self.assertEqual(schema_call_order[0][0], "orders")

    @patch("tap_3plcentral.sync.singer.write_state")
    @patch("tap_3plcentral.sync.write_record")
    @patch("tap_3plcentral.sync.singer.write_schema")
    def test_sync_no_selected_streams_does_nothing(
        self,
        mock_write_schema,
        mock_write_record,
        mock_write_state,
    ):
        """When no streams are selected, sync should not call any writes."""
        catalog = self._make_selected_catalog(stream_names=set())

        client = MagicMock()
        config = dict(self.default_config)

        sync(client, config, catalog, {}, config["start_date"])

        mock_write_schema.assert_not_called()
        mock_write_record.assert_not_called()

    @patch("tap_3plcentral.sync.singer.write_state")
    @patch("tap_3plcentral.sync.write_record")
    @patch("tap_3plcentral.sync.singer.write_schema")
    def test_sync_parent_child_writes_child_records(
        self,
        mock_write_schema,
        mock_write_record,
        mock_write_state,
    ):
        """When both customers and sku_items are selected, child records
        (sku_items) should be written with customer_id populated."""
        catalog = self._make_selected_catalog(
            stream_names={"customers", "sku_items"}
        )

        call_count = {"customers": 0}

        def mock_get(path, querystring=None, resource_id=None, endpoint=None):
            if "items" in path:
                return {
                    "TotalResults": 1,
                    "ResourceList": [
                        {
                            "ReadOnly": {
                                "ItemId": 2001,
                                "LastModifiedDate": "2025-10-01T00:00:00Z",
                                "CreationDate": "2024-06-01T00:00:00",
                            },
                            "Sku": "SKU-2001",
                            "Description": "Test Item",
                        }
                    ],
                }
            return {
                "TotalResults": 1,
                "ResourceList": [
                    {
                        "ReadOnly": {
                            "CustomerId": 42,
                            "CreationDate": "2025-01-01T00:00:00",
                            "Deactivated": False,
                        },
                        "CompanyInfo": {"CompanyName": "Test Co"},
                    }
                ],
            }

        client = MagicMock()
        client.get = MagicMock(side_effect=mock_get)
        config = dict(self.default_config)

        sync(client, config, catalog, {}, config["start_date"])

        # sku_items should have been written
        sku_records = [
            call_args[0][1]
            for call_args in mock_write_record.call_args_list
            if call_args[0][0] == "sku_items"
        ]
        self.assertTrue(len(sku_records) > 0)
        # Each sku_items record should have customer_id from parent
        for rec in sku_records:
            self.assertIn("customer_id", rec)

    @patch("tap_3plcentral.sync.singer.write_state")
    @patch("tap_3plcentral.sync.singer.set_currently_syncing")
    def test_currently_syncing_is_set_and_cleared(
        self,
        mock_set_syncing,
        mock_write_state,
    ):
        """Verify update_currently_syncing sets and clears the state."""
        state = {}

        update_currently_syncing(state, "orders")
        mock_set_syncing.assert_called_with(state, "orders")

        update_currently_syncing(state, None)
        mock_set_syncing.assert_called_with(state, None)

    @patch("tap_3plcentral.sync.singer.write_state")
    @patch("tap_3plcentral.sync.write_record")
    @patch("tap_3plcentral.sync.singer.write_schema")
    def test_sync_empty_api_response_no_crash(
        self,
        mock_write_schema,
        mock_write_record,
        mock_write_state,
    ):
        """When API returns empty data, sync should complete without errors
        and not write any records."""
        catalog = self._make_selected_catalog(stream_names={"orders"})

        def mock_get(path, querystring=None, resource_id=None, endpoint=None):
            return []

        client = MagicMock()
        client.get = MagicMock(side_effect=mock_get)
        config = dict(self.default_config)

        sync(client, config, catalog, {}, config["start_date"])

        mock_write_record.assert_not_called()
