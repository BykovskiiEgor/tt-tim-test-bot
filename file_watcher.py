import asyncio
import os
import aiosqlite
from sqlalchemy import select
from models import FolderSubscription, User, async_session
from aiogram import Bot
from config import FILES_ROOT, CHECK_INTERVAL
from datetime import datetime, timedelta
from utils import logger


DISPLAY_TIME_OFFSET_MINUTES = 60


class FileWatcher:
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.bot = Bot(token=bot_token)

    def get_full_path(self, relative_path: str) -> str:
        """Конструирует абсолютный путь из относительного (относительно FILES_ROOT)."""
        return os.path.join(FILES_ROOT, relative_path)

    def get_folder_mtime_recursive(self, folder_path: str) -> float:
        """
        Рекурсивно возвращает самое свежее время изменения в папке.
        Если папки нет — возвращает 0.0.
        """
        if not os.path.exists(folder_path):
            return 0.0
        latest = 0.0
        try:
            for root, _, files in os.walk(folder_path):
                try:
                    mtime = os.path.getmtime(root)
                    if mtime > latest:
                        latest = mtime
                except OSError:
                    pass
                for file in files:
                    try:
                        mtime = os.path.getmtime(os.path.join(root, file))
                        if mtime > latest:
                            latest = mtime
                    except OSError:
                        pass
        except Exception as e:
            logger.warning(f"Ошибка при сканировании {folder_path}: {e}")
        return latest
    
    async def get_comment_and_user(self, db: str):
        try:
            async with aiosqlite.connect(db) as conn:
                cursor = await conn.cursor()
                
                await cursor.execute(
                    "SELECT VersionNumber, Comment, UserName FROM ModelHistory ORDER BY VersionNumber DESC LIMIT 1"
                )
                rows = await cursor.fetchone()
                
                if rows:
                    return rows
                    
        except aiosqlite.Error as e:
            logger.error(f"SQLite error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in get_comment: {e}")
        
        return None

    async def find_db_file(self, dir: str):
        try:
            for root, dirs, files in os.walk(dir):
                for file in files:
                    if file == 'Model.db3':
                        db_path = os.path.join(root, file)
                        logger.info(f"Найден Models.db3: {db_path}")
                        
                        comment = await self.get_comment_and_user(db_path)
                        if comment and len(comment) >= 2:
                            return comment  
                        else:
                            return "неизвестно", "нет комментария"
                            
                await asyncio.sleep(0)
                        
        except Exception as e:
            logger.error(f"Error in find_db_file: {e}")
        
        logger.warning(f"Models.db3 не найден в {dir}")
        return "неизвестно", "нет комментария"


    async def notify_subscribers(self, sub: FolderSubscription, changed_data_path: str, current_mtime: datetime):
        """
        Отправляет уведомление подписчику о изменении в конкретной папке Data.
        """
        try:
            async with async_session() as session:
                result = await session.execute(select(User).where(User.id == sub.user_id))
                user = result.scalar_one_or_none()
                if not user:
                    logger.warning(f"Пользователь с ID {sub.user_id} не найден")
                    return
                
                try:
                    tg_user = await self.bot.get_chat(user.tg_id)
                    user.username = tg_user.username
                    user.first_name = tg_user.first_name
                    await session.commit()
                    logger.debug(f"Обновлены данные пользователя {user.tg_id} {tg_user.username} {tg_user.first_name}")
                except Exception as e:
                    logger.warning(f"Не удалось обновить данные пользователя {user.tg_id}: {e}")

            # Папка "Задание", на которую подписан пользователь (относительно FILES_ROOT)
            task_relative = sub.folder_path                          # например: "355/РД/Задание от КЖ"
            task_name = os.path.basename(task_relative)              # например: "Задание от КЖ"

            # Путь до изменившейся .rvt-папки БЕЗ "Data"
            rel_path = os.path.relpath(changed_data_path, FILES_ROOT)  # ".../.rvt/Data"
            rvt_path = os.path.dirname(rel_path)                        # убираем "Data": ".../.rvt"

            # Время для отображения (со сдвигом), в БД/логах остаётся исходное
            display_time = current_mtime + timedelta(minutes=DISPLAY_TIME_OFFSET_MINUTES)

            comment_result = await self.find_db_file(changed_data_path)
            comment_line = ""
            user_line = ""
            
            if comment_result and len(comment_result) >= 2:
                comment_text = comment_result[1]
                user_text = comment_result[2]
                if comment_text and comment_text.strip() and comment_text != "нет комментария":
                    comment_line = f"📝 Комментарий: {comment_text}"
            else:
                logger.error("Комментарий не получен или имеет неверный формат")

            message = (
                "🔄 <b>Обнаружено изменение в подписанной папке!</b>\n\n"
                f"📂 Подписка: <b>{task_name}</b>\n"
                f"📌 Путь: <code>{rvt_path}</code>\n"
                f"🕒 Время изменения: {display_time.strftime('%d.%m.%Y %H:%M')}\n"
                f"{comment_line}\n"
                f"👤 Автор - {user_text}\n"
            )

            await self.bot.send_message(
                chat_id=user.tg_id,
                text=message,
                parse_mode="HTML"
            )
            logger.info(f"✅ Уведомление отправлено пользователю {user.first_name} {user.username} {user.tg_id} ({task_relative})")

        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления: {e}")


    async def check_folder_updates(self, session):
        """
        Для каждой подписанной папки 'Задание' проверяет все подпапки (например 1.rvt, 2.rvt, ...)
        и ищет в них папку 'Data'. Если в какой-то Data есть изменения — уведомляет подписчика.
        """
        try:
            result = await session.execute(select(FolderSubscription))
            subscriptions = result.scalars().all()

            for sub in subscriptions:
                task_full_path = self.get_full_path(sub.folder_path)  # Путь до папки Задание

                if not os.path.exists(task_full_path):
                    logger.warning(f"Папка задания не найдена: {task_full_path}")
                    continue

                subfolders = [name for name in os.listdir(task_full_path)
                              if os.path.isdir(os.path.join(task_full_path, name))]

                latest_mtime_ts = 0.0
                changed_data_folder = None

                for subfolder in subfolders:
                    data_folder_path = os.path.join(task_full_path, subfolder, "Data")
                    if not os.path.exists(data_folder_path) or not os.path.isdir(data_folder_path):
                        continue

                    current_mtime_ts = self.get_folder_mtime_recursive(data_folder_path)
                    if current_mtime_ts > latest_mtime_ts:
                        latest_mtime_ts = current_mtime_ts
                        changed_data_folder = data_folder_path

                if latest_mtime_ts == 0.0:
                    continue

                current_mtime = datetime.fromtimestamp(latest_mtime_ts)

                if sub.last_modified is None:
                    sub.last_modified = current_mtime
                    session.add(sub)
                    await session.commit()
                    logger.info(f"📌 Инициализация времени изменения для {sub.folder_path}")
                    continue

                # Сравнение с точностью до секунды
                if int(latest_mtime_ts) > int(sub.last_modified.timestamp()):
                    logger.info(f"🔥 Обнаружено изменение в Data: {changed_data_folder}")
                    sub.last_modified = current_mtime
                    session.add(sub)
                    await session.commit()
                    await self.notify_subscribers(sub, changed_data_folder, current_mtime)

        except Exception as e:
            logger.error(f"Ошибка при проверке обновлений Data: {e}")

    async def start_monitoring(self):
        """Периодически проверяет все подписки."""
        logger.info("🚀 Мониторинг подписок запущен...")
        while True:
            try:
                async with async_session() as session:
                    await self.check_folder_updates(session)
                await asyncio.sleep(CHECK_INTERVAL)
            except asyncio.CancelledError:
                logger.info("🛑 Мониторинг остановлен.")
                break
            except Exception as e:
                logger.error(f"Ошибка в цикле мониторинга: {e}")
                await asyncio.sleep(CHECK_INTERVAL)

    async def close(self):
        """Закрывает ресурсы."""
        await self.bot.session.close()
        logger.info("🔌 Сессия бота закрыта")
