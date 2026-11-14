import unittest
from auth import generate_auth_token, verify_token
from user_service import UserService
from utils import format_username, sanitize_input


class TestAuthAndUser(unittest.TestCase):
    def setUp(self):
        self.service = UserService()

    def test_token_generation_and_verification(self):
        token = generate_auth_token("alice")
        self.assertTrue(verify_token(token))

    def test_authentication_success(self):
        token = self.service.authenticate("alice")
        self.assertTrue(self.service.authorize(token, "admin"))

    def test_authentication_invalid_user(self):
        with self.assertRaises(PermissionError):
            self.service.authenticate("unknown_user")

    def test_utils_formatting(self):
        self.assertEqual(format_username("  Alice  "), "alice")
        self.assertEqual(sanitize_input("<script>"), "&lt;script&gt;")


if __name__ == "__main__":
    unittest.main()
