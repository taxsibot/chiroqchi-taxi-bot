from aiogram import Bot
from aiogram.types import (
    BotCommand, BotCommandScopeAllPrivateChats,
    BotCommandScopeChat, BotCommandScopeAllGroupChats
)
from config import ADMIN_ID
import logging

logger = logging.getLogger(__name__)


async def set_commands(bot: Bot):
    """
    Sets bot commands, descriptions, and bio.
    /admin and /panel are ONLY visible to admin users — completely hidden from regular users.
    """

    # ─── 1. Bot Description (What can this bot do? — "Start" bosishdan oldin ko'rinadi) ───
    desc_uz = (
        "🚕 CHIROQCHI TAKSI — Tezkor, Arzon va Qulay safarlar!\n\n"
        "🌟 Botimiz orqali siz:\n"
        "• 📍 Chiroqchi ⇄ Toshkent va barcha yo'nalishlarda taksi chaqirishingiz;\n"
        "• 📦 Pochta va posilkalaringizni eshikdan-eshikkacha ishonchli yetkazishingiz;\n"
        "• 💺 Hamroh (poputchik) reyslarida qulay o'rindiqlarni band qilishingiz;\n"
        "• 🚗 Haydovchi sifatida ro'yxatdan o'tib, buyurtmalardan barakali daromad topishingiz mumkin!\n\n"
        "🎁 Har bir safardan keshbek va doimiy bonuslarga ega bo'ling!\n\n"
        "👇 Boshlash uchun pastdagi «Start» tugmasini bosing:"
    )
    desc_ru = (
        "🚕 CHIROQCHI TAXI — Быстрые, доступные и комфортные поездки!\n\n"
        "🌟 С помощью нашего бота вы можете:\n"
        "• 📍 Заказать такси Чирокчи ⇄ Ташкент и по всем направлениям;\n"
        "• 📦 Отправить посылку и груз с доставкой до двери;\n"
        "• 💺 Забронировать место в попутных рейсах;\n"
        "• 🚗 Зарегистрироваться водителем и получать заказы 24/7!\n\n"
        "🎁 Получайте кешбэк и бонусы с каждой поездки!\n\n"
        "👇 Нажмите «Start», чтобы начать:"
    )
    try:
        await bot.set_my_description(description=desc_uz)
        await bot.set_my_description(description=desc_uz, language_code="uz")
        await bot.set_my_description(description=desc_ru, language_code="ru")
        logger.info("✅ Bot descriptions set.")
    except Exception as e:
        logger.warning(f"set_my_description error: {e}")

    # ─── 2. Bot Short Description (Bio — max 120 chars) ───────────────────────
    bio_uz = "🚕 Toshkent ⇄ Qashqadaryo: tezkor taksi, ishonchli pochta, hamroh reyslar! 🚀"
    bio_ru = "🚕 Ташкент ⇄ Кашкадарья: быстрое такси, доставка, попутчики! 🚀"
    bio_en = "🚕 Tashkent ⇄ Kashkadarya: fast taxi, parcel delivery & shared rides! 🚀"
    try:
        await bot.set_my_short_description(short_description=bio_uz)
        await bot.set_my_short_description(short_description=bio_uz, language_code="uz")
        await bot.set_my_short_description(short_description=bio_ru, language_code="ru")
        await bot.set_my_short_description(short_description=bio_en, language_code="en")
        logger.info("✅ Bot short descriptions (Bio) set.")
    except Exception as e:
        logger.warning(f"set_my_short_description error: {e}")

    # ─── 3. Oddiy foydalanuvchilar uchun buyruqlar (ADMIN buyruqlar YO'Q) ─────
    user_commands = [
        BotCommand(command="start",  description="🚀 Botni ishga tushirish"),
        BotCommand(command="taxi",   description="🚕 Taksi chaqirish"),
        BotCommand(command="parcel", description="📦 Pochta yuborish"),
        BotCommand(command="help",   description="ℹ️ Yordam va qo'llanma"),
    ]
    try:
        await bot.set_my_commands(
            commands=user_commands,
            scope=BotCommandScopeAllPrivateChats()
        )
        logger.info("✅ User commands set (no admin commands).")
    except Exception as e:
        logger.warning(f"set_my_commands (user) error: {e}")

    # ─── 4. Guruhlar uchun buyruqlar (minimal, toza) ──────────────────────────
    group_commands = [
        BotCommand(command="start", description="🚕 Bot haqida ma'lumot"),
        BotCommand(command="info",  description="ℹ️ Bot haqida batafsil"),
    ]
    try:
        await bot.set_my_commands(
            commands=group_commands,
            scope=BotCommandScopeAllGroupChats()
        )
        logger.info("✅ Group commands set.")
    except Exception as e:
        logger.warning(f"set_my_commands (group) error: {e}")

    # ─── 5. Admin buyruqlar — FAQAT adminlar lichkasida ko'rinadi ─────────────
    admin_commands = [
        BotCommand(command="start",  description="🚀 Bosh sahifa"),
        BotCommand(command="panel",  description="🛠 Admin boshqaruv paneli"),
        BotCommand(command="admin",  description="👑 Admin panel (qisqacha)"),
        BotCommand(command="help",   description="ℹ️ Yordam"),
    ]

    # Asosiy admin (config dan)
    if ADMIN_ID and ADMIN_ID != 0:
        try:
            await bot.set_my_commands(
                commands=admin_commands,
                scope=BotCommandScopeChat(chat_id=ADMIN_ID)
            )
            logger.info(f"✅ Admin commands set for main admin {ADMIN_ID}.")
        except Exception as e:
            logger.warning(f"Admin commands set error for {ADMIN_ID}: {e}")

    # Qo'shimcha adminlar (DB dan)
    try:
        from database.db import get_all_admins
        all_admins = await get_all_admins()
        for adm in all_admins:
            adm_id = adm[0] if isinstance(adm, (list, tuple)) else adm
            if adm_id == ADMIN_ID:
                continue  # Asosiy admin allaqachon yuqorida o'rnatildi
            try:
                await bot.set_my_commands(
                    commands=admin_commands,
                    scope=BotCommandScopeChat(chat_id=adm_id)
                )
                logger.info(f"✅ Admin commands set for sub-admin {adm_id}.")
            except Exception as e:
                logger.debug(f"Admin commands set error for sub-admin {adm_id}: {e}")
    except Exception as e:
        logger.warning(f"Could not load admins from DB for command setup: {e}")
