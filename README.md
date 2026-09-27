# Fund Disbursement

Django API for fund disbursement, starting with a JWT authentication backend.

## Auth design

- Class-based models and serializers
- Function-based views and service functions
- Email-first custom user
- Hashed, expiring OTPs with attempt limits
- OTP emails for signup verification, first login, and password reset
- JWT access/refresh tokens with rotation and blacklist

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

During local development, emails are printed to the console. Switch `EMAIL_BACKEND` to `django.core.mail.backends.smtp.EmailBackend` in `.env` when you have SMTP credentials.

## Auth endpoints

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| POST | `/api/v1/auth/register/` | No | Create account and email a verification OTP |
| POST | `/api/v1/auth/verify-email/` | No | Confirm the email OTP |
| POST | `/api/v1/auth/login/` | No | Password login. First login also emails an OTP |
| POST | `/api/v1/auth/verify-first-login/` | No | Confirm first-login OTP and receive JWT tokens |
| POST | `/api/v1/auth/resend-otp/` | No | Resend an OTP (`email_verification`, `first_login`, `password_reset`) |
| POST | `/api/v1/auth/password/forgot/` | No | Email a password-reset OTP |
| POST | `/api/v1/auth/password/reset/` | No | Set a new password with the OTP |
| POST | `/api/v1/auth/password/change/` | Yes | Change password while signed in |
| POST | `/api/v1/auth/token/refresh/` | No | Rotate the refresh token |
| POST | `/api/v1/auth/logout/` | Yes | Blacklist the refresh token |
| GET/PATCH | `/api/v1/auth/me/` | Yes | Read or update the current profile |

## First-time login

1. Register with email and password.
2. Verify the emailed 6-digit code.
3. Sign in. The API emails a first-login OTP instead of returning tokens.
4. Submit that OTP to `/verify-first-login/`. After that, password login returns JWTs directly.

## Tests

```bash
python manage.py test accounts
```
