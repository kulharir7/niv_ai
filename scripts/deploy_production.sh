# Production Deployment Script for Niv AI (v0.6.x)
# Usage: ./deploy_production.sh

echo "🚀 Starting Production Deployment of Niv AI..."

# 1. Pull latest changes
git pull upstream main

# 2. Re-install requirements
pip install -r requirements.txt
pip install google-adk

# 3. Migration
bench migrate

# 4. Refresh assets
bench clear-cache
bench build --app niv_ai

# 5. Restart services
bench restart

# 6. Trigger Discovery Agent to update system map
bench execute niv_ai.niv_core.adk.discovery.trigger_discovery

echo "✅ Deployment Complete! Niv AI is now 'Smart from Start'."
