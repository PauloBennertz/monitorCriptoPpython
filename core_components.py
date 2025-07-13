import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import sys
import winsound
import ttkbootstrap as ttkb
import pandas as pd

# --- Funções Auxiliares de UI e Sistema ---

def get_application_path():
    """Retorna o caminho do diretório da aplicação, seja executável ou script."""
    if getattr(sys, 'frozen', False):
        application_path = os.path.dirname(sys.executable)
    else:
        application_path = os.path.dirname(os.path.abspath(__file__))
    return application_path

class Tooltip:
    """Cria um balão de ajuda (tooltip) para um widget."""
    def __init__(self, widget):
        self.widget = widget
        self.tooltip_window = None

    def show_tooltip(self, text, x, y):
        self.hide_tooltip()
        if not text:
            return
            
        self.tooltip_window = tk.Toplevel(self.widget)
        self.tooltip_window.wm_overrideredirect(True)
        self.tooltip_window.wm_geometry(f"+{x+20}+{y+10}")

        label = ttkb.Label(self.tooltip_window, text=text, justify='left',
                           background="#1c1c1c", foreground="white", relief='solid',
                           borderwidth=1, font=("Helvetica", 10, "normal"), padding=8,
                           wraplength=400)
        label.pack(ipadx=1)

    def hide_tooltip(self):
        if self.tooltip_window:
            self.tooltip_window.destroy()
        self.tooltip_window = None

# --- Funções de Análise Técnica ---

def calculate_rsi(df, period=14):
    if df.empty or len(df) < period + 1: return 0
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    if loss.iloc[-1] == 0: return 100
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]

def calculate_bollinger_bands(df, period=20, std_dev=2):
    if df.empty or len(df) < period: return 0, 0
    sma = df['close'].rolling(window=period).mean().iloc[-1]
    std = df['close'].rolling(window=period).std().iloc[-1]
    if pd.isna(sma) or pd.isna(std): return 0, 0
    upper_band = sma + (std * std_dev)
    lower_band = sma - (std * std_dev)
    return upper_band, lower_band

def calculate_macd(df, fast=12, slow=26, signal=9):
    if len(df) < slow: return "N/A"
    exp1 = df['close'].ewm(span=fast, adjust=False).mean()
    exp2 = df['close'].ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    if macd.iloc[-2] < signal_line.iloc[-2] and macd.iloc[-1] > signal_line.iloc[-1]:
        return "Cruzamento de Alta"
    elif macd.iloc[-2] > signal_line.iloc[-2] and macd.iloc[-1] < signal_line.iloc[-1]:
        return "Cruzamento de Baixa"
    return "Nenhum"

def calculate_emas(df, periods=[50, 200]):
    if df.empty: return {}
    emas = {}
    for period in periods:
        if len(df) >= period:
            emas[period] = df['close'].ewm(span=period, adjust=False).mean()
    return emas

# --- Janela de Configuração de Alertas ---

class AlertConfigDialog(ttkb.Toplevel):
    def __init__(self, parent_app, all_symbols, alert_data=None):
        super().__init__(parent_app.root)
        self.parent_app = parent_app; self.result = None; self.title("Configurar Alerta")
        self.geometry("800x450"); self.transient(self.master); self.grab_set()
        
        self.all_symbols = all_symbols
        main_frame = ttkb.Frame(self, padding="10"); main_frame.pack(expand=True, fill="both")
        common_frame = ttkb.Frame(main_frame); common_frame.pack(fill='x', pady=(0, 10))
        self.specific_frame = ttkb.Frame(main_frame); self.specific_frame.pack(fill='x', pady=5)
        
        ttkb.Label(common_frame, text="Símbolo:").grid(row=0, column=0, sticky="w", pady=5)
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
        self.parent_app.center_toplevel_on_main(self)

    def update_symbol_list(self, event=None):
        search_term = self.symbol_var.get().upper()
        self.symbol_listbox.delete(0, tk.END)
        if search_term:
            matches = [s for s in self.all_symbols if search_term in s.upper()][:100]
            if matches:
                for match in matches: self.symbol_listbox.insert(tk.END, match)
                self.symbol_listbox.pack(fill="x", expand=True, before=self.symbol_entry.master.pack_slaves()[-1])
            else: self.hide_symbol_list()
        else: self.hide_symbol_list()

    def on_symbol_select(self, event=None):
        if self.symbol_listbox.curselection():
            selected_symbol = self.symbol_listbox.get(self.symbol_listbox.curselection())
            self.symbol_var.set(selected_symbol)
            self.hide_symbol_list()

    def hide_symbol_list(self, event=None): self.symbol_listbox.pack_forget()

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
            status_options = [
                "SOBRECOMPRADO (RSI >= 70)", "ACIMA DA BANDA SUPERIOR", "SOBREVENDIDO (RSI <= 30)", "ABAIXO DA BANDA INFERIOR",
                "MACD: Cruzamento de Alta", "MACD: Cruzamento de Baixa", "MME: Cruz Dourada (50/200)", "MME: Cruz da Morte (50/200)"]
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
            try: winsound.PlaySound(sound_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            except Exception as e: messagebox.showerror("Erro", f"Não foi possível tocar o som:\n{e}", parent=self)
        else: messagebox.showerror("Erro", "Arquivo de som não encontrado.", parent=self)
    
    def on_save(self):
        symbol = self.symbol_var.get().strip()
        if not symbol: messagebox.showerror("Erro", "O 'Símbolo' é obrigatório.", parent=self); return
        self.result = {"symbol": symbol, "notes": self.notes_var.get(), "sound": self.sound_var.get()}
        if self.alert_category_var.get() == 'Alerta de Preço':
            price = self.price_var.get()
            if price <= 0: messagebox.showerror("Erro", "O 'Preço Alvo' deve ser > 0.", parent=self); return
            self.result.update({"type": self.price_type_var.get(), "price": price})
        else: self.result.update({"type": "status", "value": self.status_value_var.get()})
        self.destroy()

# --- Janela de Gerenciador de Alertas ---

class AlertManagerWindow(ttkb.Toplevel):
    def __init__(self, parent_app):
        super().__init__(parent_app.root)
        self.parent_app = parent_app
        self.title("Gerenciador de Alertas (Múltiplos por Moeda)")
        self.geometry("1200x600")
        self.transient(self.master)
        self.grab_set()

        self.paned_window = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.paned_window.pack(expand=True, fill='both', padx=10, pady=10)

        symbols_frame = ttkb.Frame(self.paned_window, padding=5)
        self.symbols_tree = ttkb.Treeview(symbols_frame, columns=('symbol',), show='headings', bootstyle="dark")
        self.symbols_tree.heading('symbol', text='Moedas Monitoradas')
        self.symbols_tree.pack(expand=True, fill='both')
        self.symbols_tree.bind("<<TreeviewSelect>>", self.on_symbol_selected)
        self.paned_window.add(symbols_frame, weight=1)

        alerts_frame = ttkb.Frame(self.paned_window, padding=5)
        alerts_table_frame = ttkb.Frame(alerts_frame)
        alerts_table_frame.pack(expand=True, fill='both', pady=(0, 10))
        alerts_controls_frame = ttkb.Frame(alerts_frame)
        alerts_controls_frame.pack(fill='x')
        self.paned_window.add(alerts_frame, weight=3)
        
        self.alerts_tree = ttkb.Treeview(alerts_table_frame, columns=('type', 'condition', 'notes'), show='headings', bootstyle="dark")
        self.alerts_tree.heading('type', text='Tipo de Alerta'); self.alerts_tree.column('type', width=150, anchor=tk.CENTER)
        self.alerts_tree.heading('condition', text='Condição'); self.alerts_tree.column('condition', width=250, anchor=tk.W)
        self.alerts_tree.heading('notes', text='Observações'); self.alerts_tree.column('notes', width=300, anchor=tk.W)
        self.alerts_tree.pack(expand=True, fill='both')
        self.alerts_tree.bind("<Double-1>", self.open_edit_alert_dialog)

        self.add_alert_btn = ttkb.Button(alerts_controls_frame, text="Adicionar Alerta", command=self.open_add_alert_dialog, bootstyle="success", state="disabled")
        self.add_alert_btn.pack(side='left', padx=5)
        self.edit_alert_btn = ttkb.Button(alerts_controls_frame, text="Editar Selecionado", command=self.open_edit_alert_dialog, bootstyle="info", state="disabled")
        self.edit_alert_btn.pack(side='left', padx=5)
        self.remove_alert_btn = ttkb.Button(alerts_controls_frame, text="Remover Selecionado", command=self.remove_selected_alert, bootstyle="danger", state="disabled")
        self.remove_alert_btn.pack(side='left', padx=5)
        
        ttkb.Button(symbols_frame, text="Adicionar/Remover Moedas", command=self.manage_monitored_symbols).pack(side='bottom', fill='x', pady=(10,0))
        
        self._populate_symbols_tree()
        self.parent_app.center_toplevel_on_main(self)
        
    def _populate_symbols_tree(self):
        for i in self.symbols_tree.get_children(): self.symbols_tree.delete(i)
        monitored_symbols = [crypto['symbol'] for crypto in self.parent_app.config.get("cryptos_to_monitor", [])]
        for symbol in sorted(monitored_symbols): self.symbols_tree.insert('', tk.END, iid=symbol, values=(symbol,))
        
    def on_symbol_selected(self, event=None):
        selected_items = self.symbols_tree.selection()
        if not selected_items:
            for i in self.alerts_tree.get_children(): self.alerts_tree.delete(i)
            self.add_alert_btn['state'] = 'disabled'; self.edit_alert_btn['state'] = 'disabled'; self.remove_alert_btn['state'] = 'disabled'
            return
        
        self.add_alert_btn['state'] = 'normal'
        self.edit_alert_btn['state'] = 'normal' 
        self.remove_alert_btn['state'] = 'normal'

        self._populate_alerts_tree(selected_items[0])
        
    def _populate_alerts_tree(self, symbol):
        for i in self.alerts_tree.get_children(): self.alerts_tree.delete(i)
        self.alert_map = {}; alert_id_counter = 0
        for crypto in self.parent_app.config.get("cryptos_to_monitor", []):
            if crypto['symbol'] == symbol:
                for alert in crypto.get("alerts", []):
                    alert_type_str = "Preço" if alert['type'] in ['high', 'low'] else "Análise Técnica"
                    condition = f"{'Maior que' if alert['type'] == 'high' else 'Menor que'} ${alert.get('price', 0):,.2f}" if alert_type_str == "Preço" else alert.get('value', '')
                    iid = str(alert_id_counter)
                    self.alerts_tree.insert('', tk.END, iid=iid, values=(alert_type_str, condition, alert.get('notes', '')))
                    self.alert_map[iid] = alert
                    alert_id_counter += 1
                break
                
    def get_selected_symbol(self):
        selected_items = self.symbols_tree.selection()
        return selected_items[0] if selected_items else None
        
    def open_add_alert_dialog(self):
        selected_symbol = self.get_selected_symbol()
        if not selected_symbol: return

        dialog_data = {'symbol': selected_symbol, 'sound': 'sons/Alerta.wav'}
        dialog = AlertConfigDialog(self.parent_app, self.parent_app.all_symbols_list, alert_data=dialog_data)
        dialog.symbol_entry.config(state='readonly')
        self.wait_window(dialog)
        
        if dialog.result:
            new_alert = dict(dialog.result)
            symbol = new_alert.pop('symbol')
            for crypto in self.parent_app.config.get("cryptos_to_monitor", []):
                if crypto['symbol'] == symbol:
                    crypto.setdefault('alerts', []).append(new_alert)
                    break
            if self.parent_app._save_config():
                messagebox.showinfo("Sucesso", "Alerta adicionado!", parent=self)
                # --- MUDANÇA: Linha removida daqui ---
                self._populate_alerts_tree(symbol)
                
    def open_edit_alert_dialog(self, event=None):
        selected_symbol = self.get_selected_symbol()
        selected_alert_id = self.alerts_tree.focus()
        if not selected_symbol or not selected_alert_id:
            messagebox.showwarning("Nenhuma Seleção", "Selecione uma moeda e um alerta para editar.", parent=self)
            return

        alert_to_edit = self.alert_map.get(selected_alert_id)
        if not alert_to_edit: return
        
        dialog = AlertConfigDialog(self.parent_app, self.parent_app.all_symbols_list, alert_data={**alert_to_edit, 'symbol': selected_symbol})
        dialog.symbol_entry.config(state='readonly')
        self.wait_window(dialog)
        
        if dialog.result:
            for crypto in self.parent_app.config.get("cryptos_to_monitor", []):
                if crypto['symbol'] == selected_symbol and alert_to_edit in crypto.get('alerts',[]):
                    # Limpa chaves antigas que podem não existir mais no novo tipo de alerta
                    alert_to_edit.clear()
                    alert_to_edit.update({k: v for k, v in dialog.result.items() if k != 'symbol'})
                    break
            
            if self.parent_app._save_config():
                messagebox.showinfo("Sucesso", "Alerta editado!", parent=self)
                # --- MUDANÇA: Linha removida daqui ---
                self._populate_alerts_tree(selected_symbol)
                
    def remove_selected_alert(self):
        selected_symbol = self.get_selected_symbol()
        selected_alert_id = self.alerts_tree.focus()
        if not selected_symbol or not selected_alert_id:
            messagebox.showwarning("Nenhuma Seleção", "Selecione uma moeda e um alerta para remover.", parent=self)
            return
        if not messagebox.askyesno("Confirmar Remoção", "Tem certeza?", parent=self): return
        
        alert_to_remove = self.alert_map.get(selected_alert_id)
        if not alert_to_remove: return

        for crypto in self.parent_app.config.get("cryptos_to_monitor", []):
            if crypto['symbol'] == selected_symbol and alert_to_remove in crypto.get('alerts',[]):
                crypto['alerts'].remove(alert_to_remove)
                break
        
        if self.parent_app._save_config():
            messagebox.showinfo("Sucesso", "Alerta removido!", parent=self)
            # --- MUDANÇA: Linha removida daqui ---
            self._populate_alerts_tree(selected_symbol)
            
    def manage_monitored_symbols(self):
        dialog = ManageSymbolsDialog(self)
        self.wait_window(dialog)

class ManageSymbolsDialog(ttkb.Toplevel):
    def __init__(self, parent_manager):
        super().__init__(parent_manager.parent_app.root)
        self.parent_app = parent_manager.parent_app
        self.parent_manager = parent_manager
        self.title("Gerenciar Moedas Monitoradas")
        self.geometry("800x600")
        self.transient(self.master)
        self.grab_set()

        main_frame = ttkb.Frame(self, padding=10)
        main_frame.pack(expand=True, fill='both')

        left_frame = ttkb.LabelFrame(main_frame, text="Moedas Disponíveis", padding=10)
        left_frame.pack(side='left', fill='both', expand=True, padx=(0, 5))
        self.available_search_var = ttkb.StringVar()
        self.available_search_var.trace_add("write", self._filter_available)
        self.available_entry = ttkb.Entry(left_frame, textvariable=self.available_search_var)
        self.available_entry.pack(fill='x', pady=(0, 5))
        self.available_listbox = tk.Listbox(left_frame, selectmode='extended', exportselection=False)
        self.available_listbox.pack(fill='both', expand=True)

        buttons_frame = ttkb.Frame(main_frame, padding=10)
        buttons_frame.pack(side='left', fill='y', anchor='center')
        ttkb.Button(buttons_frame, text="Adicionar >>", command=self._add_symbols, bootstyle="success-outline").pack(pady=5)
        ttkb.Button(buttons_frame, text="<< Remover", command=self._remove_symbols, bootstyle="danger-outline").pack(pady=5)

        right_frame = ttkb.LabelFrame(main_frame, text="Moedas Monitoradas", padding=10)
        right_frame.pack(side='left', fill='both', expand=True, padx=(5, 0))
        self.monitored_search_var = ttkb.StringVar()
        self.monitored_search_var.trace_add("write", self._filter_monitored)
        self.monitored_entry = ttkb.Entry(right_frame, textvariable=self.monitored_search_var)
        self.monitored_entry.pack(fill='x', pady=(0, 5))
        self.monitored_listbox = tk.Listbox(right_frame, selectmode='extended', exportselection=False)
        self.monitored_listbox.pack(fill='both', expand=True)
        
        bottom_frame = ttkb.Frame(self, padding=10)
        bottom_frame.pack(side='bottom', fill='x')
        ttkb.Button(bottom_frame, text="Salvar Alterações", command=self.on_save, bootstyle="success").pack(side='left')
        ttkb.Button(bottom_frame, text="Cancelar", command=self.destroy, bootstyle="secondary").pack(side='left', padx=10)
        
        self.setup_placeholder(self.available_entry, "Buscar disponíveis...")
        self.setup_placeholder(self.monitored_entry, "Buscar monitoradas...")
        self._populate_lists()
        self.parent_app.center_toplevel_on_main(self)

    def setup_placeholder(self, entry, placeholder):
        entry.placeholder = placeholder; entry.p_color = 'grey'; entry.default_fg_color = entry['foreground']
        entry.bind("<FocusIn>", self._on_focus_in); entry.bind("<FocusOut>", self._on_focus_out)
        self._on_focus_out(event=None, entry=entry)
        
    def _on_focus_in(self, event):
        if event.widget.get() == event.widget.placeholder:
            event.widget.delete(0, "end"); event.widget.config(foreground=event.widget.default_fg_color)
            
    def _on_focus_out(self, event, entry=None):
        widget = event.widget if event else entry
        if not widget.get():
            widget.insert(0, widget.placeholder); widget.config(foreground=widget.p_color)
            
    def _populate_lists(self):
        self.all_symbols_master = sorted(self.parent_app.all_symbols_list)
        monitored_symbols = {crypto['symbol'] for crypto in self.parent_app.config.get("cryptos_to_monitor", [])}
        self.available_listbox.delete(0, tk.END); self.monitored_listbox.delete(0, tk.END)
        for symbol in self.all_symbols_master:
            if symbol not in monitored_symbols: self.available_listbox.insert(tk.END, symbol)
        for symbol in sorted(list(monitored_symbols)): self.monitored_listbox.insert(tk.END, symbol)
        
    def _filter_available(self, *args):
        search_term = self.available_search_var.get().upper()
        self.available_listbox.delete(0, tk.END)
        monitored_symbols = set(self.monitored_listbox.get(0, tk.END))
        if search_term == "BUSCAR DISPONÍVEIS...":
            for symbol in self.all_symbols_master:
                if symbol not in monitored_symbols: self.available_listbox.insert(tk.END, symbol)
            return
        for symbol in self.all_symbols_master:
            if search_term in symbol.upper() and symbol not in monitored_symbols:
                self.available_listbox.insert(tk.END, symbol)
            
    def _filter_monitored(self, *args):
        search_term = self.monitored_search_var.get().upper()
        monitored_symbols = sorted([crypto['symbol'] for crypto in self.parent_app.config.get("cryptos_to_monitor", [])])
        self.monitored_listbox.delete(0, tk.END)
        if search_term == "BUSCAR MONITORADAS...":
             for symbol in monitored_symbols: self.monitored_listbox.insert(tk.END, symbol)
             return
        for symbol in monitored_symbols:
            if search_term in symbol.upper(): self.monitored_listbox.insert(tk.END, symbol)
            
    def _add_symbols(self):
        selected_indices = self.available_listbox.curselection();
        if not selected_indices: return
        symbols_to_move = [self.available_listbox.get(i) for i in selected_indices]
        for i in sorted(selected_indices, reverse=True): self.available_listbox.delete(i)
        current_monitored = self.monitored_listbox.get(0, tk.END)
        for symbol in symbols_to_move:
            if symbol not in current_monitored: self.monitored_listbox.insert(tk.END, symbol)
        
    def _remove_symbols(self):
        selected_indices = self.monitored_listbox.curselection()
        if not selected_indices: return
        symbols_to_move = [self.monitored_listbox.get(i) for i in selected_indices]
        for i in sorted(selected_indices, reverse=True): self.monitored_listbox.delete(i)
        current_available = self.available_listbox.get(0, tk.END)
        for symbol in symbols_to_move:
            if symbol not in current_available: self.available_listbox.insert(tk.END, symbol)
        all_available = sorted(self.available_listbox.get(0, tk.END))
        self.available_listbox.delete(0, tk.END)
        for symbol in all_available: self.available_listbox.insert(tk.END, symbol)
        
    def on_save(self):
        new_monitored_symbols = set(self.monitored_listbox.get(0, tk.END))
        new_config_list = []
        for crypto in self.parent_app.config["cryptos_to_monitor"]:
            if crypto['symbol'] in new_monitored_symbols: new_config_list.append(crypto)
        existing_symbols_in_new_list = {c['symbol'] for c in new_config_list}
        for symbol in new_monitored_symbols:
            if symbol not in existing_symbols_in_new_list:
                new_config_list.append({"symbol": symbol, "alerts": []})
        self.parent_app.config["cryptos_to_monitor"] = new_config_list
        if self.parent_app._save_config():
            messagebox.showinfo("Sucesso", "Lista de moedas atualizada.", parent=self)
            self.parent_app.load_config_and_populate()
            self.parent_manager._populate_symbols_tree()
            self.parent_manager.on_symbol_selected()
            self.destroy()