import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice
import psycopg2
from datetime import datetime, timedelta
import threading
from flask import Flask
import os

# ==========================================
# 🚨 CONFIGURAZIONE 🚨
TELEGRAM_TOKEN = "8700195342:AAGlUqka3ImYc9G5DYnCRfixisLWuguDxjk"
STRIPE_PROVIDER_TOKEN = "2051251535:TEST:OTk5MDA4ODgxLTAwNQ"
DB_URL = "postgresql://postgres.xxbjfhpbrcbryfcjuxsx:Napoli2026+++@aws-1-eu-west-1.pooler.supabase.com:6543/postgres"
# Inserisci il tuo ID numerico per ricevere le notifiche sul PC
ADMIN_ID = "IL_TUO_ID_TELEGRAM" 
# ==========================================

bot = telebot.TeleBot(TELEGRAM_TOKEN)

def get_db_connection():
    return psycopg2.connect(DB_URL)

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    testo = (
        "🚗 *Benvenuto nell'Autoscuola PRO Bot!*\n\n"
        "Vuoi controllare il tuo saldo, prenotare o disdire una guida?\n"
        "👉 *Scrivi il tuo NOME e COGNOME*."
    )
    bot.reply_to(message, testo, parse_mode="Markdown")

# --- 1. PROFILO ALLIEVO (MENU PRINCIPALE) ---
@bot.message_handler(func=lambda message: True)
def check_student(message):
    nome_inserito = message.text.strip()
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, nome, crediti, pacchetto_attivo FROM allievi WHERE nome ILIKE %s", (nome_inserito,))
        allievo = cur.fetchone()
        
        if allievo:
            id_a, nome_reale, crediti, pacchetto = allievo
            pacchetto = pacchetto if pacchetto else "Nessuno"
            
            # Aggiorna il chat_id dell'allievo per abilitare le notifiche
            cur.execute("UPDATE allievi SET chat_id = %s WHERE id = %s", (str(message.chat.id), id_a))
            conn.commit()
            
            risposta = f"👤 *Profilo: {nome_reale}*\n📦 {pacchetto}\n⌛ *Guide Rimaste: {crediti}*"
            
            markup = InlineKeyboardMarkup()
            if crediti > 0:
                markup.add(InlineKeyboardButton("🗓️ Inizia Prenotazione", callback_data=f"istr|{id_a}"))
            
            # Pulsanti con callback separati per evitare che si premano insieme
            markup.add(InlineKeyboardButton("📋 Le mie Guide (Storico)", callback_data=f"storico|{id_a}"))
            markup.add(InlineKeyboardButton("❌ Le mie Guide (Annulla)", callback_data=f"annulla_lista|{id_a}"))
            markup.add(InlineKeyboardButton("🛒 Acquista Pacchetto", callback_data=f"shop|{id_a}"))
            
            bot.reply_to(message, risposta, parse_mode="Markdown", reply_markup=markup)
        else:
            bot.reply_to(message, "❌ Non ho trovato questo nome. Riprova!")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Errore check_student: {e}")

# --- 2. GESTIONE STORICO ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('storico|'))
def mostra_storico(call):
    id_allievo = call.data.split('|')[1]
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT nome FROM allievi WHERE id = %s", (id_allievo,))
        nome_all = cur.fetchone()[0]
        
        # Recupera le ultime 10 guide incluse quelle annullate
        cur.execute("""
            SELECT data, ora, ora_fine, istruttore, stato_pagamento 
            FROM guide WHERE allievo = %s 
            ORDER BY id DESC LIMIT 10
        """, (nome_all,))
        guide = cur.fetchall()
        
        testo = "📋 *STORICO ULTIME 10 GUIDE*\n\n"
        if not guide:
            testo += "Nessuna guida trovata."
        else:
            for g in guide:
                icona = "✅" if "Scalato" in g[4] else "❌"
                testo += f"{icona} {g[0]} | {g[1]}-{g[2]}\n👤 {g[3]}\n\n"
        
        bot.send_message(call.message.chat.id, testo, parse_mode="Markdown")
        bot.answer_callback_query(call.id)
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Errore storico: {e}")

# --- 3. GESTIONE ANNULLAMENTO ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('annulla_lista|'))
def lista_per_annullare(call):
    id_allievo = call.data.split('|')[1]
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT nome FROM allievi WHERE id = %s", (id_allievo,))
        nome_all = cur.fetchone()[0]
        
        # Mostra solo guide che hanno lo stato 'Scalato' per poterle annullare
        cur.execute("""
            SELECT id, data, ora, istruttore 
            FROM guide WHERE allievo = %s AND stato_pagamento LIKE '%%Scalato%%' 
            ORDER BY id DESC LIMIT 5
        """, (nome_all,))
        guide = cur.fetchall()
        
        markup = InlineKeyboardMarkup()
        if not guide:
            bot.edit_message_text("Non hai guide attive da annullare.", 
                                  chat_id=call.message.chat.id, message_id=call.message.message_id)
            return

        for g in guide:
            markup.add(InlineKeyboardButton(f"❌ Annulla {g[1]} {g[2]}", callback_data=f"delguida|{id_allievo}|{g[0]}"))
        
        bot.edit_message_text("Quale guida vuoi **CANCELLARE**?", 
                              chat_id=call.message.chat.id, message_id=call.message.message_id, 
                              reply_markup=markup, parse_mode="Markdown")
        bot.answer_callback_query(call.id)
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Errore lista annulla: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('delguida|'))
def esegui_annullamento(call):
    dati = call.data.split('|')
    id_allievo, id_guida = dati[1], dati[2]
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT data, ora, scatti FROM guide WHERE id = %s", (id_guida,))
        guida = cur.fetchone()
        
        if guida:
            cur.execute("DELETE FROM guide WHERE id = %s", (id_guida,))
            cur.execute("UPDATE allievi SET crediti = crediti + %s WHERE id = %s", (guida[2], id_allievo))
            conn.commit()
            bot.edit_message_text(f"✅ Guida del {guida[0]} alle {guida[1]} **Annullata**.\nI crediti sono stati rimborsati.", 
                                  chat_id=call.message.chat.id, message_id=call.message.message_id)
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Errore cancellazione: {e}")

# --- 4. PRENOTAZIONI ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('istr|'))
def scegli_istruttore(call):
    id_allievo = call.data.split('|')[1]
    markup = InlineKeyboardMarkup()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT nome FROM istruttori ORDER BY nome")
    for istr in cur.fetchall():
        markup.add(InlineKeyboardButton(f"👨‍🏫 {istr[0]}", callback_data=f"data|{id_allievo}|{istr[0]}"))
    bot.edit_message_text("Scegli l'istruttore:", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)
    cur.close()
    conn.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith('data|'))
def scegli_giorno(call):
    dati = call.data.split('|')
    markup = InlineKeyboardMarkup()
    oggi = datetime.now()
    for i in range(1, 8):
        g = oggi + timedelta(days=i)
        if g.weekday() != 6:
            markup.add(InlineKeyboardButton(g.strftime('%d/%m (%a)'), callback_data=f"ora|{dati[1]}|{dati[2]}|{g.strftime('%d/%m/%Y')}"))
    bot.edit_message_text("Scegli il giorno:", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('ora|'))
def scegli_orario(call):
    dati = call.data.split('|')
    markup = InlineKeyboardMarkup()
    for h in range(8, 20):
        markup.add(InlineKeyboardButton(f"{h}:00", callback_data=f"dur|{dati[1]}|{dati[2]}|{dati[3]}|{h:02d}:00"))
    bot.edit_message_text("A che ora?", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('dur|'))
def scegli_durata(call):
    dati = call.data.split('|')
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("⏱️ 20 min", callback_data=f"conf|{dati[1]}|{dati[2]}|{dati[3]}|{dati[4]}|1"))
    markup.add(InlineKeyboardButton("⏱️ 40 min", callback_data=f"conf|{dati[1]}|{dati[2]}|{dati[3]}|{dati[4]}|2"))
    markup.add(InlineKeyboardButton("⏱️ 1 Ora", callback_data=f"conf|{dati[1]}|{dati[2]}|{dati[3]}|{dati[4]}|3"))
    bot.edit_message_text("Durata della guida?", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('conf|'))
def conferma_prenotazione(call):
    dati = call.data.split('|')
    id_a, istr, data, ora, scatti = dati[1], dati[2], dati[3], dati[4], int(dati[5])
    
    # Calcolo orario di fine
    h, m = map(int, ora.split(':'))
    minuti = m + (scatti * 20)
    ora_fine = f"{(h + minuti // 60):02d}:{(minuti % 60):02d}"
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT nome, crediti FROM allievi WHERE id=%s", (id_a,))
        allievo = cur.fetchone()
        
        if allievo and allievo[1] >= scatti:
            # Registrazione della guida
            cur.execute("""
                INSERT INTO guide (allievo, istruttore, veicolo, data, ora, ora_fine, stato_pagamento, scatti) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (allievo[0], istr, "Da Assegnare", data, ora, ora_fine, f"Scalato ({scatti})", scatti))
            
            # Scalaggio crediti
            cur.execute("UPDATE allievi SET crediti = crediti - %s WHERE id=%s", (scatti, id_a))
            conn.commit()
            
            # Messaggio di conferma all'allievo
            bot.edit_message_text(f"✅ **CONFERMATA!**\n📅 {data}\n⏰ {ora} - {ora_fine}\n👤 {istr}", 
                                  chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="Markdown")
        else:
            bot.send_message(call.message.chat.id, "❌ Crediti insufficienti.")
            
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Errore conferma: {e}")

# --- 5. SHOP ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('shop|'))
def apri_negozio(call):
    id_allievo = call.data.split('|')[1]
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📦 Pacchetto 3 Ore (9 Guide) - 63€", callback_data=f"buy|{id_allievo}|9|63"))
    bot.edit_message_text("🛒 **Negozio Guide**:", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('buy|'))
def genera_fattura(call):
    dati = call.data.split('|')
    prezzi = [LabeledPrice(label="Ricarica Guide", amount=int(dati[3]) * 100)]
    bot.send_invoice(call.message.chat.id, "Ricarica Guide", "Crediti per prenotazioni", f"PAG|{dati[1]}|{dati[2]}", STRIPE_PROVIDER_TOKEN, "EUR", prezzi)

@bot.message_handler(content_types=['successful_payment'])
def pagamento_successo(message):
    dati = message.successful_payment.invoice_payload.split('|')
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE allievi SET crediti = crediti + %s WHERE id = %s", (int(dati[2]), dati[1]))
    conn.commit()
    bot.reply_to(message, "🎉 Pagamento ricevuto! Crediti aggiornati.")

# --- SERVER WEB E POLLING ---
app = Flask(__name__)
@app.route('/')
def home(): return "✅ Bot Online"

if __name__ == "__main__":
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))).start()
    bot.infinity_polling()





