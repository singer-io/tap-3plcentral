"""Mock integration test: interrupted sync resumes correctly using
currently_syncing state."""
import unittest
from unittest.mock import patch, MagicMock

from tap_3plcentral.sync import sync

try:
    from .base import ThreePLCentralMockBaseTest
except ImportError:
    from base import ThreePLCentralMockBaseTest


class InterruptedSyncIntegrationTest(ThreePLCentralMockBaseTest, unittest.TestCase):

    @patch("tap_3plcentral.sync.singer.write_state")
    @patch("tap_3plcentral.sync.write_record")
    @patch("tap_3plcentral.sync.singer.write_schema")
    def test_interrupted_sync_resumes_from_currently_syncing(
        self,
        mock_write_schema,
        mock_write_record,
        mock_write_state,
    ):
        """When state has currently_syncing set, sync should resume from
        that stream and skip streams that come before it."""
        # Select all top-level streams
        catalog = self._make_selected_catalog(
            stream_names={"inventory", "locations", "stock_summaries", "customers", "orders"}
        )

        def mock_get(path, querystring=None, resource_id=None, endpoint=None):
            if path.startswith("orders"):
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
            if path.startswith("customers"):
                return {
                    "TotalResults": 1,
                    "ResourceList": [
                        {
                            "ReadOnly": {
                                "CustomerId": 1,
                                "CreationDate": "2025-01-01T00:00:00",
                                "Deactivated": False,
                            },
                            "CompanyInfo": {"CompanyName": "Test Co"},
                        }
                    ],
                }
            return {"TotalResults": 0, "ResourceList": []}

        client = MagicMock()
        client.get = MagicMock(side_effect=mock_get)
        config = dict(self.default_config)

        # Simulate interrupted sync: we were syncing "orders" when interrupted
        state = {
            "currently_syncing": "orders",
            "bookmarks": {
                "orders": {"last_modified_date": "2025-07-01T00:00:00Z"}
            },
        }

        sync(client, config, catalog, state, config["start_date"])

        # "orders" should have been synced (it was currently_syncing)
        written_streams = {
            call_args[0][0] for call_args in mock_write_record.call_args_list
        }
        self.assertIn("orders", written_streams)

        # Streams before "orders" in endpoint order should have been skipped
        # (inventory, locations, stock_summaries, customers all come before orders)
        self.assertNotIn("inventory", written_streams)
        self.assertNotIn("locations", written_streams)
        self.assertNotIn("stock_summaries", written_streams)
        self.assertNotIn("customers", written_streams)

    @patch("tap_3plcentral.sync.singer.write_state")
    @patch("tap_3plcentral.sync.write_record")
    @patch("tap_3plcentral.sync.singer.write_schema")
    def test_no_currently_syncing_syncs_all(
        self,
        mock_write_schema,
        mock_write_record,
        mock_write_state,
    ):
        """Without currently_syncing, all selected streams should sync."""
        catalog = self._make_selected_catalog(stream_names={"inventory", "orders"})

        def mock_get(path, querystring=None, resource_id=None, endpoint=None):
            if path.startswith("orders"):
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
            return {
                "TotalResults": 1,
                "ResourceList": [
                    {"ReceiveItemId": 1, "ReceivedDate": "2025-06-01T00:00:00"}
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
        self.assertIn("inventory", written_streams)
        self.assertIn("orders", written_streams)
