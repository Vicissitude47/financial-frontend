# Financial Management App

A personal financial management application built with Streamlit, featuring Google OAuth authentication and AWS S3 integration for data storage.

## Features

- 🔐 Secure Google OAuth authentication
- 📊 Transaction data visualization
- 💰 Expense categorization with rules
- 📈 Monthly spending analysis
- 💳 Credit card usage tracking
- ☁️ Cloud storage with AWS S3
- 🌐 Multi-currency support

## Setup Instructions

### Prerequisites

- Python 3.8 or higher
- AWS Account with S3 access
- Google Cloud Project with OAuth 2.0 credentials

### Local Development Setup

1. Clone the repository:
```bash
git clone https://github.com/Vicissitude47/financial-frontend.git
cd financial-frontend
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create `.streamlit/secrets.toml` file with the following structure:
```toml
# Google OAuth Credentials
[google_oauth]
client_id = "YOUR_GOOGLE_CLIENT_ID"
client_secret = "YOUR_GOOGLE_CLIENT_SECRET"
redirect_uri = "http://localhost:8501/oauth2callback"  # For local development
allowed_emails = ["your.email@gmail.com"]

# AWS Configuration
[aws]
region = "YOUR_AWS_REGION"
access_key_id = "YOUR_AWS_ACCESS_KEY"
secret_access_key = "YOUR_AWS_SECRET_KEY"
bucket_name = "YOUR_S3_BUCKET_NAME"
```

5. Run the application:
```bash
streamlit run transaction_manager.py
```

### Streamlit Cloud Deployment

1. Fork or push the repository to your GitHub account

2. Deploy on Streamlit Cloud:
   - Connect your GitHub repository
   - Set the main file path as `transaction_manager.py`
   - Configure secrets in Streamlit Cloud settings (copy from your local `.streamlit/secrets.toml`)
   - Update the `redirect_uri` in Google Cloud Console to match your Streamlit Cloud URL

3. Update Google OAuth settings:
   - Add your Streamlit Cloud URL to authorized redirect URIs in Google Cloud Console
   - Format: `https://your-app-name.streamlit.app/oauth2callback`

## Project Structure

- `transaction_manager.py`: Main application file with UI and business logic
- `auth.py`: Google OAuth authentication implementation
- `requirements.txt`: Python dependencies
- `.streamlit/secrets.toml`: Configuration file (not in repository)

## Security Notes

- Never commit `.streamlit/secrets.toml` to version control
- Keep your AWS credentials secure
- Restrict Google OAuth to specific email addresses
- Use environment-specific configurations for local development and production

## Data Storage

- Transaction data is stored in AWS S3 as CSV files
- Categories and rules are stored as JSON files
- All data is versioned and encrypted in S3

## Contributing

1. Create a new branch for your feature
2. Make your changes
3. Submit a pull request

## License

This project is private and not open for public use. 