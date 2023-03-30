#!/usr/bin/python
from os import environ

from aiorun import run
# noinspection PyPackageRequirements
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorClient
from pymotyc import Engine
from pymotyc.errors import NotFound
# noinspection PyPackageRequirements
from telebot.async_telebot import AsyncTeleBot
# noinspection PyPackageRequirements
from telebot.asyncio_helper import ApiTelegramException
# noinspection PyPackageRequirements
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
# noinspection PyPackageRequirements
from telebot.util import extract_arguments, antiflood

from database import Database
from database.models import User, Event
from utils import SelfCleaningDict
from utils.middlewares import RegisterMiddleware, HandleBannedMiddleware

# Создание клиентов для БД и телеги
bot = AsyncTeleBot(environ.get("TELEBOT_TOKEN", ""))
client = AsyncIOMotorClient(environ.get("DATABASE_URL", ""))

messages_to_reply_photo = SelfCleaningDict(3600, 3600)  # Самоочищающийся словарь для хранения типа отсутствия в диалоге
admins_actions = {}  # Словарь для хранения действий с админами для чатов

bot.setup_middleware(RegisterMiddleware())  # Настройка промежуточного шлюза для регистрации пользователей
bot.setup_middleware(HandleBannedMiddleware(bot))  # Настройка промежуточного шлюза для проверки бана


@bot.message_handler(commands=["ban"])
async def handle_ban(message: Message):
    user = await Database.users.find_one({"telegram_id": message.from_user.id}, inject_default_id=True)
    if user.banned:
        await bot.reply_to(message, "Вы находитесь в черном списке")
        return
    if not user.admin:
        return
    uid = extract_arguments(message.text)
    if not uid:
        await bot.reply_to(message, "Использование: /ban id")
        return
    if not uid.isdigit():
        await bot.reply_to(message, "Использование: /ban id")
        return
    user_to_ban = await Database.users.find({"telegram_id": int(uid)}, inject_default_id=True)
    if not user_to_ban:
        await bot.reply_to(message, "Пользователь не найден")
        return
    user_to_ban[0].banned = True
    await Database.users.save(user_to_ban[0])
    await bot.reply_to(message, "Пользователь внесен в черный список")


@bot.message_handler(commands=["unban"])
async def handle_unban(message: Message):
    user = await Database.users.find_one({"telegram_id": message.from_user.id}, inject_default_id=True)
    if user.banned:
        await bot.reply_to(message, "Вы находитесь в черном списке")
        return
    if not user.admin:
        return
    uid = extract_arguments(message.text)
    if not uid:
        await bot.reply_to(message, "Использование: /unban id")
        return
    if not uid.isdigit():
        await bot.reply_to(message, "Использование: /ban id")
        return
    user_to_unban = await Database.users.find({"telegram_id": int(uid)}, inject_default_id=True)
    if not user_to_unban:
        await bot.reply_to(message, "Пользователь не найден")
        return
    user_to_unban[0].banned = True
    await Database.users.save(user_to_unban[0])
    await bot.reply_to(message, "Пользователь внесен в черный список")


@bot.message_handler(commands=["admin"])
async def handle_unban(message: Message):
    user = await Database.users.find_one({"telegram_id": message.from_user.id}, inject_default_id=True)
    if user.banned:
        await bot.reply_to(message, "Вы находитесь в черном списке")
        return
    if not user.can_add_admin:
        return
    s = extract_arguments(message.text)
    if s:
        s = s.split()
        if len(s) == 2:
            if s[0].isdigit():
                user = await Database.users.find({"telegram_id": int(s[0])}, inject_default_id=True)
                if user:
                    user = user[0]
                    if s[1].lower() == "true":
                        user.admin = True
                        user.send_notif = True
                        await Database.users.save(user)
                        await bot.reply_to(message, "Админ добавлен")
                        return
                    if s[1].lower() == "false":
                        user.admin = False
                        user.send_notif = False
                        await Database.users.save(user)
                        await bot.reply_to(message, "Админ удален")
                        return
        if len(s) == 1:
            if s[0].lower() in ["true", "false"]:
                await bot.reply_to(message, "Перешлите сообщение от пользователя")
                admins_actions[message.from_user.id] = s[0].lower()
                return
    await bot.reply_to(message, "Использование: /admin id true|false")


@bot.message_handler(func=lambda message: message.forward_from is not None)
async def handle_forwarded(message: Message):
    user = await Database.users.find_one({"telegram_id": message.from_user.id}, inject_default_id=True)
    if user.banned:
        await bot.reply_to(message, "Вы находитесь в черном списке")
        return
    if not user.can_add_admin:
        return
    if not message.forward_from:
        return
    if message.from_user.id not in admins_actions.keys():
        return
    user_to_edit = await Database.users.find({"telegram_id": message.forward_from.id}, inject_default_id=True)
    if user_to_edit:
        user_to_edit = user_to_edit[0]
    else:
        user_to_edit = User(telegram_id=message.forward_from.id, name=message.forward_from.first_name)
    if admins_actions[message.from_user.id] == "true":
        user_to_edit.admin = True
        user_to_edit.send_notif = True
    else:
        user_to_edit.admin = False
        user_to_edit.send_notif = False
    del admins_actions[message.from_user.id]
    await Database.users.save(user_to_edit)
    await bot.reply_to(message, f"Изменения произведены\nId пользователя: {message.forward_from.id}")


@bot.message_handler(commands=['start'])
async def handle_start(message: Message):
    uid = extract_arguments(message.text)
    if uid and len(uid) == 24:
        user = await Database.users.find_one({"telegram_id": message.from_user.id}, inject_default_id=True)
        if user.banned:
            await bot.reply_to(message, "Вы находитесь в черном списке")
            return
        try:
            cooler = await Database.coolers.find_one(_id=uid, inject_default_id=True)
        except (InvalidId, NotFound):
            await bot.reply_to(message, "Отсканируйте qr-код на кулере")
            return
        if cooler.empty_glass and cooler.empty_watter:
            await bot.reply_to(message, "Отсутствие воды и стаканчиков уже зарегистрировано")
            return
        keyboard = InlineKeyboardMarkup()
        if cooler.empty_glass:
            await bot.reply_to(message, "Отсутствие стаканчиков уже зарегистрировано")
            keyboard.row(InlineKeyboardButton("Нет воды", callback_data=f"{uid} no_water"))
        elif cooler.empty_watter:
            await bot.reply_to(message, "Отсутствие воды уже зарегистрировано")
            keyboard.row(InlineKeyboardButton("Нет стаканчиков", callback_data=f"{uid} no_glass"))
        else:
            keyboard \
                .row(InlineKeyboardButton("Нет стаканчиков", callback_data=f"{uid} no_glass"),
                     InlineKeyboardButton("Нет воды", callback_data=f"{uid} no_water")) \
                .row(InlineKeyboardButton("Нет стаканчиков и воды", callback_data=f"{uid} no_all"))
        await bot.reply_to(message, "Выберите, чего не хватает", reply_markup=keyboard)
    else:
        await bot.reply_to(message, "Отсканируйте qr-код на кулере")


@bot.message_handler(content_types=["photo"])
async def photo_handler(message: Message):
    user = await Database.users.find_one({"telegram_id": message.from_user.id}, inject_default_id=True)
    if user.banned:
        await bot.reply_to(message, "Вы находитесь в черном списке")
        return
    if message.photo and message.reply_to_message:
        messages_to_reply_photo.prone()
        try:
            uid, status = messages_to_reply_photo[message.reply_to_message.id]
            del messages_to_reply_photo[message.reply_to_message.id]
        except KeyError:
            await bot.reply_to(message, "Попробуйте отсканировать код еще раз")
            return

        try:
            cooler = await Database.coolers.find_one(_id=uid, inject_default_id=True)
        except (InvalidId, NotFound):
            await bot.reply_to(message, "Отсканируйте qr-код на кулере")
            return

        keyboard = InlineKeyboardMarkup()

        match status:
            case "no_water":
                if cooler.empty_watter:
                    await bot.reply_to(message, "Обращение уже зарегистрировано")
                    return
                m = "Закончилась вода в кулере: "
                cooler.empty_watter = True
                keyboard.row(InlineKeyboardButton("Вода загружена", callback_data=f"{uid} reset_water"))
            case "no_glass":
                if cooler.empty_glass:
                    await bot.reply_to(message, "Обращение уже зарегистрировано")
                    return
                m = "Закончились стаканчики в кулере: "
                cooler.empty_glass = True
                keyboard.row(InlineKeyboardButton("Стаканчики загружены", callback_data=f"{uid} reset_glass"))
            case "no_all":
                if cooler.empty_watter and cooler.empty_glass:
                    await bot.reply_to(message, "Обращение уже зарегистрировано")
                    return
                m = "Закончились стаканчики и вода в кулере: "
                cooler.empty_glass = True
                cooler.empty_watter = True
                keyboard \
                    .row(InlineKeyboardButton("Стаканчики загружены", callback_data=f"{uid} reset_glass"),
                         InlineKeyboardButton("Вода загружена", callback_data=f"{uid} reset_water")) \
                    .row(InlineKeyboardButton("Вода и cтаканчики загружены", callback_data=f"{uid} reset_all"))
            case _:
                await bot.reply_to(message, "Произошла ошибка")
                return

        if len(cooler.sent_messages) != 0:
            keyboard = InlineKeyboardMarkup()
            keyboard \
                .row(InlineKeyboardButton("Стаканчики загружены", callback_data=f"{uid} reset_glass"),
                     InlineKeyboardButton("Вода загружена", callback_data=f"{uid} reset_water")) \
                .row(InlineKeyboardButton("Вода и cтаканчики загружены", callback_data=f"{uid} reset_all"))

        m += f"'{cooler.name}'\nОтправил @{message.from_user.username}, id: {message.from_user.id}"
        keyboard.row(InlineKeyboardButton("Взялся за работу", callback_data=f"{uid} take"))
        keyboard.row(InlineKeyboardButton("Забанить", callback_data=f"{message.from_user.id} ban"))

        if len(cooler.sent_messages) != 0:
            for i, j in enumerate(cooler.sent_messages):
                try:
                    await antiflood(bot.edit_message_reply_markup, i, j, reply_markup=keyboard)
                except ApiTelegramException as e:
                    print(e)
                    del cooler.sent_messages[cooler.sent_messages.index([i, j])]

        for i in await Database.users.find({"send_notif": True}, inject_default_id=True):
            try:
                msg = await antiflood(bot.send_photo, i.telegram_id, message.photo[0].file_id, m, reply_markup=keyboard)
                cooler.sent_messages.append([msg.chat.id, msg.id])
            except ApiTelegramException as e:
                print(e)
                i.send_notif = False
                await Database.users.save(i)

        await Database.coolers.save(cooler)
        await Database.events.save(Event(type=status, from_id=message.from_user.id,
                                         description=f"@{message.from_user.username} sent {status} event"))

        await bot.reply_to(message, "Спасибо за обращение")


@bot.callback_query_handler(lambda query: query.message is not None)
async def handle_inline_keyboard(query: CallbackQuery):
    user = await Database.users.find_one({"telegram_id": query.message.chat.id}, inject_default_id=True)
    if user.banned:
        await bot.answer_callback_query(query.id, "Вы находитесь в черном списке")
        return
    try:
        if query.data == "empty":
            await bot.answer_callback_query(query.id)
            return
        uid, status = query.data.split()
        if status.startswith("no_"):
            try:
                await Database.coolers.find_one(_id=uid, inject_default_id=True)
            except (InvalidId, NotFound):
                await bot.answer_callback_query(query.id, "Отсканируйте qr-код на кулере")
                return
            await bot.edit_message_reply_markup(query.message.chat.id, query.message.id,
                                                reply_markup=InlineKeyboardMarkup())
            await bot.edit_message_text("Отправьте фотографию ответным сообщением", query.message.chat.id,
                                        query.message.id)
            await bot.answer_callback_query(query.id, "Пожалуйста, отправьте фотографию ответным сообщением")
            messages_to_reply_photo[query.message.id] = (uid, status)
        elif status.startswith("reset_") and user.admin:
            try:
                cooler = await Database.coolers.find_one(_id=uid, inject_default_id=True)
            except (InvalidId, NotFound):
                await bot.answer_callback_query(query.id, "Произошла ошибка")
                return

            keyboard = query.message.reply_markup.keyboard

            match status:
                case "reset_water":
                    if len(keyboard[0]) == 2:
                        del keyboard[0][1]
                        del keyboard[1]
                    else:
                        del keyboard[0]
                    cooler.empty_watter = False
                case "reset_glass":
                    if len(keyboard[0]) == 2:
                        del keyboard[0][0]
                        del keyboard[1]
                    else:
                        del keyboard[0]
                    cooler.empty_glass = False
                case "reset_all":
                    del keyboard[0]
                    del keyboard[1]
                    cooler.empty_glass = False
                    cooler.empty_watter = False

            for i, j in cooler.sent_messages:
                try:
                    if len(keyboard) == 2:
                        await antiflood(bot.delete_message, i, j)
                    else:
                        await antiflood(bot.edit_message_reply_markup, i, j,
                                        reply_markup=InlineKeyboardMarkup(keyboard))
                except ApiTelegramException as e:
                    print(e)
                    del cooler.sent_messages[cooler.sent_messages.index([i, j])]

            if len(keyboard) == 2:
                cooler.sent_messages = []

            await Database.coolers.save(cooler)
            await bot.answer_callback_query(query.id, "Изменения внесены")
        elif status == "ban" and user.admin:
            user_to_ban = await Database.users.find({"telegram_id": int(uid)}, inject_default_id=True)
            if not user_to_ban:
                await bot.answer_callback_query(query.id, "Пользователь не найден")
                return
            user_to_ban[0].banned = True
            await Database.users.save(user_to_ban[0])
            await bot.answer_callback_query(query.id, "Пользователь внесен в черный список")
        elif status == "take" and user.admin:
            try:
                cooler = await Database.coolers.find_one(_id=uid, inject_default_id=True)
            except (InvalidId, NotFound):
                await bot.answer_callback_query(query.id, "Произошла ошибка")
                return
            keyboard = query.message.reply_markup.keyboard
            keyboard[-2][0] = InlineKeyboardButton(f"Взялся: @{query.from_user.username}", callback_data="empty")
            for i, j in cooler.sent_messages:
                try:
                    await antiflood(bot.edit_message_reply_markup, i, j, reply_markup=InlineKeyboardMarkup(keyboard))
                except ApiTelegramException as e:
                    print(e)
                    del cooler.sent_messages[cooler.sent_messages.index([i, j])]
            await Database.coolers.save(cooler)
            await bot.answer_callback_query(query.id)
        else:
            await bot.answer_callback_query(query.id)
    except Exception as e:
        print(e)
        await bot.answer_callback_query(query.id, "Произошла ошибка")


async def main():
    await Engine().bind(motor=client, databases=[Database], inject_motyc_fields=True)
    await bot.polling()


if __name__ == '__main__':
    run(main())
