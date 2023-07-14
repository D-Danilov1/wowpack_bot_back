import os
import threading
import re
import datetime

import flask
import gspread
import telebot
from telebot import types
from flask import Flask, request, make_response, redirect, abort
import mysql.connector
from mysql.connector import Error
from telebot.types import ReplyKeyboardRemove
from dotenv import load_dotenv

load_dotenv("config/env")

BOT_API_KEY = os.getenv('BOT_API_KEY')
BOT_MANAGER_NICKNAME = os.getenv('BOT_MANAGER_NICKNAME')

GOOGLE_SHEET_CONFIG = os.getenv('GOOGLE_SHEET_CONFIG')
GOOGLE_SHEET_NAME = os.getenv('GOOGLE_SHEET_NAME')

DB_HOST = os.getenv('DB_HOST')
DB_DATABASE = os.getenv('DB_DATABASE')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')

ADMIN_LOGIN = os.getenv('ADMIN_LOGIN')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD')

HOST = os.getenv('HOST')
PORT = os.getenv('PORT')

bot = telebot.TeleBot(BOT_API_KEY)

gc = gspread.service_account(filename='config/gspread/' + GOOGLE_SHEET_CONFIG)
sh = gc.open(GOOGLE_SHEET_NAME)

dbConnection = ''

while not dbConnection:
    try:
        dbConnection = mysql.connector.connect(
            host=DB_HOST,
            database=DB_DATABASE,
            user=DB_USER,
            password=DB_PASSWORD)
    except Error as e:
        print("Error while connecting to MySQL", e)

application = Flask(__name__)
application.config['JSON_AS_ASCII'] = False
application.config['JSON_SORT_KEYS'] = False
threading.Thread(target=lambda: application.run(host=HOST, port=PORT)).start()


@application.route('/', methods=['GET', 'POST'])
def flask_ok():
    if request.cookies.get('logged') == "True":
        return "<h1>logged</h1>"
    else:
        return "<h1>auth page</h1>"


@application.route('/login', methods=['POST'])
def flask_login():
    args = request.form
    if args['login'] == ADMIN_LOGIN and args['password'] == ADMIN_PASSWORD:
        res = make_response(redirect('/'))
        res.set_cookie('logged', 'True')
        return res
    else:
        abort(403)


@application.route('/getUsers', methods=['GET'])
def flask_getUsers():
    if request.cookies.get('logged') == "True":
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
        response.headers.add('Access-Control-Allow-Origin', 'ORIGIN')
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


@application.route('/sendMessages', methods=['POST'])
def flask_sendMessages():
    if request.cookies.get('logged') == "True":
        args = request.form
        for user in args['users'].split(','):
            print(user)
            bot.send_message(user, f"""\
            {args['message']}
            """)
        return "ok"
    else:
        abort(401)


# Handle '/start'
@bot.message_handler(commands=['start'], func=lambda message: True)
def send_welcome(message):
    try:
        keyboard = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
        button_phone = types.KeyboardButton(text="Отправить номер телефона", request_contact=True)
        keyboard.add(button_phone)
        msg = bot.send_message(message.chat.id, """\
        Привет! Для идентификации отправь свой номер телефона или нажми на кнопку
        """, reply_markup=keyboard)
        bot.register_next_step_handler(msg, registration_enterPhone)
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
        print("text")
        registration_checkPhone(message.chat.id, message.text, message)
    else:
        msg = bot.send_message(message.chat.id, """\
        Извини, мы не смогли считать номер телефона из контакта. Попробуй отправить его вручную.
        """, )
        bot.register_next_step_handler(msg, registration_enterPhone)


def registration_checkPhone(chatId, message, info):
    try:
        special_characters = [' ', '(', ')', '-', '.']

        tempMessage = message
        for i in special_characters:
            tempMessage = tempMessage.replace(i, "")

        phone = re.search(r"^(\+\d{1,2}\s?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}$", tempMessage)
        if len(phone.group(1) if phone.group(1) != None else "PLUG") <= 2:  # Because I can
            phoneNumber = phone.group(0)[len(phone.group(1)):]
        else:
            phoneNumber = phone.group(0)

        print(phoneNumber)
        userUpdate(chatId, info.from_user.username, phoneNumber, info.from_user.first_name, info.from_user.last_name)

        msg = bot.send_message(chatId, f"""
        Номер записан. Теперь можешь присылать боту номера заказов, а он расскажет о их статусе.
        """, reply_markup=ReplyKeyboardRemove())
        bot.register_next_step_handler(msg, order_findOrder)

    except Exception as e:
        print(e)
        keyboard = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
        button_phone = types.KeyboardButton(text="Отправить номер телефона", request_contact=True)
        keyboard.add(button_phone)
        msg = bot.send_message(chatId, """\
        Извини, мы не смогли распознать номер телефона. Попробуй отправить его ещё раз.
        """, reply_markup=keyboard)
        bot.register_next_step_handler(msg, registration_enterPhone)


@bot.message_handler(func=lambda m: True)
def order_findOrder(message):
    orderNumber = message.text

    managerContact_btn = types.InlineKeyboardButton('Связаться с менеджером',
                                                    url='https://t.me/' + BOT_MANAGER_NICKNAME)
    managerKeyboard = types.InlineKeyboardMarkup()
    managerKeyboard.add(managerContact_btn)

    try:
        cell = sh.sheet1.find(orderNumber, in_column=1)

        userActions(message.chat.id, orderNumber)

        msg = bot.send_message(message.chat.id, f"""\
Номер груза: `{sh.sheet1.cell(cell.row, 1).value}`
Дата отправки: {sh.sheet1.cell(cell.row, 2).value}
Примерная дата поступления: {sh.sheet1.cell(cell.row, 4).value}
Статус: *{sh.sheet1.cell(cell.row, 3).value}*
        """, reply_markup=managerKeyboard, parse_mode='Markdown')
        bot.register_next_step_handler(msg, order_findOrder)
    except Exception as e:
        msg = bot.send_message(message.chat.id, f"""\
        Извини, мы не смогли найти заказ. Проверь номер заказа и отправь его ещё раз.
        """, reply_markup=managerKeyboard)
        bot.register_next_step_handler(msg, order_findOrder)


def userUpdate(chatId, username, phone, name, surname):
    try:
        dbConnection.ping(True)
        cursor = dbConnection.cursor()
        cursor.execute(f"""
                INSERT INTO users (user_id, user_nick, user_phone, user_name, user_surname) 
                VALUES({chatId}, '{username}', {phone}, '{name}', '{surname}') 
                ON DUPLICATE KEY 
                UPDATE user_id={chatId}, user_nick='{username}', user_phone={phone}, user_name='{name}', user_surname='{surname}'
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


bot.infinity_polling()
