$headers = @{ "X-API-Key" = "demo-public-key" }
$body = @{
  tenant_id = "demo-tenant"
  knowledge_base_id = "kb_support"
  name = "support"
  description = "support knowledge base"
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/v1/knowledge-bases" -Headers $headers -ContentType "application/json" -Body $body

