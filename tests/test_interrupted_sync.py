from base import ThreePLCentralBaseTest
from tap_tester.base_suite_tests.interrupted_sync_test import InterruptedSyncTest


class ThreePLCentralInterruptedSyncTest(InterruptedSyncTest, ThreePLCentralBaseTest):
    """Test tap sets a bookmark and respects it for the next sync of a
    stream."""

    @staticmethod
    def name():
        return "tap_tester_3plcentral_interrupted_sync_test"

    def streams_to_test(self):
        # Only incremental, non-child streams
        return {"orders"}

    def manipulate_state(self):
        return {
            "currently_syncing": "orders",
            "bookmarks": {
                "orders": {"last_modified_date": "2025-07-01T00:00:00Z"},
            },
        }

    def test_interrupted_sync_stream_order(self):
        """Override: only one non-child incremental stream, so no 'already synced' streams."""
        expected_interrupted_sync = self.manipulate_state()['currently_syncing']
        self.assertEqual(self.resuming_sync_order[0], expected_interrupted_sync)

        expected_yet_to_be_synced = self.streams_to_test().difference(
            self.manipulate_state()['bookmarks'].keys())
        actual_next_synced = set(self.resuming_sync_order[1:1 + len(expected_yet_to_be_synced)])
        self.assertSetEqual(actual_next_synced, expected_yet_to_be_synced)
