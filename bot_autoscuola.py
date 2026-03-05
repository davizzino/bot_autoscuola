import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice
import psycopg2
from datetime import datetime, timedelta
import threading
from flask import Flask
import os

# ==========================================
# 🚨 INSERISCI QUI LE TUE 3 CHIAVI SEGRETE 🚨
TELEGRAM_TOKEN = "8700195342:AAGlUqka3ImYc9G5DYnCRfixisLWuguDxjk"
STRIPE_PROVIDER_TOKEN = "2051251535:TEST:OTk5MDA4ODgxLTAwNQ"
DB_URL = "postgresql://postgres.xxbjfhpbrcbryfcjuxsx:Napoli2026+++@aws-1-eu-west-1.pooler.supabase.com:6543/postgres"
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

# --- 1. CERCA L'ALLIEVO E SALVA IL CHAT_ID ---
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
            
            # MAGIA: Salva il numero di telefono virtuale (chat_id) di questo allievo!
            cur.execute("UPDATE allievi SET chat_id = %s WHERE id = %s", (message.chat.id, id_a))
            conn.commit()
            
            risposta = f"👤 *Profilo: {nome_reale}*\n📦 {pacchetto}\n⏳ *Guide Rimaste: {crediti}*"
            
            markup = InlineKeyboardMarkup()
            if crediti > 0:
                markup.add(InlineKeyboardButton("🗓️ Inizia Prenotazione", callback_data=f"istr|{id_a}"))
            
            markup.add(InlineKeyboardButton("❌ Le mie Guide (Annulla)", callback_data=f"mieguide|{id_a}"))
            markup.add(InlineKeyboardButton("🛒 Acquista Pacchetto", callback_data=f"shop|{id_a}"))
                
            bot.reply_to(message, risposta, parse_mode="Markdown", reply_markup=markup)
        else:
            bot.reply_to(message, "❌ Non ho trovato questo nome. Riprova!")
        cur.close()
        conn.close()
    except Exception as e:
        bot.reply_to(message, "⚠️ Errore di rete.")
        print(e)

# ==========================================
# SEZIONE DISDETTE (NOVITÀ!)
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data.startswith('mieguide|'))
def mostra_guide_allievo(call):
    id_allievo = call.data.split('|')[1]
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT nome FROM allievi WHERE id = %s", (id_allievo,))
        nome_allievo = cur.fetchone()[0]
        
        cur.execute("SELECT id, data, ora, istruttore FROM guide WHERE allievo = %s ORDER BY id DESC LIMIT 5", (nome_allievo,))
        guide = cur.fetchall()
        cur.close()
        conn.close()
        
        markup = InlineKeyboardMarkup()
        if not guide:
            bot.edit_message_text("Non hai guide prenotate da annullare.", chat_id=call.message.chat.id, message_id=call.message.message_id)
            return
        
        for g in guide:
            id_guida, data, ora, istr = g
            markup.add(InlineKeyboardButton(f"❌ {data} - {ora} ({istr})", callback_data=f"delguida|{id_allievo}|{id_guida}"))
        
        bot.edit_message_text("Scegli la guida che vuoi **ANNULLARE**:\n*(I crediti ti verranno rimborsati istantaneamente)*", 
                              chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        print(e)

@bot.callback_query_handler(func=lambda call: call.data.startswith('delguida|'))
def annulla_guida_allievo(call):
    dati = call.data.split('|')
    id_allievo, id_guida = dati[1], dati[2]
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT data, ora, scatti FROM guide WHERE id = %s", (id_guida,))
        guida = cur.fetchone()
        
        if guida:
            data_g, ora_g, scatti = guida
            cur.execute("DELETE FROM guide WHERE id = %s", (id_guida,))
            cur.execute("UPDATE allievi SET crediti = crediti + %s WHERE id = %s", (scatti, id_allievo))
            conn.commit()
            bot.edit_message_text(f"✅ **Guida Annullata!**\nLa tua guida del {data_g} alle {ora_g} è stata cancellata.\nTi sono state rimborsate {scatti} guide.", 
                                  chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="Markdown")
        cur.close()
        conn.close()
    except Exception as e:
        print(e)

# ==========================================
# SEZIONE NEGOZIO ONLINE (PAGAMENTI)
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data.startswith('shop|'))
def apri_negozio(call):
    id_allievo = call.data.split('|')[1]
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📦 Pacchetto 3 Ore (9 Guide) - 63€", callback_data=f"buy|{id_allievo}|9|63"))
    markup.add(InlineKeyboardButton("📦 Pacchetto 6 Ore (18 Guide) - 126€", callback_data=f"buy|{id_allievo}|18|126"))
    bot.edit_message_text("🛒 **Negozio Autoscuola**\nScegli il pacchetto da ricaricare:", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith('buy|'))
def genera_fattura(call):
    dati = call.data.split('|')
    id_allievo, quantita_guide, prezzo_euro = dati[1], int(dati[2]), int(dati[3])
    titolo = f"Pacchetto {quantita_guide} Guide"
    descrizione = f"Ricarica automatica di {quantita_guide} guide."
    prezzi = [LabeledPrice(label=titolo, amount=prezzo_euro * 100)]
    bot.send_invoice(chat_id=call.message.chat.id, title=titolo, description=descrizione, invoice_payload=f"PAGAMENTO|{id_allievo}|{quantita_guide}", provider_token=STRIPE_PROVIDER_TOKEN, currency="EUR", prices=prezzi, start_parameter="ricarica")

@bot.pre_checkout_query_handler(func=lambda query: True)
def checkout_sicurezza(pre_checkout_query):
    bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def pagamento_successo(message):
    dati = message.successful_payment.invoice_payload.split('|')
    id_allievo, guide_acquistate = dati[1], int(dati[2])
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE allievi SET crediti = crediti + %s, pacchetto_attivo = %s WHERE id = %s", (guide_acquistate, f"Pacchetto ({guide_acquistate} Guide)", id_allievo))
        conn.commit()
        bot.reply_to(message, f"🎉 *PAGAMENTO RICEVUTO!*\n{guide_acquistate} guide accreditate istantaneamente!", parse_mode="Markdown")
        cur.close()
        conn.close()
    except Exception as e:
        print(e)

# ==========================================
# SEZIONE PRENOTAZIONI GUIDA
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data.startswith('istr|'))
def scegli_istruttore(call):
    id_allievo = call.data.split('|')[1]
    markup = InlineKeyboardMarkup()
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT nome FROM istruttori ORDER BY nome")
        istruttori = cur.fetchall()
        cur.close()
        conn.close()
        for istr in istruttori: markup.add(InlineKeyboardButton(f"👨‍🏫 {istr[0]}", callback_data=f"data|{id_allievo}|{istr[0]}"))
        markup.add(InlineKeyboardButton("🔄 Nessuna preferenza", callback_data=f"data|{id_allievo}|Da Assegnare"))
        bot.edit_message_text("Con quale istruttore vuoi fare la guida?", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)
    except Exception as e: print(e)

@bot.callback_query_handler(func=lambda call: call.data.startswith('data|'))
def scegli_giorno(call):
    dati = call.data.split('|')
    id_allievo, nome_istruttore = dati[1], dati[2]
    markup = InlineKeyboardMarkup()
    giorni_it = {0: "Lunedì", 1: "Martedì", 2: "Mercoledì", 3: "Giovedì", 4: "Venerdì", 5: "Sabato"}
    oggi = datetime.now()
    giorni_aggiunti, i = 0, 1
    while giorni_aggiunti < 10:
        gc = oggi + timedelta(days=i)
        if gc.weekday() != 6:
            testo = f"Domani ({gc.strftime('%d/%m')})" if i == 1 else f"📅 {giorni_it[gc.weekday()]} {gc.strftime('%d/%m')}"
            markup.add(InlineKeyboardButton(testo, callback_data=f"ora|{id_allievo}|{nome_istruttore}|{gc.strftime('%d/%m/%Y')}"))
            giorni_aggiunti += 1
        i += 1
    bot.edit_message_text(f"🗓️ Scegli il GIORNO:", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('ora|'))
def scegli_orario(call):
    dati = call.data.split('|')
    markup = InlineKeyboardMarkup()
    row = []
    for h in range(8, 21):
        row.append(InlineKeyboardButton(f"🕒 {h:02d}:00", callback_data=f"dur|{dati[1]}|{dati[2]}|{dati[3]}|{h:02d}:00"))
        if len(row) == 3:
            markup.row(*row)
            row = []
    if row: markup.row(*row)
    bot.edit_message_text("🕒 A che ora?", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('dur|'))
def scegli_durata(call):
    dati = call.data.split('|')
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("⏱️ 20 min (1 Guida)", callback_data=f"conf|{dati[1]}|{dati[2]}|{dati[3]}|{dati[4]}|1"))
    markup.add(InlineKeyboardButton("⏱️ 40 min (2 Guide)", callback_data=f"conf|{dati[1]}|{dati[2]}|{dati[3]}|{dati[4]}|2"))
    markup.add(InlineKeyboardButton("⏱️ 1 Ora (3 Guide)", callback_data=f"conf|{dati[1]}|{dati[2]}|{dati[3]}|{dati[4]}|3"))
    bot.edit_message_text("⏳ Quanto vuoi guidare?", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('conf|'))
def conferma_prenotazione(call):
    dati = call.data.split('|')
    id_allievo, nome_istr, data_scelta, ora_inizio, scatti = dati[1], dati[2], dati[3], dati[4], int(dati[5])
    h, m = map(int, ora_inizio.split(':'))
    minuti = m + (scatti * 20)
    ora_fine = f"{(h + minuti // 60):02d}:{(minuti % 60):02d}"
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT nome, crediti FROM allievi WHERE id=%s", (id_allievo,))
        allievo = cur.fetchone()
        if allievo and allievo[1] >= scatti:
            cur.execute("INSERT INTO guide (allievo, istruttore, veicolo, data, ora, ora_fine, stato_pagamento, scatti) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", (allievo[0], nome_istr, "Non assegnato", data_scelta, ora_inizio, ora_fine, f"Scalato ({scatti})", scatti))
            cur.execute("UPDATE allievi SET crediti = crediti - %s WHERE id=%s", (scatti, id_allievo))
            conn.commit()
            bot.edit_message_text(f"✅ *CONFERMATA!*\n🗓 {data_scelta} alle {ora_inizio} con {nome_istr}", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="Markdown")
        else:
            bot.edit_message_text("❌ Crediti insufficienti.", chat_id=call.message.chat.id, message_id=call.message.message_id)
        cur.close()
        conn.close()
    except Exception as e: print(e)

# ==========================================
# TRUCCO PER RENDER (Server Web)
# ==========================================
app = Flask(__name__)
@app.route('/')
def home(): return "✅ Bot ACCESO!"
def run_web(): app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
if __name__ == "__main__":
    threading.Thread(target=run_web).start()
    bot.infinity_polling()
