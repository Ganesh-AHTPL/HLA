import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app import app, db
from models import User, Role, PasswordResetToken
from email_service import send_user_welcome_setup_email

def test_invitation_setup_flow():
    with app.app_context():
        db.create_all()

        test_username = 'invite_test_user'
        test_email = 'invitee@enterprise.com'
        User.query.filter((User.username == test_username) | (User.email == test_email)).delete()
        db.session.commit()

        client = app.test_client()

        dummy_user = User(
            username=test_username,
            email=test_email,
            password_hash='placeholder',
            role='architect',
            status='ACTIVE'
        )
        db.session.add(dummy_user)
        db.session.commit()

        import secrets
        from datetime import datetime, timezone, timedelta

        now_utc = datetime.now(timezone.utc)
        token_str = secrets.token_urlsafe(48)
        token = PasswordResetToken(
            user_id=dummy_user.id,
            verified=True,
            verified_at=now_utc,
            reset_token=token_str,
            reset_token_expires_at=now_utc + timedelta(hours=24),
            expires_at=now_utc + timedelta(hours=24),
            used=False
        )
        db.session.add(token)
        db.session.commit()
        assert token.reset_token is not None
        assert not token.used

        setup_link = f"http://localhost:5173/?reset_token={token.reset_token}&username={dummy_user.username}"

        result = send_user_welcome_setup_email(dummy_user, setup_link, expires_minutes=1440)
        assert result.get('status') in ['SENT', 'SIMULATED', 'FAILED']
        assert result.get('setup_link') == setup_link

        res = client.post('/api/auth/reset-password', json={
            'reset_token': token.reset_token,
            'new_password': 'SecureP@ssword2026!',
            'confirm_password': 'SecureP@ssword2026!'
        })
        assert res.status_code == 200
        data = res.get_json()
        assert data.get('success') is True

        login_res = client.post('/api/auth/login', json={
            'username': test_username,
            'password': 'SecureP@ssword2026!'
        })
        assert login_res.status_code == 200
        login_data = login_res.get_json()
        assert login_data.get('user', {}).get('username') == test_username

        # Direct POST /api/governance/users without password
        admin_user = User.query.filter_by(username='admin').first()
        assert admin_user is not None
        login_admin = client.post('/api/auth/login', json={
            'username': 'admin',
            'password': 'admin123'
        })
        token_jwt = login_admin.get_json().get('access_token') or login_admin.get_json().get('token')
        auth_headers = {'Authorization': f'Bearer {token_jwt}'}

        new_gov_user = 'prov_user_test'
        new_gov_email = 'prov@enterprise.com'
        User.query.filter((User.username == new_gov_user) | (User.email == new_gov_email)).delete()
        db.session.commit()

        create_res = client.post('/api/governance/users', headers=auth_headers, json={
            'username': new_gov_user,
            'email': new_gov_email,
            'role': 'architect',
            'status': 'ACTIVE'
        })
        assert create_res.status_code == 201
        create_data = create_res.get_json()
        assert create_data.get('user', {}).get('username') == new_gov_user
        assert 'setup_link' in create_data

        created_user = User.query.filter_by(username=new_gov_user).first()
        assert created_user is not None
        assert created_user.email == new_gov_email

        db_token = PasswordResetToken.query.filter_by(user_id=created_user.id, used=False).first()
        assert db_token is not None

        activate_res = client.post('/api/auth/reset-password', json={
            'reset_token': db_token.reset_token,
            'new_password': 'NewSecurePassword123!',
            'confirm_password': 'NewSecurePassword123!'
        })
        assert activate_res.status_code == 200

        user_login_res = client.post('/api/auth/login', json={
            'username': new_gov_user,
            'password': 'NewSecurePassword123!'
        })
        assert user_login_res.status_code == 200

        PasswordResetToken.query.filter_by(user_id=created_user.id).delete()
        User.query.filter_by(id=created_user.id).delete()
        PasswordResetToken.query.filter_by(user_id=dummy_user.id).delete()
        User.query.filter_by(id=dummy_user.id).delete()
        db.session.commit()

if __name__ == '__main__':
    test_invitation_setup_flow()
    print("ALL INVITATION SETUP TESTS PASSED SUCCESSFULLY!")
