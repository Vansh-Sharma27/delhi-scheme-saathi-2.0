# Quick Start Guide

This guide walks you through setting up Delhi Scheme Saathi locally.

## Prerequisites

- **Docker** (20.10+) and **Docker Compose** (v2)
- **Python 3.11** (for running scripts outside the container; CI and the image use 3.11.16)
- API keys:
  - [xAI API Key](https://x.ai/) for Grok LLM
  - [Jina AI Key](https://jina.ai/) for primary embeddings and/or [Voyage AI Key](https://www.voyageai.com/) for fallback embeddings
  - [Telegram Bot Token](https://core.telegram.org/bots#creating-a-new-bot) from BotFather

## Step 1: Clone and Configure

```bash
git clone git@github.com:Vansh-Sharma27/delhi-scheme-saathi-2.0.git
cd delhi-scheme-saathi-2.0

# Copy environment template
cp .env.example .env
```

Edit `.env` with your API keys:

```env
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/delhi_scheme_saathi
XAI_API_KEY=xai-your-key-here
XAI_BASE_URL=https://api.x.ai/v1
JINA_API_KEY=jina-your-key-here
VOYAGE_API_KEY=pa-your-key-here
TELEGRAM_BOT_TOKEN=123456:ABC-your-token-here
LOG_LEVEL=INFO
```

Embeddings use Jina first and fall back to Voyage, so `JINA_API_KEY` is the one
to set if you only configure one. See `.env.example` for voice and access
control keys. The current Compose definition forwards Voyage but does not forward Jina, Sarvam, Bhashini, `CHAT_API_KEY`, or `TELEGRAM_WEBHOOK_SECRET`; setting those only in `.env` does not enable them inside that container. Configure the required environment explicitly for the deployment you use.

## Step 2: Start Services

```bash
# Start PostgreSQL and the application
docker compose up -d

# Check container status
docker compose ps

# View logs
docker compose logs -f app
```

On first boot with a fresh Docker volume, the app container auto-loads the bundled seed JSON into PostgreSQL.

The services will be available at:
- **API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **PostgreSQL**: localhost:5434

## Step 3: Verify Setup

```bash
# Health check
curl http://localhost:8000/health

# Expected response:
# {"status":"ok","database":"connected","schemes_count":5}
```

If `schemes_count` is 0 after the first boot, inspect `docker compose logs app` because local seeding should have happened automatically.

## Step 4: Reseed Database (if needed)

Local Docker startup now seeds the database automatically. If you need to reseed from scratch:

```bash
# Stop containers and remove volume
docker compose down -v

# Restart (will reseed on startup)
docker compose up -d
```

## Step 5: Generate Embeddings

Generate semantic embeddings using the existing script and locked dependencies. The script currently requires `VOYAGE_API_KEY` even if the provider client uses Jina first.

```bash
docker compose exec app python scripts/generate_embeddings.py
```

## Step 6: Test the Chat API

```bash
# Send a greeting
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "message": "Namaste"}'

# Ask about widow pension
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "message": "Mera pati guzar gaye, pension chahiye"}'
```

## Step 7: Set Up Telegram Webhook (Optional)

For production Telegram integration:

```bash
# Using ngrok for local testing
ngrok http 8000

# Set webhook (replace with your ngrok URL)
curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook?url=https://xxx.ngrok.io/webhook/telegram"

# Verify webhook
curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo"
```

## Running Tests

```bash
# Create virtual environment and install dev dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

# Run tests
export DATABASE_URL="postgresql://postgres:postgres@localhost:5434/delhi_scheme_saathi"
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=term-missing
```

## Step 8: Voice Integration with Sarvam AI (Optional)

Sarvam AI provides the preferred STT/TTS integration. Check its current account terms before enabling live calls.

### Getting Sarvam AI API Keys

1. Visit [Sarvam AI Console](https://console.sarvam.ai/)
2. Sign up for a developer account
3. Create an API subscription key from the dashboard
4. Add to your `.env` file:

```env
SARVAM_API_KEY=your-api-subscription-key
```

### Alternative: Bhashini (Fallback)

If Sarvam is not configured, the webhook selects Bhashini when its key is set. It does not automatically switch providers after a Sarvam request fails.
1. Visit [Bhashini ULCA Portal](https://bhashini.gov.in/ulca)
2. Register for a developer account
3. Add to `.env`:

```env
BHASHINI_API_KEY=your-api-key
BHASHINI_USER_ID=your-user-id
BHASHINI_ULCA_API_KEY=your-ulca-api-key
```

### Testing Voice Integration

```bash
# With virtual environment activated
python scripts/test_voice_integration.py
```

The script will:
- Test TTS (text-to-speech) in Hindi using Sarvam AI
- Test STT (speech-to-text) transcription
- Test language detection

### Voice Features

When configured, the bot will:
- Accept Hindi voice messages via Telegram
- Transcribe voice to text using Sarvam AI ASR (Saaras v3 model with transcribe mode)
- Respond with both text and audio (TTS via bulbul:v3 model)

**Supported Languages:** Hindi, English, Bengali, Tamil, Telugu, Marathi, Gujarati, Kannada, Malayalam, Punjabi, Odia

**Note:** Voice features gracefully degrade to text-only when no voice API is configured.

## Stopping Services

```bash
# Stop containers (preserves data)
docker compose stop

# Stop and remove containers
docker compose down

# Stop and remove containers + data
docker compose down -v
```

## Troubleshooting

### Database Connection Failed
```bash
# Check if postgres is running
docker compose ps postgres

# Check postgres logs
docker compose logs postgres
```

### Port Already in Use
```bash
# Check what's using port 5434
lsof -i :5434

# Edit docker-compose.yml to use different port
```

### LLM API Errors
- Verify `XAI_API_KEY` is correct
- Check rate limits on your xAI account
- View app logs: `docker compose logs app`

### Embeddings Not Working
- Verify the configured embedding-provider keys and the container environment
- Check if embeddings exist: `docker exec dss-postgres psql -U postgres -d delhi_scheme_saathi -c "SELECT id, description_embedding IS NOT NULL as has_emb FROM schemes;"`
