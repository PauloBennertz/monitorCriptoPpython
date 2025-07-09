import tkinter as tk
from tkinter import ttk, messagebox, filedialog
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
from PIL import Image

# --- Funções Auxiliares ---
def get_application_path():
    """Retorna o caminho do diretório da aplicação, seja executável ou script."""
    if getattr(sys, 'frozen', False):
        application_path = os.path.dirname(sys.executable)
    else:
        application_path = os.path.dirname(os.path.abspath(__file__))
    return application_path

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

# --- Funções de Análise Técnica ---
def calculate_rsi(df, period=14):
    """Calcula o Índice de Força Relativa (RSI)."""
    if df.empty or len(df) < period: return 0
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    if loss.iloc[-1] == 0: return 100
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]

def calculate_bollinger_bands(df, period=20, std_dev=2):
    """Calcula as Bandas de Bollinger."""
    if df.empty or len(df) < period: return 0, 0
    sma = df['close'].rolling(window=period).mean().iloc[-1]
    std = df['close'].rolling(window=period).std().iloc[-1]
    if pd.isna(sma) or pd.isna(std): return 0, 0
    upper_band = sma + (std * std_dev)
    lower_band = sma - (std * std_dev)
    return upper_band, lower_band

# --- Classe para a janela de diálogo de Adicionar/Editar Alerta ---
class AlertConfigDialog(ttkb.Toplevel):
    def __init__(self, parent, all_symbols, alert_data=None):
        super().__init__(parent)
        self.parent = parent; self.result = None; self.title("Configurar Alerta")
        self.geometry("800x450"); self.transient(parent); self.grab_set()
        self.center_window(parent)
        self.all_symbols = all_symbols

        main_frame = ttkb.Frame(self, padding="10"); main_frame.pack(expand=True, fill="both")
        common_frame = ttkb.Frame(main_frame); common_frame.pack(fill='x', pady=(0, 10))
        self.specific_frame = ttkb.Frame(main_frame); self.specific_frame.pack(fill='x', pady=5)
        
        # --- Campo de busca inteligente para símbolos ---
        ttkb.Label(common_frame, text="Símbolo:").grid(row=0, column=0, sticky="w", pady=5)
        # CORREÇÃO: Frame dedicado para o campo de busca e a lista de sugestões
        symbol_search_frame = ttkb.Frame(common_frame)
        symbol_search_frame.grid(row=0, column=1, sticky="ew")
        
        self.symbol_var = ttkb.StringVar(value=alert_data.get('symbol', '') if alert_data else '')
        self.symbol_entry = ttkb.Entry(symbol_search_frame, textvariable=self.symbol_var)
        self.symbol_entry.pack(fill="x", expand=True)
        self.symbol_entry.bind("<KeyRelease>", self.update_symbol_list)
        self.symbol_entry.bind("<FocusOut>", lambda e: self.hide_symbol_list())
        
        self.symbol_listbox = tk.Listbox(symbol_search_frame, height=5)
        self.symbol_listbox.bind("<<ListboxSelect>>", self.on_symbol_select)
        
        ttkb.Label(common_frame, text="Observações:").grid(row=1, column=0, sticky="w", pady=5)
        self.notes_var = ttkb.StringVar(value=alert_data.get('notes', '') if alert_data else '')
        self.notes_entry = ttkb.Entry(common_frame, textvariable=self.notes_var)
        self.notes_entry.grid(row=1, column=1, sticky="ew", pady=5)
        
        ttkb.Label(common_frame, text="Arquivo de Som:").grid(row=2, column=0, sticky="w", pady=5)
        sound_frame = ttkb.Frame(common_frame)
        sound_frame.grid(row=2, column=1, sticky="ew")
        self.sound_var = ttkb.StringVar(value=alert_data.get('sound', 'sons/Alerta.wav') if alert_data else 'sons/Alerta.wav')
        self.sound_entry = ttkb.Entry(sound_frame, textvariable=self.sound_var, state="readonly")
        self.sound_entry.pack(side="left", fill="x", expand=True)
        ttkb.Button(sound_frame, text="Procurar...", command=self.browse_sound_file, bootstyle="secondary-outline").pack(side="left", padx=5)
        ttkb.Button(sound_frame, text="▶", command=self.preview_sound, bootstyle="secondary-outline", width=3).pack(side="left", padx=(0,5))

        ttkb.Label(common_frame, text="Categoria do Alerta:").grid(row=3, column=0, sticky="w", pady=(15, 5))
        self.alert_category_var = ttkb.StringVar()
        self.alert_category_combo = ttkb.Combobox(common_frame, textvariable=self.alert_category_var, values=['Alerta de Preço', 'Alerta de Análise Técnica'], state="readonly")
        self.alert_category_combo.grid(row=3, column=1, sticky="ew", pady=(15, 5))
        self.alert_category_combo.bind("<<ComboboxSelected>>", self.update_alert_fields)

        common_frame.columnconfigure(1, weight=1)

        btn_frame = ttkb.Frame(main_frame); btn_frame.pack(side='bottom', fill='x', pady=(20, 0))
        ttkb.Button(btn_frame, text="Salvar", command=self.on_save, bootstyle="success").pack(side="left", padx=5)
        ttkb.Button(btn_frame, text="Cancelar", command=self.destroy, bootstyle="danger").pack(side="left", padx=5)

        if alert_data: self.alert_category_combo.set('Alerta de Preço' if alert_data.get('type') in ['high', 'low'] else 'Alerta de Análise Técnica')
        else: self.alert_category_combo.current(0)
        self.update_alert_fields(alert_data=alert_data)

    def update_symbol_list(self, event=None):
        search_term = self.symbol_var.get().upper()
        self.symbol_listbox.delete(0, tk.END)
        
        if search_term:
            matches = [s for s in self.all_symbols if search_term in s][:100] # Limita a 100 resultados
            if matches:
                for match in matches:
                    self.symbol_listbox.insert(tk.END, match)
                # CORREÇÃO: Usa pack para mostrar a lista
                self.symbol_listbox.pack(fill="x", expand=True, before=self.symbol_entry.master.pack_slaves()[-1])
            else:
                self.hide_symbol_list()
        else:
            self.hide_symbol_list()

    def on_symbol_select(self, event=None):
        if self.symbol_listbox.curselection():
            selected_symbol = self.symbol_listbox.get(self.symbol_listbox.curselection())
            self.symbol_var.set(selected_symbol)
            self.hide_symbol_list()

    def hide_symbol_list(self, event=None):
        # CORREÇÃO: Usa pack_forget para esconder a lista
        self.symbol_listbox.pack_forget()

    def center_window(self, parent_window):
        self.update_idletasks()
        parent_geo = parent_window.geometry().split('+')
        parent_x, parent_y = int(parent_geo[1]), int(parent_geo[2])
        parent_width, parent_height = parent_window.winfo_width(), parent_window.winfo_height()
        width, height = self.winfo_width(), self.winfo_height()
        x = parent_x + (parent_width // 2) - (width // 2)
        y = parent_y + (parent_height // 2) - (height // 2)
        self.geometry(f'+{x}+{y}')

    def update_alert_fields(self, event=None, alert_data=None):
        for widget in self.specific_frame.winfo_children(): widget.destroy()
        category = self.alert_category_var.get()
        if category == 'Alerta de Preço':
            ttkb.Label(self.specific_frame, text="Tipo (Preço):").grid(row=0, column=0, sticky="w", pady=5)
            self.price_type_var = ttkb.StringVar(value=alert_data.get('type', 'high') if alert_data else 'high')
            self.price_type_combo = ttkb.Combobox(self.specific_frame, textvariable=self.price_type_var, values=['high', 'low'], state="readonly")
            self.price_type_combo.grid(row=0, column=1, sticky="ew", pady=5)
            ttkb.Label(self.specific_frame, text="Preço Alvo ($):").grid(row=1, column=0, sticky="w", pady=5)
            self.price_var = ttkb.DoubleVar(value=alert_data.get('price', 0.0) if alert_data else 0.0)
            self.price_entry = ttkb.Entry(self.specific_frame, textvariable=self.price_var)
            self.price_entry.grid(row=1, column=1, sticky="ew", pady=5)
        elif category == 'Alerta de Análise Técnica':
            status_options = ["SOBRECOMPRADO (RSI >= 70)", "ACIMA DA BANDA SUPERIOR", "SOBREVENDIDO (RSI <= 30)", "ABAIXO DA BANDA INFERIOR"]
            ttkb.Label(self.specific_frame, text="Condição de Status:").grid(row=0, column=0, sticky="w", pady=5)
            self.status_value_var = ttkb.StringVar(value=alert_data.get('value', status_options[0]) if alert_data else status_options[0])
            self.status_value_combo = ttkb.Combobox(self.specific_frame, textvariable=self.status_value_var, values=status_options, state="readonly")
            self.status_value_combo.grid(row=0, column=1, sticky="ew", pady=5)
        self.specific_frame.columnconfigure(1, weight=1)

    def browse_sound_file(self):
        app_path = get_application_path(); initial_dir = os.path.join(app_path, 'sons')
        if not os.path.isdir(initial_dir): initial_dir = app_path
        filepath = filedialog.askopenfilename(title="Selecione um arquivo .wav", initialdir=initial_dir, filetypes=[("Arquivos de Som", "*.wav")])
        if filepath: self.sound_var.set(os.path.relpath(filepath, app_path).replace("\\", "/"))

    def preview_sound(self):
        sound_path_str = self.sound_var.get()
        if not sound_path_str: messagebox.showwarning("Aviso", "Nenhum arquivo de som selecionado.", parent=self); return
        sound_path = sound_path_str if os.path.isabs(sound_path_str) else os.path.join(get_application_path(), sound_path_str)
        if os.path.exists(sound_path):
            try:
                winsound.PlaySound(sound_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            except Exception as e:
                messagebox.showerror("Erro", f"Não foi possível tocar o som:\n{e}", parent=self)
        else:
            messagebox.showerror("Erro", "Arquivo de som não encontrado.", parent=self)

    def on_save(self):
        symbol = self.symbol_var.get().upper().strip()
        if not symbol: messagebox.showerror("Erro", "O 'Símbolo' é obrigatório.", parent=self); return
        self.result = {"symbol": symbol, "notes": self.notes_var.get(), "sound": self.sound_var.get()}
        if self.alert_category_var.get() == 'Alerta de Preço':
            price = self.price_var.get()
            if price <= 0: messagebox.showerror("Erro", "O 'Preço Alvo' deve ser > 0.", parent=self); return
            self.result.update({"type": self.price_type_var.get(), "price": price})
        else:
            self.result.update({"type": "status", "value": self.status_value_var.get()})
        self.destroy()

class AlertManagerWindow(ttkb.Toplevel):
    def __init__(self, parent_app):
        super().__init__(parent_app.root)
        self.parent_app = parent_app
        self.title("Gerenciador de Alertas")
        self.geometry("1100x600") # Aprox. 29cm de largura
        self.transient(parent_app.root)
        self.grab_set()
        self.center_window(parent_app.root)

        config_table_frame = ttkb.Frame(self); config_table_frame.pack(expand=True, fill='both', padx=10, pady=10)
        config_controls_frame = ttkb.Frame(self); config_controls_frame.pack(fill='x', padx=10, pady=10)
        
        self.config_tree = ttkb.Treeview(config_table_frame, columns=('symbol', 'type', 'condition', 'notes'), show='headings', bootstyle="dark")
        self.config_tree.heading('symbol', text='Símbolo'); self.config_tree.column('symbol', width=150, anchor=tk.W)
        self.config_tree.heading('type', text='Tipo de Alerta'); self.config_tree.column('type', width=150, anchor=tk.CENTER)
        self.config_tree.heading('condition', text='Condição'); self.config_tree.column('condition', width=250, anchor=tk.W)
        self.config_tree.heading('notes', text='Observações'); self.config_tree.column('notes', width=300, anchor=tk.W)
        self.config_tree.pack(expand=True, fill='both')
        self.config_tree.bind("<Double-1>", self.open_edit_alert_dialog)

        ttkb.Button(config_controls_frame, text="Adicionar Alerta", command=self.open_add_alert_dialog, bootstyle="success").pack(side='left', padx=5)
        ttkb.Button(config_controls_frame, text="Editar Selecionado", command=self.open_edit_alert_dialog, bootstyle="info").pack(side='left', padx=5)
        ttkb.Button(config_controls_frame, text="Remover Selecionado", command=self.remove_selected_alert, bootstyle="danger").pack(side='left', padx=5)
        
        self._populate_tree()

    def center_window(self, parent_window):
        self.update_idletasks()
        parent_geo = parent_window.geometry().split('+')
        parent_x, parent_y = int(parent_geo[1]), int(parent_geo[2])
        parent_width, parent_height = parent_window.winfo_width(), parent_window.winfo_height()
        width, height = self.winfo_width(), self.winfo_height()
        x = parent_x + (parent_width // 2) - (width // 2)
        y = parent_y + (parent_height // 2) - (height // 2)
        self.geometry(f'+{x}+{y}')

    def _populate_tree(self):
        for i in self.config_tree.get_children(): self.config_tree.delete(i)
        self.alert_map = {}
        alert_id_counter = 0
        for crypto in self.parent_app.config.get("cryptos_to_monitor", []):
            for alert in crypto.get("alerts", []):
                alert_type_str = "Preço" if alert['type'] in ['high', 'low'] else "Análise Técnica"
                condition = f"{'Maior que' if alert['type'] == 'high' else 'Menor que'} ${alert['price']:,.2f}" if alert_type_str == "Preço" else alert.get('value', '')
                iid = str(alert_id_counter)
                self.config_tree.insert('', tk.END, iid=iid, values=(crypto['symbol'], alert_type_str, condition, alert.get('notes', '')))
                self.alert_map[iid] = (crypto, alert)
                alert_id_counter += 1

    def open_add_alert_dialog(self):
        dialog = AlertConfigDialog(self, self.parent_app.all_binance_symbols)
        self.wait_window(dialog)
        if dialog.result:
            new_alert = dict(dialog.result); symbol_to_add = new_alert.pop('symbol'); symbol_found = False
            for crypto in self.parent_app.config.get("cryptos_to_monitor", []):
                if crypto['symbol'] == symbol_to_add: crypto['alerts'].append(new_alert); symbol_found = True; break
            if not symbol_found: self.parent_app.config.get("cryptos_to_monitor", []).append({"symbol": symbol_to_add, "alerts": [new_alert]})
            if self.parent_app._save_config(): messagebox.showinfo("Sucesso", "Alerta adicionado!", parent=self); self.parent_app.load_config_and_populate(); self._populate_tree()

    def open_edit_alert_dialog(self, event=None):
        selected_item_id = self.config_tree.focus()
        if not selected_item_id: messagebox.showwarning("Nenhuma Seleção", "Selecione um alerta para editar.", parent=self); return
        
        crypto_container, alert_to_edit = self.alert_map.get(selected_item_id)
        if not alert_to_edit: return

        dialog = AlertConfigDialog(self, self.parent_app.all_binance_symbols, alert_data={**alert_to_edit, 'symbol': crypto_container['symbol']}); self.wait_window(dialog)
        if dialog.result:
            crypto_container['alerts'].remove(alert_to_edit)
            if not crypto_container['alerts']: self.parent_app.config['cryptos_to_monitor'].remove(crypto_container)
            
            edited_alert = dict(dialog.result); edited_symbol = edited_alert.pop('symbol')
            symbol_found = False
            for c in self.parent_app.config.get("cryptos_to_monitor", []):
                if c['symbol'] == edited_symbol: c['alerts'].append(edited_alert); symbol_found = True; break
            if not symbol_found: self.parent_app.config.get("cryptos_to_monitor", []).append({"symbol": edited_symbol, "alerts": [edited_alert]})
            
            if self.parent_app._save_config(): messagebox.showinfo("Sucesso", "Alerta editado!", parent=self); self.parent_app.load_config_and_populate(); self._populate_tree()

    def remove_selected_alert(self):
        selected_item_id = self.config_tree.focus()
        if not selected_item_id: messagebox.showwarning("Nenhuma Seleção", "Selecione um alerta para remover.", parent=self); return
        if not messagebox.askyesno("Confirmar Remoção", "Tem certeza?", parent=self): return
        
        crypto_container, alert_to_remove = self.alert_map.get(selected_item_id)
        if alert_to_remove:
            crypto_container['alerts'].remove(alert_to_remove)
            if not crypto_container['alerts']: self.parent_app.config['cryptos_to_monitor'].remove(crypto_container)
            if self.parent_app._save_config(): messagebox.showinfo("Sucesso", "Alerta removido!", parent=self); self.parent_app.load_config_and_populate(); self._populate_tree()

class CryptoMonitorApp:
    def __init__(self, root):
        self.root = root; self.root.title("Monitor de Criptomoedas Avançado")
        self.set_initial_geometry()
        
        self.config = {}; self.check_interval_ms = 60000; self.alert_details = {}
        self.current_prices = {}; self.ticker_24h_data = {}; self.sound_threads = {}
        self.config_path = os.path.join(get_application_path(), "config.json")
        self.history_path = os.path.join(get_application_path(), "alert_history.json")
        self.update_job = None; self.interval_map = {"1 Minuto": 60, "5 Minutos": 300, "15 Minutos": 900, "30 Minutos": 1800, "1 Hora": 3600}
        self.tray_icon = None
        self.all_binance_symbols = []

        self._setup_styles(); self._create_widgets()
        self.load_config_and_populate(); self.load_alert_history()
        self.root.protocol("WM_DELETE_WINDOW", self.minimize_to_tray)
        threading.Thread(target=self._fetch_binance_symbols, daemon=True).start()
        self.root.after(500, self.force_update)

    def _fetch_binance_symbols(self):
        try:
            url = "https://api.binance.com/api/v3/exchangeInfo"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            symbols = sorted([s['symbol'] for s in data['symbols'] if s['symbol'].endswith('USDT')])
            self.all_binance_symbols = symbols
            print(f"{len(symbols)} símbolos USDT carregados com sucesso.")
        except Exception as e:
            print(f"--> Erro ao buscar símbolos da Binance: {e}")
            messagebox.showerror("Erro de API", "Não foi possível carregar a lista de moedas da Binance. Verifique sua conexão.")

    def set_initial_geometry(self):
        width = int(29 * 37.8) 
        height = 750
        screen_width = self.root.winfo_screenwidth(); screen_height = self.root.winfo_screenheight()
        x = (screen_width / 2) - (width / 2); y = (screen_height / 2) - (height / 2)
        self.root.geometry(f'{width}x{height}+{int(x)}+{int(y)}')

    def _setup_styles(self):
        style = ttkb.Style(); style.configure("Treeview", font=(None, 10), rowheight=28); style.configure("Treeview.Heading", font=(None, 11, 'bold'))
    
    def _create_widgets(self):
        self.notebook = ttkb.Notebook(self.root); self.notebook.pack(expand=True, fill='both', padx=10, pady=10)
        self.monitor_frame = ttkb.Frame(self.notebook); self.history_frame = ttkb.Frame(self.notebook); self.legend_frame = ttkb.Frame(self.notebook)
        self.notebook.add(self.monitor_frame, text='Monitor'); self.notebook.add(self.history_frame, text='Histórico de Alertas'); self.notebook.add(self.legend_frame, text='Legenda')
        self.create_monitor_widgets(); self.create_history_widgets(); self.create_legend_widgets()

    def create_monitor_widgets(self):
        table_frame = ttkb.Frame(self.monitor_frame); table_frame.pack(expand=True, fill='both', padx=5, pady=5)
        controls_frame = ttkb.Frame(self.monitor_frame); controls_frame.pack(fill='x', padx=5, pady=5)
        columns = ('symbol', 'current_price', 'price_change_24h', 'status', 'notes_monitor')
        self.tree = ttkb.Treeview(table_frame, columns=columns, show='headings', bootstyle="dark")
        self.tree.heading('symbol', text='Símbolo'); self.tree.column('symbol', width=100, anchor=tk.W)
        self.tree.heading('current_price', text='Preço Atual'); self.tree.column('current_price', width=120, anchor=tk.E)
        self.tree.heading('price_change_24h', text='Variação 24h'); self.tree.column('price_change_24h', width=120, anchor=tk.CENTER)
        self.tree.heading('status', text='Status da Análise'); self.tree.column('status', width=250, anchor=tk.W)
        self.tree.heading('notes_monitor', text='Alertas Ativos'); self.tree.column('notes_monitor', width=550, anchor=tk.W)
        self.tree.pack(expand=True, fill='both')
        self._setup_monitor_tags()
        ttkb.Button(controls_frame, text="Gerenciar Alertas", command=self.open_alert_manager, bootstyle="primary").pack(side='left', padx=5)
        ttkb.Button(controls_frame, text="Sincronizar Agora", command=self.force_update, bootstyle="info").pack(side='left', padx=5)
        ttkb.Label(controls_frame, text="Intervalo:").pack(side='left', padx=(20, 5))
        self.interval_combo = ttkb.Combobox(controls_frame, values=list(self.interval_map.keys()), width=15, state="readonly")
        self.interval_combo.pack(side='left'); self.interval_combo.bind("<<ComboboxSelected>>", self.on_interval_change)

    def open_alert_manager(self):
        AlertManagerWindow(self)
    
    def on_closing(self):
        if messagebox.askokcancel("Sair", "Tem certeza que deseja fechar o monitor?", parent=self.root):
            self._quit_application()
    def _create_tray_icon(self):
        icon_path = os.path.join(get_application_path(), 'icone.ico')
        try: image = Image.open(icon_path)
        except FileNotFoundError: image = Image.new('RGB', (64, 64), 'black')
        menu = (item('Mostrar', self.show_window), item('Sair', self._quit_application))
        self.tray_icon = pystray.Icon("MonitorCripto", image, "Monitor de Criptomoedas", menu)
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
        for key, thread_info in list(self.sound_threads.items()):
            if thread_info['thread'].is_alive(): thread_info['stop_event'].set()
        self.root.destroy()
    def _setup_monitor_tags(self):
        self.tree.tag_configure('price_up', foreground='#45d862'); self.tree.tag_configure('price_down', foreground='#ff4d4d')
        self.tree.tag_configure('status_buy', foreground='#45d862'); self.tree.tag_configure('status_sell', foreground='#ff4d4d')
        self.tree.tag_configure('status_neutral', foreground='white')
    def _trigger_sound(self, sound_path_str, stop_event):
        if not sound_path_str: return
        sound_path = sound_path_str if os.path.isabs(sound_path_str) else os.path.join(get_application_path(), sound_path_str)
        key = (sound_path, id(stop_event)); 
        if self.sound_threads.get(key) and self.sound_threads[key]['thread'].is_alive(): return
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
        symbol = alert_data.get('symbol'); alert_type_raw = alert_data.get("type", "N/A")
        notes = alert_data.get("notes", "Sem observações."); current_price = self.current_prices.get(symbol, 0)
        alert_title = f"ALERTA: {symbol}"
        if alert_type_raw in ['high', 'low']:
            alert_price = alert_data.get("price", 0)
            alert_message = (f"{symbol} atingiu seu alvo de {alert_type_raw.upper()} em ${alert_price:,.2f}!\nPreço Atual: ${current_price:,.2f}\n\nObs: {notes}")
            telegram_message = (f"🔔 *ALERTA DE PREÇO: {symbol}*\n\nAtingiu *{alert_type_raw.upper()}* em *${alert_price:,.2f}*.\nPreço: `${current_price:,.2f}`\nObs: _{notes}_")
            history_trigger = f"{alert_type_raw.upper()} @ ${alert_price:,.2f}"
        else:
            status_value = alert_data.get("value", "N/A")
            alert_message = (f"Sinal de Análise Técnica para {symbol}!\n\nStatus: {status_value}\nPreço Atual: ${current_price:,.2f}\n\nObs: {notes}")
            telegram_message = (f"📈 *SINAL TÉCNICO: {symbol}*\n\nStatus: *{status_value}*\nPreço: `${current_price:,.2f}`\nObs: _{notes}_")
            history_trigger = f"Status: {status_value}"
        stop_event = threading.Event(); alert_data['stop_event'] = stop_event
        threading.Thread(target=show_windows_ok_popup, args=(alert_title, alert_message, stop_event), daemon=True).start()
        send_telegram_alert(self.config.get('telegram_bot_token'), self.config.get('telegram_chat_id'), telegram_message)
        if alert_data.get("sound"): self._trigger_sound(alert_data.get("sound"), stop_event)
        self.add_to_history(symbol, history_trigger, notes)
    def _save_config(self):
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f: json.dump(self.config, f, indent=2, ensure_ascii=False); return True
        except Exception as e: messagebox.showerror("Erro", f"Não foi possível salvar 'config.json':\n{e}"); return False
    def update_prices(self):
        all_symbols = {c['symbol'] for c in self.config.get("cryptos_to_monitor", [])}
        if not all_symbols:
            if self.root.winfo_exists(): self.update_job = self.root.after(self.check_interval_ms, self.update_prices); return
        self.ticker_24h_data = self.get_24hr_ticker_data(list(all_symbols))
        for symbol in all_symbols:
            if not self.tree.exists(symbol): continue
            data = self.ticker_24h_data.get(symbol)
            if not data: continue
            
            price_usd = float(data.get('lastPrice', 0)); price_change_percent = float(data.get('priceChangePercent', 0)); self.current_prices[symbol] = price_usd
            klines = self.get_kline_data(symbol, interval='1h', limit=100)
            if klines:
                df = pd.DataFrame(klines, columns=['timestamp','open','high','low','close','volume','close_time','quote_asset_volume','number_of_trades','taker_buy_base_asset_volume','taker_buy_quote_asset_volume','ignore'])
                df['close'] = pd.to_numeric(df['close']); rsi = calculate_rsi(df); upper_band, lower_band = calculate_bollinger_bands(df)
            else: rsi, upper_band, lower_band = 0, 0, 0
            
            status_text, status_tag = "Em observação", 'status_neutral'
            if rsi >= 70: status_text, status_tag = "SOBRECOMPRADO (RSI >= 70)", 'status_sell'
            elif price_usd > upper_band and upper_band > 0: status_text, status_tag = "ACIMA DA BANDA SUPERIOR", 'status_sell'
            elif rsi <= 30 and rsi > 0: status_text, status_tag = "SOBREVENDIDO (RSI <= 30)", 'status_buy'
            elif price_usd < lower_band and lower_band > 0: status_text, status_tag = "ABAIXO DA BANDA INFERIOR", 'status_buy'
            
            tags = ['price_up' if price_change_percent >= 0 else 'price_down', status_tag]; self.tree.item(symbol, tags=tags)
            self.tree.set(symbol, 'current_price', f"${price_usd:,.2f}"); self.tree.set(symbol, 'price_change_24h', f"{price_change_percent:+.2f}%")
            self.tree.set(symbol, 'status', status_text)

            for crypto in self.config.get("cryptos_to_monitor", []):
                if crypto['symbol'] == symbol:
                    for alert in crypto.get("alerts", []):
                        alert_type = alert.get('type'); is_triggered = False
                        if alert_type in ['high', 'low']: is_triggered = (alert_type == 'high' and price_usd >= alert.get('price', 0)) or (alert_type == 'low' and price_usd <= alert.get('price', 0))
                        elif alert_type == 'status': is_triggered = (status_text == alert.get('value'))
                        if is_triggered and not alert.get("triggered_now", False): alert["triggered_now"] = True; self.trigger_alert({**alert, 'symbol': symbol})
                        elif not is_triggered: alert["triggered_now"] = False
        if self.root.winfo_exists(): self.update_job = self.root.after(self.check_interval_ms, self.update_prices)
    def load_config_and_populate(self):
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f: self.config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.config = {"telegram_bot_token": "SEU_TOKEN_AQUI", "telegram_chat_id": "SEU_CHAT_ID_AQUI", "check_interval_seconds": 60, "cryptos_to_monitor": []}
            self._save_config()
        self.check_interval_ms = self.config.get("check_interval_seconds", 60) * 1000
        current_interval_sec = self.config.get("check_interval_seconds", 60)
        for text, seconds in self.interval_map.items():
            if seconds == current_interval_sec: self.interval_combo.set(text); break
        else: self.interval_combo.set("5 Minutos")
        for i in self.tree.get_children(): self.tree.delete(i)
        all_symbols = {c['symbol'] for c in self.config.get("cryptos_to_monitor", [])}
        for symbol in all_symbols:
            alerts_for_symbol = [f"Preço {a['type']} @ ${a['price']:,.2f}" if a['type'] in ['high', 'low'] else f"Status: {a['value']}" for c in self.config.get("cryptos_to_monitor", []) if c['symbol'] == symbol for a in c.get("alerts", [])]
            self.tree.insert('', tk.END, iid=symbol, values=(symbol, "Carregando...", " ", " ", " | ".join(alerts_for_symbol)))
        for crypto in self.config.get("cryptos_to_monitor", []):
            for alert in crypto.get("alerts", []): alert['triggered_now'] = False
    def create_history_widgets(self):
        history_table_frame = ttkb.Frame(self.history_frame); history_table_frame.pack(expand=True, fill='both', padx=5, pady=5)
        history_controls_frame = ttkb.Frame(self.history_frame); history_controls_frame.pack(fill='x', padx=5, pady=5)
        history_columns = ('timestamp', 'symbol', 'trigger', 'notes'); self.history_tree = ttkb.Treeview(history_table_frame, columns=history_columns, show='headings', bootstyle="dark")
        self.history_tree.heading('timestamp', text='Data e Hora'); self.history_tree.column('timestamp', width=150, anchor=tk.W)
        self.history_tree.heading('symbol', text='Símbolo'); self.history_tree.column('symbol', width=120, anchor=tk.CENTER)
        self.history_tree.heading('trigger', text='Alerta Disparado'); self.history_tree.column('trigger', width=250, anchor=tk.W)
        self.history_tree.heading('notes', text='Observações'); self.history_tree.column('notes', width=400, anchor=tk.W)
        self.history_tree.pack(expand=True, fill='both')
        ttkb.Button(history_controls_frame, text="Limpar Histórico de Alertas", command=self.clear_alert_history, bootstyle="danger").pack(side='left', padx=5)
    def create_legend_widgets(self):
        canvas = tk.Canvas(self.legend_frame, borderwidth=0, background="#2b3e50"); frame = ttkb.Frame(canvas, padding=(30, 20)); scrollbar = ttkb.Scrollbar(self.legend_frame, orient="vertical", command=canvas.yview, bootstyle="round-dark")
        canvas.configure(yscrollcommand=scrollbar.set); scrollbar.pack(side="right", fill="y"); canvas.pack(side="left", fill="both", expand=True)
        canvas_frame = canvas.create_window((4,4), window=frame, anchor="nw")
        def on_frame_configure(event): canvas.configure(scrollregion=canvas.bbox("all"))
        def on_canvas_configure(event): canvas.itemconfig(canvas_frame, width=event.width)
        frame.bind("<Configure>", on_frame_configure); canvas.bind("<Configure>", on_canvas_configure)
        def create_entry(parent, title, title_color, description):
            entry_frame = ttkb.Frame(parent, padding=(0, 10)); entry_frame.pack(fill='x', expand=True, anchor='w')
            title_label = ttkb.Label(entry_frame, text=title, font=("Helvetica", 12, "bold"), foreground=title_color); title_label.pack(anchor='w')
            desc_label = ttkb.Label(entry_frame, text=description, wraplength=800, justify='left', font=("Helvetica", 10)); desc_label.pack(anchor='w', pady=(5, 0))
        header = ttkb.Label(frame, text="Legenda dos Sinais de Análise Técnica", font=("Helvetica", 16, "bold")); header.pack(anchor='w', pady=(0, 20))
        sell_signals_frame = ttkb.LabelFrame(frame, text=" Sinais de Venda / Cautela (Cor Vermelha) ", bootstyle="danger", padding=15); sell_signals_frame.pack(fill='x', expand=True, pady=10, anchor='w')
        create_entry(sell_signals_frame, "SOBRECOMPRADO (RSI >= 70)", "#ff4d4d", "O RSI indica que o ativo foi comprado excessivamente e pode estar 'caro'.\nIsso aumenta a probabilidade de uma correção de preço (queda) em breve.")
        create_entry(sell_signals_frame, "ACIMA DA BANDA SUPERIOR", "#ff4d4d", "O preço 'estourou' para fora da sua faixa de volatilidade normal (Bandas de Bollinger).\nEste é um sinal de que o movimento de alta está superesticado e pode reverter a qualquer momento.")
        buy_signals_frame = ttkb.LabelFrame(frame, text=" Sinais de Compra / Oportunidade (Cor Verde) ", bootstyle="success", padding=15); buy_signals_frame.pack(fill='x', expand=True, pady=10, anchor='w')
        create_entry(buy_signals_frame, "SOBREVENDIDO (RSI <= 30)", "#45d862","O RSI indica que o ativo foi vendido excessivamente e pode estar 'barato'.\nIsso aumenta a probabilidade de uma recuperação de preço (alta) em breve.")
        create_entry(buy_signals_frame, "ABAIXO DA BANDA INFERIOR", "#45d862","O preço caiu para fora da sua faixa de volatilidade normal (Bandas de Bollinger).\nEste é um sinal de que o movimento de queda pode estar se esgotando, representando uma potencial oportunidade de compra.")
        other_signals_frame = ttkb.LabelFrame(frame, text=" Outros Indicadores ", bootstyle="info", padding=15); other_signals_frame.pack(fill='x', expand=True, pady=10, anchor='w')
        create_entry(other_signals_frame, "Variação 24h (%)", "white","Mostra a performance do ativo nas últimas 24 horas. O texto fica verde para alta e vermelho para baixa.")
        create_entry(other_signals_frame, "RSI (14p)", "white","O Índice de Força Relativa mede a velocidade e a mudança dos movimentos de preços. É um indicador de 'momentum' que varia de 0 a 100.")
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
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S"); new_record = {'timestamp': timestamp, 'symbol': symbol, 'trigger': trigger, 'notes': notes}
        history.append(new_record)
        with open(self.history_path, 'w', encoding='utf-8') as f: json.dump(history, f, indent=2)
        self.history_tree.insert('', 0, values=(timestamp, symbol, trigger, notes))
    def clear_alert_history(self):
        if not messagebox.askyesno("Confirmar", "Tem certeza que deseja apagar permanentemente todo o histórico de alertas?", parent=self.root): return
        try:
            with open(self.history_path, 'w', encoding='utf-8') as f: json.dump([], f)
            for i in self.history_tree.get_children(): self.history_tree.delete(i)
            messagebox.showinfo("Sucesso", "O histórico de alertas foi limpo.", parent=self.root)
        except Exception as e: messagebox.showerror("Erro", f"Não foi possível limpar o histórico:\n{e}", parent=self.root)
    def on_interval_change(self, event=None):
        selected_text = self.interval_combo.get(); new_interval_sec = self.interval_map.get(selected_text)
        if new_interval_sec:
            self.config['check_interval_seconds'] = new_interval_sec
            if self._save_config(): self.check_interval_ms = new_interval_sec * 1000; print(f"Intervalo de atualização alterado para {selected_text} e salvo.")
    def force_update(self):
        print("Sincronização manual solicitada..."); 
        if self.update_job: self.root.after_cancel(self.update_job)
        self.update_prices()
    def get_24hr_ticker_data(self, symbols):
        if not symbols: return {}
        binance_api_url = "https://api.binance.com/api/v3/ticker/24hr"
        params = {'symbols': json.dumps(list(symbols), separators=(',', ':'))}
        try:
            response = requests.get(binance_api_url, params=params, timeout=10); response.raise_for_status()
            return {item['symbol']: item for item in response.json()}
        except Exception as e: print(f"--> Erro ao buscar dados do ticker 24h: {e}"); return {}
    def get_kline_data(self, symbol, interval='1h', limit=100):
        binance_api_url = "https://api.binance.com/api/v3/klines"
        params = {'symbol': symbol, 'interval': interval, 'limit': limit}
        try:
            response = requests.get(binance_api_url, params=params, timeout=10); response.raise_for_status()
            return response.json()
        except Exception as e: print(f"--> Erro ao buscar dados de kline para '{symbol}': {e}"); return None
    def calculate_sma(self, klines, period=20):
        if not klines or len(klines) < period: return None
        closes = [float(k[4]) for k in klines]; df = pd.DataFrame(closes, columns=['close'])
        sma = df['close'].rolling(window=period).mean().iloc[-1]
        return sma

if __name__ == "__main__":
    try:
        import pandas as pd
        from pystray import MenuItem as item
        import pystray
        from PIL import Image, ImageTk
    except ImportError as e:
        messagebox.showerror("Biblioteca Faltando", f"Uma biblioteca necessária não foi encontrada: {e.name}. Por favor, instale-a com 'pip install {e.name}'")
        sys.exit()
    root = ttkb.Window(themename="superhero")
    app = CryptoMonitorApp(root)
    root.mainloop()
