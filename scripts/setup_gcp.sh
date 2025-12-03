#!/bin/bash
# =============================================================================
# One-Time GCP Setup for InspectAI Deployment
# =============================================================================
# Run this ONCE before using GitHub Actions deployment
#
# PREREQUISITES:
#   1. Install gcloud CLI: brew install google-cloud-sdk
#   2. Have a GCP project created with billing enabled
#
# USAGE:
#   chmod +x scripts/setup_gcp.sh
#   ./scripts/setup_gcp.sh
# =============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Login if needed
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>/dev/null | grep -q .; then
    echo -e "${YELLOW}Logging in to Google Cloud...${NC}"
    gcloud auth login
fi

# Get project ID
echo -e "${YELLOW}Enter your GCP Project ID:${NC}"
read -r PROJECT_ID
if [ -z "$PROJECT_ID" ]; then
    echo -e "${RED}❌ Project ID is required${NC}"
    exit 1
fi

REGION="us-central1"
SERVICE_ACCOUNT_NAME="github-actions-deployer"

echo -e "${GREEN}✓ Project: $PROJECT_ID${NC}"
echo -e "${GREEN}✓ Region: $REGION${NC}"
echo ""

# Set project
gcloud config set project "$PROJECT_ID"

# Step 1: Enable required APIs
echo -e "${BLUE}📦 Step 1: Enabling required APIs...${NC}"
gcloud services enable cloudbuild.googleapis.com --quiet
gcloud services enable run.googleapis.com --quiet
gcloud services enable artifactregistry.googleapis.com --quiet
gcloud services enable iam.googleapis.com --quiet
echo -e "${GREEN}✓ APIs enabled${NC}"
echo ""

# Step 2: Create Artifact Registry repository
echo -e "${BLUE}📦 Step 2: Creating Artifact Registry...${NC}"
if ! gcloud artifacts repositories describe inspectai --location=$REGION &>/dev/null; then
    gcloud artifacts repositories create inspectai \
        --repository-format=docker \
        --location=$REGION \
        --description="InspectAI Docker images"
    echo -e "${GREEN}✓ Artifact Registry 'inspectai' created${NC}"
else
    echo -e "${GREEN}✓ Artifact Registry 'inspectai' already exists${NC}"
fi
echo ""

# Step 3: Create Service Account for GitHub Actions
echo -e "${BLUE}🔑 Step 3: Creating Service Account for GitHub Actions...${NC}"
SA_EMAIL="$SERVICE_ACCOUNT_NAME@$PROJECT_ID.iam.gserviceaccount.com"

if ! gcloud iam service-accounts describe "$SA_EMAIL" &>/dev/null; then
    gcloud iam service-accounts create $SERVICE_ACCOUNT_NAME \
        --display-name="GitHub Actions Deployer" \
        --description="Service account for GitHub Actions to deploy to Cloud Run"
    echo -e "${GREEN}✓ Service account created${NC}"
else
    echo -e "${GREEN}✓ Service account already exists${NC}"
fi
echo ""

# Step 4: Grant necessary IAM roles
echo -e "${BLUE}🔐 Step 4: Granting IAM roles...${NC}"

ROLES=(
    "roles/run.admin"
    "roles/iam.serviceAccountUser"
    "roles/artifactregistry.writer"
    "roles/storage.admin"
)

for ROLE in "${ROLES[@]}"; do
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:$SA_EMAIL" \
        --role="$ROLE" \
        --quiet 2>/dev/null
    echo "  ✓ Granted $ROLE"
done
echo -e "${GREEN}✓ IAM roles granted${NC}"
echo ""

# Step 5: Create and download service account key
echo -e "${BLUE}🔑 Step 5: Creating service account key...${NC}"
KEY_FILE="gcp-sa-key.json"
gcloud iam service-accounts keys create "$KEY_FILE" \
    --iam-account="$SA_EMAIL"
echo -e "${GREEN}✓ Key saved to $KEY_FILE${NC}"
echo ""

# Step 6: Generate base64 encoded key for GitHub
echo -e "${BLUE}📋 Step 6: Generating GitHub secret value...${NC}"
BASE64_KEY=$(base64 -i "$KEY_FILE" | tr -d '\n')
echo ""

echo -e "${GREEN}"
echo "=============================================="
echo "   ✅ GCP SETUP COMPLETE!"
echo "=============================================="
echo -e "${NC}"
echo ""
echo -e "${YELLOW}NEXT STEPS:${NC}"
echo ""
echo "1. Go to your GitHub repo: Settings > Secrets and variables > Actions"
echo ""
echo "2. Add these secrets:"
echo ""
echo -e "   ${BLUE}GCP_PROJECT_ID${NC}"
echo "   $PROJECT_ID"
echo ""
echo -e "   ${BLUE}GCP_SA_KEY${NC} (copy this entire value):"
echo ""
echo "$BASE64_KEY"
echo ""
echo ""
echo "3. After adding secrets, push to main branch or manually trigger the workflow"
echo ""
echo "4. Delete the local key file for security:"
echo "   rm $KEY_FILE"
echo ""
echo "=============================================="
