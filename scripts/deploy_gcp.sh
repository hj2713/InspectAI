#!/bin/bash
# =============================================================================
# Deploy InspectAI to Google Cloud Run
# =============================================================================
#
# PREREQUISITES:
#   1. Install gcloud CLI: https://cloud.google.com/sdk/docs/install
#   2. Have a GCP project created
#   3. Have billing enabled on the project
#
# FIRST TIME SETUP (run these commands manually first):
#   gcloud auth login
#   gcloud config set project YOUR_PROJECT_ID
#
# USAGE:
#   ./scripts/deploy_gcp.sh
#
# =============================================================================

set -e  # Exit on any error

# ============= CONFIGURATION =============
# Change these values to match your setup
PROJECT_ID="${GCP_PROJECT_ID:-}"
REGION="${GCP_REGION:-us-central1}"
SERVICE_NAME="inspectai-webhook"
REPO_NAME="inspectai"
IMAGE_NAME="inspectai-webhook"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
echo "=============================================="
echo "   InspectAI - Cloud Run Deployment Script   "
echo "=============================================="
echo -e "${NC}"

# ============= CHECK PREREQUISITES =============

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}❌ gcloud CLI not found!${NC}"
    echo ""
    echo "Install it from: https://cloud.google.com/sdk/docs/install"
    echo ""
    echo "For macOS:"
    echo "  brew install google-cloud-sdk"
    echo ""
    exit 1
fi

# Check if logged in
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>/dev/null | grep -q .; then
    echo -e "${YELLOW}⚠️  Not logged in to gcloud${NC}"
    echo "Running: gcloud auth login"
    gcloud auth login
fi

# Get or set project ID
if [ -z "$PROJECT_ID" ]; then
    echo -e "${YELLOW}Enter your GCP Project ID:${NC}"
    read -r PROJECT_ID
    if [ -z "$PROJECT_ID" ]; then
        echo -e "${RED}❌ Project ID is required${NC}"
        exit 1
    fi
fi

echo -e "${GREEN}✓ Using Project: $PROJECT_ID${NC}"
echo -e "${GREEN}✓ Using Region: $REGION${NC}"
echo ""

# Set the project
gcloud config set project "$PROJECT_ID"

# ============= ENABLE REQUIRED APIs =============
echo -e "${BLUE}📦 Enabling required GCP APIs...${NC}"

gcloud services enable cloudbuild.googleapis.com --quiet
gcloud services enable run.googleapis.com --quiet
gcloud services enable artifactregistry.googleapis.com --quiet
gcloud services enable secretmanager.googleapis.com --quiet

echo -e "${GREEN}✓ APIs enabled${NC}"
echo ""

# ============= CREATE ARTIFACT REGISTRY =============
echo -e "${BLUE}📦 Setting up Artifact Registry...${NC}"

# Check if repo exists, create if not
if ! gcloud artifacts repositories describe $REPO_NAME --location=$REGION &>/dev/null; then
    echo "Creating Artifact Registry repository..."
    gcloud artifacts repositories create $REPO_NAME \
        --repository-format=docker \
        --location=$REGION \
        --description="InspectAI Docker images"
fi

echo -e "${GREEN}✓ Artifact Registry ready${NC}"
echo ""

# ============= STORE SECRETS =============
echo -e "${BLUE}🔐 Setting up secrets...${NC}"

# Function to create or update a secret
create_secret() {
    local secret_name=$1
    local secret_value=$2
    
    if gcloud secrets describe "$secret_name" &>/dev/null; then
        echo "$secret_value" | gcloud secrets versions add "$secret_name" --data-file=-
    else
        echo "$secret_value" | gcloud secrets create "$secret_name" --data-file=-
    fi
}

# Check for required environment variables
if [ -z "$GITHUB_APP_PRIVATE_KEY" ]; then
    # Try to read from .pem file
    PEM_FILE=$(find . -name "*.private-key.pem" -type f | head -1)
    if [ -n "$PEM_FILE" ]; then
        echo "Found private key file: $PEM_FILE"
        GITHUB_APP_PRIVATE_KEY=$(cat "$PEM_FILE")
    else
        echo -e "${YELLOW}⚠️  GITHUB_APP_PRIVATE_KEY not set and no .pem file found${NC}"
        echo "You'll need to add this secret manually later."
    fi
fi

# Create the private key secret if we have it
if [ -n "$GITHUB_APP_PRIVATE_KEY" ]; then
    echo "Creating/updating github-app-private-key secret..."
    if gcloud secrets describe "github-app-private-key" &>/dev/null; then
        echo "$GITHUB_APP_PRIVATE_KEY" | gcloud secrets versions add "github-app-private-key" --data-file=-
    else
        echo "$GITHUB_APP_PRIVATE_KEY" | gcloud secrets create "github-app-private-key" --data-file=-
    fi
    
    # Grant Cloud Run access to the secret
    gcloud secrets add-iam-policy-binding github-app-private-key \
        --member="serviceAccount:$PROJECT_ID-compute@developer.gserviceaccount.com" \
        --role="roles/secretmanager.secretAccessor" --quiet 2>/dev/null || true
fi

echo -e "${GREEN}✓ Secrets configured${NC}"
echo ""

# ============= BUILD AND PUSH IMAGE =============
echo -e "${BLUE}🔨 Building Docker image...${NC}"

IMAGE_URI="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO_NAME/$IMAGE_NAME"

# Configure docker for artifact registry
gcloud auth configure-docker "$REGION-docker.pkg.dev" --quiet

# Build the image
docker build -t "$IMAGE_URI:latest" .

echo -e "${GREEN}✓ Image built${NC}"
echo ""

echo -e "${BLUE}📤 Pushing image to Artifact Registry...${NC}"
docker push "$IMAGE_URI:latest"

echo -e "${GREEN}✓ Image pushed${NC}"
echo ""

# ============= DEPLOY TO CLOUD RUN =============
echo -e "${BLUE}🚀 Deploying to Cloud Run...${NC}"

# Load environment variables from .env if it exists
if [ -f .env ]; then
    source .env
fi

# Build the deploy command
DEPLOY_CMD="gcloud run deploy $SERVICE_NAME \
    --image $IMAGE_URI:latest \
    --platform managed \
    --region $REGION \
    --allow-unauthenticated \
    --memory 512Mi \
    --cpu 1 \
    --timeout 300 \
    --min-instances 0 \
    --max-instances 10"

# Add environment variables if they exist
if [ -n "$GITHUB_APP_ID" ]; then
    DEPLOY_CMD="$DEPLOY_CMD --set-env-vars GITHUB_APP_ID=$GITHUB_APP_ID"
fi

if [ -n "$GITHUB_WEBHOOK_SECRET" ]; then
    DEPLOY_CMD="$DEPLOY_CMD --set-env-vars GITHUB_WEBHOOK_SECRET=$GITHUB_WEBHOOK_SECRET"
fi

if [ -n "$BYTEZ_API_KEY" ]; then
    DEPLOY_CMD="$DEPLOY_CMD --set-env-vars BYTEZ_API_KEY=$BYTEZ_API_KEY"
fi

# Add the private key secret reference
if gcloud secrets describe "github-app-private-key" &>/dev/null; then
    DEPLOY_CMD="$DEPLOY_CMD --set-secrets GITHUB_APP_PRIVATE_KEY=github-app-private-key:latest"
fi

# Execute deployment
eval $DEPLOY_CMD

echo ""
echo -e "${GREEN}✓ Deployment complete!${NC}"
echo ""

# ============= GET SERVICE URL =============
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME \
    --platform managed \
    --region $REGION \
    --format 'value(status.url)')

echo -e "${BLUE}"
echo "=============================================="
echo "   🎉 DEPLOYMENT SUCCESSFUL!"
echo "=============================================="
echo -e "${NC}"
echo ""
echo -e "📍 ${GREEN}Service URL:${NC} $SERVICE_URL"
echo ""
echo -e "🔗 ${GREEN}Webhook URL:${NC} $SERVICE_URL/webhooks/webhook/github"
echo ""
echo -e "📚 ${GREEN}API Docs:${NC} $SERVICE_URL/docs"
echo ""
echo "=============================================="
echo ""
echo -e "${YELLOW}NEXT STEPS:${NC}"
echo "1. Update your GitHub App webhook URL to:"
echo "   $SERVICE_URL/webhooks/webhook/github"
echo ""
echo "2. Test by commenting on a PR:"
echo "   /InspectAI_review"
echo "   /InspectAI_bugs"
echo "   /InspectAI_refactor"
echo ""
echo "=============================================="
