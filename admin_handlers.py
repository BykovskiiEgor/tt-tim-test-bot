from aiogram import Router, F
from aiogram.filters import Command 
from aiogram.types import Message
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from config import ADMIN_IDS
from models import User, FolderSubscription, async_session
from sqlalchemy import select

admin_router = Router()

@admin_router.message(Command('admin'), F.from_user.id.in_(ADMIN_IDS))
async def admin_command_handler(message: Message):
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="/users_list")],
            [KeyboardButton(text="/exit")],
        ],
        resize_keyboard=True
    )
    await message.reply("Режим админа", reply_markup=kb)

@admin_router.message(Command('exit'), F.from_user.id.in_(ADMIN_IDS))
async def exit_admin_handler(message: Message):
    user_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="/subscribe")],
            [KeyboardButton(text="/my_subs")]
        ],
        resize_keyboard=True
    )
    await message.reply("👤 <b>Обычный режим пользователя</b>", reply_markup=user_kb)

@admin_router.message(Command('users_list'), F.from_user.id.in_(ADMIN_IDS))
async def users_list_handler(message: Message):
    async with async_session() as session:
        
        result = await session.execute(select(User))
        users = result.unique().scalars().all()
        
        if not users:
            await message.reply("No users found.")
            return
        
        subs_res = await session.execute(select(FolderSubscription))
        subs = subs_res.scalars().all()
            
        response = "Registered Users:\n\n"
        for user in users:
            folder_names = [sub.folder_path for sub in subs if user.id == sub.user_id]
            
            response += f"👤 <b>Пользователь:</b> @{user.username or 'без username'}\n"
            response += f"🆔 ID: {user.id} | TG ID: {user.tg_id}\n"
            
            if user.first_name or user.last_name:
                name_parts = []
                if user.first_name:
                    name_parts.append(user.first_name)
                if user.last_name:
                    name_parts.append(user.last_name)
                response += f"📝 Имя: {' '.join(name_parts)}\n"
            
            if folder_names:
                response += f"📂 <b>Подписки ({len(folder_names)}):</b>\n"
                for i, folder in enumerate(folder_names, 1):
                    if len(folder) > 50:
                        folder = folder[:47] + "..."
                    response += f"   {i}. 📁 {folder}\n"
            else:
                response += "📂 <i>Нет активных подписок</i>\n"
            
            response += "┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
                
        await message.reply(response)