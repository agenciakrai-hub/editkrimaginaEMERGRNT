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

    def test_invalid_primary_uses_valid_fallback(self):
        valid = photo((750, 500))
        model = AsyncMock(side_effect=[photo((500, 500)), valid])
        with patch.object(ai_edit, "MODEL", "primary"), patch.object(ai_edit, "FALLBACK_MODEL", "fallback"), patch.object(ai_edit, "_call_model", model):
            result = asyncio.run(ai_edit.run_edit(photo((1500, 1000)), "complete", {}, "test"))
        self.assertEqual(result, valid)
        self.assertEqual(model.await_count, 2)

    def test_all_invalid_outputs_fail_without_delivering_distorted_format(self):
        with patch.object(ai_edit, "_call_model", AsyncMock(return_value=photo((500, 500)))):
            self.assertIsNone(asyncio.run(ai_edit.run_edit(photo((1500, 1000)), "complete", {}, "test")))

    def test_pro_prompt_is_unchanged(self):
        self.assertIn("do NOT add, remove, move or duplicate furniture or objects", ai_edit.build_prompt("auto_pro", {}))
        self.assertNotIn("preserve all furniture, fixtures and intentional decor", ai_edit.build_prompt("complete", {}))


if __name__ == "__main__":
    unittest.main()
