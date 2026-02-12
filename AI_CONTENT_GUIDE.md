# AI-Generated Content Guide

## Overview

The bot now uses **OpenAI GPT-4o-mini** to generate natural, insightful market updates instead of template-based content. This creates more engaging, context-aware posts that provide real value to your audience.

## Setup

### 1. Get OpenAI API Key

1. Go to https://platform.openai.com/api-keys
2. Create a new API key
3. Copy the key (starts with `sk-proj-...`)

### 2. Add to .env

```bash
nano .env
```

Add your OpenAI API key:
```
OPENAI_API_KEY=sk-proj-your-key-here
OPENAI_MODEL=gpt-4o-mini
OPENAI_MAX_TOKENS=150
```

### 3. Restart Bot

```bash
# If running directly
pkill -f "python -m src.main"
uv run python -m src.main

# If using Docker
docker-compose restart
```

## How It Works

### Data Flow

```
API Data (JSON) → AI Analysis → Natural Language Post
```

**Example:**

**Input (JSON):**
```json
{
  "score": 44.1,
  "rating": "Fear",
  "comparisons": {"previous_close": 44.9},
  "indicators": [
    {"name": "Market Momentum", "rating": "fear"},
    {"name": "VIX", "rating": "fear"}
  ]
}
```

**AI System Prompt:**
```
You are a professional financial analyst writing concise, insightful
market updates for Twitter. Focus on key insights and actionable information.
Use 1-2 essential emojis maximum. Stay under 250 characters.
```

**AI User Prompt:**
```
Write a concise market sentiment update based on this data:

CNN Fear & Greed Index: 44.1/100 (Fear)
Change from yesterday: -0.8 (was 44.9)
Indicators breakdown: 6 showing fear, 3 showing greed out of 9 total

Focus on what this means for traders and market direction.
```

**Output (Twitter Post):**
```
Market sentiment slides into Fear territory at 44.1, down from 44.9.
With 6 of 9 indicators flashing caution, traders should watch support
levels closely. Volatility may persist. 📊

#Stocks #Trading
```

## Content Characteristics

### Twitter Posts (≤280 chars)
- **Concise**: Focus on 1-2 key insights
- **Actionable**: What traders should watch or do
- **Contextual**: Explains significance, not just data
- **Minimal emojis**: 1-2 essential ones (📊 📈 📉)
- **Natural tone**: Professional but conversational

### Discord Posts (3-5 sentences)
- **Detailed analysis**: More context and implications
- **Market context**: How this fits into broader trends
- **Forward-looking**: What to watch for next
- **Markdown formatting**: Bold for emphasis
- **Professional tone**: Deeper insights for serious traders

## AI Prompts by Endpoint

### 1. CNN Fear & Greed
**Focus:** Market sentiment interpretation, what it means for traders

**Sample Output:**
```
Fear index drops to 44.1 as investors grow cautious. The pullback from
44.9 reflects heightened uncertainty, with most indicators signaling
defensive positioning. Watch for support tests. 📊
```

### 2. Reddit Trending
**Focus:** Retail sentiment, momentum analysis

**Sample Output:**
```
Retail traders are laser-focused on $NVDA (847 mentions) and $TSLA (612).
This concentrated attention often precedes volatility—watch volume for
confirmation of moves. 🔥
```

### 3. Top Gainers
**Focus:** Strength of move, sector implications

**Sample Output:**
```
Strong buying in $XYZ (+12.3%), $ABC (+10.1%), $DEF (+9.8%). Tech leading
the charge suggests risk-on sentiment returning. Momentum could continue
if volume holds. 📈
```

### 4. Sector Performance
**Focus:** Market rotation, leadership analysis

**Sample Output:**
```
Technology (+2.8%) and Communication (+1.9%) leading today's rally while
defensive sectors lag. Clear rotation into growth suggests improving risk
appetite. Watch if this holds. 📊
```

### 5. VIX
**Focus:** Volatility implications, risk management

**Sample Output:**
```
VIX at $24.50 (+3.2%) signals rising uncertainty. Not panic levels, but
option premiums are elevated. Consider tightening stops if you're in
momentum plays. ⚠️
```

### 6. Economic Calendar
**Focus:** Key reports to watch, impact potential

**Sample Output:**
```
This week's earnings lineup features $NVDA, $TSLA, and $AAPL—three
mega-caps that could set the tone. Tech sector guidance will be critical
given recent volatility. 📅
```

### 7. SEC Insider
**Focus:** What insider moves signal

**Sample Output:**
```
Notable insider buying in $XYZ ($5.2M) and $ABC ($3.8M). When executives
put personal capital to work, it often signals confidence in near-term
outlook. Worth watching. 👀
```

### 8. Yahoo Quotes
**Focus:** Price action, directional bias

**Sample Output:**
```
Mixed action: $SPY -0.3%, $QQQ +0.5%, $IWM -0.8%. Tech showing relative
strength while small caps lag suggests selective buying. Market lacks
clear direction. 📊
```

## Cost Management

### Pricing (GPT-4o-mini)
- **Input:** ~$0.15 per 1M tokens
- **Output:** ~$0.60 per 1M tokens
- **Per tweet:** ~$0.0001 (very cheap!)

### Estimated Monthly Cost
- 8 endpoints
- Average 12 posts/day per endpoint
- = 96 posts/day × 30 days = 2,880 posts/month
- **Cost:** ~$0.30/month (negligible!)

### If Using GPT-4 Instead
- **Cost:** ~$30/month
- Only use if you need highest quality

## Fallback System

The bot has a **dual-layer system**:

1. **Primary:** AI-generated content (when OpenAI key is set)
2. **Fallback:** Template-based content (if AI fails or no key)

**This ensures the bot always works**, even if:
- OpenAI API is down
- Rate limit is reached
- API key is invalid
- You prefer templates

## Customizing AI Behavior

Edit `src/ai_generator.py` to customize:

### System Prompts
```python
# Make it more aggressive/bullish
"content": "You are an optimistic trader highlighting opportunities..."

# Make it more conservative
"content": "You are a risk-focused analyst emphasizing caution..."

# Change tone
"content": "You are a casual trader using everyday language..."
```

### Temperature (Creativity)
```python
temperature=0.7  # Balanced (default)
temperature=0.3  # More consistent/conservative
temperature=0.9  # More creative/varied
```

### Max Tokens (Length)
```python
max_tokens=150  # Twitter default
max_tokens=200  # Longer Discord posts
max_tokens=100  # Ultra-concise
```

## Quality Control

### What Makes Good AI Posts

✅ **Good:**
- Actionable insights
- Context and implications
- What traders should watch
- Professional but accessible

❌ **Avoid:**
- Just repeating numbers
- Generic advice
- Excessive emojis
- Predictions without caveats

### Monitoring AI Output

Check logs for AI generation:
```bash
tail -f logs/bot_*.log | grep "AI generated"
```

If AI consistently fails:
```bash
# Test OpenAI connection
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

## Advanced: A/B Testing

Want to test AI vs Templates?

1. **Run two bots:**
   - Bot A: `OPENAI_API_KEY=sk-...` (AI)
   - Bot B: `OPENAI_API_KEY=` (Templates)

2. **Compare engagement:**
   - Track likes/retweets for each
   - See which generates more responses
   - Measure click-through rates

3. **Optimize:**
   - Adjust AI prompts based on what works
   - Fine-tune temperature and tokens
   - Test different tones/styles

## Troubleshooting

### AI Generation Not Working

1. **Check API key:**
   ```bash
   echo $OPENAI_API_KEY
   ```

2. **Check logs:**
   ```bash
   grep "AI generation failed" logs/bot_*.log
   ```

3. **Test directly:**
   ```python
   from src.ai_generator import AIContentGenerator
   from src.config import load_config

   config = load_config()
   generator = AIContentGenerator(config)
   # Test generation...
   ```

### Bot Using Templates Instead of AI

- Check if `OPENAI_API_KEY` is set in .env
- Restart bot after adding key
- Look for "OpenAI API key not found" in logs

### Rate Limits

- OpenAI has generous limits for GPT-4o-mini
- If hit, bot automatically falls back to templates
- Consider upgrading OpenAI tier if needed

## Example: Testing AI Generation

```bash
# Create test script
cat > test_ai.py << 'EOF'
import asyncio
from src.config import load_config
from src.ai_generator import AIContentGenerator

async def test():
    config = load_config()
    generator = AIContentGenerator(config)

    # Mock data
    data = {
        "success": True,
        "data": {
            "score": 44.1,
            "rating": "Fear",
            "comparisons": {"previous_close": 44.9},
            "indicators": [
                {"rating": "fear"},
                {"rating": "fear"},
                {"rating": "greed"}
            ]
        }
    }

    tweet = await generator.generate_twitter_post("cnn_fear_greed", data)
    print("AI-Generated Tweet:")
    print("=" * 60)
    print(tweet)
    print("=" * 60)

asyncio.run(test())
EOF

# Run test
uv run python test_ai.py
```

---

**Bottom Line:** AI-generated content makes your posts more engaging and valuable, costs almost nothing, and has automatic fallback to ensure reliability.
