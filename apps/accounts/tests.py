from unittest.mock import patch

from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import OTPChallenge, OTPPurpose, User

TEST_MAILERS = {
    "default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}
}


@override_settings(MAILERS=TEST_MAILERS)
class AuthenticationFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.password = "Str0ngPassw0rd!"
        self.user_payload = {
            "email": "ada@example.com",
            "password": self.password,
            "first_name": "Ada",
            "last_name": "Lovelace",
        }

    def register(self, otp="123456"):
        with patch("accounts.services.generate_otp_code", return_value=otp):
            response = self.client.post(reverse("auth-register"), self.user_payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        return User.objects.get(email="ada@example.com")

    def verify_email(self, otp="123456"):
        response = self.client.post(
            reverse("auth-verify-email"),
            {"email": "ada@example.com", "otp": otp},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_register_sends_verification_email(self):
        self.register()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("123456", mail.outbox[0].body)
        user = User.objects.get(email="ada@example.com")
        self.assertFalse(user.is_email_verified)
        self.assertTrue(user.is_first_login)

    def test_unverified_user_cannot_login(self):
        self.register()
        response = self.client.post(
            reverse("auth-login"),
            {"email": "ada@example.com", "password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_first_login_requires_otp_then_issues_tokens(self):
        self.register()
        self.verify_email()

        with patch("accounts.services.generate_otp_code", return_value="654321"):
            login_response = self.client.post(
                reverse("auth-login"),
                {"email": "ada@example.com", "password": self.password},
                format="json",
            )
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        self.assertTrue(login_response.data["otp_required"])
        self.assertNotIn("access", login_response.data)

        verify_response = self.client.post(
            reverse("auth-verify-first-login"),
            {"email": "ada@example.com", "otp": "654321"},
            format="json",
        )
        self.assertEqual(verify_response.status_code, status.HTTP_200_OK)
        self.assertIn("access", verify_response.data)
        self.assertIn("refresh", verify_response.data)
        user = User.objects.get(email="ada@example.com")
        self.assertFalse(user.is_first_login)

        second_login = self.client.post(
            reverse("auth-login"),
            {"email": "ada@example.com", "password": self.password},
            format="json",
        )
        self.assertEqual(second_login.status_code, status.HTTP_200_OK)
        self.assertIn("access", second_login.data)
        self.assertFalse(second_login.data.get("otp_required", False))

    def test_invalid_otp_is_rejected(self):
        self.register()
        response = self.client.post(
            reverse("auth-verify-email"),
            {"email": "ada@example.com", "otp": "000000"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_password_reset_flow(self):
        self.register()
        self.verify_email()
        with patch("accounts.services.generate_otp_code", return_value="111222"):
            forgot = self.client.post(
                reverse("auth-password-forgot"),
                {"email": "ada@example.com"},
                format="json",
            )
        self.assertEqual(forgot.status_code, status.HTTP_200_OK)

        new_password = "N3wStr0ngPass!"
        reset = self.client.post(
            reverse("auth-password-reset"),
            {
                "email": "ada@example.com",
                "otp": "111222",
                "new_password": new_password,
            },
            format="json",
        )
        self.assertEqual(reset.status_code, status.HTTP_200_OK)
        user = User.objects.get(email="ada@example.com")
        self.assertTrue(user.check_password(new_password))

    def test_forgot_password_does_not_reveal_missing_accounts(self):
        response = self.client.post(
            reverse("auth-password-forgot"),
            {"email": "missing@example.com"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 0)

    def test_me_and_password_change_and_logout(self):
        self.register()
        self.verify_email()
        with patch("accounts.services.generate_otp_code", return_value="654321"):
            self.client.post(
                reverse("auth-login"),
                {"email": "ada@example.com", "password": self.password},
                format="json",
            )
        tokens = self.client.post(
            reverse("auth-verify-first-login"),
            {"email": "ada@example.com", "otp": "654321"},
            format="json",
        ).data

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        me = self.client.get(reverse("auth-me"))
        self.assertEqual(me.status_code, status.HTTP_200_OK)
        self.assertEqual(me.data["email"], "ada@example.com")

        change = self.client.post(
            reverse("auth-password-change"),
            {
                "current_password": self.password,
                "new_password": "An0therStr0ng!",
            },
            format="json",
        )
        self.assertEqual(change.status_code, status.HTTP_200_OK)

        logout = self.client.post(
            reverse("auth-logout"),
            {"refresh": tokens["refresh"]},
            format="json",
        )
        self.assertEqual(logout.status_code, status.HTTP_200_OK)

        refresh = self.client.post(
            reverse("auth-token-refresh"),
            {"refresh": tokens["refresh"]},
            format="json",
        )
        self.assertEqual(refresh.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_account_lockout_after_failed_logins(self):
        self.register()
        self.verify_email()
        with patch("accounts.services.generate_otp_code", return_value="654321"):
            self.client.post(
                reverse("auth-login"),
                {"email": "ada@example.com", "password": self.password},
                format="json",
            )
        self.client.post(
            reverse("auth-verify-first-login"),
            {"email": "ada@example.com", "otp": "654321"},
            format="json",
        )

        for _ in range(5):
            response = self.client.post(
                reverse("auth-login"),
                {"email": "ada@example.com", "password": "wrong-password"},
                format="json",
            )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        user = User.objects.get(email="ada@example.com")
        self.assertTrue(user.is_locked())
        self.assertGreater(user.locked_until, timezone.now())

    def test_otp_hash_is_stored_not_plaintext(self):
        self.register(otp="123456")
        challenge = OTPChallenge.objects.get(purpose=OTPPurpose.EMAIL_VERIFICATION)
        self.assertNotEqual(challenge.code_hash, "123456")
        self.assertEqual(len(challenge.code_hash), 64)
