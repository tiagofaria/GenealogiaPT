from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from archive_pdf.adapters.archeevo import ArcheevoAdapter
from archive_pdf.jobs import parse_page_selection, safe_filename


class PageSelectionTests(unittest.TestCase):
    def test_empty_means_all_pages(self) -> None:
        self.assertEqual(parse_page_selection("", 4), [1, 2, 3, 4])

    def test_ranges_and_duplicates_are_normalized(self) -> None:
        self.assertEqual(parse_page_selection("3, 1-2, 2", 5), [1, 2, 3])

    def test_out_of_bounds_page_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            parse_page_selection("1-8", 5)

    def test_inverted_range_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            parse_page_selection("8-2", 10)


class AdapterTests(unittest.TestCase):
    def test_archeevo_detection(self) -> None:
        adapter = ArcheevoAdapter()
        self.assertTrue(adapter.supports("https://pesquisa.auc.uc.pt/viewer/descriptions/41652"))
        self.assertFalse(adapter.supports("https://example.org/document/123"))

    def test_storage_url_is_encoded(self) -> None:
        self.assertEqual(
            ArcheevoAdapter._storage_url("https://example.org", "vault://ABC"),
            "https://example.org/api/storage/storageobject?objectId=vault%3A%2F%2FABC",
        )


class FilenameTests(unittest.TestCase):
    def test_unsafe_characters_are_removed(self) -> None:
        self.assertEqual(safe_filename('Batismos: 1814/1859?*'), "Batismos 18141859")


if __name__ == "__main__":
    unittest.main()
