# 🚀 GCP Deployment Guide for InspectAI

This guide will walk you through deploying InspectAI to Google Cloud Run.

## Prerequisites

1. **Google Cloud Account** - [Sign up here](https://cloud.google.com/free) (free $300 credit)
2. **GCP Project** - Create one in [Google Cloud Console](https://console.cloud.google.com)
3. **gcloud CLI** - Install it (see below)

---

## Step 1: Install Google Cloud CLI

### macOS (using Homebrew):
```bash
brew install google-cloud-sdk
```

### Or download directly:
```bash
curl https://sdk.cloud.google.com | bash
exec -l $SHELL  # Restart shell
```

### Verify installation:
```bash
gcloud --version
```

---

## Step 2: Create a GCP Project

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Click "Select a project" → "New Project"
3. Name it: `inspectai-project` (or any name)
4. Note your **Project ID** (e.g., `inspectai-project-123456`)

---

## Step 3: Enable Billing

1. Go to [Billing](https://console.cloud.google.com/billing)
2. Link your project to a billing account
3. (New accounts get $300 free credit!)

---

## Step 4: Authenticate gcloud

```bash
# Login to your Google account
gcloud auth login

# Set your project
gcloud config set project YOUR_PROJECT_ID

# Verify
gcloud config list
```

---

## Step 5: Set Environment Variables

Before deploying, make sure your `.env` file has these values:

```bash
# In your .env file:
GITHUB_APP_ID=2371321
GITHUB_WEBHOOK_SECRET=your_webhook_secret
BYTEZ_API_KEY=your_bytez_key
```

Export them for the deploy script:
```bash
export GCP_PROJECT_ID="your-project-id"
source .env
export GITHUB_APP_ID GITHUB_WEBHOOK_SECRET BYTEZ_API_KEY
```

---

## Step 6: Deploy to Cloud Run

### Option A: Using the deploy script (Recommended)
```bash
cd /Users/himanshujhawar/Desktop/COMSE6998-015-Fall-2025-Multi-Agent-Code-Review-and-Debugging-Network

# Make script executable
chmod +x scripts/deploy_gcp.sh

# Run deployment
./scripts/deploy_gcp.sh
```

### Option B: Manual deployment
```bash
# Set variables
PROJECT_ID="your-project-id"
REGION="us-central1"
SERVICE_NAME="inspectai-webhook"

# Enable APIs
gcloud services enable run.googleapis.com
gcloud services enable artifactregistry.googleapis.com

# Build and deploy using Cloud Build
gcloud run deploy $SERVICE_NAME \
    --source . \
    --platform managed \
    --region $REGION \
    --allow-unauthenticated
```

---

## Step 7: Get Your Webhook URL

After deployment, you'll see output like:
```
Service URL: https://inspectai-webhook-xxxxx-uc.a.run.app
```

Your webhook URL is:
```
https://inspectai-webhook-xxxxx-uc.a.run.app/webhooks/webhook/github
```

---

## Step 8: Update GitHub App Settings

1. Go to your [GitHub App settings](https://github.com/settings/apps)
2. Click on your app (InspectAI)
3. Update **Webhook URL** to your Cloud Run URL:
   ```
   https://inspectai-webhook-xxxxx-uc.a.run.app/webhooks/webhook/github
   ```
4. Save changes

---

## Step 9: Test the Deployment

1. Go to any PR in a repo where your app is installed
2. Comment: `/InspectAI_review`
3. The bot should respond! 🎉

---

## Setting Up Auto-Deployment (CI/CD)

Once manual deployment works, set up auto-deploy:

### 1. Create a Service Account

```bash
# Create service account
gcloud iam service-accounts create github-deployer \
    --display-name="GitHub Actions Deployer"

# Grant permissions
PROJECT_ID=$(gcloud config get-value project)

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:github-deployer@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/run.admin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:github-deployer@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/storage.admin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:github-deployer@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/artifactregistry.admin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:github-deployer@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/iam.serviceAccountUser"

# Create and download key
gcloud iam service-accounts keys create ~/gcp-key.json \
    --iam-account=github-deployer@$PROJECT_ID.iam.gserviceaccount.com

# Base64 encode the key (for GitHub secrets)
base64 -i ~/gcp-key.json | pbcopy
echo "Key copied to clipboard!"
```

### 2. Add GitHub Secrets

Go to your repo: **Settings → Secrets and variables → Actions**

Add these secrets:

| Secret Name | Value |
|-------------|-------|
| `GCP_PROJECT_ID` | Your GCP project ID |
| `GCP_SA_KEY` | The base64 encoded service account key |
| `GITHUB_APP_ID` | `2371321` |
| `GITHUB_WEBHOOK_SECRET` | Your webhook secret |
| `BYTEZ_API_KEY` | Your Bytez API key |

### 3. Push to Deploy!

Now every push to `main` or `hj2713` branch will auto-deploy:

```bash
git add .
git commit -m "Deploy to Cloud Run"
git push origin hj2713
```

Check the Actions tab in GitHub to see the deployment progress!

---

## Useful Commands

### View logs
```bash
gcloud run services logs read inspectai-webhook --region us-central1
```

### Check service status
```bash
gcloud run services describe inspectai-webhook --region us-central1
```

### Update environment variables
```bash
gcloud run services update inspectai-webhook \
    --set-env-vars "NEW_VAR=value" \
    --region us-central1
```

### Delete the service (if needed)
```bash
gcloud run services delete inspectai-webhook --region us-central1
```

---

## Troubleshooting

### "Permission denied" errors
```bash
gcloud auth login
gcloud auth application-default login
```

### "Billing not enabled" error
Enable billing at: https://console.cloud.google.com/billing

### Container fails to start
Check logs:
```bash
gcloud run services logs read inspectai-webhook --region us-central1 --limit 50
```

### Webhook not working
1. Check the webhook URL is correct
2. Verify the webhook secret matches
3. Check Cloud Run logs for errors

---

## Cost Estimate

Cloud Run pricing (pay-per-use):
- **Free tier**: 2 million requests/month
- **CPU**: $0.00002400 per vCPU-second
- **Memory**: $0.00000250 per GiB-second

For a code review bot with occasional use: **~$0-5/month**
