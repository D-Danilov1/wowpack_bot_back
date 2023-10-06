import json
import os
import threading
import re
from datetime import datetime, timedelta, date
import webbrowser
import random

import flask
from flask import render_template
import gspread
import telebot
from fast_bitrix24 import Bitrix
from telebot import types
from flask import Flask, request, make_response, redirect, abort
import mysql.connector
from mysql.connector import Error
from telebot.types import ReplyKeyboardRemove, WebAppInfo
from dotenv import load_dotenv

load_dotenv("config/env")

BOT_API_KEY = os.getenv('BOT_API_KEY')
BOT_MANAGER_NICKNAME = os.getenv('BOT_MANAGER_NICKNAME')

GOOGLE_SHEET_CONFIG = os.getenv('GOOGLE_SHEET_CONFIG')
GOOGLE_SHEET_NAME = os.getenv('GOOGLE_SHEET_NAME')

BITRIX_LINK = os.getenv('BITRIX_LINK')

DB_HOST = os.getenv('DB_HOST')
DB_DATABASE = os.getenv('DB_DATABASE')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')

ADMIN_LOGIN = os.getenv('ADMIN_LOGIN')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD')

WHEEL_DAYS = os.getenv('WHEEL_DAYS')

HOST = os.getenv('HOST')
PORT = os.getenv('PORT')

bot = telebot.TeleBot(BOT_API_KEY)

gc = gspread.service_account(filename='config/gspread/' + GOOGLE_SHEET_CONFIG)
sh = gc.open(GOOGLE_SHEET_NAME)
b = Bitrix(BITRIX_LINK)

dbConnection = ''

while not dbConnection:
    try:
        print("Connecting to DB")
        dbConnection = mysql.connector.connect(
            host=DB_HOST,
            database=DB_DATABASE,
            user=DB_USER,
            password=DB_PASSWORD)
    except Error as e:
        print("Error while connecting to MySQL", e)

print("Connected to DB")

application = Flask(__name__)
application.config['JSON_AS_ASCII'] = False
application.config['JSON_SORT_KEYS'] = False
threading.Thread(target=lambda: application.run(host=HOST, port=PORT, ssl_context=('cert.pem', 'cert-key.pem'))).start()


@application.route('/', methods=['GET', 'POST'])
def flask_ok():
    if request.cookies.get('logged') == "True":
        res = make_response(redirect('/dashboard/index'))
        return res
    else:
        return "<h1>auth page</h1>"


@application.route('/updateSheetCallback', methods=['GET'])
def flask_updateSheetCallback():
    # Get data from request
    args = request.args
    order_key = args.get('order_key')
    send_date = args.get('send_date')
    status = args.get('status')
    predicted_date = args.get('predicted_date')

    if order_key == "" or send_date == "" or status == "" or predicted_date == "":
        return "err_empty"

    try:
        dbConnection.ping(True)

        cursor = dbConnection.cursor()
        cursor.execute(f"""\
                SELECT track_user FROM track WHERE track_order = '{order_key}'
                """)
        usersList = cursor.fetchall()
        for user in usersList:
            print(user)
            # Send message if found
            managerContact_btn = types.InlineKeyboardButton('Задать вопрос',
                                                            url='https://t.me/' + BOT_MANAGER_NICKNAME)
            managerKeyboard = types.InlineKeyboardMarkup()
            managerKeyboard.add(managerContact_btn)

            formatedSendDate = datetime.strptime(send_date[:-17], '%a %b %d %Y %H:%M:%S %Z')
            formatedPredictedDate = datetime.strptime(predicted_date[:-17], '%a %b %d %Y %H:%M:%S %Z')

            bot.send_message(user[0], f"""\
Обновление статуса заказа

Номер груза: `{order_key}`
Дата отправки: {formatedSendDate.strftime("%d.%m.%Y")}
Примерная дата поступления: {formatedPredictedDate.strftime("%d.%m.%Y")}
Статус: *{status}*
            """, reply_markup=managerKeyboard, parse_mode='Markdown')
        return "ok"
    except Exception as e:
        print(e)


@application.route('/login', methods=['GET'])
def flask_login():
    args = request.args
    if args.get('login') == ADMIN_LOGIN and args.get('password') == ADMIN_PASSWORD:
        res = make_response(redirect('login'))
        res.set_cookie('logged', 'True')
        res.headers.add('Access-Control-Allow-Methods', 'PUT, GET, HEAD, POST, DELETE, OPTIONS')
        res.headers.add('Access-Control-Allow-Credentials', 'true')
        res.headers.add('Access-Control-Allow-Headers', '*')
        res.headers.add('Access-Control-Allow-Origin', '*')
        res.headers.add('Access-Control-Max-Age', 86400)
        return res
    else:
        abort(403)


@application.route('/getUsers', methods=['GET'])
def flask_getUsers():
    if True:  # request.cookies.get('logged') == "True":
        dbConnection.ping(True)
        cursor = dbConnection.cursor()
        cursor.execute(f"""\
        SELECT * FROM users
        """)
        usersList = cursor.fetchall()
        json_data = []
        for result in usersList:
            json_data.append({"userId": result[0], "nickname": result[1], "phone": result[2], "name": result[3],
                              "surname": result[4]})

        response = flask.jsonify(json_data)  # json.dumps(json_data, ensure_ascii=False)
        response.headers.add('Access-Control-Allow-Methods', 'PUT, GET, HEAD, POST, DELETE, OPTIONS')
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        response.headers.add('Access-Control-Allow-Headers', '*')
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Max-Age', 86400)
        return response
    else:
        abort(401)


def json_serial_time(o):
    if isinstance(o, (datetime.date, datetime.datetime)):
        return o.isoformat()


@application.route('/getActions', methods=['GET'])
def flask_getActions():
    if request.cookies.get('logged') == "True":
        dbConnection.ping(True)
        cursor = dbConnection.cursor()
        cursor.execute(f"""\
        SELECT actions.id, actions.action_user_id, users.user_phone, actions.action_order, actions.action_date FROM actions, users WHERE actions.action_user_id = users.user_id
        """)
        actionsList = cursor.fetchall()
        json_data = []
        for result in actionsList:
            json_data.append(
                {"id": result[0], "userId": result[1], "phone": result[2], "order": result[3], "date": result[4]})
        # return json.dumps(json_data, ensure_ascii=False, default=json_serial_time)
        response = flask.jsonify(json_data)
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        return response
    else:
        abort(401)


@application.route('/sendMessages', methods=['POST', 'GET'])
def flask_sendMessages():
    if True:  # request.cookies.get('logged') == "True":
        args = request.args
        formattedMessage = str(args.get('message')).replace('\\n', '\n').replace('\\t', '\t')[1:-1]
        for user in args.get('users').split(','):
            print(user)
            print(f"{formattedMessage}")
            bot.send_message(user, f"{formattedMessage}")
        return "ok"
    else:
        abort(401)


# Wheel section

@application.route('/wheel', methods=['GET'])
def flask_wheel():
    return render_template('wheel.html')


@application.route('/getWheelPrizes', methods=['GET'])
def flask_getWheelPrizes():
    args = request.args
    user_id = str(args.get('user_id'))

    dbConnection.ping(True)
    cursor = dbConnection.cursor()
    cursor.execute(f"""\
            SELECT * FROM users WHERE users.user_id = {user_id}
            """)
    usersList = cursor.fetchall()

    if (len(usersList) == 0): abort(401)

    cursor = dbConnection.cursor()
    cursor.execute(f"""\
                SELECT * FROM winners WHERE winners.winner_user_id = {user_id} ORDER BY winner_date DESC
                """)
    winnersList = cursor.fetchall()

    #if (len(winnersList) != 0 and (datetime.now() - winnersList[0][4]).days <= int(WHEEL_DAYS)): abort(503)

    prizes = b.get_all('crm.contact.fields')
    json_data = []

    for id, x in enumerate(prizes['UF_CRM_1692611885']['items']):
        prize = str(x['VALUE']).split('|')
        if prize[2] == "Y":
            json_data.append({"id": id, "name": prize[0], "link": prize[3]})

    response = flask.jsonify(json_data)
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response


@application.route('/getWinner', methods=['GET'])
def flask_getWinner():
    args = request.args
    user_id = str(args.get('user_id'))

    dbConnection.ping(True)
    cursor = dbConnection.cursor()
    cursor.execute(f"""\
                SELECT * FROM users WHERE users.user_id = {user_id}
                """)
    usersList = cursor.fetchall()

    if (len(usersList) == 0): abort(401)

    cursor = dbConnection.cursor()
    cursor.execute(f"""\
                    SELECT * FROM winners WHERE winners.winner_user_id = {user_id} ORDER BY winner_date DESC
                    """)
    winnersList = cursor.fetchall()

    # if (len(winnersList) != 0 and (datetime.now() - winnersList[0][4]).days <= int(WHEEL_DAYS)): abort(503)

    prizes = b.get_all('crm.contact.fields')
    json_data = []
    chances = []

    for id, x in enumerate(prizes['UF_CRM_1692611885']['items']):
        prize = str(x['VALUE']).split('|')
        if prize[2] == "Y":
            json_data.append({"id": id, "intId": x['ID'], "name": prize[0], "link": prize[3] + '.jpg'})
            chances.append(float(prize[1]))

    selectedPrize = random.choices(json_data, weights=chances, k=1)
    print(selectedPrize)

    phone = addWinner(user_id, selectedPrize[0]['name'])

    print(f'+{phone}')

    contact = b.get_all('crm.contact.list',
                        params={
                            'filter': {'PHONE': f'+{phone}'},
                            'select': ['ID', 'NAME', 'PHONE', 'UF_CRM_1692611885']
                        })
    print(contact)

    bitrixUserId = contact[0]['ID']
    bitrixUserPrizes = contact[0]['UF_CRM_1692611885']
    bitrixUserPrizes.append(int(selectedPrize[0]['intId']))

    print(bitrixUserId)
    print(bitrixUserPrizes)

    addPrize = b.get_all('crm.contact.update',
                         params={
                             "id": bitrixUserId,
                             "fields": {
                                 "UF_CRM_1692611885": bitrixUserPrizes
                             }
                         })

    print(addPrize)

    response = flask.jsonify(selectedPrize)
    response.headers.add('Access-Control-Allow-Origin', '*')

    print(selectedPrize)

    bot.send_message(user_id, f"""\
{date.today().strftime("%d.%m")}: Поздравляем с выигрышем приза "{selectedPrize[0]['name']}"! 
Использовать его вы можете при обращении к менеджеру.
Следующее вращение доступно {(date.today() + timedelta(days=int(WHEEL_DAYS))).strftime("%d.%m.%Y")}
    """, parse_mode='Markdown')

    return response


# Handle '/start'
@bot.message_handler(commands=['start'], func=lambda message: True)
def send_welcome(message):
    try:
        userUpdate(message.chat.id, message.from_user.username, "70000000000", message.from_user.first_name,
                   message.from_user.last_name, 1)
        keyboard = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True, one_time_keyboard=True)
        button_phone = types.KeyboardButton(text="Отправить номер телефона", request_contact=True)
        keyboard.add(button_phone)
        msg = bot.send_message(message.chat.id, """\
        Здравствуйте! Для идентификации отправьте свой номер телефона или нажмите на кнопку
        """, reply_markup=keyboard)
        bot.register_next_step_handler(msg, registration_enterPhone)
    except:
        bot.send_message(message.chat.id, f"""
        ❌Регистрация не удалась.
        Пожалуйста, попробуйте чуть позже.
        """)


@bot.message_handler(commands=['stop'], func=lambda message: True)
def stop_bot(message):
    try:
        msg = bot.send_message(message.chat.id, """\
        Бот остановлен
        """, )
        bot.register_next_step_handler(msg, send_welcome)
    except:
        bot.send_message(message.chat.id, f"""
        ❌Регистрация не удалась.
        Пожалуйста, попробуйте чуть позже.
        """)


@bot.message_handler(content_types=['contact'])
def registration_enterPhone(message):
    # bot.edit_message_reply_markup(message.chat.id, message.message_id-1, None)

    if message.contact is not None:
        print("contact")
        registration_checkPhone(message.chat.id, message.contact.phone_number, message)
    elif message.text is not None:
        if message.text == "/stop":
            stop_bot(message)
        else:
            print("text")
            registration_checkPhone(message.chat.id, message.text, message)
    else:
        msg = bot.send_message(message.chat.id, """\
        Извините, мы не смогли считать номер телефона из контакта. Попробуйте отправить его вручную.
        """, )
        bot.register_next_step_handler(msg, registration_enterPhone)


def registration_checkPhone(chatId, message, info):
    try:
        special_characters = [' ', '(', ')', '-', '.']

        tempMessage = message
        for i in special_characters:
            tempMessage = tempMessage.replace(i, "")

        # phone = re.search(r"^(\+\d{1,2}\s?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}$", tempMessage)
        # if len(phone.group(1) if phone.group(1) != None else "PLUG") <= 2:  # Because I can
        #     phoneNumber = phone.group(0)[len(phone.group(1)):]
        # else:
        #     phoneNumber = phone.group(0)

        print(tempMessage)

        # contacts = b.get_all('crm.contact.list',
        #                   params={
        #                       'select': ['COMMENTS']})
        #
        # isPhoneFound = False
        # for contact in contacts:
        #     if str(contact['COMMENTS']).find(phoneNumber) > -1:
        #         isPhoneFound = True
        #
        # if not isPhoneFound:
        #     managerContact_btn = types.InlineKeyboardButton('Задать вопрос',
        #                                                     url='https://t.me/' + BOT_MANAGER_NICKNAME)
        #     managerKeyboard = types.InlineKeyboardMarkup()
        #     managerKeyboard.add(managerContact_btn)
        #     msg = bot.send_message(chatId, """\
        #                             Извини, мы не смогли найти номер телефона в нашей базе. Проверь его правильность и попробуй ещё раз.
        #                             """, reply_markup=managerKeyboard)
        #     bot.register_next_step_handler(msg, registration_enterPhone)
        #     return None

        userUpdate(chatId, info.from_user.username, tempMessage, info.from_user.first_name, info.from_user.last_name, 0)

        managerKeyboard = types.InlineKeyboardMarkup()
        wheel = types.InlineKeyboardButton(text="Колесо удачи", url="https://wowpack-dev.ru/wheel?url="+str(chatId))
        managerContact_btn = types.InlineKeyboardButton(text='Задать вопрос', url='https://t.me/' + BOT_MANAGER_NICKNAME)
        managerKeyboard.add(managerContact_btn, wheel)

        bot.send_message(chatId, f"""Регистрация завершена""", reply_markup=types.ReplyKeyboardRemove())

        msg = bot.send_message(chatId, f"""
        Отлично! Теперь вы можете присылать боту номера заказов, а он расскажет о их статусе.
        """, reply_markup=managerKeyboard)
        bot.register_next_step_handler(msg, order_findOrder)

    except Exception as e:
        print(e)
        keyboard = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True, one_time_keyboard=True)
        button_phone = types.KeyboardButton(text="Отправить номер телефона", request_contact=True)
        keyboard.add(button_phone)
        msg = bot.send_message(chatId, """\
        Извините, мы не смогли распознать номер телефона. Попробуйте отправить его ещё раз.
        """, reply_markup=keyboard)
        bot.register_next_step_handler(msg, registration_enterPhone)


@bot.message_handler(func=lambda m: True)
def order_findOrder(message):
    orderNumber = message.text

    if message.text == "/stop":
        stop_bot(message)
        return None

    try:
        cell = sh.sheet1.find(orderNumber, in_column=1)

        userActions(message.chat.id, orderNumber)

        managerKeyboard = types.InlineKeyboardMarkup()
        wheel = types.InlineKeyboardButton(text="Колесо удачи", url="https://wowpack-dev.ru/wheel?url="+str(message.chat.id))
        managerContact_btn = types.InlineKeyboardButton(text='Задать вопрос',
                                                        url='https://t.me/' + BOT_MANAGER_NICKNAME)
        managerKeyboard.add(managerContact_btn, wheel)

        msg = bot.send_message(message.chat.id, f"""\
Номер груза: `{sh.sheet1.cell(cell.row, 1).value}`
Дата отправки: {sh.sheet1.cell(cell.row, 2).value}
Примерная дата поступления: {sh.sheet1.cell(cell.row, 4).value}
Статус: *{sh.sheet1.cell(cell.row, 3).value}*
        """, parse_mode='Markdown', reply_markup=managerKeyboard)
        bot.register_next_step_handler(msg, order_findOrder)

        addTrack(message.chat.id, orderNumber)
    except Exception as e:
        msg = bot.send_message(message.chat.id, f"""\
        Извините, мы не смогли найти заказ. Проверьте номер заказа и отправь его ещё раз.
        """)
        bot.register_next_step_handler(msg, order_findOrder)


def userUpdate(chatId, username, phone, name, surname, isNew):
    try:
        dbConnection.ping(True)
        cursor = dbConnection.cursor()
        cursor.execute(f"""
                INSERT INTO users (user_id, user_nick, user_phone, user_name, user_surname, user_is_new) 
                VALUES({chatId}, '{username}', {phone}, '{name}', '{surname}','{isNew}') 
                ON DUPLICATE KEY 
                UPDATE user_id={chatId}, user_nick='{username}', user_phone={phone}, user_name='{name}', user_surname='{surname}', user_is_new='{isNew}'
                """)
        dbConnection.commit()
    except Exception as e:
        print(e)


def userActions(chatId, order):
    try:
        dbConnection.ping(True)
        cursor = dbConnection.cursor()
        cursor.execute(f"""\
                    INSERT INTO actions (action_user_id, action_order, action_date) 
                    VALUES({chatId}, '{order}', NOW()) 
                    """)
        dbConnection.commit()
    except Exception as e:
        print(e)


def addTrack(chatId, order):
    try:
        dbConnection.ping(True)

        cursor = dbConnection.cursor()
        cursor.execute(f"""\
                SELECT * FROM track WHERE track_order = '{order}' AND track_user = '{chatId}'
                """)
        usersList = cursor.fetchall()
        if len(usersList) > 0:
            return None

        cursor = dbConnection.cursor()
        cursor.execute(f"""
                INSERT INTO track (track_order, track_user) 
                VALUES('{order}', '{chatId}') 
                """)
        dbConnection.commit()
    except Exception as e:
        print(e)


def addWinner(chatId, prize):
    try:
        dbConnection.ping(True)

        cursor = dbConnection.cursor()
        cursor.execute(f"""
                INSERT INTO winners (winner_user_id, winner_phone, winner_prize) 
                VALUES('{chatId}', (SELECT user_phone FROM users WHERE users.user_id = '{chatId}'), '{prize}')  
                """)
        dbConnection.commit()

        cursor = dbConnection.cursor()
        cursor.execute(f"""
                        SELECT user_phone FROM users WHERE user_id = '{chatId}'  
                        """)

        phone = cursor.fetchall()
        return phone[0][0]
    except Exception as e:
        print(e)


bot.infinity_polling()
