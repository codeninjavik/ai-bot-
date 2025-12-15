import logging
import asyncio
from io import BytesIO

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode, ChatAction
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from telegram.error import BadRequest
from groq import Groq

# Optional nice console output for the operator (uses `rich` if installed)
try:
    from rich.console import Console
    console = Console()
except Exception:
    console = None

# Optional: generate syntax-highlighted code images using Pygments
try:
    from pygments import highlight
    from pygments.lexers import guess_lexer, get_lexer_by_name
    from pygments.formatters import ImageFormatter
    PYGMENTS_AVAILABLE = True
except Exception:
    PYGMENTS_AVAILABLE = False

# ================= 🔧 CONFIGURATION =================

# 🔴 1. TELEGRAM BOT TOKEN (From @BotFather)
TELEGRAM_BOT_TOKEN = "8250223012:AAGcHRkFqM4laaboLhbDVZ_fHdDYAHH_lIk"

# 🟢 2. GROQ API KEY
GROQ_API_KEY = "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"

# 📢 3. CHANNEL & BRANDING
REQUIRED_CHANNEL = "@Codeninja_vik"
OWNER_CONTACT = "@Codeninja_vik"
BOT_NAME = "Codeninja AI"
OWNER_INSTAGRAM = "codeninjavik"
OWNER_YOUTUBE = "codeninjavik"

# ================= 🧠 AI BRAIN SETUP =================
client = Groq(api_key=GROQ_API_KEY)
# Using the stable, fast Llama 3 model
GROQ_MODEL = "llama-3.3-70b-versatile"

# 🔥 SYSTEM PROMPT (Controls Bot Personality & Format)
SYSTEM_PROMPT = """
You are Codeninja AI, an elite Developer & Cyber-Security Coding Assistant.

STRICT FORMATTING RULES:
1. **MARKDOWN ONLY**: You must use Markdown syntax.
   - Use `*bold text*` for headers or emphasis (Do NOT use **).
   - Use triple backticks for code blocks (e.g. ```python ... ```).
   - Use bullet points (•) for lists.
2. **LINE BY LINE**: Keep responses structured, clean, and spaced out.
3. **NO UNDERSCORES IN TEXT**: Avoid using underscores (_) in normal text because it breaks Telegram formatting. Use hyphens (-) instead.
4. **PERSONALITY**: Smart, Concise, Professional, "Hacker" style.

If asked for code: Provide the logic first, then the code block.
"""

# ================= 📝 LOGGING =================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ================= 🛠 HELPER FUNCTIONS =================

def get_watermark():
    """Returns the official footer/watermark."""
    return (
        f"\n\n──────────────────────\n"
        f"🤖 {BOT_NAME} • Official Channel: {REQUIRED_CHANNEL}\n"
        f"👨‍💻 Dev: {OWNER_CONTACT}\n"
        f"📸 Instagram: @{OWNER_INSTAGRAM}  •  ▶️ YouTube: @{OWNER_YOUTUBE}"
    )


def get_watermark_markdown():
    """Return a Markdown version of the watermark (used when sending Markdown)."""
    return (
        f"\n\n──────────────────────\n"
        f"🤖 *{BOT_NAME}* • {REQUIRED_CHANNEL}\n"
        f"👨‍💻 Dev: {OWNER_CONTACT}\n"
        f"📸 Instagram: @{OWNER_INSTAGRAM} • ▶️ YouTube: @{OWNER_YOUTUBE}"
    )

async def check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Checks if the user is a member of the required channel."""
    user_id = update.effective_user.id
    try:
        member = await context.bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
        if member.status in ['left', 'kicked']:
            return False
        return True
    except Exception as e:
        # If bot isn't admin or error occurs, allow access (Fail-Safe)
        logging.error(f"⚠️ Channel Check Error: {e}")
        return True

async def get_ai_response(prompt_text):
    """Sends prompt to Groq API and returns response."""
    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt_text}
            ],
            model=GROQ_MODEL,
            temperature=0.7, 
            max_tokens=2048
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        return f"⚡ *System Error:* Connection interrupted.\nError: {str(e)}"

async def send_smart_response(update: Update, text: str, prefer_image_for_code: bool = True):
    """
    Sends message with MARKDOWN formatting + Watermark.
    - If the text contains large code blocks or markdown code fences and Pygments is available,
      it will send a syntax-highlighted image instead (better colors on Telegram).
    - Falls back to Markdown or plain text on errors.
    """
    final_text = text + get_watermark_markdown()

    # If Pygments is available and text looks like code, try sending an image
    is_code_like = '```' in text or (len(text) > 800 and '\n' in text and any(k in text.lower() for k in ['def ', 'class ', 'import ', 'function', '{', ';']))
    if prefer_image_for_code and PYGMENTS_AVAILABLE and is_code_like:
        try:
            img = render_code_image(text)
            img.seek(0)
            caption = f"{BOT_NAME} • Code (image)" + get_watermark()
            await update.message.reply_photo(photo=img, caption=caption)
            return
        except Exception as e:
            logging.warning(f"Code image generation failed: {e}")

    try:
        await update.message.reply_text(final_text, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
    except BadRequest:
        # Try HTML version
        try:
            html_text = text + get_watermark()
            await update.message.reply_text(html_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            return
        except BadRequest:
            try:
                logging.warning("Markdown/HTML failed, sending plain text and watermark separately.")
                await update.message.reply_text(text, parse_mode=None, disable_web_page_preview=True)
                await update.message.reply_text(get_watermark(), parse_mode=None)
            except Exception as e:
                logging.error(f"Final Send Error: {e}")
    except Exception as e:
        logging.error(f"Unexpected Error: {e}")


# ====== Color / Theme helpers ======
CHAT_THEMES = {}  # simple in-memory map: chat_id -> pygments style name

DEFAULT_STYLE = 'monokai'
STYLE_MAP = {
    'red': 'fruity',
    'blue': 'monokai',
    'pink': 'pastie',
    'default': DEFAULT_STYLE,
}

def render_code_image(code_text: str, style: str = None) -> BytesIO:
    """Render syntax-highlighted PNG of given code using Pygments ImageFormatter.
    Returns a BytesIO containing PNG data. Raises if pygments not available.
    """
    if not PYGMENTS_AVAILABLE:
        raise RuntimeError('Pygments not installed')

    # Try to extract code from triple backticks if present
    if '```' in code_text:
        try:
            parts = code_text.split('```')
            # prefer the first fenced block or last non-empty
            fenced = next((p for p in parts if p.strip() and '\n' in p), parts[-1])
            # Sometimes the first line is language name
            if '\n' in fenced:
                first, rest = fenced.split('\n', 1)
                if first.strip().isalpha():
                    lang_hint = first.strip()
                    code = rest
                else:
                    code = fenced
            else:
                code = fenced
        except Exception:
            code = code_text
    else:
        code = code_text

    # Guess lexer
    try:
        lexer = guess_lexer(code)
    except Exception:
        try:
            lexer = get_lexer_by_name('python')
        except Exception:
            lexer = None

    style_name = style or DEFAULT_STYLE
    formatter = ImageFormatter(style=style_name, font_name='DejaVu Sans Mono', line_numbers=False, font_size=14)
    data = highlight(code, lexer, formatter) if lexer else highlight(code, get_lexer_by_name('text'), formatter)

    bio = BytesIO()
    bio.write(data)
    bio.name = 'code.png'
    bio.seek(0)
    return bio


def extract_fenced_code(response: str):
    """Try to extract fenced code and optional language hint from AI response."""
    if '```' in response:
        try:
            parts = response.split('```')
            fenced = next((p for p in parts if '\n' in p), parts[-1])
            if fenced.strip():
                if '\n' in fenced:
                    first, rest = fenced.split('\n', 1)
                    if first.strip().isalpha():
                        return rest.strip(), first.strip().lower()
                    return fenced.strip(), None
                return fenced.strip(), None
        except Exception:
            pass
    return None, None


async def handle_code_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generates syntax-highlighted image for code. Usage: /codeimg (language) <code or topic>
    If user provides a short topic, AI will generate code then return an image.
    """
    if not await check_subscription(update, context): return

    args = context.args
    if not args:
        await update.message.reply_text("💡 Usage: /codeimg python <short prompt or paste code block>")
        return

    # If there's a fenced code block in message reply or text, use it; otherwise, ask AI to generate
    incoming = update.message.text.replace('/codeimg', '').strip()
    if '```' in incoming:
        code_text = incoming
    else:
        # treat remaining text as a prompt
        prompt = incoming or 'Create a short python example'
        status = await update.message.reply_text("⚡ Generating code image...", parse_mode=ParseMode.MARKDOWN)
        response = await get_ai_response(f"Write a concise code example for: {prompt}")
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=status.message_id)
        code_text = response

    # determine style from chat settings
    chat_id = str(update.effective_chat.id)
    style = STYLE_MAP.get(CHAT_THEMES.get(chat_id, 'default'), DEFAULT_STYLE)

    try:
        img = render_code_image(code_text, style=style)
        await update.message.reply_photo(photo=img, caption=f"{BOT_NAME} • Code (image)")
    except Exception as e:
        logging.error(f"Code image send error: {e}")
        await send_smart_response(update, code_text)


async def handle_theme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set theme for chat (`red`, `blue`, `pink`, `default`)."""
    if not await check_subscription(update, context): return
    args = context.args
    chat_id = str(update.effective_chat.id)

    if not args:
        current = CHAT_THEMES.get(chat_id, 'default')
        await update.message.reply_text(f"🎨 Current theme: {current}. Available: red, blue, pink, default")
        return

    choice = args[0].lower()
    if choice not in STYLE_MAP:
        await update.message.reply_text("❌ Invalid theme. Choose from: red, blue, pink, default")
        return

    CHAT_THEMES[chat_id] = choice
    await update.message.reply_text(f"✅ Theme set to: {choice}")

# ================= 🎮 COMMAND HANDLERS =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Professional Start Menu."""
    if not await check_subscription(update, context):
        keyboard = [[InlineKeyboardButton("🚀 Join Channel to Access", url=f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}")]]
        msg = (
            f"⛔ *ACCESS DENIED*\n\n"
            f"⚠️ You must join our official channel to use *{BOT_NAME}*.\n"
            f"👉 {REQUIRED_CHANNEL}"
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # Premium Welcome Menu
    keyboard = [
        [InlineKeyboardButton("👨‍💻 Developer", url=f"https://t.me/{OWNER_CONTACT.replace('@', '')}"),
         InlineKeyboardButton("📢 Channel", url=f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}")],
        [InlineKeyboardButton("📸 Instagram", url=f"https://instagram.com/{OWNER_INSTAGRAM}"),
         InlineKeyboardButton("▶️ YouTube", url=f"https://www.youtube.com/@{OWNER_YOUTUBE}")]
    ]
    
    welcome_msg = (
        f"🤖 *WELCOME TO CODENINJA AI* ⚡\n"
        f"_The Ultimate Developer & Hacking Assistant._\n\n"
        f"🚀 *AVAILABLE COMMANDS:*\n"
        f"💻 `/code (topic)` - Generate Scripts (Py, JS, PHP)\n"
        f"🛠 `/fix (error)` - Analyze & Fix Bugs\n"
        f"📋 `/plan (idea)` - Get a Project Roadmap\n"
        f"🔒 `/audit (code)` - Check Security Vulnerabilities\n"
        f"📝 `/prompt (topic)` - Generate AI Prompts\n"
        f"💬 `/chat` - Developer Mode Chat\n\n"
        f"🖼 `/codeimg` - Generate syntax-highlighted code image\n"
        f"🎨 `/theme` - Set code image theme (red, blue, pink)\n\n"
        f"🛡 _System Online. Waiting for input..._"
    )
    
    await update.message.reply_text(welcome_msg, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generates Code."""
    if not await check_subscription(update, context): return
    user_input = " ".join(context.args)

    if not user_input:
        await update.message.reply_text("💻 *Usage:* `/code python telegram bot` (use `--text` to get plain text, `--file` to download)", parse_mode=ParseMode.MARKDOWN)
        return

    # flags
    raw_text = update.message.text or ''
    want_file = raw_text.strip().lower().startswith('/codefile') or ('--file' in context.args)
    want_text = ('--text' in context.args)
    # clean flags from args for prompt
    context.args = [a for a in context.args if a not in ('--file','--text')]
    prompt = " ".join(context.args)

    status = await update.message.reply_text("⚡ *Compiling Code...*", parse_mode=ParseMode.MARKDOWN)
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    response = await get_ai_response(f"Write a professional, commented code script for: {prompt}")
    await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=status.message_id)

    # If user explicitly asked for file, send document
    if want_file:
        code_text, lang = extract_fenced_code(response)
        if not code_text:
            code_text = response
        ext_map = {'python':'.py','py':'.py','javascript':'.js','js':'.js','php':'.php'}
        ext = ext_map.get(lang, '.txt')
        filename = f"snippet{ext}"
        bio = BytesIO()
        bio.write(code_text.encode('utf-8'))
        bio.seek(0)
        try:
            await update.message.reply_document(document=bio, filename=filename, caption=get_watermark())
            return
        except Exception as e:
            logging.warning(f"Sending file failed: {e}")

    # If user asked for plain text, send as text
    if want_text or not PYGMENTS_AVAILABLE:
        await send_smart_response(update, response)
        return

    # Default: send as colored image
    try:
        img = render_code_image(response, style=STYLE_MAP.get(CHAT_THEMES.get(str(update.effective_chat.id), 'default'), DEFAULT_STYLE))
        img.seek(0)
        caption = f"{BOT_NAME} • Code" + get_watermark()
        await update.message.reply_photo(photo=img, caption=caption)
    except Exception as e:
        logging.warning(f"Image render failed, falling back to text: {e}")
        await send_smart_response(update, response)

async def handle_fix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fixes Bugs."""
    if not await check_subscription(update, context): return
    user_input = " ".join(context.args)

    if not user_input:
        await update.message.reply_text("🛠 *Usage:* `/fix (paste code or error)`", parse_mode=ParseMode.MARKDOWN)
        return

    status = await update.message.reply_text("🔍 *Debugging System...*", parse_mode=ParseMode.MARKDOWN)
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    
    response = await get_ai_response(f"Find errors in this code, explain them, and provide the fixed version: {user_input}")
    
    await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=status.message_id)
    await send_smart_response(update, response)

async def handle_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Project Planning."""
    if not await check_subscription(update, context): return
    user_input = " ".join(context.args)

    if not user_input:
        await update.message.reply_text("📋 *Usage:* `/plan (project idea)`\nEx: `/plan To-Do App in Python`", parse_mode=ParseMode.MARKDOWN)
        return

    status = await update.message.reply_text("🧠 *Constructing Roadmap...*", parse_mode=ParseMode.MARKDOWN)
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    
    response = await get_ai_response(f"Create a step-by-step development plan for: {user_input}. Break it down into Features, Tech Stack, and Logic.")
    
    await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=status.message_id)
    await send_smart_response(update, response)

async def handle_audit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Security Audit."""
    if not await check_subscription(update, context): return
    user_input = " ".join(context.args)

    if not user_input:
        await update.message.reply_text("🔒 *Usage:* `/audit (paste code)`", parse_mode=ParseMode.MARKDOWN)
        return

    status = await update.message.reply_text("🛡 *Scanning for Vulnerabilities...*", parse_mode=ParseMode.MARKDOWN)
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    
    response = await get_ai_response(f"Audit this code for security vulnerabilities (SQL Injection, XSS, Logic flaws) and provide a secure version: {user_input}")
    
    await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=status.message_id)
    await send_smart_response(update, response)

async def handle_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Prompt Generator."""
    if not await check_subscription(update, context): return
    user_input = " ".join(context.args)

    if not user_input:
        await update.message.reply_text("📝 *Usage:* `/prompt (topic)`", parse_mode=ParseMode.MARKDOWN)
        return

    status = await update.message.reply_text("✍️ *Crafting Prompt...*", parse_mode=ParseMode.MARKDOWN)
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    
    response = await get_ai_response(f"Generate a high-quality, detailed AI prompt for: {user_input}. Suitable for ChatGPT or Midjourney.")
    
    await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=status.message_id)
    await send_smart_response(update, response)

async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """General Chat."""
    if not await check_subscription(update, context): return
    
    user_text = update.message.text
    if user_text.startswith('/chat'): user_text = user_text.replace('/chat', '').strip()
    
    if not user_text:
        await update.message.reply_text("💬 *Developer Mode Active.* Ask me anything.", parse_mode=ParseMode.MARKDOWN)
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    response = await get_ai_response(user_text)
    await send_smart_response(update, response)

# ================= 🚀 MAIN LOOP =================

if __name__ == '__main__':
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Add Handlers
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('code', handle_code))
    application.add_handler(CommandHandler('fix', handle_fix))
    application.add_handler(CommandHandler('chat', handle_chat))
    application.add_handler(CommandHandler('codeimg', handle_code_image))
    application.add_handler(CommandHandler('theme', handle_theme))
    
    # New Advanced Handlers
    application.add_handler(CommandHandler('plan', handle_plan))
    application.add_handler(CommandHandler('audit', handle_audit))
    application.add_handler(CommandHandler('prompt', handle_prompt))
    
    # Text Handler
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_chat))

    if console:
        console.print(f"✅ {BOT_NAME} System Online...", style="bold green")
    else:
        print(f"✅ {BOT_NAME} System Online...")
    application.run_polling()
