"""Mock integration test: bookmark is advanced after sync for incremental streams."""
import unittest
from unittest.mock import patch, MagicMock

from tap_3plcentral.sync import sync

try:
    from .base import ThreePLCentralMockBaseTest
except ImportError:
    from base import ThreePLCentralMockBaseTest


class BookmarkIntegrationTest(ThreePLCentralMockBaseTest, unittest.TestCase):

    @patch("tap_3plcentral.sync.singer.write_state")
    @patch("tap_3plcentral.sync.write_record")
    @patch("tap_3plcentral.sync.singer.write_schema")
    def test_sync_advances_bookmark_for_orders(
        self,
        mock_write_schema,
        mock_write_record,
        mock_write_state,
    ):
        """After syncing orders, the bookmark should advance to the
        max last_modified_date seen in the records."""
        catalog = self._make_selected_catalog(stream_names={"orders"})

        def mock_get(path, querystring=None, resource_id=None, endpoint=None):
            return {
                "TotalResults": 3,
                "ResourceList": [
                    {
                        "ReadOnly": {
                            "OrderId": 1,
                            "LastModifiedDate": "2025-08-01T00:00:00Z",
                            "CreationDate": "2025-07-01T00:00:00Z",
                        },
                        "ReferenceNum": "ORD-1",
                    },
                    {
                        "ReadOnly": {
                            "OrderId": 2,
                            "LastModifiedDate": "2025-10-15T00:00:00Z",
                            "CreationDate": "2025-09-01T00:00:00Z",
                        },
                        "ReferenceNum": "ORD-2",
                    },
                    {
                        "ReadOnly": {
                            "OrderId": 3,
                            "LastModifiedDate": "2025-09-20T00:00:00Z",
                            "CreationDate": "2025-08-01T00:00:00Z",
                        },
                        "ReferenceNum": "ORD-3",
                    },
                ],
            }

        client = MagicMock()
        client.get = MagicMock(side_effect=mock_get)
        config = dict(self.default_config)
        state = {}

        sync(client, config, catalog, state, config["start_date"])

        # Bookmark should be set to the max last_modified_date
        self.assertIn("bookmarks", state)
        self.assertIn("orders", state["bookmarks"])
        bookmark_value = state["bookmarks"]["orders"]["last_modified_date"]
        # The transformer normalizes to ISO format with microseconds
        self.assertIn("2025-10-15", bookmark_value)

    @patch("tap_3plcentral.sync.singer.write_state")
    @patch("tap_3plcentral.sync.write_record")
    @patch("tap_3plcentral.sync.singer.write_schema")
    def test_sync_respects_existing_bookmark(
        self,
        mock_write_schema,
        mock_write_record,
        mock_write_state,
    ):
        """When a bookmark already exists, only records at or after the
        bookmark should be written."""
        catalog = self._make_selected_catalog(stream_names={"orders"})

        old_records = [
            {
                "ReadOnly": {
                    "OrderId": 1,
                    "LastModifiedDate": "2025-06-01T00:00:00Z",
                    "CreationDate": "2025-05-01T00:00:00Z",
                },
                "ReferenceNum": "ORD-OLD",
            },
            {
                "ReadOnly": {
                    "OrderId": 2,
                    "LastModifiedDate": "2025-10-01T00:00:00Z",
                    "CreationDate": "2025-09-01T00:00:00Z",
                },
                "ReferenceNum": "ORD-NEW",
            },
        ]

        def mock_get(path, querystring=None, resource_id=None, endpoint=None):
            return {
                "TotalResults": len(old_records),
                "ResourceList": old_records,
            }

        client = MagicMock()
        client.get = MagicMock(side_effect=mock_get)
        config = dict(self.default_config)
        # Pre-set bookmark so only records >= 2025-09-01 are written
        state = {
            "bookmarks": {
                "orders": {"last_modified_date": "2025-09-01T00:00:00Z"}
            }
        }

        sync(client, config, catalog, state, config["start_date"])

        # Only the record at/after the bookmark should be written
        written_records = [
            call_args[0][1] for call_args in mock_write_record.call_args_list
            if call_args[0][0] == "orders"
        ]
        # The API might still return old records (mocked here), but
        # process_records filters by bookmark — only >= bookmark are written
        for record in written_records:
            self.assertGreaterEqual(
                record.get("last_modified_date", ""),
                "2025-09-01T00:00:00",
            )

    @patch("tap_3plcentral.sync.singer.write_state")
    @patch("tap_3plcentral.sync.write_record")
    @patch("tap_3plcentral.sync.singer.write_schema")
    def test_full_table_stream_has_no_bookmark(
        self,
        mock_write_schema,
        mock_write_record,
        mock_write_state,
    ):
        """Full table streams (like customers) should not set a bookmark."""
        catalog = self._make_selected_catalog(stream_names={"customers"})

        def mock_get(path, querystring=None, resource_id=None, endpoint=None):
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

        client = MagicMock()
        client.get = MagicMock(side_effect=mock_get)
        config = dict(self.default_config)
        state = {}

        sync(client, config, catalog, state, config["start_date"])

        # Full table stream should not have a bookmark entry
        if "bookmarks" in state:
            self.assertNotIn("customers", state["bookmarks"])

    @patch("tap_3plcentral.sync.singer.write_state")
    @patch("tap_3plcentral.sync.write_record")
    @patch("tap_3plcentral.sync.singer.write_schema")
    def test_sync_advances_bookmark_for_sku_items(
        self,
        mock_write_schema,
        mock_write_record,
        mock_write_state,
    ):
        """sku_items is also INCREMENTAL — bookmark should advance after sync."""
        catalog = self._make_selected_catalog(
            stream_names={"customers", "sku_items"}
        )

        def mock_get(path, querystring=None, resource_id=None, endpoint=None):
            if "items" in path:
                return {
                    "TotalResults": 2,
                    "ResourceList": [
                        {
                            "ReadOnly": {
                                "ItemId": 1001,
                                "LastModifiedDate": "2025-08-01T00:00:00Z",
                                "CreationDate": "2024-01-01T00:00:00",
                            },
                            "Sku": "SKU-1001",
                        },
                        {
                            "ReadOnly": {
                                "ItemId": 1002,
                                "LastModifiedDate": "2025-11-01T00:00:00Z",
                                "CreationDate": "2024-06-01T00:00:00",
                            },
                            "Sku": "SKU-1002",
                        },
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
        state = {}

        sync(client, config, catalog, state, config["start_date"])

        # sku_items bookmark should be set to max last_modified_date
        self.assertIn("bookmarks", state)
        self.assertIn("sku_items", state["bookmarks"])
        bookmark_value = state["bookmarks"]["sku_items"]["last_modified_date"]
        self.assertIn("2025-11-01", bookmark_value)
