
"""
Google Calendar OAuth2 authentication script.
Robust implementation for Docker environments.

Usage:
    python scripts/authenticate_calendar.py
    python scripts/authenticate_calendar.py --force
"""
import os
import sys
import json
import argparse
from pathlib import Path

# Allow OAuth over HTTP (for local development)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# Pinned absolute paths for Docker compatibility
TOKEN_PATH = Path("/app/credentials/token.json")
CLIENT_SECRETS_PATH = Path("/app/credentials/client_secrets.json")
SCOPES = ['https://www.googleapis.com/auth/calendar']


def load_token():
    """Load token from file if exists."""
    if TOKEN_PATH.exists():
        try:
            with open(TOKEN_PATH, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load token: {e}")
    return None


def save_token(token_data):
    """Save token to file."""
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TOKEN_PATH, 'w') as f:
        json.dump(token_data, f, indent=2)
    print(f"Token saved to {TOKEN_PATH}")


def refresh_token_if_needed(credentials):
    """Refresh token if expired."""
    from google.auth.transport.requests import Request
    
    if credentials and credentials.expired and credentials.refresh_token:
        print("Token expired, refreshing...")
        try:
            credentials.refresh(Request())
            save_token({
                'token': credentials.token,
                'refresh_token': credentials.refresh_token,
                'token_uri': credentials.token_uri,
                'client_id': credentials.client_id,
                'client_secret': credentials.client_secret,
                'scopes': list(credentials.scopes)
            })
            print("Token refreshed successfully")
            return True
        except Exception as e:
            print(f"Token refresh failed: {e}")
            return False
    return True


def authenticate():
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not CLIENT_SECRETS_PATH.exists():
        print(f"ERROR: client_secrets.json not found at {CLIENT_SECRETS_PATH}")
        sys.exit(1)

    print("=" * 50)
    print("Google Calendar OAuth2 Authentication")
    print("=" * 50)

    # 1. Crear flow PRIMERO
    flow = InstalledAppFlow.from_client_secrets_file(
        str(CLIENT_SECRETS_PATH),
        SCOPES
    )

    # 2. Setear redirect_uri
    flow.redirect_uri = "urn:ietf:wg:oauth:2.0:oob"

    # 3. Generar URL
    auth_url, _ = flow.authorization_url(
        access_type='offline',
        prompt='consent'
    )

    print("\nOpen this URL in your browser:\n")
    print(auth_url)

    # 4. Input manual
    code = input("\nPaste the authorization code here: ").strip()

    # 5. Intercambio por token
    flow.fetch_token(code=code)

    credentials = flow.credentials

    save_token({
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': list(credentials.scopes)
    })

    print("Authentication successful!")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Google Calendar OAuth2 Authentication')
    parser.add_argument('--force', action='store_true', help='Force re-authentication')
    args = parser.parse_args()
    
    # Check for existing token and refresh if needed
    if not args.force:
        token_data = load_token()
        if token_data and 'token' in token_data:
            print(f"Found existing token at {TOKEN_PATH}")
            try:
                from google.oauth2.credentials import Credentials
                creds = Credentials(token=token_data.get('token'))
                if refresh_token_if_needed(creds):
                    print("Token is valid, no re-authentication needed")
                    return
            except Exception as e:
                print(f"Could not refresh token: {e}")
    
    # Run OAuth flow
    authenticate()
    print("Authentication complete!")


if __name__ == "__main__":
    main()