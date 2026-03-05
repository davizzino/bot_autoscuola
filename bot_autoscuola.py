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
        "Vuoi controllare il tuo saldo o prenotare una guida?\n"
        "👉 *Scrivi il tuo NOME e COGNOME*."
    )
    bot.reply_to(message, testo, parse_mode="Markdown")

# --- 1. CERCA L'ALLIEVO ---
@bot.message_handler(func=lambda message: True)
def check_student(message):
    nome_inserito = message.text.strip()
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, nome, crediti, pacchetto_attivo FROM allievi WHERE nome ILIKE %s", (nome_inserito,))
        allievo = cur.fetchone()
        cur.close()
        conn.close()
        
        if allievo:
            id_a, nome_reale, crediti, pacchetto = allievo
            pacchetto = pacchetto if pacchetto else "Nessuno"
            
            risposta = f"👤 *Profilo: {nome_reale}*\n📦 {pacchetto}\n⏳ *Guide Rimaste: {crediti}*"
            
            markup = InlineKeyboardMarkup()
            if crediti > 0:
                markup.add(InlineKeyboardButton("🗓️ Inizia Prenotazione", callback_data=f"istr|{id_a}"))
            
            markup.add(InlineKeyboardButton("🛒 Acquista Pacchetto Prepagato", callback_data=f"shop|{id_a}"))
                
            bot.reply_to(message, risposta, parse_mode="Markdown", reply_markup=markup)
        else:
            bot.reply_to(message, "❌ Non ho trovato questo nome. Riprova!")
    except Exception as e:
        bot.reply_to(message, "⚠️ Errore di rete.")
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
    
    bot.edit_message_text("🛒 **Negozio Autoscuola**\nScegli il pacchetto da ricaricare sul tuo profilo:", 
                          chat_id=call.message.chat.id, message_id=call.message.message_id, 
                          reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith('buy|'))
def genera_fattura(call):
    dati = call.data.split('|')
    id_allievo, quantita_guide, prezzo_euro = dati[1], int(dati[2]), int(dati[3])
    
    titolo = f"Pacchetto {quantita_guide} Guide"
    descrizione = f"Ricarica automatica di {quantita_guide} guide prepagate sul tuo profilo allievo."
    
    prezzo_centesimi = prezzo_euro * 100
    prezzi = [LabeledPrice(label=titolo, amount=prezzo_centesimi)]
    
    payload_segreto = f"PAGAMENTO|{id_allievo}|{quantita_guide}"
    
    bot.send_invoice(
        chat_id=call.message.chat.id,
        title=titolo,
        description=descrizione,
        invoice_payload=payload_segreto,
        provider_token=STRIPE_PROVIDER_TOKEN,
        currency="EUR",
        prices=prezzi,
        start_parameter="ricarica-autoscuola"
    )

@bot.pre_checkout_query_handler(func=lambda query: True)
def checkout_sicurezza(pre_checkout_query):
    bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def pagamento_successo(message):
    payload = message.successful_payment.invoice_payload
    dati = payload.split('|')
    id_allievo = dati[1]
    guide_acquistate = int(dati[2])
    
    nome_pacchetto = f"Pacchetto Online ({guide_acquistate} Guide)"
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("UPDATE allievi SET crediti = crediti + %s, pacchetto_attivo = %s WHERE id = %s", 
                    (guide_acquistate, nome_pacchetto, id_allievo))
        conn.commit()
        
        cur.execute("SELECT nome FROM allievi WHERE id=%s", (id_allievo,))
        nome_allievo = cur.fetchone()[0]
        cur.close()
        conn.close()
        
        bot.reply_to(message, f"🎉 *PAGAMENTO RICEVUTO!*\n\nGrazie {nome_allievo}, le tue {guide_acquistate} guide sono state accreditate sul tuo conto istantaneamente!\nPuoi già iniziare a prenotarle.", parse_mode="Markdown")
        
    except Exception as e:
        print("Errore durante l'aggiornamento del DB dopo il pagamento:", e)
        bot.reply_to(message, "Pagamento ricevuto, ma c'è stato un ritardo nell'aggiornamento. Contatta la segreteria.")

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
        for istr in istruttori:
            markup.add(InlineKeyboardButton(f"👨‍🏫 {istr[0]}", callback_data=f"data|{id_allievo}|{istr[0]}"))
        markup.add(InlineKeyboardButton("🔄 Nessuna preferenza", callback_data=f"data|{id_allievo}|Da Assegnare"))
        bot.edit_message_text("Ottimo! **Con quale istruttore vuoi fare la guida?**", 
                              chat_id=call.message.chat.id, message_id=call.message.message_id, 
                              reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        print(e)

@bot.callback_query_handler(func=lambda call: call.data.startswith('data|'))
def scegli_giorno(call):
    dati = call.data.split('|')
    id_allievo, nome_istruttore = dati[1], dati[2]
    markup = InlineKeyboardMarkup()
    giorni_it = {0: "Lunedì", 1: "Martedì", 2: "Mercoledì", 3: "Giovedì", 4: "Venerdì", 5: "Sabato"}
    oggi = datetime.now()
    giorni_aggiunti = 0
    i = 1
    while giorni_aggiunti < 10:
        giorno_calcolato = oggi + timedelta(days=i)
        wd = giorno_calcolato.weekday()
        if wd != 6:
            data_str = giorno_calcolato.strftime('%d/%m/%Y')
            testo_bottone = f"📅 {giorni_it[wd]} {giorno_calcolato.strftime('%d/%m')}"
            if i == 1: testo_bottone = f"Domani ({giorno_calcolato.strftime('%d/%m')})"
            markup.add(InlineKeyboardButton(testo_bottone, callback_data=f"ora|{id_allievo}|{nome_istruttore}|{data_str}"))
            giorni_aggiunti += 1
        i += 1
    bot.edit_message_text(f"Istruttore: {nome_istruttore}\n🗓️ **Scegli il GIORNO della guida:**", 
                          chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith('ora|'))
def scegli_orario(call):
    dati = call.data.split('|')
    id_allievo, nome_istruttore, data_scelta = dati[1], dati[2], dati[3]
    orari = [f"{h:02d}:00" for h in range(8, 21)]
    markup = InlineKeyboardMarkup()
    row = []
    for o in orari:
        row.append(InlineKeyboardButton(f"🕒 {o}", callback_data=f"dur|{id_allievo}|{nome_istruttore}|{data_scelta}|{o}"))
        if len(row) == 3:
            markup.row(*row)
            row = []
    if row: markup.row(*row)
    bot.edit_message_text(f"Giorno: {data_scelta}\n🕒 **A che ora vuoi INIZIARE la guida?**", 
                          chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith('dur|'))
def scegli_durata(call):
    dati = call.data.split('|')
    id_allievo, nome_istr, data_scelta, ora_scelta = dati[1], dati[2], dati[3], dati[4]
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("⏱️ 20 min (Consuma 1 Guida)", callback_data=f"conf|{id_allievo}|{nome_istr}|{data_scelta}|{ora_scelta}|1"))
    markup.add(InlineKeyboardButton("⏱️ 40 min (Consuma 2 Guide)", callback_data=f"conf|{id_allievo}|{nome_istr}|{data_scelta}|{ora_scelta}|2"))
    markup.add(InlineKeyboardButton("⏱️ 1 Ora (Consuma 3 Guide)", callback_data=f"conf|{id_allievo}|{nome_istr}|{data_scelta}|{ora_scelta}|3"))
    bot.edit_message_text(f"Inizio alle {ora_scelta}.\n⏳ **Quanto vuoi guidare?**", 
                          chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith('conf|'))
def conferma_prenotazione(call):
    dati = call.data.split('|')
    id_allievo, nome_istr, data_scelta, ora_inizio, scatti = dati[1], dati[2], dati[3], dati[4], int(dati[5])
    h, m = map(int, ora_inizio.split(':'))
    minuti_totali = m + (scatti * 20)
    h += minuti_totali // 60
    m = minuti_totali % 60
    ora_fine = f"{h:02d}:{m:02d}"
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT nome, crediti FROM allievi WHERE id=%s", (id_allievo,))
        allievo = cur.fetchone()
        if allievo and allievo[1] >= scatti:
            nome_allievo = allievo[0]
            cur.execute("""
                INSERT INTO guide (allievo, istruttore, veicolo, data, ora, ora_fine, stato_pagamento, scatti) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (nome_allievo, nome_istr, "Non assegnato", data_scelta, ora_inizio, ora_fine, f"Scalato da Pacchetto ({scatti})", scatti))
            cur.execute("UPDATE allievi SET crediti = crediti - %s WHERE id=%s", (scatti, id_allievo))
            conn.commit()
            testo_ok = f"✅ *PRENOTAZIONE CONFERMATA!*\n\n👤 Allievo: {nome_allievo}\n👨‍🏫 Istruttore: {nome_istr}\n🗓 Data: {data_scelta}\n🕒 Dalle {ora_inizio} alle {ora_fine}\n\nLa segreteria ha ricevuto la tua prenotazione."
            bot.edit_message_text(testo_ok, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="Markdown")
        else:
            bot.edit_message_text("❌ Operazione negata: non hai abbastanza guide per questa durata.", chat_id=call.message.chat.id, message_id=call.message.message_id)
        cur.close()
        conn.close()
    except Exception as e:
        bot.answer_callback_query(call.id, "Errore di rete.")

# ==========================================
# TRUCCO PER RENDER (Server Web Finto)
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Il Bot dell'Autoscuola è ACCESO e funziona nel Cloud!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    print("🤖 Avvio del Server Web e del Bot in corso...")
    threading.Thread(target=run_web).start()
    bot.infinity_polling()