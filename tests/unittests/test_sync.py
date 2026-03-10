import unittest
from unittest.mock import MagicMock, patch, call

import singer
from tap_3plcentral.sync import (
    get_bookmark,
    write_bookmark,
    write_schema,
    get_selected_streams,
    should_sync_stream,
    update_currently_syncing,
    process_records,
    sync_endpoint,
    sync,
)


class TestGetBookmark(unittest.TestCase):
    """Tests for get_bookmark helper."""

    def test_get_bookmark_no_state(self):
        """Returns default when state is None."""
        result = get_bookmark(None, "orders", "2019-01-01T00:00:00Z")
        self.assertEqual(result, "2019-01-01T00:00:00Z")

    def test_get_bookmark_empty_state(self):
        """Returns default when state has no bookmarks key."""
        result = get_bookmark({}, "orders", "2019-01-01T00:00:00Z")
        self.assertEqual(result, "2019-01-01T00:00:00Z")

    def test_get_bookmark_missing_stream(self):
        """Returns default when stream not found in bookmarks."""
        state = {"bookmarks": {"sku_items": "2025-01-01T00:00:00Z"}}
        result = get_bookmark(state, "orders", "2019-01-01T00:00:00Z")
        self.assertEqual(result, "2019-01-01T00:00:00Z")

    def test_get_bookmark_existing_stream(self):
        """Returns bookmark value when stream exists in bookmarks."""
        state = {"bookmarks": {"orders": "2025-01-01T00:00:00Z"}}
        result = get_bookmark(state, "orders", "2019-01-01T00:00:00Z")
        self.assertEqual(result, "2025-01-01T00:00:00Z")


class TestWriteBookmark(unittest.TestCase):
    """Tests for write_bookmark helper."""

    @patch("tap_3plcentral.sync.singer.write_state")
    def test_write_bookmark_new_state(self, mock_write_state):
        """Creates bookmarks key and writes bookmark when state is empty."""
        state = {}
        write_bookmark(state, "orders", "2025-06-01T00:00:00Z")
        self.assertEqual(state, {"bookmarks": {"orders": "2025-06-01T00:00:00Z"}})
        mock_write_state.assert_called_once_with(state)

    @patch("tap_3plcentral.sync.singer.write_state")
    def test_write_bookmark_existing_state(self, mock_write_state):
        """Updates existing bookmark value."""
        state = {"bookmarks": {"orders": "2025-01-01T00:00:00Z"}}
        write_bookmark(state, "orders", "2025-06-01T00:00:00Z")
        self.assertEqual(state, {"bookmarks": {"orders": "2025-06-01T00:00:00Z"}})
        mock_write_state.assert_called_once_with(state)


class TestWriteSchema(unittest.TestCase):
    """Tests for write_schema helper."""

    @patch("tap_3plcentral.sync.singer.write_schema")
    def test_write_schema_success(self, mock_singer_write_schema):
        """Verifies write_schema calls singer.write_schema correctly."""
        mock_stream = MagicMock()
        mock_stream.schema.to_dict.return_value = {"type": "object", "properties": {}}
        mock_stream.key_properties = ["order_id"]

        mock_catalog = MagicMock()
        mock_catalog.get_stream.return_value = mock_stream

        write_schema(mock_catalog, "orders")

        mock_catalog.get_stream.assert_called_once_with("orders")
        mock_singer_write_schema.assert_called_once_with(
            "orders",
            {"type": "object", "properties": {}},
            ["order_id"],
        )

    @patch("tap_3plcentral.sync.singer.write_schema", side_effect=OSError("write error"))
    def test_write_schema_os_error(self, mock_singer_write_schema):
        """Verifies write_schema re-raises OSError."""
        mock_stream = MagicMock()
        mock_stream.schema.to_dict.return_value = {"type": "object"}
        mock_stream.key_properties = ["order_id"]

        mock_catalog = MagicMock()
        mock_catalog.get_stream.return_value = mock_stream

        with self.assertRaises(OSError):
            write_schema(mock_catalog, "orders")


class TestGetSelectedStreams(unittest.TestCase):
    """Tests for get_selected_streams."""

    def test_no_selected_streams(self):
        """Returns empty list when no streams are selected."""
        mock_catalog = MagicMock()
        stream1 = MagicMock()
        stream1.metadata = [{"breadcrumb": (), "metadata": {"selected": False}}]
        stream1.tap_stream_id = "orders"
        mock_catalog.streams = [stream1]
        result = get_selected_streams(mock_catalog)
        self.assertEqual(result, [])

    def test_selected_streams(self):
        """Returns list of selected stream tap_stream_ids."""
        mock_catalog = MagicMock()

        stream1 = MagicMock()
        stream1.metadata = [{"breadcrumb": (), "metadata": {"selected": True}}]
        stream1.tap_stream_id = "orders"

        stream2 = MagicMock()
        stream2.metadata = [{"breadcrumb": (), "metadata": {"selected": True}}]
        stream2.tap_stream_id = "customers"

        stream3 = MagicMock()
        stream3.metadata = [{"breadcrumb": (), "metadata": {"selected": False}}]
        stream3.tap_stream_id = "inventory"

        mock_catalog.streams = [stream1, stream2, stream3]
        result = get_selected_streams(mock_catalog)
        self.assertIn("orders", result)
        self.assertIn("customers", result)
        self.assertNotIn("inventory", result)


class TestShouldSyncStream(unittest.TestCase):
    """Tests for should_sync_stream."""

    def test_should_sync_when_no_last_stream(self):
        """Should sync when last_stream is None and stream is selected."""
        result, last = should_sync_stream(["orders", "customers"], None, "orders")
        self.assertTrue(result)
        self.assertIsNone(last)

    def test_should_not_sync_when_not_selected(self):
        """Should not sync when stream is not in selected_streams."""
        result, last = should_sync_stream(["customers"], None, "orders")
        self.assertFalse(result)

    def test_should_sync_when_last_stream_matches(self):
        """Should sync when last_stream matches the current stream_name."""
        result, last = should_sync_stream(["orders", "customers"], "orders", "orders")
        self.assertTrue(result)
        self.assertIsNone(last)

    def test_should_not_sync_when_last_stream_differs(self):
        """Should not sync when last_stream doesn't match current stream."""
        result, last = should_sync_stream(["orders", "customers"], "customers", "orders")
        self.assertFalse(result)
        self.assertEqual(last, "customers")


class TestUpdateCurrentlySyncing(unittest.TestCase):
    """Tests for update_currently_syncing."""

    @patch("tap_3plcentral.sync.singer.write_state")
    @patch("tap_3plcentral.sync.singer.set_currently_syncing")
    def test_set_currently_syncing(self, mock_set, mock_write_state):
        """Sets currently_syncing and writes state."""
        state = {}
        update_currently_syncing(state, "orders")
        mock_set.assert_called_once_with(state, "orders")
        mock_write_state.assert_called_once_with(state)

    @patch("tap_3plcentral.sync.singer.write_state")
    @patch("tap_3plcentral.sync.singer.set_currently_syncing")
    def test_remove_currently_syncing(self, mock_set, mock_write_state):
        """Removes currently_syncing when stream_name is None."""
        state = {"currently_syncing": "orders"}
        update_currently_syncing(state, None)
        self.assertNotIn("currently_syncing", state)
        mock_set.assert_not_called()
        mock_write_state.assert_called_once_with(state)


class TestProcessRecords(unittest.TestCase):
    """Tests for process_records."""

    def _make_catalog_stream(self, stream_name, schema, key_properties):
        """Helper to create a mock catalog with a stream."""
        mock_stream = MagicMock()
        mock_stream.schema.to_dict.return_value = schema
        mock_stream.metadata = [{"breadcrumb": (), "metadata": {}}]
        mock_stream.key_properties = key_properties

        mock_catalog = MagicMock()
        mock_catalog.get_stream.return_value = mock_stream
        return mock_catalog

    @patch("tap_3plcentral.sync.write_record")
    def test_process_records_full_table(self, mock_write_record):
        """All records written for full table stream (no bookmark)."""
        schema = {
            "type": "object",
            "properties": {
                "customer_id": {"type": ["null", "integer"]},
                "name": {"type": ["null", "string"]},
            },
        }
        catalog = self._make_catalog_stream("customers", schema, ["customer_id"])

        records = [
            {"customer_id": 1, "name": "Alice"},
            {"customer_id": 2, "name": "Bob"},
        ]
        from singer import utils

        time_extracted = utils.now()

        max_bm, count = process_records(
            catalog=catalog,
            stream_name="customers",
            records=records,
            time_extracted=time_extracted,
        )
        self.assertEqual(count, 2)
        self.assertIsNone(max_bm)

    @patch("tap_3plcentral.sync.write_record")
    def test_process_records_with_parent(self, mock_write_record):
        """Records include parent_id when parent is specified."""
        schema = {
            "type": "object",
            "properties": {
                "item_id": {"type": ["null", "integer"]},
                "customer_id": {"type": ["null", "integer"]},
            },
        }
        catalog = self._make_catalog_stream("sku_items", schema, ["item_id"])

        records = [{"item_id": 10}]
        from singer import utils

        time_extracted = utils.now()

        max_bm, count = process_records(
            catalog=catalog,
            stream_name="sku_items",
            records=records,
            time_extracted=time_extracted,
            parent="customer",
            parent_id=1,
        )
        self.assertEqual(count, 1)
        # The record written should contain customer_id = 1
        written_record = mock_write_record.call_args[0][1]
        self.assertEqual(written_record["customer_id"], 1)


class TestSync(unittest.TestCase):
    """Tests for the main sync function."""

    @patch("tap_3plcentral.sync.update_currently_syncing")
    @patch("tap_3plcentral.sync.sync_endpoint", return_value=5)
    @patch("tap_3plcentral.sync.get_selected_streams", return_value=["orders"])
    @patch("singer.get_currently_syncing", return_value=None)
    def test_sync_calls_sync_endpoint_for_selected(
        self, mock_currently_syncing, mock_get_selected, mock_sync_endpoint, mock_update
    ):
        """Sync calls sync_endpoint for each selected stream."""
        mock_client = MagicMock()
        config = {
            "start_date": "2019-01-01T00:00:00Z",
            "customer_id": "50",
            "facility_id": "1",
        }
        mock_catalog = MagicMock()
        state = {}

        sync(mock_client, config, mock_catalog, state, "2019-01-01T00:00:00Z")
        mock_sync_endpoint.assert_called_once()

    @patch("tap_3plcentral.sync.get_selected_streams", return_value=[])
    def test_sync_no_selected_streams(self, mock_get_selected):
        """Sync returns early when no streams are selected."""
        mock_client = MagicMock()
        config = {
            "start_date": "2019-01-01T00:00:00Z",
            "customer_id": "50",
            "facility_id": "1",
        }
        mock_catalog = MagicMock()
        state = {}

        # Should return without error
        result = sync(mock_client, config, mock_catalog, state, "2019-01-01T00:00:00Z")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
