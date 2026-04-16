import socket
import json
import threading
import queue
import csv
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

class ClientApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Napro Telemetry (Modo Cliente)")
        self.root.geometry("1400x850")
        self.root.configure(bg="#2d3436")
        
        self.running = False
        self.client_socket = None
        self.data_queue = queue.Queue()
        self.session_start = None
        
        self.history = []
        self.intervals = []
        self.last_packet_time = None
        
        self.graphs = {
            'times': [], 'time_labels': [],
            'CO': [], 'CO2': [], 'O2': [], 
            'HC': [], 'NOx': [], 'RPM': []
        }

        self._build_ui()
        self.poll_queue()
        self.update_graphs_daemon()

    def _build_ui(self):
        # HEADER (DARK THEME)
        frame_top = tk.Frame(self.root, padx=15, pady=10, bg="#2d3436")
        frame_top.pack(fill="x")

        tk.Label(frame_top, text="IP do Backend:", bg="#2d3436", fg="white", font=("Arial", 10, "bold")).pack(side="left", padx=5)
        self.ent_ip = tk.Entry(frame_top, width=15, font=("Arial", 11))
        self.ent_ip.insert(0, "127.0.0.1")
        self.ent_ip.pack(side="left", padx=5)

        tk.Label(frame_top, text="Porta:", bg="#2d3436", fg="white", font=("Arial", 10, "bold")).pack(side="left", padx=5)
        self.ent_port = tk.Entry(frame_top, width=8, font=("Arial", 11))
        self.ent_port.insert(0, "9999")
        self.ent_port.pack(side="left", padx=5)

        self.btn_connect = tk.Button(frame_top, text="▶ CONECTAR AO HARDWARE", command=self.toggle_connection, bg="#0984e3", fg="white", font=("Arial", 10, "bold"), relief="flat", padx=10, pady=3)
        self.btn_connect.pack(side="left", padx=20)

        self.btn_export = tk.Button(frame_top, text="♻️ Novo Ciclo Global (Salvar/Limpar)", command=self.trigger_remote_reset, bg="#00b894", fg="white", font=("Arial", 9, "bold"), relief="flat")
        self.btn_export.pack(side="right", padx=10)

        self.lbl_state = tk.Label(frame_top, text="[ STATUS: OFFLINE ]", fg="#ff7675", bg="#2d3436", font=("Consolas", 12, "bold"))
        self.lbl_state.pack(side="right", padx=30)

        # PANED SPLIT
        self.paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg="#b2bec3", sashwidth=5)
        self.paned.pack(fill=tk.BOTH, expand=1, padx=5, pady=5)

        # LEFT STATS BOARD
        self.frame_stats = tk.Frame(self.paned, width=320, bg="#dfe6e9", padx=10, pady=10)
        self.paned.add(self.frame_stats, minsize=280)
        self._build_stats_panel()

        # RIGHT TABS
        self.notebook = ttk.Notebook(self.paned)
        self.paned.add(self.notebook, minsize=600)

        self.tab_dashboard = ttk.Frame(self.notebook)
        self.tab_table = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_dashboard, text=" 📉 Monitor de Telemetria Contínua ")
        self.notebook.add(self.tab_table, text=" 📋 Histórico Tabelado (Pacotes) ")

        self.build_graphs_tab()
        self.build_table_tab()

    def _build_stats_panel(self):
        lbl_head = tk.Label(self.frame_stats, text="DADOS EM TEMPO DE VOO", font=("Arial", 12, "bold"), bg="#dfe6e9", fg="#2d3436")
        lbl_head.pack(pady=(2, 5))
        
        self.val_vars = {}
        self.gas_stats = {}
        
        # Métrica, Cor, Padrão
        metrics = [
            ("CO (%)", "#d63031", "0.00"),
            ("CO2 (%)", "#00b894", "0.0"),
            ("HC (ppm)", "#e17055", "0"),
            ("O2 (%)", "#0984e3", "0.00"),
            ("NOx (ppm)", "#6c5ce7", "0"),
            ("RPM", "#2d3436", "0")
        ]

        for m_name, color, def_val in metrics:
            box = tk.Frame(self.frame_stats, bg="#ffffff", highlightbackground=color, highlightcolor=color, highlightthickness=3, bd=0)
            box.pack(fill="x", pady=2, ipady=1)
            
            key = m_name.split()[0]
            tk.Label(box, text=m_name, font=("Arial", 10, "bold"), bg="#ffffff", fg=color).pack(anchor="nw", padx=8, pady=(0, 0))
            
            tv = tk.StringVar(value=def_val)
            self.val_vars[key] = tv
            tk.Label(box, textvariable=tv, font=("Consolas", 20, "bold"), bg="#ffffff", fg="#2d3436").pack(anchor="e", padx=15)

            # Barra Específica de Estatisticas (Min, Méd, Max) dentro do próprio Box
            var_min = tk.StringVar(value="Min: --")
            var_avg = tk.StringVar(value="Méd: --")
            var_max = tk.StringVar(value="Max: --")
            self.gas_stats[key] = {"min_v": var_min, "avg_v": var_avg, "max_v": var_max, 
                                   "sum": 0.0, "count": 0, "c_min": 99999.0, "c_max": -99999.0}
            
            f_stats = tk.Frame(box, bg="#ffffff")
            f_stats.pack(fill="x", padx=8, pady=(0, 2))
            tk.Label(f_stats, textvariable=var_min, font=("Arial", 8, "bold"), bg="#ffffff", fg="#636e72").pack(side="left")
            tk.Label(f_stats, text="|", font=("Arial", 8), bg="#ffffff", fg="#b2bec3").pack(side="left", padx=2)
            tk.Label(f_stats, textvariable=var_avg, font=("Arial", 8, "bold"), bg="#ffffff", fg="#636e72").pack(side="left")
            tk.Label(f_stats, text="|", font=("Arial", 8), bg="#ffffff", fg="#b2bec3").pack(side="left", padx=2)
            tk.Label(f_stats, textvariable=var_max, font=("Arial", 8, "bold"), bg="#ffffff", fg="#636e72").pack(side="left")

        ttk.Separator(self.frame_stats, orient='horizontal').pack(fill='x', pady=5)

        tk.Label(self.frame_stats, text="⚙️ ESTATÍSTICAS GERAIS", font=("Arial", 10, "bold"), bg="#dfe6e9", fg="#2d3436").pack(pady=2)

        self.lbl_degradation = tk.Label(self.frame_stats, text="AGUARDANDO SINAL...", font=("Arial", 10, "bold"), bg="#b2bec3", fg="#ffffff", pady=4)
        self.lbl_degradation.pack(fill="x", pady=5)
        
        self.stat_vars = {
            "Tempo Trans. (s)": tk.StringVar(value="--"),
            "Médio (10 pcts)": tk.StringVar(value="--"),
            "Duração (s)": tk.StringVar(value="0"),
            "Pacotes Salvos": tk.StringVar(value="0")
        }
        
        for p, s_var in self.stat_vars.items():
            f = tk.Frame(self.frame_stats, bg="#dfe6e9")
            f.pack(fill="x", pady=0)
            tk.Label(f, text=f"{p}:", font=("Arial", 10), bg="#dfe6e9", fg="#636e72").pack(side="left")
            tk.Label(f, textvariable=s_var, font=("Consolas", 11, "bold"), bg="#dfe6e9", fg="#2d3436").pack(side="right")

    def build_graphs_tab(self):
        # Agora montaremos numa proporção 6 linhas e 1 coluna, empilhadas, unidas pelo Eixo X
        self.fig = Figure(figsize=(9, 11), dpi=100)
        self.fig.patch.set_facecolor('#ffffff')
        self.fig.subplots_adjust(hspace=0.08, left=0.07, right=0.98, top=0.97, bottom=0.05)

        self.ax_co = self.fig.add_subplot(611)
        self.ax_co2 = self.fig.add_subplot(612, sharex=self.ax_co)
        self.ax_o2 = self.fig.add_subplot(613, sharex=self.ax_co)
        self.ax_hc = self.fig.add_subplot(614, sharex=self.ax_co)
        self.ax_nox = self.fig.add_subplot(615, sharex=self.ax_co)
        self.ax_rpm = self.fig.add_subplot(616, sharex=self.ax_co)

        self.axs = [self.ax_co, self.ax_co2, self.ax_o2, self.ax_hc, self.ax_nox, self.ax_rpm]
        titles = ["CO (%)", "CO2 (%)", "O2 (%)", "HC (ppm)", "NOx (ppm)", "Motor (RPM)"]
        colors = ["#d63031", "#00b894", "#0984e3", "#e17055", "#6c5ce7", "#2d3436"]

        self.lines = []
        for i, ax in enumerate(self.axs):
            ax.grid(True, linestyle="--", alpha=0.6)
            ax.set_ylabel(titles[i], fontsize=10, color=colors[i], fontweight="bold")
            ax.tick_params(axis='y', labelsize=8)
            if i < 5:
                # Ocultar o eixo X pros graficos de cima pra parecer Polígrafo grudado
                ax.tick_params(labelbottom=False, bottom=False)
            line, = ax.plot([], [], color=colors[i], linewidth=1.5)
            self.lines.append(line)

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.tab_dashboard)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    def build_table_tab(self):
        cols_data = ("Time", "CO (%)", "CO2 (%)", "HC (ppm)", "O2 (%)", "NOx (ppm)", "RPM", "Temp (ºC)")
        self.tree_data = ttk.Treeview(self.tab_table, columns=cols_data, show="headings")
        for c in cols_data:
            self.tree_data.heading(c, text=c)
            self.tree_data.column(c, width=120, anchor="center")
        
        scroll_data = ttk.Scrollbar(self.tab_table, orient="vertical", command=self.tree_data.yview)
        self.tree_data.configure(yscrollcommand=scroll_data.set)
        scroll_data.pack(side="right", fill="y")
        self.tree_data.pack(side="left", fill="both", expand=True)

    def socket_receiver(self):
        buffer = ""
        while self.running:
            try:
                data = self.client_socket.recv(4096)
                if not data:
                    self.root.after(0, self.lbl_state.config, {"text": "[ OFFLINE: SERVIDOR FECHOU A PORTA ]", "fg": "#ff7675"})
                    self.data_queue.put(("ERROR", "Conexão perdida do servidor."))
                    break
                
                buffer += data.decode('utf-8')
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if line.strip():
                        try:
                            payload = json.loads(line)
                            self.data_queue.put(("PAYLOAD", payload))
                        except Exception: pass
            except Exception as e:
                if self.running:
                    self.data_queue.put(("ERROR", str(e)))
                break

    def toggle_connection(self):
        if not self.running:
            try:
                ip = self.ent_ip.get().strip()
                port = int(self.ent_port.get().strip())
                
                self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.client_socket.settimeout(2.0) # Espera maximo pra conectar
                self.client_socket.connect((ip, port))
                self.client_socket.settimeout(None) # bloqueio longo pos conexao pra nao fechar sozinho
                
                self.running = True
                self.session_start = datetime.now()
                self.btn_connect.config(text="■ DESCONECTAR HARDWARE", bg="#d63031")
                self.lbl_state.config(text="[ ONLINE E CAPTURANDO JSON ]", fg="#00b894")
                
                threading.Thread(target=self.socket_receiver, daemon=True).start()
            except Exception as e:
                messagebox.showerror("Conexão Frustrada", f"Backend não localizado em {ip}:{port}\nVerifique se o Server_app iniciou lá.\n\n({e})")
        else:
            self.disconnect()

    def disconnect(self):
        self.running = False
        self.btn_connect.config(text="▶ CONECTAR AO HARDWARE", bg="#0984e3")
        self.lbl_state.config(text="[ OFFLINE: VOCÊ DESCONECTOU ]", fg="#ff7675")
        self.lbl_degradation.config(text="SINAL PERDIDO (OFFLINE)", bg="#b2bec3")
        self.intervals.clear()
        self.last_packet_time = None
        try: self.client_socket.close()
        except: pass

    def poll_queue(self):
        try:
            items_processed = 0
            last_tree_id = None
            
            for _ in range(5000): # Processamento rápido em lote
                item = self.data_queue.get_nowait()
                
                if item[0] == "ERROR":
                    if self.running: self.disconnect()
                    
                elif item[0] == "PAYLOAD":
                    payload = item[1]
                    
                    if payload.get("type") == "CMD" and payload.get("action") == "NEW_SESSION":
                        self.export_data()
                        
                    elif payload.get("type") == "POLLUTANTS":
                        note = payload.get("note", "")
                        if note:
                            # Trocando a label pro estado do Hardware
                            self.lbl_state.config(text=f"[ HARDWARE: {note} ]")
                            
                        packets = payload.get("packets", [])
                        for rec in packets:
                            # Extração robusta contornando nulls gerados no json da serial
                            co = float(rec.get("CO") if rec.get("CO") is not None else 0.0)
                            co2 = float(rec.get("CO2") if rec.get("CO2") is not None else 0.0)
                            hc = int(rec.get("HC") if rec.get("HC") is not None else 0)
                            o2 = float(rec.get("O2") if rec.get("O2") is not None else 0.0)
                            nox = int(rec.get("NOx") if rec.get("NOx") is not None else 0)
                            rpm = int(rec.get("RPM") if rec.get("RPM") is not None else 0)
                            temp = float(rec.get("Temp") if rec.get("Temp") is not None else 0.0)
                            
                            self.history.append(rec)
                            
                            # Atualiza Matrizes dos Gráficos
                            ctr = len(self.graphs["times"])
                            self.graphs["times"].append(ctr)
                            self.graphs["time_labels"].append(rec.get("Time", ""))
                            self.graphs["CO"].append(co)
                            self.graphs["CO2"].append(co2)
                            self.graphs["O2"].append(o2)
                            self.graphs["HC"].append(hc)
                            self.graphs["NOx"].append(nox)
                            self.graphs["RPM"].append(rpm)
                            
                            # Células da Tabela Histórico
                            v_co, v_co2, v_hc = f"{co:.2f}", f"{co2:.1f}", f"{hc}"
                            v_o2, v_nox, v_rpm, v_temp = f"{o2:.2f}", f"{nox}", f"{rpm}", f"{temp:.1f}"
                            last_tree_id = self.tree_data.insert("", tk.END, values=(rec.get("Time"), v_co, v_co2, v_hc, v_o2, v_nox, v_rpm, v_temp))
                            
                            # Atualiza Visores Grandes Digitais Individuais
                            self.val_vars["CO"].set(v_co)
                            self.val_vars["CO2"].set(v_co2)
                            self.val_vars["HC"].set(v_hc)
                            self.val_vars["O2"].set(v_o2)
                            self.val_vars["NOx"].set(v_nox)
                            self.val_vars["RPM"].set(v_rpm)
                            
                            # Estatísticas Individuais em tempo real por Gás
                            for k_p, val_p in [("CO", co), ("CO2", co2), ("HC", hc), ("O2", o2), ("NOx", nox), ("RPM", rpm)]:
                                st = self.gas_stats[k_p]
                                st["count"] += 1
                                st["sum"] += val_p
                                if val_p > st["c_max"]: st["c_max"] = val_p
                                if val_p < st["c_min"]: st["c_min"] = val_p
                                
                                fmt = ".0f" if k_p in ("HC", "NOx", "RPM") else ".2f"
                                
                                st["max_v"].set(f"Max: {st['c_max']:{fmt}}")
                                st["min_v"].set(f"Min: {st['c_min']:{fmt}}")
                                st["avg_v"].set(f"Méd: {(st['sum'] / st['count']):{fmt}}")
                            
                            # Estatísticas Gerais
                            self.stat_vars["Pacotes Salvos"].set(str(len(self.history)))
                            if self.session_start:
                                secs = int((datetime.now() - self.session_start).total_seconds())
                                self.stat_vars["Duração (s)"].set(str(secs))
                                
                            # Avaliação de Degradação (Intervalos)
                            packet_time_str = rec.get("Time")
                            if packet_time_str:
                                try:
                                    pt = datetime.strptime(packet_time_str, '%Y-%m-%d %H:%M:%S.%f')
                                    if self.last_packet_time:
                                        delta = (pt - self.last_packet_time).total_seconds()
                                        if delta < 0: delta += 86400 # correção do midnight rollover
                                        
                                        self.intervals.append(delta)
                                        if len(self.intervals) > 10:
                                            self.intervals.pop(0)

                                        avg_interv = sum(self.intervals) / len(self.intervals)
                                        
                                        self.stat_vars["Tempo Trans. (s)"].set(f"{delta:.2f}s")
                                        self.stat_vars["Médio (10 pcts)"].set(f"{avg_interv:.2f}s")

                                        if avg_interv > 1.5 or delta > 3.0:
                                            self.lbl_degradation.config(text="⚠️ DEGRADAÇÃO: SINAL LENTO", bg="#e17055") # Vermelho/Laranja
                                        elif avg_interv < 0.5:
                                            self.lbl_degradation.config(text="⚠️ ANÔMALIA: MUITO RÁPIDO", bg="#fdcb6e") # Amarelo
                                        else:
                                            self.lbl_degradation.config(text="✅ SINAL ESTÁVEL (~1 Hz)", bg="#00b894") # Verde
                                            
                                    self.last_packet_time = pt
                                except Exception:
                                    pass

                items_processed += 1
                
            # Limpeza Lote O(1) do Grid de Tabela
            if items_processed > 0:
                if last_tree_id:
                    self.tree_data.see(last_tree_id)
                ch = self.tree_data.get_children()
                if len(ch) > 8000:
                    self.tree_data.delete(*ch[:-8000])

        except queue.Empty: pass
        self.root.after(50, self.poll_queue)

    def update_graphs_daemon(self):
        times = self.graphs["times"]
        if len(times) > 1:
            for i, key in enumerate(["CO", "CO2", "O2", "HC", "NOx", "RPM"]):
                self.lines[i].set_data(times, self.graphs[key])
            
            # Dinâmica de X axis
            x_min = max(0, times[-1] - 400) # Mantém janela lateral mais longa na tela empilhada 
            x_max = times[-1] + 20
            
            for ax in self.axs:
                ax.set_xlim(x_min, x_max)
                ax.relim()
                ax.autoscale_view(scalex=False, scaley=True)

            self.canvas.draw_idle()
            
        self.root.after(1000, self.update_graphs_daemon)

    def trigger_remote_reset(self):
        if self.running and self.client_socket:
            try:
                # Dispara sinal TCP para o Backend fechar o CSV dele e dar o rebote na gente
                self.client_socket.sendall(json.dumps({"type": "CMD", "action": "NEW_SESSION"}).encode('utf-8') + b"\n")
            except:
                self.export_data()
        else:
            self.export_data()

    def export_data(self):
        if not self.history:
            messagebox.showinfo("Aviso", "Não há dados em memória na interface do Cliente para exportar.")
            return
            
        import os
        dest_dir = os.path.join(os.path.dirname(__file__), "ensaios_salvos")
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir)
            
        dest = os.path.join(dest_dir, f"captura_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.csv")
        
        try:
            with open(dest, "w", newline='', encoding='utf-8') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow(["dateTime", "CO_%", "CO2_%", "HC_ppm", "O2_%", "NOx_ppm", "RPM", "Temp_C"])
                for rec in self.history:
                    writer.writerow([
                        rec.get("CSV_Time", rec.get("Time")),
                        str(rec.get("CO", 0)),
                        str(rec.get("CO2", 0)),
                        str(rec.get("HC", 0)),
                        str(rec.get("O2", 0)),
                        str(rec.get("NOx", 0)),
                        str(rec.get("RPM", 0)),
                        str(rec.get("Temp", 0))
                    ])
                    
            # --- LIMPEZA DE CACHE E MEMÓRIA ---
            self.history.clear()
            self.intervals.clear()
            self.last_packet_time = None
            if self.running:
                self.session_start = datetime.now()
                
            for key in ['times', 'time_labels', 'CO', 'CO2', 'O2', 'HC', 'NOx', 'RPM']:
                self.graphs[key].clear()
                
            self.tree_data.delete(*self.tree_data.get_children())
            
            # Limpar Estatísticas e Gráficos da UI
            for key, def_val in [("CO", "0.00"), ("CO2", "0.0"), ("HC", "0"), ("O2", "0.00"), ("NOx", "0"), ("RPM", "0")]:
                self.val_vars[key].set(def_val)
                st = self.gas_stats[key]
                st["sum"] = 0.0
                st["count"] = 0
                st["c_min"] = 99999.0
                st["c_max"] = -99999.0
                st["min_v"].set("Min: --")
                st["avg_v"].set("Méd: --")
                st["max_v"].set("Max: --")
                
            self.stat_vars["Pacotes Salvos"].set("0")
            self.stat_vars["Duração (s)"].set("0")
            self.stat_vars["Tempo Trans. (s)"].set("--")
            self.stat_vars["Médio (10 pcts)"].set("--")
            
            for ax in self.axs:
                ax.relim()
                ax.autoscale_view(scalex=False, scaley=True)
            self.canvas.draw_idle()
            
            messagebox.showinfo("Sucesso: Ensaio Salvo e Cache Limpo", f"1-Click Backup concluído com sucesso.\nSalvo automaticamente em:\n{dest}\n\nO cache foi limpo e o monitor está livre para continuar acompanhando de onde parou.")
        except Exception as e:
            messagebox.showerror("Erro Export", str(e))

if __name__ == "__main__":
    root = tk.Tk()
    app = ClientApp(root)
    root.mainloop()
