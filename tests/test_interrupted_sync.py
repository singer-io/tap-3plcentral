from base import ThreePLCentralBaseTest
from tap_tester.base_suite_tests.interrupted_sync_test import InterruptedSyncTest


class ThreePLCentralInterruptedSyncTest(InterruptedSyncTest, ThreePLCentralBaseTest):
    """Test tap sets a bookmark and respects it for the next sync of a
    stream."""

    @staticmethod
    def name():
        return "tap_tester_3plcentral_interrupted_sync_test"

    def streams_to_test(self):
        # Only incremental streams support interrupted sync
        streams_to_exclude = {
            # Full table replication streams (no bookmark/interruption support)
            "customers",
            "stock_details",
            "stock_summaries",
            "locations",
            "inventory",
        }
        return self.expected_stream_names().difference(streams_to_exclude)

    def manipulate_state(self):
        return {
            "currently_syncing": "orders",
            "bookmarks": {
                "orders": {"last_modified_date": "2025-07-01T00:00:00Z"},
                "sku_items": {"last_modified_date": "2025-07-01T00:00:00Z"},
            },
        }
