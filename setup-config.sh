#!/bin/bash
# Setup script: creates ~/.agent-catalogue/ settings for this project

mkdir -p ~/.agent-catalogue

# Settings: Anthropic for LLM, Azure OpenAI for embeddings (RBAC)
cat > ~/.agent-catalogue/settings.yaml << 'SETTINGS'
providers:
  - module: provider-anthropic
    config:
      api_key: ${ANTHROPIC_API_KEY}
      default_model: claude-sonnet-4-20250514
      priority: 1

embeddings:
  endpoint: https://amplifier-teamtracking-foundry.cognitiveservices.azure.com/
  deployment: text-embedding-3-large
  model: text-embedding-3-large
  dimensions: 3072
  api_version: "2024-12-01-preview"
  auth: rbac

storage:
  db_path: ./data/catalogue.duckdb

server:
  host: 127.0.0.1
  port: 8000
  debug: true
SETTINGS

echo "Created ~/.agent-catalogue/settings.yaml"

# Keys: prompt for Anthropic API key if not already set
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo ""
    echo "Anthropic API key not found in environment."
    echo "Either:"
    echo "  1. export ANTHROPIC_API_KEY=sk-ant-..."
    echo "  2. Or add it to ~/.agent-catalogue/keys.env:"
    echo '     echo '"'"'ANTHROPIC_API_KEY="sk-ant-..."'"'"' >> ~/.agent-catalogue/keys.env'
    echo '     chmod 600 ~/.agent-catalogue/keys.env'
else
    echo "ANTHROPIC_API_KEY found in environment - good to go."
fi

echo ""
echo "Done. Run: agent-catalogue serve"
