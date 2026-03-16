from base import ThreePLCentralBaseTest
from tap_tester.base_suite_tests.bookmark_test import BookmarkTest


class ThreePLCentralBookmarkTest(BookmarkTest, ThreePLCentralBaseTest):
    """Test tap sets a bookmark and respects it for the next sync of a
    stream."""

    bookmark_format = "%Y-%m-%dT%H:%M:%S.%fZ"

    initial_bookmarks = {
        "bookmarks": {
            "orders": {"last_modified_date": "2025-09-01T00:00:00Z"},
        }
    }

    @staticmethod
    def name():
        return "tap_tester_3plcentral_bookmark_test"

    def streams_to_test(self):
        # Only incremental, non-child streams support independent bookmarks
        return {"orders"}
