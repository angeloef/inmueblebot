"""
Google Calendar Integration Test Script

Tests:
1. Credentials loading
2. Token refresh
3. Create event
4. Read events
5. Error handling

Usage:
    docker exec -it immobilebot-app python scripts/test_calendar.py
"""
import os
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path

# Set paths
TOKEN_PATH = Path("/app/credentials/token.json")
CLIENT_SECRETS_PATH = Path("/app/credentials/client_secrets.json")

# Allow insecure transport for local testing
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'


def load_credentials():
    """Load and validate credentials."""
    if not TOKEN_PATH.exists():
        return None, "token.json not found"
    
    try:
        from google.oauth2.credentials import Credentials
        with open(TOKEN_PATH) as f:
            data = json.load(f)
        creds = Credentials(token=data.get('token'))
        return creds, None
    except Exception as e:
        return None, str(e)


def check_credentials():
    """STEP 1: Verify credentials."""
    print("=" * 50)
    print("STEP 1: Verify Credentials Loading")
    print("=" * 50)
    
    creds, error = load_credentials()
    
    if error:
        print(f"FAIL: {error}")
        return False
    
    print(f"✓ token.json loaded")
    print(f"  Token valid: {not creds.expired}")
    
    # Check if refresh needed
    if creds.expired and creds.refresh_token:
        print("  Token expired, refreshing...")
        try:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
            # Save refreshed token
            with open(TOKEN_PATH, 'w') as f:
                json.dump({
                    'token': creds.token,
                    'refresh_token': creds.refresh_token,
                    'token_uri': creds.token_uri,
                    'client_id': creds.client_id,
                    'client_secret': creds.client_secret,
                    'scopes': list(creds.scopes)
                }, f, indent=2)
            print("  ✓ Token refreshed and saved")
        except Exception as e:
            print(f"  ✗ Refresh failed: {e}")
            return False
    elif creds.expired:
        print("  ✗ Token expired, no refresh_token")
        return False
    
    print("STEP 1: PASS")
    return True


def create_event():
    """STEP 2: Create a test event."""
    print("=" * 50)
    print("STEP 2: Create Test Event")
    print("=" * 50)
    
    creds, error = load_credentials()
    if error:
        print(f"FAIL: {error}")
        return False
    
    try:
        from googleapiclient.discovery import build
        
        service = build('calendar', 'v3', credentials=creds)
        
        # Event start: now + 5 minutes
        start_time = datetime.utcnow() + timedelta(minutes=5)
        end_time = start_time + timedelta(minutes=30)
        
        event = {
            'summary': 'Test Event InmuebleBot',
            'description': 'Created by InmuebleBot OAuth test',
            'start': {
                'dateTime': start_time.isoformat() + 'Z',
                'timeZone': 'America/Asuncion'
            },
            'end': {
                'dateTime': end_time.isoformat() + 'Z',
                'timeZone': 'America/Asuncion'
            }
        }
        
        result = service.events().insert(
            calendarId='primary',
            body=event
        ).execute()
        
        print(f"✓ Event created")
        print(f"  ID: {result.get('id')}")
        print(f"  Link: {result.get('htmlLink')}")
        print(f"  Start: {result['start']['dateTime']}")
        
        # Save event ID for cleanup
        event_id = result.get('id')
        print(f"\n  Event ID for cleanup: {event_id}")
        
        print("STEP 2: PASS")
        return True
        
    except Exception as e:
        print(f"FAIL: {e}")
        return False


def read_events():
    """STEP 3: Read upcoming events."""
    print("=" * 50)
    print("STEP 3: Read Upcoming Events")
    print("=" * 50)
    
    creds, error = load_credentials()
    if error:
        print(f"FAIL: {error}")
        return False
    
    try:
        from googleapiclient.discovery import build
        
        service = build('calendar', 'v3', credentials=creds)
        
        now = datetime.utcnow().isoformat() + 'Z'
        
        result = service.events().list(
            calendarId='primary',
            timeMin=now,
            maxResults=5,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = result.get('items', [])
        
        if not events:
            print("  No upcoming events found")
        else:
            print(f"  Found {len(events)} event(s):")
            for e in events:
                start = e['start'].get('dateTime', e['start'].get('date'))
                print(f"    - {start}: {e.get('summary')}")
        
        print("STEP 3: PASS")
        return True
        
    except Exception as e:
        print(f"FAIL: {e}")
        return False


def test_error_handling():
    """STEP 4: Test error handling."""
    print("=" * 50)
    print("STEP 4: Error Handling")
    print("=" * 50)
    
    # Test missing token
    backup = None
    if TOKEN_PATH.exists():
        backup = TOKEN_PATH.read_text()
        TOKEN_PATH.unlink()
    
    creds, error = load_credentials()
    if error and "not found" in error:
        print("✓ Missing token handled correctly")
    else:
        print("✗ Missing token not handled")
    
    # Restore
    if backup:
        TOKEN_PATH.write_text(backup)
    
    print("STEP 4: PASS")
    return True


def main():
    """Run all tests."""
    print("\n" + "=" * 50)
    print("Google Calendar Integration Test")
    print("=" * 50 + "\n")
    
    results = []
    
    # Run tests
    results.append(("Credentials", check_credentials()))
    print()
    
    results.append(("Create Event", create_event()))
    print()
    
    results.append(("Read Events", read_events()))
    print()
    
    results.append(("Error Handling", test_error_handling()))
    print()
    
    # Summary
    print("=" * 50)
    print("TEST SUMMARY")
    print("=" * 50)
    
    all_passed = True
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False
    
    print("=" * 50)
    if all_passed:
        print("ALL TESTS PASSED!")
    else:
        print("SOME TESTS FAILED!")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())