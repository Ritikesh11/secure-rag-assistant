# Azure Container Apps Deployment

This is the intended production path for the Northstar Analytics RAG chatbot.

## Azure Resources

- Azure Container Registry for the Docker image.
- Azure Container Apps for the Streamlit service.
- Azure Key Vault for `GROQ_API_KEY`, `LANGCHAIN_API_KEY`, and related secrets.
- Azure Files or a managed vector database for persistent vector storage.
- Azure Monitor and Log Analytics for application logs and cost alerts.

## Deployment Flow

```bash
az group create --name northstar-rag-rg --location eastus
az acr create --resource-group northstar-rag-rg --name northstarragrbac --sku Basic
az acr build --registry northstarragrbac --image northstar-rag-rbac:latest .
az containerapp env create --name northstar-rag-env --resource-group northstar-rag-rg --location eastus
az containerapp create \
  --name northstar-rag-chatbot \
  --resource-group northstar-rag-rg \
  --environment northstar-rag-env \
  --image northstarragrbac.azurecr.io/northstar-rag-rbac:latest \
  --target-port 8501 \
  --ingress external \
  --secrets groq-api-key="<from-key-vault>" \
  --env-vars GROQ_API_KEY=secretref:groq-api-key
```

## Production Notes

- Replace demo users with SSO claims from Microsoft Entra ID.
- Map Entra groups to `UserProfile` departments and roles.
- Use private networking for the vector database.
- Send `logs/usage.csv` events to Azure Monitor or Application Insights.
- Create an alert when daily `total_cost_usd` exceeds the configured threshold.
- Keep the CI eval job as a required deployment check.

