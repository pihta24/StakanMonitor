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
from telebot.util import extract_arguments, antiflood, extract_command

from database import Database, get_user_from_msg
from database.models import User, Event
from utils import SelfCleaningDict, generate_qr_code
from utils.middlewares import RegisterMiddleware, HandleBannedMiddleware

# Создание клиентов для БД и телеги
bot = AsyncTeleBot(environ.get("TELEBOT_TOKEN", ""))
client = AsyncIOMotorClient(environ.get("DATABASE_URL", ""))

messages_to_reply_photo = SelfCleaningDict(3600, 3600)  # Самоочищающийся словарь для хранения типа отсутствия в диалоге
admins_actions = {}  # Словарь для хранения действий с админами для чатов

bot.setup_middleware(RegisterMiddleware())  # Настройка промежуточного шлюза для регистрации пользователей
bot.setup_middleware(HandleBannedMiddleware(bot))  # Настройка промежуточного шлюза для проверки бана


@bot.message_handler(commands=["coolers"])
async def handle_coolers(message: Message):
    user = await get_user_from_msg(message)

    if not user.admin:
        return

    coolers = await Database.coolers.find({}, inject_default_id=True)

    if not coolers:
        await bot.reply_to(message, "Кулеров нет")
        return
    args = extract_arguments(message.text).split()

    match len(args):
        case 0:
            await bot.reply_to(message, "\n".join([f"{i.name} - {i._id}" for i in coolers]))
        case 1:
            if args[0] == "qr":
                for i in coolers:
                    await antiflood(bot.send_document, message.chat.id, generate_qr_code(i._id), caption=i.name)


# Обработка команд для бана/разбана пользователей
@bot.message_handler(commands=["ban", "unban"])
async def handle_ban(message: Message):
    user = await get_user_from_msg(message)

    if not user.admin:  # Проверяем является ли пользователь админом
        return

    try:
        uid = int(extract_arguments(message.text))  # Добываем id пользователя, которого нужно изменить
        try:
            # Изменяем информацию в БД
            await Database.users.update_one({
                "telegram_id": uid
            }, update={
                "$set": {
                    "banned": extract_command(message.text) == "ban"
                }
            })

            await bot.reply_to(message, f"Изменения произведены\nId пользователя: {uid}")  # Оповещаем пользователя
        except NotFound:
            # В БД не найден пользователь, которого нужно изменить
            await bot.reply_to(message, "Пользователь не найден")
    except ValueError:
        # Не передали id или передали не число
        await bot.reply_to(message, "Использование:\n/ban id\n/unban id")


@bot.message_handler(commands=["chat"])
async def handle_chat(message: Message):
    user = await get_user_from_msg(message)

    if not user.admin:
        return

    if message.chat.type == "private":
        await bot.reply_to(message, "Это команда для чатов")
        return

    try:
        arguments = extract_arguments(message.text).split()
        match len(arguments):
            case 1:
                if arguments[0] not in ["true", "false"]:
                    raise ValueError

                await Database.chats.update_one({
                    "chat_id": message.chat.id
                }, update={
                    "$set": {
                        "send_notif": arguments[0] == "true"
                    }
                })

                await bot.reply_to(message, f"Изменения произведены\nId чата: {message.chat.id}")
            case _:
                raise ValueError
    except (AttributeError, ValueError):
        await bot.reply_to(message, "Использование: /chat true|false")


# Обработка редактирования администраторов
@bot.message_handler(commands=["admin"])
async def handle_admin(message: Message):
    user = await get_user_from_msg(message)

    if not user.can_add_admin:  # Проверяем может ли пользователь изменять админов
        return

    if message.chat.type != "private":
        await bot.reply_to(message, "Это команда для личных сообщений")
        return

    try:
        arguments = extract_arguments(message.text).split()
        match len(arguments):
            case 2:
                if not arguments[0].isdigit() or arguments[1] not in ["true", "false"]:
                    raise ValueError

                await Database.users.update_one({
                    "telegram_id": int(arguments[0])
                }, update={
                    "$set": {
                        "admin": arguments[1] == "true",
                        "send_notif": arguments[1] == "true"
                    }
                })
                await bot.reply_to(message, f"Изменения произведены\nId пользователя: {arguments[0]}")
            case 1:
                if arguments[0] not in ["true", "false"]:
                    raise ValueError

                await bot.reply_to(message, "Перешлите сообщение от пользователя")
                admins_actions[message.from_user.id] = arguments[0]
            case _:
                raise ValueError
    except (AttributeError, ValueError):
        await bot.reply_to(message, "Использование: /admin id true|false")


# Обработка редактирования администраторов через пересланное сообщение
@bot.message_handler(func=lambda message: message.forward_from is not None)
async def handle_forwarded_for_admin(message: Message):
    user = await get_user_from_msg(message)

    if not user.can_add_admin:  # Проверяем может ли пользователь изменять админов
        return

    if message.from_user.id not in admins_actions.keys():  # Проверяем запрашивал ли пользователь действия
        return

    if message.chat.type != "private":
        return

    # Находим пользователя, если нет, то создаём
    user_to_edit = await Database.users.find({
        "telegram_id": message.forward_from.id
    }, inject_default_id=True)
    if user_to_edit:
        user_to_edit = user_to_edit[0]
    else:
        user_to_edit = User(telegram_id=message.forward_from.id, name=message.forward_from.first_name)

    # Вносим изменения
    user_to_edit.admin = admins_actions[message.from_user.id] == "true"
    user_to_edit.send_notif = admins_actions[message.from_user.id] == "true"

    # Отмечаем действие выполненным, сохраняем БД, отправляем уведомление
    del admins_actions[message.from_user.id]
    await Database.users.save(user_to_edit)
    await bot.reply_to(message, f"Изменения произведены\nId пользователя: {message.forward_from.id}")


# Обрабатываем начало диалога
@bot.message_handler(commands=['start'])
async def handle_start(message: Message):
    if message.chat.type != "private":
        return

    uid = extract_arguments(message.text)
    try:
        cooler = await Database.coolers.find_one(_id=uid, inject_default_id=True)

        if cooler.empty_glass and cooler.empty_watter:  # Уведомляем, что мы уже знаем об отсутствии всего
            await bot.reply_to(message, "Отсутствие воды и стаканчиков уже зарегистрировано")
            return

        if cooler.empty_glass:  # Уведомляем, что мы уже знаем об отсутствии чего-то одного
            await bot.reply_to(message, "Отсутствие стаканчиков уже зарегистрировано")
        elif cooler.empty_watter:
            await bot.reply_to(message, "Отсутствие воды уже зарегистрировано")

        # inline клавиатура для отправки обращений
        keyboard = InlineKeyboardMarkup().row(
            InlineKeyboardButton("Нет стаканчиков", callback_data=f"{uid} no_glass"),
            InlineKeyboardButton("Нет воды", callback_data=f"{uid} no_water")
        ).row(
            InlineKeyboardButton("Нет стаканчиков и воды", callback_data=f"{uid} no_all")
        )
        await bot.reply_to(message, "Выберите, чего не хватает", reply_markup=keyboard)
    except (AssertionError, InvalidId, NotFound):
        # Пользователь использовал команду /start не через qr-код
        await bot.reply_to(message, "Отсканируйте qr-код на кулере")


# Обработка отправленной фотографии
@bot.message_handler(content_types=["photo"])
async def photo_handler(message: Message):
    if message.chat.type != "private":
        return

    if not message.photo:  # Проверяем, что сообщение — фотография
        return

    if not message.reply_to_message:  # Проверяем, что сообщение — ответ
        await bot.reply_to(message, "Ответьте на сообщение от бота(свайп влево)")
        return

    # Смотрим, какую кнопку нажал пользователь
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
            keyboard.row(
                InlineKeyboardButton("Стаканчики загружены", callback_data=f"{uid} reset_glass"),
                InlineKeyboardButton("Вода загружена", callback_data=f"{uid} reset_water")
            ).row(
                InlineKeyboardButton("Вода и cтаканчики загружены", callback_data=f"{uid} reset_all")
            )
        case _:
            await bot.reply_to(message, "Ты как сюда попал?\nНапиши @pihta24")
            return

    # Если уже есть нерешенные задачи, значит кулер пустой
    if len(cooler.sent_messages) != 0:
        keyboard = InlineKeyboardMarkup()
        keyboard.row(
            InlineKeyboardButton("Стаканчики загружены", callback_data=f"{uid} reset_glass"),
            InlineKeyboardButton("Вода загружена", callback_data=f"{uid} reset_water")
        ).row(
            InlineKeyboardButton("Вода и cтаканчики загружены", callback_data=f"{uid} reset_all")
        )

    m += f"'{cooler.name}'\nОтправил @{message.from_user.username}, id: {message.from_user.id}"
    keyboard.row(InlineKeyboardButton("Взялся за работу", callback_data=f"{uid} take"))
    keyboard.row(InlineKeyboardButton("Забанить", callback_data=f"{message.from_user.id} ban"))

    if len(cooler.sent_messages) != 0:
        for i, j in cooler.sent_messages:
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

    for i in await Database.chats.find({"send_notif": True}, inject_default_id=True):
        try:
            msg = await antiflood(bot.send_photo, i.chat_id, message.photo[0].file_id, m, reply_markup=keyboard)
            cooler.sent_messages.append([msg.chat.id, msg.id])
        except ApiTelegramException as e:
            print(e)
            i.send_notif = False
            await Database.chats.save(i)

    await Database.coolers.save(cooler)
    await Database.events.save(
        Event(
            type=status,
            from_id=message.from_user.id,
            description=f"@{message.from_user.username} sent {status} event"
        )
    )

    await bot.reply_to(message, "Спасибо за обращение")


# Обрабатываем все запросы от inline кнопок
@bot.callback_query_handler(lambda query: query.message is not None)
async def handle_inline_keyboard(query: CallbackQuery):
    if query.message.chat.type != "private":
        from_chat = await Database.chats.find_one({"chat_id": query.message.chat.id}, inject_default_id=True)
        if not from_chat or not from_chat.send_notif:
            from_chat = None
    else:
        from_chat = None
    user = await Database.users.find_one({"telegram_id": query.from_user.id}, inject_default_id=True)
    if user.banned:  # Проверяем, не в бане ли пользователь
        await bot.answer_callback_query(query.id, "Вы находитесь в черном списке")
        return

    # Ловим все ошибки, чтобы не крутилась загрузка у пользователя, если упадёт
    try:
        if query.data == "empty":  # Заглушка для кнопок, которые просто показывают информацию
            await bot.answer_callback_query(query.id)
            return

        uid, status = query.data.split()
        if status.startswith("no_"):
            try:
                cooler = await Database.coolers.find_one(_id=uid, inject_default_id=True)
            except (InvalidId, NotFound):
                try:
                    await bot.answer_callback_query(query.id, "Отсканируйте qr-код на кулере")
                    await bot.edit_message_reply_markup(query.message.chat.id, query.message.id,
                                                        reply_markup=InlineKeyboardMarkup())
                    await bot.edit_message_text("Отсканируйте qr-код на кулере", query.message.chat.id,
                                                query.message.id)
                finally:
                    return
            if status not in ["no_water", "no_glass", "no_all"]:
                try:
                    await bot.answer_callback_query(query.id, "Отсканируйте qr-код на кулере")
                    await bot.edit_message_reply_markup(query.message.chat.id, query.message.id,
                                                        reply_markup=InlineKeyboardMarkup())
                    await bot.edit_message_text("Отсканируйте qr-код на кулере", query.message.chat.id,
                                                query.message.id)
                finally:
                    return
            if (status == "no_water" and cooler.empty_watter) or \
                    (status == "no_glass" and cooler.empty_glass) or \
                    (status == "no_all" and cooler.empty_watter and cooler.empty_glass):
                try:
                    await bot.answer_callback_query(query.id, "Обращение уже зарегистрировано")
                    await bot.edit_message_reply_markup(query.message.chat.id, query.message.id,
                                                        reply_markup=InlineKeyboardMarkup())
                    await bot.edit_message_text("Обращение уже зарегистрировано", query.message.chat.id,
                                                query.message.id)
                finally:
                    return
            try:
                await bot.answer_callback_query(query.id, "Пожалуйста, отправьте фотографию ответным сообщением")
                await bot.edit_message_reply_markup(query.message.chat.id, query.message.id,
                                                    reply_markup=InlineKeyboardMarkup())
                await bot.edit_message_text("Отправьте фотографию ответным сообщением", query.message.chat.id,
                                            query.message.id)
            finally:
                messages_to_reply_photo[query.message.id] = (uid, status)
        elif status.startswith("reset_") and (user.admin or from_chat):
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
        elif status == "ban" and (user.admin or from_chat):
            user_to_ban = await Database.users.find({"telegram_id": int(uid)}, inject_default_id=True)
            if not user_to_ban:
                await bot.answer_callback_query(query.id, "Пользователь не найден")
                return
            user_to_ban[0].banned = True
            await Database.users.save(user_to_ban[0])
            await bot.answer_callback_query(query.id, "Пользователь внесен в черный список")
        elif status == "take" and (user.admin or from_chat):
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
            await bot.answer_callback_query(
                query.id, "Теоретически, ты не можешь это видеть, но, похоже, мы что-то забыли\nНапиши @pihta24")
    except Exception as e:
        print(e)
        await bot.answer_callback_query(query.id, "Произошла ошибка\nКаким образом ты все сломал?\nНапиши @pihta24")


async def main():
    await Engine().bind(motor=client, databases=[Database], inject_motyc_fields=True)
    await bot.polling(non_stop=True)


if __name__ == '__main__':
    run(main())
