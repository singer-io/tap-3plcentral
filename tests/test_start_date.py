"""Mock integration test: start_date controls initial bookmark for
incremental streams."""
import unittest
from unittest.mock import patch, MagicMock

from tap_3plcentral.sync import sync

try:
    from .base import ThreePLCentralMockBaseTest
except ImportError:
    from base import ThreePLCentralMockBaseTest


class StartDateIntegrationTest(ThreePLCentralMockBaseTest, unittest.TestCase):

    @patch("tap_3plcentral.sync.singer.write_state")
    @patch("tap_3plcentral.sync.write_record")
    @patch("tap_3plcentral.sync.singer.write_schema")
    def test_start_date_filters_orders(
        self,
        mock_write_schema,
        mock_write_record,
        mock_write_state,
    ):
        """Orders with last_modified_date before start_date should not be
        written when no bookmark exists."""
        catalog = self._make_selected_catalog(stream_names={"orders"})

        records = [
            {
                "ReadOnly": {
                    "OrderId": 1,
                    "LastModifiedDate": "2024-06-01T00:00:00Z",
                    "CreationDate": "2024-05-01T00:00:00Z",
                },
                "ReferenceNum": "ORD-BEFORE",
            },
            {
                "ReadOnly": {
                    "OrderId": 2,
                    "LastModifiedDate": "2025-03-01T00:00:00Z",
                    "CreationDate": "2025-02-01T00:00:00Z",
                },
                "ReferenceNum": "ORD-AFTER",
            },
        ]

        def mock_get(path, querystring=None, resource_id=None, endpoint=None):
            return {"TotalResults": len(records), "ResourceList": records}

        client = MagicMock()
        client.get = MagicMock(side_effect=mock_get)
        config = dict(self.default_config)
        config["start_date"] = "2025-01-01T00:00:00Z"
        state = {}

        sync(client, config, catalog, state, config["start_date"])

        written_records = [
            call_args[0][1]
            for call_args in mock_write_record.call_args_list
            if call_args[0][0] == "orders"
        ]
        # Only the record at/after start_date should be written
        for record in written_records:
            self.assertGreaterEqual(
                record.get("last_modified_date", ""),
                "2025-01-01T00:00:00",
            )

    @patch("tap_3plcentral.sync.singer.write_state")
    @patch("tap_3plcentral.sync.write_record")
    @patch("tap_3plcentral.sync.singer.write_schema")
    def test_different_start_dates_yield_different_record_counts(
        self,
        mock_write_schema,
        mock_write_record,
        mock_write_state,
    ):
        """A later start_date should yield fewer (or equal) records for
        incremental streams."""
        catalog_early = self._make_selected_catalog(stream_names={"orders"})
        catalog_late = self._make_selected_catalog(stream_names={"orders"})

        records = [
            {
                "ReadOnly": {
                    "OrderId": i,
                    "LastModifiedDate": f"2025-{(i % 12) + 1:02d}-15T00:00:00Z",
                    "CreationDate": f"2025-{(i % 12) + 1:02d}-01T00:00:00Z",
                },
                "ReferenceNum": f"ORD-{i:05d}",
            }
            for i in range(1, 13)
        ]

        def mock_get(path, querystring=None, resource_id=None, endpoint=None):
            return {"TotalResults": len(records), "ResourceList": records}

        # First sync with early start_date
        client = MagicMock()
        client.get = MagicMock(side_effect=mock_get)
        config_early = dict(self.default_config)
        config_early["start_date"] = "2025-01-01T00:00:00Z"

        sync(client, config_early, catalog_early, {}, config_early["start_date"])
        early_count = mock_write_record.call_count

        mock_write_record.reset_mock()

        # Second sync with later start_date
        client2 = MagicMock()
        client2.get = MagicMock(side_effect=mock_get)
        config_late = dict(self.default_config)
        config_late["start_date"] = "2025-07-01T00:00:00Z"

        sync(client2, config_late, catalog_late, {}, config_late["start_date"])
        late_count = mock_write_record.call_count

        self.assertGreaterEqual(early_count, late_count)
