import tkinter as tk
from tkinter import ttk, messagebox
import json
import os
import requests
import time
import sys
import threading
import ctypes
import winsound
from datetime import datetime
import ttkbootstrap as ttkb
import pandas as pd
from pystray import MenuItem as item
import pystray
from PIL import Image, ImageTk

# --- Importação dos componentes modulares ---
from core_components import (
    get_application_path, Tooltip, AlertConfigDialog, AlertManagerWindow,
    calculate_rsi, calculate_bollinger_bands, calculate_macd, calculate_emas
)

# --- Funções de Comunicação e Formatação ---

def show_windows_ok_popup(title, message, sound_stop_event=None):
    """Exibe um popup de notificação do Windows e para o som ao ser fechado."""
    ctypes.windll.user32.MessageBoxW(None, str(message), str(title), 0x00000040 | 0x00001000)
    if sound_stop_event:
        sound_stop_event.set()

def send_telegram_alert(bot_token, chat_id, message):
    """Envia uma mensagem de alerta para um chat do Telegram."""
    if not bot_token or "AQUI" in str(bot_token) or not chat_id or "AQUI" in str(chat_id):
        return
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {'chat_id': chat_id, 'text': message, 'parse_mode': 'Markdown'}
    try:
        requests.post(url, data=payload, timeout=10).raise_for_status()
        print("Alerta enviado para o Telegram.")
    except Exception as e:
        print(f"--> Erro ao enviar para o Telegram: {e}")

def format_large_number(num):
    """Formata números grandes para uma leitura mais fácil (K, M, B, T)."""
    if num is None or not isinstance(num, (int, float)):
        return "N/A"
    if num < 1_000:
        return f"${num:,.2f}"
    if num < 1_000_000:
        return f"${num/1_000:,.2f} K"
    if num < 1_000_000_000:
        return f"${num/1_000_000:,.2f} M"
    if num < 1_000_000_000_000:
        return f"${num/1_000_000_000:,.2f} B"
    return f"${num/1_000_000_000_000:,.2f} T"


# --- Classe Principal da Aplicação ---

class CryptoMonitorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Programa Alerta Cripto (Análise Integrada)")
        self.set_initial_geometry()
        
        self.config = {}
        self.check_interval_ms = 60000
        self.current_prices = {}
        self.ticker_24h_data = {}
        self.sound_threads = {}
        self.fundamental_data = {}
        self.coin_gecko_ids = {}
        self.icons = {}
        self.symbol_source_map = {} 
        
        self.config_path = os.path.join(get_application_path(), "config.json")
        self.history_path = os.path.join(get_application_path(), "alert_history.json")
        
        self.update_job = None
        self.interval_map = {"1 Minuto": 60, "5 Minutos": 300, "15 Minutos": 900, "30 Minutos": 1800, "1 Hora": 3600}
        
        self.tray_icon = None
        self.all_symbols_list = []

        self._load_icons()
        self._setup_styles()
        self._create_widgets()
        
        self.load_config_and_populate()
        self.load_alert_history()
        
        self.root.protocol("WM_DELETE_WINDOW", self.minimize_to_tray)
        
        threading.Thread(target=self._fetch_all_symbols, daemon=True).start()
        
        self.root.after(1000, self.force_update)

    def _load_icons(self):
        icon_files = { "manage": "manage_icon.png", "sync": "sync_icon.png", "clear": "clear_icon.png" }
        app_path = get_application_path()
        for name, filename in icon_files.items():
            try:
                image_path = os.path.join(app_path, 'icons', filename)
                if not os.path.exists(image_path): image_path = os.path.join(app_path, filename)
                image = Image.open(image_path).resize((16, 16), Image.Resampling.LANCZOS)
                self.icons[name] = ImageTk.PhotoImage(image)
            except Exception as e:
                print(f"Aviso: Não foi possível carregar o ícone '{filename}'. {e}")
                self.icons[name] = None
    
    def center_toplevel_on_main(self, toplevel_window):
        self.root.update_idletasks()
        main_x,main_y,main_width,main_height = self.root.winfo_x(),self.root.winfo_y(),self.root.winfo_width(),self.root.winfo_height()
        toplevel_window.update_idletasks()
        toplevel_width,toplevel_height = toplevel_window.winfo_width(),toplevel_window.winfo_height()
        x = main_x + (main_width // 2) - (toplevel_width // 2)
        y = main_y + (main_height // 2) - (toplevel_height // 2)
        toplevel_window.geometry(f"+{x}+{y}")
        
    def _fetch_all_symbols(self):
        binance_symbols, coingecko_map = set(), {}

        def fetch_binance():
            nonlocal binance_symbols
            try:
                response = requests.get("https://api.binance.com/api/v3/exchangeInfo", timeout=15)
                response.raise_for_status()
                symbols = {s['symbol'] for s in response.json()['symbols'] if 'USDT' in s['symbol']}
                binance_symbols.update(symbols)
            except Exception as e: print(f"--> Erro na thread ao buscar símbolos da Binance: {e}")

        def fetch_coingecko():
            nonlocal coingecko_map
            try:
                response = requests.get("https://api.coingecko.com/api/v3/coins/list?include_platform=false", timeout=15)
                response.raise_for_status()
                for item in response.json(): coingecko_map[item['id']] = {'symbol': item['symbol'].upper(), 'id': item['id']}
            except Exception as e: print(f"--> Erro na thread ao buscar IDs da CoinGecko: {e}")

        t1, t2 = threading.Thread(target=fetch_binance), threading.Thread(target=fetch_coingecko)
        t1.start(); t2.start(); t1.join(); t2.join()

        final_symbols = set(binance_symbols)
        self.coin_gecko_ids = {}
        temp_cg_symbol_to_id_map = {v['symbol']: k for k, v in coingecko_map.items()}

        for symbol in binance_symbols:
            self.symbol_source_map[symbol] = 'binance'
            base_currency = symbol.replace('USDT', '')
            if base_currency in temp_cg_symbol_to_id_map:
                 self.coin_gecko_ids[symbol] = temp_cg_symbol_to_id_map[base_currency]

        for cg_id, cg_data in coingecko_map.items():
            if f"{cg_data['symbol']}USDT" not in binance_symbols:
                final_symbols.add(cg_id); self.symbol_source_map[cg_id] = 'coingecko'; self.coin_gecko_ids[cg_id] = cg_id

        self.all_symbols_list = sorted(list(final_symbols))

    def _fetch_fundamental_data(self, coingecko_ids):
        if not coingecko_ids: return {}
        try:
            ids_string = ",".join(list(set(coingecko_ids)))
            params = {'vs_currency': 'usd', 'ids': ids_string, 'price_change_percentage': '24h'}
            response = requests.get(f"https://api.coingecko.com/api/v3/coins/markets", params=params, timeout=15)
            response.raise_for_status()
            return {item['id']: item for item in response.json()}
        except Exception as e:
            print(f"--> Erro ao buscar dados fundamentais da CoinGecko: {e}"); return {}

    def get_coingecko_id(self, symbol):
        return self.coin_gecko_ids.get(symbol)
    
    def set_initial_geometry(self):
        width, height = 1600, 800
        screen_width, screen_height = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x, y = (screen_width / 2) - (width / 2), (screen_height / 2) - (height / 2)
        self.root.geometry(f'{width}x{height}+{int(x)}+{int(y)}')
        
    def _setup_styles(self):
        style = ttkb.Style(); style.configure("Treeview", font=(None, 10), rowheight=30); style.configure("Treeview.Heading", font=(None, 11, 'bold'))
    
    def _create_widgets(self):
        self.notebook = ttkb.Notebook(self.root, padding=10); self.notebook.pack(expand=True, fill='both')
        self.monitor_frame, self.history_frame, self.legend_frame = ttkb.Frame(self.notebook), ttkb.Frame(self.notebook), ttkb.Frame(self.notebook)
        self.notebook.add(self.monitor_frame, text='Monitor'); self.notebook.add(self.history_frame, text='Histórico de Alertas'); self.notebook.add(self.legend_frame, text='Legenda')
        self.create_monitor_widgets(); self.create_history_widgets(); self.create_legend_widgets()
        
    def create_monitor_widgets(self):
        table_frame = ttkb.Frame(self.monitor_frame); table_frame.pack(expand=True, fill='both', padx=5, pady=5)
        controls_frame = ttkb.Frame(self.monitor_frame, padding=(0, 10)); controls_frame.pack(fill='x', padx=5, pady=5)
        
        columns = ('symbol', 'current_price', 'price_change_24h', 
                   'rsi_signal', 'bollinger_signal', 'macd_signal', 'mme_cross', 
                   'market_cap', 'fdv', 'mcap_fdv_ratio')
                   
        self.tree = ttkb.Treeview(table_frame, columns=columns, show='headings', bootstyle="dark")
        
        self.header_tooltips = {
            'symbol': "Símbolo do par (ex: BTCUSDT) ou ID da CoinGecko (ex: bitcoin).",
            'current_price': "Último preço negociado na Binance ou CoinGecko.",
            'price_change_24h': "Variação percentual do preço nas últimas 24 horas.",
            'rsi_signal': "Sinal do RSI (Índice de Força Relativa) no gráfico diário. 'SOBREVENDIDO' é um sinal de compra potencial; 'SOBRECOMPRADO' é um sinal de venda potencial.",
            'bollinger_signal': "Sinal das Bandas de Bollinger no gráfico diário. 'ABAIXO DA BANDA' é um sinal de compra potencial; 'ACIMA DA BANDA' é um sinal de venda potencial.",
            'macd_signal': "Sinais de cruzamento MACD no gráfico diário. 'Cruzamento de Alta' é otimista; 'Cruzamento de Baixa' é pessimista.",
            'mme_cross': "Sinais de Cruz Dourada/Morte (MME 50/200). A Cruz Dourada é um forte sinal de alta a longo prazo.",
            'market_cap': "Capitalização de Mercado: Valor total de todas as moedas em circulação.",
            'fdv': "Fully Diluted Valuation: Valor de mercado se todos os tokens estivessem em circulação.",
            'mcap_fdv_ratio': "Razão entre Market Cap e FDV. Um valor próximo a 1.0 é positivo, indicando baixa inflação futura."
        }
        for col_id in columns: self.tree.heading(col_id, text=col_id.replace('_', ' ').title(), command=lambda _c=col_id: self.sort_column(_c, False))
        
        self.tree.column('symbol', width=120, anchor=tk.W)
        self.tree.column('current_price', width=120, anchor=tk.E)
        self.tree.column('price_change_24h', width=100, anchor=tk.CENTER)
        self.tree.column('rsi_signal', width=200, anchor=tk.W)
        self.tree.column('bollinger_signal', width=200, anchor=tk.W)
        self.tree.column('macd_signal', width=150, anchor=tk.CENTER)
        self.tree.column('mme_cross', width=180, anchor=tk.CENTER)
        self.tree.column('market_cap', width=120, anchor=tk.E)
        self.tree.column('fdv', width=120, anchor=tk.E)
        self.tree.column('mcap_fdv_ratio', width=80, anchor=tk.CENTER)

        self.tree.pack(expand=True, fill='both')
        self._setup_monitor_tags()
        self.tooltip = Tooltip(self.tree); self.tree.bind('<Motion>', self._on_treeview_motion, add='+'); self.tree.bind('<Leave>', self._on_treeview_leave, add='+')
        
        ttkb.Button(controls_frame, text=" Gerenciar Alertas", image=self.icons.get("manage"), compound="left", command=self.open_alert_manager, bootstyle="primary").pack(side='left', padx=5)
        ttkb.Button(controls_frame, text=" Sincronizar Agora", image=self.icons.get("sync"), compound="left", command=self.force_update, bootstyle="info").pack(side='left', padx=5)
        ttkb.Label(controls_frame, text="Intervalo:").pack(side='left', padx=(20, 5))
        self.interval_combo = ttkb.Combobox(controls_frame, values=list(self.interval_map.keys()), width=15, state="readonly"); self.interval_combo.pack(side='left')
        self.interval_combo.bind("<<ComboboxSelected>>", self.on_interval_change)

    def update_prices(self):
        all_symbols_to_monitor = list({c['symbol'] for c in self.config.get("cryptos_to_monitor", [])})
        if not all_symbols_to_monitor:
            if self.root.winfo_exists(): self.update_job = self.root.after(self.check_interval_ms, self.update_prices); return

        binance_symbols = [s for s in all_symbols_to_monitor if self.symbol_source_map.get(s) == 'binance']
        coingecko_ids = [s for s in all_symbols_to_monitor if self.symbol_source_map.get(s) == 'coingecko']
        
        all_cg_ids_for_fundamentals = [cg_id for symbol in all_symbols_to_monitor if (cg_id := self.get_coingecko_id(symbol))]
        self.fundamental_data = self._fetch_fundamental_data(all_cg_ids_for_fundamentals)
        self.ticker_24h_data = self.get_24hr_ticker_data(binance_symbols)

        for cg_id in coingecko_ids:
            if cg_id in self.fundamental_data:
                item = self.fundamental_data[cg_id]
                self.ticker_24h_data[item['id']] = {
                    'symbol': item['id'],
                    'lastPrice': item.get('current_price', 0),
                    'priceChangePercent': item.get('price_change_percentage_24h_in_currency', 0)
                }

        for symbol in all_symbols_to_monitor:
            if not self.tree.exists(symbol): continue
            
            source_data = self.ticker_24h_data.get(symbol)
            if not source_data:
                self.tree.set(symbol, 'current_price', "Erro"); continue

            price = float(source_data.get('lastPrice', 0))
            change_24h = float(source_data.get('priceChangePercent', 0)) if source_data.get('priceChangePercent') is not None else 0.0
            self.current_prices[symbol] = price
            
            cg_id = self.get_coingecko_id(symbol)
            fund_data = self.fundamental_data.get(cg_id)
            
            rsi_signal, bollinger_signal, macd, mme = "", "", "N/A", "N/A"
            s_tag, mme_tag = 'status_neutral', 'status_neutral'
            
            if self.symbol_source_map.get(symbol) == 'binance':
                klines = self.get_kline_data(symbol, interval='1d', limit=300)
                if klines:
                    df = pd.DataFrame(klines, columns=['ts','o','h','l','close','v','ct','qav','nt','tbbav','tbqav','ig'])
                    df['close'] = pd.to_numeric(df['close'])
                    
                    rsi, (ub, lb) = calculate_rsi(df), calculate_bollinger_bands(df)
                    macd, emas = calculate_macd(df), calculate_emas(df, [50, 200])
                    
                    if rsi >= 70: rsi_signal = "SOBRECOMPRADO (RSI >= 70)"
                    elif rsi <= 30 and rsi > 0: rsi_signal = "SOBREVENDIDO (RSI <= 30)"
                    
                    if price > ub and ub > 0: bollinger_signal = "ACIMA DA BANDA SUPERIOR"
                    elif price < lb and lb > 0: bollinger_signal = "ABAIXO DA BANDA INFERIOR"

                    if 50 in emas and 200 in emas:
                        if emas[50].iloc[-2] < emas[200].iloc[-2] and emas[50].iloc[-1] > emas[200].iloc[-1]: mme = "MME: Cruz Dourada (50/200)"
                        elif emas[50].iloc[-2] > emas[200].iloc[-2] and emas[50].iloc[-1] < emas[200].iloc[-1]: mme = "MME: Cruz da Morte (50/200)"

            if "SOBREVENDIDO" in rsi_signal or "ABAIXO" in bollinger_signal: s_tag = 'status_buy'
            elif "SOBRECOMPRADO" in rsi_signal or "ACIMA" in bollinger_signal: s_tag = 'status_sell'
            
            if "Alta" in str(macd) or "Dourada" in str(mme): mme_tag = 'status_buy'
            elif "Baixa" in str(macd) or "Morte" in str(mme): mme_tag = 'status_sell'
            
            mcap, fdv, ratio = "N/A", "N/A", "N/A"
            if fund_data:
                mcap_val, fdv_val = fund_data.get('market_cap'), fund_data.get('fully_diluted_valuation')
                mcap, fdv = format_large_number(mcap_val), format_large_number(fdv_val)
                if mcap_val and fdv_val and fdv_val > 0:
                    ratio = f"{(mcap_val / fdv_val):.2f}"
            
            self.tree.item(symbol, tags=['price_up' if change_24h >= 0 else 'price_down', s_tag, mme_tag])
            d_symbol = symbol.upper() if self.symbol_source_map.get(symbol) == 'binance' else f"{fund_data.get('symbol', symbol).upper()} (CG)"
            
            self.tree.set(symbol, 'symbol', d_symbol)
            self.tree.set(symbol, 'current_price', f"${price:,.8f}".rstrip('0').rstrip('.'))
            self.tree.set(symbol, 'price_change_24h', f"{change_24h:+.2f}%")
            self.tree.set(symbol, 'rsi_signal', rsi_signal)
            self.tree.set(symbol, 'bollinger_signal', bollinger_signal)
            self.tree.set(symbol, 'macd_signal', macd)
            self.tree.set(symbol, 'mme_cross', mme)
            self.tree.set(symbol, 'market_cap', mcap)
            self.tree.set(symbol, 'fdv', fdv)
            self.tree.set(symbol, 'mcap_fdv_ratio', ratio)
            
            for crypto in self.config.get("cryptos_to_monitor", []):
                if crypto['symbol'] == symbol:
                    for alert in crypto.get("alerts", []):
                        a_type, triggered = alert.get('type'), False
                        
                        if a_type in ['high', 'low']:
                            triggered = (a_type == 'high' and price >= alert.get('price', 0)) or \
                                      (a_type == 'low' and price <= alert.get('price', 0))
                        
                        elif a_type == 'status' and self.symbol_source_map.get(symbol) == 'binance':
                            a_val = alert.get('value')
                            triggered = (a_val == rsi_signal) or \
                                        (a_val == bollinger_signal) or \
                                        (a_val == f"MACD: {macd}") or \
                                        (a_val == mme)
                        
                        if triggered and not alert.get("triggered_now", False):
                            alert["triggered_now"] = True
                            alert_info = {**alert, 'symbol': d_symbol, 'original_symbol': symbol}
                            self.trigger_alert(alert_info)
                        elif not triggered:
                            alert["triggered_now"] = False
                            
        if self.root.winfo_exists():
            self.update_job = self.root.after(self.check_interval_ms, self.update_prices)

    def load_config_and_populate(self):
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f: self.config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.config = {"telegram_bot_token": "SEU_TOKEN_AQUI", "telegram_chat_id": "SEU_CHAT_ID_AQUI", "check_interval_seconds": 300, "cryptos_to_monitor": []}
            self._save_config()
        self.check_interval_ms = self.config.get("check_interval_seconds", 300) * 1000
        current_interval_sec = self.config.get("check_interval_seconds", 300)
        for text, seconds in self.interval_map.items():
            if seconds == current_interval_sec: self.interval_combo.set(text); break
        else: self.interval_combo.set("5 Minutos")
        
        for i in self.tree.get_children(): self.tree.delete(i)
        all_symbols = {c['symbol'] for c in self.config.get("cryptos_to_monitor", [])}
        for symbol in sorted(list(all_symbols)):
            self.tree.insert('', tk.END, iid=symbol, values=(symbol, "Carregando...", "...", "...", "...", "...", "...", "...", "...", "..."))
            
        for crypto in self.config.get("cryptos_to_monitor", []):
            for alert in crypto.get("alerts", []): alert['triggered_now'] = False
            
    def _on_treeview_motion(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "heading":
            col_id_str = self.tree.identify_column(event.x)
            if not col_id_str: self.tooltip.hide_tooltip(); return
            col_idx = int(col_id_str.replace('#', '')) - 1
            if col_idx < len(self.tree['columns']):
                col_name = self.tree['columns'][col_idx]
                self.tooltip.show_tooltip(self.header_tooltips.get(col_name, ""), event.x_root, event.y_root)
        else: self.tooltip.hide_tooltip()
        
    def _on_treeview_leave(self, event): self.tooltip.hide_tooltip()
    
    def sort_column(self, col, reverse):
        try:
            data = [(self.tree.set(child, col), child) for child in self.tree.get_children('')]
            def sort_key(item):
                val = item[0].replace('$', '').replace('%', '').replace(',', '').replace('(CG)','').strip()
                mult = 1
                if 'T' in val: mult=1e12; val=val.replace('T','').strip()
                elif 'B' in val: mult=1e9; val=val.replace('B','').strip()
                elif 'M' in val: mult=1e6; val=val.replace('M','').strip()
                elif 'K' in val: mult=1e3; val=val.replace('K','').strip()
                try: return float(val) * mult
                except (ValueError, TypeError): return val.lower()
            data.sort(key=sort_key, reverse=reverse)
            for index, (val, child) in enumerate(data): self.tree.move(child, '', index)
            self.tree.heading(col, command=lambda: self.sort_column(col, not reverse))
        except Exception as e: print(f"Erro ao ordenar: {e}")

    def open_alert_manager(self): AlertManagerWindow(self)
    def on_closing(self):
        if messagebox.askokcancel("Sair", "Deseja fechar o monitor?", parent=self.root): self._quit_application()
    
    def _create_tray_icon(self):
        icon_path = os.path.join(get_application_path(), 'icone.ico')
        image = Image.open(icon_path) if os.path.exists(icon_path) else Image.new('RGB', (64, 64), 'black')
        menu = (item('Mostrar', self.show_window), item('Sair', self._quit_application))
        self.tray_icon = pystray.Icon("MonitorCripto", image, "Programa Alerta Cripto", menu)
        self.tray_icon.run()

    def minimize_to_tray(self):
        self.root.withdraw()
        if not self.tray_icon or not self.tray_icon.visible:
            threading.Thread(target=self._create_tray_icon, daemon=True).start()

    def show_window(self):
        if self.tray_icon: self.tray_icon.stop()
        self.root.after(0, self.root.deiconify)
        
    def _quit_application(self):
        if self.tray_icon: self.tray_icon.stop()
        if self.update_job: self.root.after_cancel(self.update_job)
        for thread_info in self.sound_threads.values():
            if thread_info['thread'].is_alive(): thread_info['stop_event'].set()
        self.root.destroy()
        
    def _setup_monitor_tags(self):
        self.tree.tag_configure('price_up', foreground='#28a745')
        self.tree.tag_configure('price_down', foreground='#dc3545')
        self.tree.tag_configure('status_buy', foreground='#28a745')
        self.tree.tag_configure('status_sell', foreground='#dc3545')
        self.tree.tag_configure('status_neutral', foreground='white')
        
    def _trigger_sound(self, sound_path_str, stop_event):
        if not sound_path_str: return
        sound_path = sound_path_str if os.path.isabs(sound_path_str) else os.path.join(get_application_path(), sound_path_str)
        key = (sound_path, id(stop_event))
        if self.sound_threads.get(key, {}).get('thread', threading.Thread()).is_alive(): return
        thread = threading.Thread(target=self._play_sound_looped, args=(sound_path, stop_event, key), daemon=True)
        self.sound_threads[key] = {'thread': thread, 'stop_event': stop_event}; thread.start()
        
    def _play_sound_looped(self, sound_path, stop_event, key):
        if not os.path.exists(sound_path): print(f"Arquivo de som não encontrado: {sound_path}"); return
        try:
            while not stop_event.is_set(): winsound.PlaySound(sound_path, winsound.SND_FILENAME); time.sleep(0.1)
        except Exception as e: print(f"Erro ao tocar som: {e}")
        finally:
            if key in self.sound_threads: del self.sound_threads[key]
            
    def trigger_alert(self, alert_data):
        symbol, o_symbol = alert_data.get('symbol'), alert_data.get('original_symbol')
        a_type = alert_data.get("type", "N/A"); notes = alert_data.get("notes", "Sem observações.")
        price = self.current_prices.get(o_symbol, 0)
        title = f"ALERTA: {symbol}"
        if a_type in ['high', 'low']:
            a_price = alert_data.get("price", 0)
            msg = (f"{symbol} atingiu alvo de {a_type.upper()} em ${a_price:,.2f}!\nPreço: ${price:,.2f}\n\nObs: {notes}")
            tg_msg = (f"🔔 *ALERTA PREÇO: {symbol}*\n\nAtingiu *{a_type.upper()}* em *${a_price:,.2f}*.\nPreço: `${price:,.2f}`\nObs: _{notes}_")
            h_trigger = f"{a_type.upper()} @ ${a_price:,.2f}"
        else: # status
            a_value = alert_data.get("value", "N/A")
            msg = (f"Sinal Técnico para {symbol}!\n\nStatus: {a_value}\nPreço: ${price:,.2f}\n\nObs: {notes}")
            tg_msg = (f"📈 *SINAL TÉCNICO: {symbol}*\n\nStatus: *{a_value}*\nPreço: `${price:,.2f}`\nObs: _{notes}_")
            h_trigger = f"Status: {a_value}"
        stop_event = threading.Event(); alert_data['stop_event'] = stop_event
        threading.Thread(target=show_windows_ok_popup, args=(title, msg, stop_event), daemon=True).start()
        send_telegram_alert(self.config.get('telegram_bot_token'), self.config.get('telegram_chat_id'), tg_msg)
        if alert_data.get("sound"): self._trigger_sound(alert_data.get("sound"), stop_event)
        self.add_to_history(symbol, h_trigger, notes)
        
    def _save_config(self):
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f: json.dump(self.config, f, indent=2, ensure_ascii=False); return True
        except Exception as e: messagebox.showerror("Erro", f"Não foi possível salvar 'config.json':\n{e}"); return False
        
    def create_history_widgets(self):
        frame = ttkb.Frame(self.history_frame); frame.pack(expand=True, fill='both', padx=5, pady=5)
        ctrl_frame = ttkb.Frame(self.history_frame, padding=(0, 10)); ctrl_frame.pack(fill='x', padx=5, pady=5)
        cols = ('timestamp', 'symbol', 'trigger', 'notes'); self.history_tree = ttkb.Treeview(frame, columns=cols, show='headings', bootstyle="dark")
        self.history_tree.heading('timestamp', text='Data e Hora'); self.history_tree.column('timestamp', width=150, anchor=tk.W)
        self.history_tree.heading('symbol', text='Símbolo'); self.history_tree.column('symbol', width=120, anchor=tk.CENTER)
        self.history_tree.heading('trigger', text='Alerta Disparado'); self.history_tree.column('trigger', width=250, anchor=tk.W)
        self.history_tree.heading('notes', text='Observações'); self.history_tree.column('notes', width=400, anchor=tk.W)
        self.history_tree.pack(expand=True, fill='both')
        ttkb.Button(ctrl_frame, text=" Limpar Histórico", image=self.icons.get("clear"), compound="left", command=self.clear_alert_history, bootstyle="danger").pack(side='left', padx=5)
        
    def create_legend_widgets(self):
        canvas = tk.Canvas(self.legend_frame, borderwidth=0, background="#222b31"); frame = ttkb.Frame(canvas, padding=(30, 20))
        scrollbar = ttkb.Scrollbar(self.legend_frame, orient="vertical", command=canvas.yview, bootstyle="round-dark")
        canvas.configure(yscrollcommand=scrollbar.set); scrollbar.pack(side="right", fill="y"); canvas.pack(side="left", fill="both", expand=True)
        canvas_frame = canvas.create_window((4, 4), window=frame, anchor="nw")
        frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(canvas_frame, width=e.width))
        def create_entry(p, title, color, desc):
            f = ttkb.Frame(p, padding=(0, 10)); f.pack(fill='x', expand=True, anchor='w')
            ttkb.Label(f, text=title, font=("Helvetica", 12, "bold"), foreground=color).pack(anchor='w')
            ttkb.Label(f, text=desc, wraplength=800, justify='left', font=("Helvetica", 10)).pack(anchor='w', pady=(5, 0))
        ttkb.Label(frame, text="Legenda dos Sinais de Análise", font=("Helvetica", 16, "bold")).pack(anchor='w', pady=(0, 20))
        tech_frame = ttkb.LabelFrame(frame, text=" Sinais de Análise Técnica ", bootstyle="info", padding=15); tech_frame.pack(fill='x', expand=True, pady=10, anchor='w')
        create_entry(tech_frame, "SOBRECOMPRADO/ACIMA DA BANDA", "#dc3545", "Indica que o ativo foi comprado em excesso (RSI>=70) ou está acima da sua volatilidade normal.\nAumenta a probabilidade de uma correção de preço (queda).")
        create_entry(tech_frame, "SOBREVENDIDO/ABAIXO DA BANDA", "#28a745", "Indica que o ativo foi vendido em excesso (RSI<=30) ou está abaixo da sua volatilidade normal.\nAumenta a probabilidade de uma recuperação de preço (alta).")
        create_entry(tech_frame, "Sinal MACD (1D)", "white", "Cruzamento de Alta (otimista) ou de Baixa (pessimista) no gráfico diário.")
        create_entry(tech_frame, "Cruzamento MME (1D)", "white", "Cruz Dourada (MME 50 > 200) é um forte sinal de alta. Cruz da Morte (MME 50 < 200) é um forte sinal de baixa.")
        fund_frame = ttkb.LabelFrame(frame, text=" Indicadores Fundamentais ", bootstyle="primary", padding=15); fund_frame.pack(fill='x', expand=True, pady=10, anchor='w')
        create_entry(fund_frame, "Market Cap (MCap)", "white", "Valor total de mercado do projeto (Preço x Fornecimento Circulante).")
        create_entry(fund_frame, "FDV (Fully Diluted Valuation)", "white", "Valor total de mercado se todos os tokens existissem. Ajuda a medir a inflação futura.")
        create_entry(fund_frame, "MCap/FDV Ratio", "white", "Razão entre MCap e FDV. Próximo de 1.0 indica baixa inflação futura de tokens, o que é positivo.")
        
    def load_alert_history(self):
        try:
            with open(self.history_path, 'r', encoding='utf-8') as f: history = json.load(f)
            for i in self.history_tree.get_children(): self.history_tree.delete(i)
            for record in reversed(history): self.history_tree.insert('', 0, values=(record['timestamp'], record['symbol'], record['trigger'], record['notes']))
        except (FileNotFoundError, json.JSONDecodeError): pass
        
    def add_to_history(self, symbol, trigger, notes):
        history = []; 
        try:
            with open(self.history_path, 'r', encoding='utf-8') as f: history = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError): pass
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        history.append({'timestamp': timestamp, 'symbol': symbol, 'trigger': trigger, 'notes': notes})
        with open(self.history_path, 'w', encoding='utf-8') as f: json.dump(history, f, indent=2)
        self.history_tree.insert('', 0, values=(timestamp, symbol, trigger, notes))
        
    def clear_alert_history(self):
        if not messagebox.askyesno("Confirmar", "Limpar permanentemente o histórico de alertas?", parent=self.root): return
        try:
            with open(self.history_path, 'w', encoding='utf-8') as f: json.dump([], f)
            for i in self.history_tree.get_children(): self.history_tree.delete(i)
            messagebox.showinfo("Sucesso", "Histórico de alertas limpo.", parent=self.root)
        except Exception as e: messagebox.showerror("Erro", f"Não foi possível limpar o histórico:\n{e}", parent=self.root)
        
    def on_interval_change(self, event=None):
        selected = self.interval_combo.get()
        if (new_sec := self.interval_map.get(selected)):
            self.config['check_interval_seconds'] = new_sec
            if self._save_config(): self.check_interval_ms = new_sec * 1000; print(f"Intervalo alterado para {selected}.")
            self.force_update()
            
    def force_update(self):
        print("Sincronização de dados iniciada..."); 
        if self.update_job: self.root.after_cancel(self.update_job)
        threading.Thread(target=self.update_prices, daemon=True).start()
        
    def get_24hr_ticker_data(self, symbols):
        if not symbols: return {}
        try:
            params = {'symbols': json.dumps(list(symbols), separators=(',', ':'))}
            response = requests.get("https://api.binance.com/api/v3/ticker/24hr", params=params, timeout=10)
            response.raise_for_status()
            return {item['symbol']: item for item in response.json()}
        except Exception as e: print(f"--> Erro ao buscar ticker 24h da Binance: {e}"); return {}
        
    def get_kline_data(self, symbol, interval='1d', limit=300):
        try:
            params = {'symbol': symbol, 'interval': interval, 'limit': limit}
            response = requests.get("https://api.binance.com/api/v3/klines", params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e: print(f"--> Erro ao buscar klines da Binance para '{symbol}': {e}"); return None

if __name__ == "__main__":
    try:
        import pandas as pd
        from pystray import MenuItem as item, Icon
        from PIL import Image, ImageTk
    except ImportError as e:
        messagebox.showerror("Biblioteca Faltando", f"Biblioteca necessária não encontrada: {e.name}.\nInstale com 'pip install {e.name}'")
        sys.exit()
    
    root = ttkb.Window(themename="cyborg")
    app = CryptoMonitorApp(root)
    root.mainloop()