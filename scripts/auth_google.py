from app.settings import settings
from app.google_clients import get_credentials

if __name__ == "__main__":
    creds = get_credentials(settings.google_token_file, settings.google_credentials_file)
    print("Google auth complete. Token saved to", settings.google_token_file)
    print("Scopes:", creds.scopes)
