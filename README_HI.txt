TELEGRAM CHATGPT BOT - SETUP GUIDE

Is project mein ye features hain:
- AI text chat aur short-term conversation memory
- Photo/image understanding
- AI image generation (/image prompt)
- Voice message transcription + AI answer
- Text-to-speech (/voice text)
- PDF/TXT reading aur summary
- Web search mode (/web question)
- Basic admin stats (/stats)

IMPORTANT:
1. Ye ChatGPT ke har official feature ka exact clone nahi hai.
2. OpenAI API aur Telegram dono ki usage limits/pricing alag hain.
3. API keys ko kisi ke saath share mat karna.
4. Chat history abhi RAM mein hai; bot restart hone par clear ho jayegi.
5. Scanned PDF OCR, DOCX/XLSX, video understanding, live voice conversation,
   user database, subscription/payment aur robust admin dashboard is starter
   version mein included nahi hain.

SETUP:
1. Telegram mein @BotFather kholo.
2. /newbot bhejo, bot ka name aur username set karo.
3. BotFather ka token copy karo.
4. OpenAI platform par API key banao aur billing/credits configure karo.
5. Is folder mein .env.example ki copy bana kar uska naam .env rakho.
6. .env mein Telegram token aur OpenAI API key paste karo.
7. Terminal mein:
   pip install -r requirements.txt
   python bot.py
8. Telegram par apne bot ko /start bhejo.

ANDROID:
Termux install karke Python environment set kar sakte ho, ya project ko
Python-supporting hosting service par deploy kar sakte ho. Phone band ya
Termux stop hone par local bot offline ho sakta hai. 24/7 ke liye hosting chahiye.

COMMANDS:
 /start
 /help
 /new
 /usage
 /image a beautiful futuristic city
 /web latest AI news
 /voice Hello, how are you?

WEB SEARCH:
Bot web mode mein Responses API ke web_search tool ka use karta hai.
Agar tumhare account/model mein tool access na ho, /web request error de sakta hai.

SAFETY:
- API keys ko GitHub ya public group mein upload mat karna.
- Public bot ke liye per-user rate limits, spending caps, abuse controls,
  persistent database aur privacy notice add karna zaroori hai.
