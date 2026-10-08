import asyncio
import io
import unittest
from unittest.mock import AsyncMock, patch
from PIL import Image
import ai_edit


def photo(size):
    b = io.BytesIO()
    Image.new("RGB", size, "white").save(b, "JPEG")
    return b.getvalue()


class CompleteResultTests(unittest.TestCase):
    def test_preserves_ratio_at_different_resolution(self):
        ai_edit._validate_complete_result(photo((1500, 1000)), photo((768, 512)))

    def test_rejects_changed_ratio_orientation_and_corrupt_output(self):
        for output in (photo((1000, 1000)), photo((1000, 1500)), b"invalid"):
            with self.subTest(output_length=len(output)), self.assertRaises(Exception):
                ai_edit._validate_complete_result(photo((1500, 1000)), output)



    def test_direct_model_editing_is_disabled(self):
        with self.assertRaises(RuntimeError):
            asyncio.run(ai_edit.run_edit(photo((1500, 1000)), "complete", {}, "test"))

    def test_pro_prompt_is_unchanged(self):
        self.assertIn("do NOT add, remove, move or duplicate furniture or objects", ai_edit.build_prompt("auto_pro", {}))
        self.assertNotIn("preserve all furniture, fixtures and intentional decor", ai_edit.build_prompt("complete", {}))


if __name__ == "__main__":
    unittest.main()
