import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import app
import email_service

def run_diagnostic(recipient: str = None):
    print("==================================================")
    print("HLA STUDIO • BACKEND SMTP DIAGNOSTIC SUITE")
    print("==================================================")

    with app.app_context():
        cfg = email_service.get_smtp_config()
        host = cfg.get("host")
        port = cfg.get("port")
        user = cfg.get("user")
        pwd = cfg.get("password")
        from_email = cfg.get("from_email")
        security = cfg.get("security")

        print("\n--- 1. Environment & Configuration Check ---")
        print(f"SMTP_HOST:     {'configured' if host else 'MISSING'}")
        print(f"SMTP_PORT:     {'configured (' + str(port) + ')' if port else 'MISSING'}")
        print(f"SMTP_USERNAME: {'configured' if user else 'MISSING'}")
        print(f"SMTP_PASSWORD: {'configured (masked)' if pwd else 'MISSING'}")
        print(f"SMTP_FROM:     {'configured' if from_email else 'MISSING'}")
        print(f"SMTP_SECURITY: {security.upper() if security else 'NONE'}")

        if not email_service.is_smtp_configured(cfg):
            print("\n[RESULT] SMTP IS NOT CONFIGURED.")
            print("Please fill in SMTP credentials in .env (or configure via Admin UI).")
            print("Required variables: SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM")
            return False

        target = recipient or user or from_email
        print(f"\n--- 2. Connecting to SMTP Server ({host}:{port}) ---")
        res = email_service.test_smtp_connection(target)

        print(f"\n--- 3. SMTP Diagnostic Response ---")
        print(f"Success:              {res.get('success')}")
        print(f"Delivery Mode:        {res.get('delivery_mode')}")
        print(f"SMTP Connection:      {res.get('smtp_connection', 'unknown')}")
        print(f"SMTP Authentication:  {res.get('smtp_authentication', 'unknown')}")
        print(f"SMTP Acceptance:      {res.get('smtp_acceptance', 'unknown')}")
        print(f"Note:                 {res.get('note', '')}")
        print(f"Message:              {res.get('message')}")
        if res.get("diagnostics"):
            print(f"Diagnostics:          {res.get('diagnostics')}")
        if res.get("error"):
            print(f"Underlying Error:     {res.get('error')}")

        return res.get("success")

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "ganesh.raman@analytixhub.ai"
    run_diagnostic(target)
