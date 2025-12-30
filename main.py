#!/usr/bin/env python3
"""
LEGEND EXPERT — Photo Enhancer Telegram Bot
"""

import asyncio
import io
import logging
import os
import time
from typing import Optional

import aiohttp
from PIL import Image, ImageFilter, ImageEnhance
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ================= CONFIG =================
BOT_TOKEN = os.environ.get(
    "BOT_TOKEN",
    "PUT_YOUR_BOT_TOKEN_HERE"
)

CHANNEL_USERNAME = os.environ.get(
    "CHANNEL_USERNAME",
    "@legendxexpert"
)

REPLICATE_API_TOKEN = os.environ.get("REPLICATE_API_TOKEN")
REPLICATE_MODEL = os.environ.get(
    "REPLICATE_MODEL",
    "xinntao/Real-ESRGAN"
)
# =========================================

ALLOWED_STATUS_STRINGS = {"creator", "owner", "administrator", "admin", "member"}
verified_users = {}
VERIFIED_TTL = 12 * 3600

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("legend-expert-bot")


def build_join_keyboard():
    join_button = InlineKeyboardButton(
        text="Join Channel",
        url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}",
    )
    check_button = InlineKeyboardButton(
        text="I've Joined — Check",
        callback_data="check_membership",
    )
    return InlineKeyboardMarkup([[join_button], [check_button]])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 **Welcome to LEGEND EXPERT ✨**\n\n"
        "Professional AI Photo Enhancement Bot\n\n"
        f"🔔 Join our channel first:\nhttps://t.me/{CHANNEL_USERNAME.lstrip('@')}\n\n"
        "After joining, press **I've Joined — Check**",
        reply_markup=build_join_keyboard(),
        parse_mode="Markdown",
    )


async def check_user_membership(chat_id, user_id, context):
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        status = str(member.status).lower()
        if any(x in status for x in ALLOWED_STATUS_STRINGS):
            return True, None
        return False, "not_member"
    except Exception as e:
        logger.warning("Membership check failed: %s", e)
        return False, "error"


def is_verified(user_id):
    exp = verified_users.get(user_id)
    if not exp:
        return False
    if time.time() > exp:
        del verified_users[user_id]
        return False
    return True


# ========== LOCAL PHOTO ENHANCE ==========
def enhance_image_bytes_sync(original_bytes: bytes) -> bytes:
    with Image.open(io.BytesIO(original_bytes)) as im:
        im = im.convert("RGB")

        if max(im.size) > 2000:
            scale = 2000 / max(im.size)
            im = im.resize(
                (int(im.width * scale), int(im.height * scale)),
                Image.LANCZOS,
            )

        im = im.filter(ImageFilter.UnsharpMask(radius=1.5, percent=150, threshold=3))
        im = ImageEnhance.Sharpness(im).enhance(1.3)
        im = ImageEnhance.Contrast(im).enhance(1.12)
        im = ImageEnhance.Color(im).enhance(1.08)
        im = im.filter(ImageFilter.DETAIL)

        out = io.BytesIO()
        im.save(out, format="JPEG", quality=92, optimize=True)
        return out.getvalue()


async def enhance_image_bytes_local(original_bytes):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, enhance_image_bytes_sync, original_bytes)


async def enhance_image_bytes(original_bytes):
    if REPLICATE_API_TOKEN:
        try:
            enhanced = await enhance_image_bytes_local(original_bytes)
            if enhanced:
                return enhanced
        except Exception:
            pass
    return await enhance_image_bytes_local(original_bytes)


# ========== PHOTO HANDLER ==========
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    if not is_verified(user.id):
        ok, reason = await check_user_membership(
            CHANNEL_USERNAME, user.id, context
        )
        if not ok:
            await update.message.reply_text(
                "❌ Please join the channel first and verify.",
                reply_markup=build_join_keyboard(),
            )
            return
        verified_users[user.id] = time.time() + VERIFIED_TTL

    photo = update.message.photo[-1]
    tg_file = await context.bot.get_file(photo.file_id)
    file_bytes = await tg_file.download_as_bytearray()

    msg = await update.message.reply_text(
        "⏳ Enhancing your photo, please wait..."
    )

    enhanced = await enhance_image_bytes(bytes(file_bytes))
    if not enhanced:
        await msg.edit_text("❌ Enhancement failed.")
        return

    await context.bot.send_photo(
        chat_id=chat.id,
        photo=enhanced,
        caption="✨ Enhanced by LEGEND EXPERT",
    )
    await msg.delete()


async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    ok, reason = await check_user_membership(
        CHANNEL_USERNAME, update.effective_user.id, context
    )
    if ok:
        verified_users[update.effective_user.id] = time.time() + VERIFIED_TTL
        await query.edit_message_text(
            "✅ Verified!\nSend a photo and LEGEND EXPERT will enhance it ✨"
        )
    else:
        await query.edit_message_text(
            "❌ Please join the channel first."
        )


async def unknown_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📸 Send a photo to enhance.\nUse /start if needed."
    )


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_query_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_text))

    logger.info("LEGEND EXPERT Bot Started...")
    app.run_polling()


if __name__ == "__main__":
    main()
