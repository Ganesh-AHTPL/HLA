import os

keys = [
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USERNAME",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "SMTP_FROM",
    "SMTP_FROM_EMAIL",
    "SMTP_USE_TLS",
    "SMTP_TLS",
    "SMTP_USE_SSL",
    "SMTP_SECURITY"
]

for k in keys:
    val = os.getenv(k)
    status = "configured" if val and val.strip() else "missing"
    print(f"{k}: {status}")
